"""
ics_fetcher.py — ICS URL 구독 fetch + unified_task 저장

1시간마다 action_handlers_gcal.py 에서 호출됩니다.
icalendar 라이브러리를 사용합니다 (requirements.txt에 추가 필요: icalendar>=5.0).

ICS 이벤트는 unified_task에 다음 방식으로 저장됩니다:
  - calendar_id = "ics::{url_hash}"
  - gcal_sync_mode = 'remote_mirror'  (쓰기 불가)
  - gcal_event_id = event UID (ICS unique identifier)
  - gcal_source_calendar_id = calendar_id (ics::...)
  - gcal_dirty = 0
"""

from datetime import date, datetime, timedelta
import logging
import urllib.error
import urllib.request

logger = logging.getLogger("IcsFetcher")


def _try_import_icalendar():
    try:
        import icalendar

        return icalendar
    except ImportError:
        return None


def fetch_and_sync(calendar_id: str, ics_url: str) -> tuple[int, int, str | None]:
    """
    ICS URL을 fetch하여 unified_task에 upsert합니다.

    Returns:
        (upserted_count, deleted_count, error_message_or_None)
    """
    icalendar = _try_import_icalendar()
    if not icalendar:
        msg = "icalendar 라이브러리가 없습니다. pip install icalendar"
        logger.error(msg)
        return 0, 0, msg

    # 1. ICS 다운로드
    try:
        req = urllib.request.Request(
            ics_url,
            headers={"User-Agent": "DarkCalendar/1.0 ICS-Fetcher"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
    except urllib.error.URLError as e:
        msg = f"ICS fetch 실패 ({ics_url}): {e}"
        logger.error(msg)
        return 0, 0, msg
    except Exception as e:
        msg = f"ICS fetch 오류: {e}"
        logger.error(msg)
        return 0, 0, msg

    # 2. 파싱
    try:
        cal = icalendar.Calendar.from_ical(raw)
    except Exception as e:
        msg = f"ICS 파싱 실패: {e}"
        logger.error(msg)
        return 0, 0, msg

    # 3. DB upsert
    from calendar_app.infrastructure.db.database_unified import db_manager

    conn = db_manager.get_connection()
    if not conn:
        return 0, 0, "DB 연결 실패"

    cur = conn.cursor()
    fetched_uids: set[str] = set()
    upserted = 0

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        uid = str(component.get("UID", ""))
        if not uid:
            continue
        fetched_uids.add(uid)

        summary = str(component.get("SUMMARY", ""))
        description = str(component.get("DESCRIPTION", "")) or None
        location = str(component.get("LOCATION", "")) or None

        dtstart = component.get("DTSTART")
        dtend = component.get("DTEND")

        deadline_str, end_date_str, all_day = _parse_dt(dtstart, dtend)

        try:
            cur.execute(
                """
                INSERT INTO unified_task
                    (name, type, calendar_id, deadline, end_date, all_day,
                     description, location,
                     gcal_event_id, gcal_source_calendar_id, gcal_sync_mode,
                     gcal_dirty, status,
                     created_at, updated_at)
                VALUES (?, 'schedule', ?, ?, ?, ?, ?, ?,
                        ?, ?, 'remote_mirror', 0, 'in_progress',
                        datetime('now','localtime'), datetime('now','localtime'))
                ON CONFLICT(
                    COALESCE(NULLIF(trim(gcal_source_calendar_id), ''), NULLIF(trim(gcal_target_calendar_id), ''), 'primary'),
                    gcal_event_id
                ) WHERE gcal_event_id IS NOT NULL AND gcal_event_id != ''
                DO UPDATE SET
                    name        = excluded.name,
                    deadline    = excluded.deadline,
                    end_date    = excluded.end_date,
                    all_day     = excluded.all_day,
                    description = excluded.description,
                    location    = excluded.location,
                    updated_at  = excluded.updated_at
            """,
                (
                    summary,
                    calendar_id,
                    deadline_str,
                    end_date_str,
                    1 if all_day else 0,
                    description,
                    location,
                    uid,
                    calendar_id,
                ),
            )
            upserted += 1
        except Exception as e:
            logger.warning(f"ICS upsert 실패 (uid={uid}): {e}")

    # 4. 이 캘린더에서 가져왔는데 fetch 결과에 없는 이벤트 → 삭제
    deleted = 0
    if fetched_uids:
        cur.execute(
            "SELECT id, gcal_event_id FROM unified_task WHERE gcal_source_calendar_id = ? AND gcal_event_id IS NOT NULL",
            (calendar_id,),
        )
        existing = cur.fetchall()
        for row in existing:
            task_id, event_uid = row
            if event_uid not in fetched_uids:
                cur.execute("DELETE FROM unified_task WHERE id = ?", (task_id,))
                deleted += 1

    conn.commit()

    from calendar_app.infrastructure.db.calendar_repo import update_ics_last_fetched

    update_ics_last_fetched(calendar_id)

    logger.info(f"ICS sync [{calendar_id}]: upserted={upserted}, deleted={deleted}")
    return upserted, deleted, None


def _parse_dt(dtstart, dtend) -> tuple[str | None, str | None, bool]:
    """DTSTART/DTEND를 (deadline_str, end_date_str, all_day) 로 변환합니다."""
    if dtstart is None:
        return None, None, False

    val = dtstart.dt

    # 종일 이벤트 (date 타입)
    if isinstance(val, date) and not isinstance(val, datetime):
        deadline_str = val.strftime("%Y-%m-%d")
        end_str = None
        if dtend is not None:
            ev = dtend.dt
            if isinstance(ev, date) and not isinstance(ev, datetime):
                end_str = (ev - timedelta(days=1)).strftime("%Y-%m-%d")
        return deadline_str, end_str, True

    # 시간 포함 이벤트 (datetime 타입)
    if isinstance(val, datetime):
        if val.tzinfo is not None:
            val = val.astimezone().replace(tzinfo=None)
        deadline_str = val.strftime("%Y-%m-%d %H:%M")
        end_str = None
        if dtend is not None:
            ev = dtend.dt
            if isinstance(ev, datetime):
                if ev.tzinfo is not None:
                    ev = ev.astimezone().replace(tzinfo=None)
                end_str = ev.strftime("%Y-%m-%d %H:%M")
        return deadline_str, end_str, False

    return None, None, False


# ---------------------------------------------------------------------------
# 앱 레벨 진입점: 모든 ICS 캘린더 동기화
# ---------------------------------------------------------------------------


def sync_all_ics_calendars() -> dict[str, tuple[int, int, str | None]]:
    """
    calendar 테이블의 type='ics', is_active=1 인 캘린더를 모두 fetch합니다.
    Returns: {calendar_id: (upserted, deleted, error)}
    """
    from calendar_app.infrastructure.db.calendar_repo import list_calendars

    results = {}
    for cal in list_calendars(include_inactive=False):
        if cal["type"] != "ics":
            continue
        url = cal.get("ics_url")
        if not url:
            continue
        results[cal["id"]] = fetch_and_sync(cal["id"], url)
    return results

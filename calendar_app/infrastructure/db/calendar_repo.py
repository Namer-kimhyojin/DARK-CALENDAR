"""
calendar_repo.py — calendar 테이블 CRUD + 마이그레이션 헬퍼

calendar.id 형식:
  "gcal::{google_calendar_id}"   — Google Calendar 연동
  "local::{slug}"                — 로컬 전용
  "ics::{url_hash}"              — ICS URL 구독 (read-only)
"""

from datetime import datetime
import hashlib
import logging
import re

from calendar_app.infrastructure.db.database_unified import db_manager
from calendar_app.infrastructure.google_sync.common import is_gcal_enabled
from calendar_app.shared.calendar_defaults import DEFAULT_CALENDAR_COLOR

logger = logging.getLogger("CalendarRepo")

# 타입별 기본 색상 순환 팔레트
_COLOR_PALETTE = [
    DEFAULT_CALENDAR_COLOR,  # blue
    "#ff6b6b",  # red
    "#51cf66",  # green
    "#fcc419",  # yellow
    "#cc5de8",  # purple
    "#ff922b",  # orange
    "#20c997",  # teal
    "#f06595",  # pink
]


def _next_color() -> str:
    """기존 캘린더 수에 따라 팔레트 색상을 순환 반환합니다."""
    conn = db_manager.get_connection()
    if conn is None:
        return _COLOR_PALETTE[0]
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM calendar")
    count = cur.fetchone()[0]
    return _COLOR_PALETTE[count % len(_COLOR_PALETTE)]


def _slug(name: str) -> str:
    """이름을 ID에 쓸 수 있는 slug로 변환합니다."""
    s = re.sub(r"[^\w가-힣]", "_", name.strip()).strip("_") or "cal"
    return s[:40]


def make_gcal_id(gcal_calendar_id: str) -> str:
    return f"gcal::{gcal_calendar_id}"


def make_local_id(name: str) -> str:
    return f"local::{_slug(name)}"


def make_ics_id(url: str) -> str:
    h = hashlib.md5(url.encode()).hexdigest()[:12]
    return f"ics::{h}"


# ---------------------------------------------------------------------------
# READ
# ---------------------------------------------------------------------------


def list_calendars(include_inactive: bool = True, visible_only: bool = False) -> list[dict]:
    """모든 캘린더를 sort_order → name 순으로 반환합니다."""
    conn = db_manager.get_connection()
    if conn is None:
        return []
    cur = conn.cursor()
    where_clauses = []
    if not include_inactive:
        where_clauses.append("is_active = 1")
    if visible_only:
        where_clauses.append("is_visible = 1")
    where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    cur.execute(f"SELECT * FROM calendar {where} ORDER BY sort_order, name")
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]


def get_calendar(calendar_id: str) -> dict | None:
    conn = db_manager.get_connection()
    if conn is None:
        return None
    cur = conn.cursor()
    cur.execute("SELECT * FROM calendar WHERE id = ?", (calendar_id,))
    row = cur.fetchone()
    if not row:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row, strict=False))


def _to_bool(value, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"1", "true", "yes", "on"}:
            return True
        if token in {"0", "false", "no", "off", ""}:
            return False
    return bool(value)


def is_calendar_row_read_only(calendar_row: dict | None) -> bool:
    """Return True when a calendar row should be treated as read-only.

    판단 기준:
    - ICS 구독 캘린더: 항상 read-only
    - GCal 캘린더: access_role 이 'owner'/'writer' 이면 is_active 값에 관계없이 편집 가능.
      (is_active=0 은 sync 비활성화이지 편집 권한 제거가 아님)
      access_role 이 없을 때만 is_active=0 을 read-only fallback 으로 사용.
    """
    if not isinstance(calendar_row, dict):
        return False
    cal_type = str(calendar_row.get("type") or "").strip().lower()
    if cal_type == "ics":
        return True
    if cal_type == "gcal":
        # access_role 이 있으면 is_active 와 무관하게 역할만으로 판단
        own_role = str(calendar_row.get("access_role") or "").strip().lower()
        if own_role:
            return own_role not in ("owner", "writer")
        # Fall back to gcal_subscription table lookup
        gcal_id = str(calendar_row.get("gcal_calendar_id") or "").strip()
        if gcal_id:
            try:
                conn = db_manager.get_connection()
                if conn is not None:
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT access_role FROM gcal_subscription WHERE calendar_id = ? LIMIT 1",
                        (gcal_id,),
                    )
                    row = cur.fetchone()
                    if row is not None:
                        role = str(row[0] or "").strip().lower()
                        if role:
                            return role not in ("owner", "writer")
            except Exception:
                pass
        # access_role 을 알 수 없을 때만 is_active=0 을 read-only 신호로 사용
        return not _to_bool(calendar_row.get("is_active"), default=True)
    return False


def is_calendar_read_only(calendar_id: str | None) -> bool:
    cal_key = str(calendar_id or "").strip()
    if not cal_key:
        return False
    return is_calendar_row_read_only(get_calendar(cal_key))


def get_default_calendar() -> dict | None:
    """is_default=1 인 캘린더를 반환합니다. 없으면 첫 번째 캘린더를 반환합니다."""
    conn = db_manager.get_connection()
    if conn is None:
        return None
    cur = conn.cursor()
    cur.execute("SELECT * FROM calendar WHERE is_default = 1 LIMIT 1")
    row = cur.fetchone()
    if not row:
        cur.execute("SELECT * FROM calendar ORDER BY sort_order, name LIMIT 1")
        row = cur.fetchone()
    if not row:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row, strict=False))


def get_writable_calendars() -> list[dict]:
    """쓰기 가능한 캘린더만 반환.
    - ICS 구독(read-only) 제외
    - GCal reader 전용(is_active=0) 제외 — is_active는 import 시 accessRole 기준으로 설정됨
    - 로컬/공유 캘린더는 항상 포함
    """
    conn = db_manager.get_connection()
    if conn is None:
        return []
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM calendar
        WHERE type != 'ics'
          AND (type != 'gcal' OR is_active = 1)
        ORDER BY sort_order, name
    """)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# WRITE
# ---------------------------------------------------------------------------


def upsert_calendar(
    calendar_id: str,
    cal_type: str,
    name: str,
    color: str | None = None,
    is_default: bool = False,
    is_active: bool = True,
    is_visible: bool = True,
    gcal_calendar_id: str | None = None,
    ics_url: str | None = None,
    sort_order: int = 0,
    access_role: str | None = None,
) -> bool:
    """calendar 레코드를 삽입하거나 업데이트합니다."""
    conn = db_manager.get_connection()
    if conn is None:
        logger.error("upsert_calendar: DB 연결 실패")
        return False
    cur = conn.cursor()
    if color is None:
        color = _next_color()
    # access_role 컬럼 존재 여부 확인 (스키마 마이그레이션 전 구버전 대비)
    cur.execute("PRAGMA table_info(calendar)")
    col_names = {r[1] for r in cur.fetchall()}
    has_access_role = "access_role" in col_names
    try:
        if has_access_role:
            cur.execute(
                """
                INSERT INTO calendar (id, type, name, color, is_default, is_active, is_visible,
                                      gcal_calendar_id, ics_url, sort_order, access_role)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    type             = excluded.type,
                    name             = excluded.name,
                    color            = excluded.color,
                    is_default       = excluded.is_default,
                    is_active        = excluded.is_active,
                    is_visible       = excluded.is_visible,
                    gcal_calendar_id = excluded.gcal_calendar_id,
                    ics_url          = excluded.ics_url,
                    sort_order       = excluded.sort_order,
                    access_role      = COALESCE(excluded.access_role, access_role)
            """,
                (
                    calendar_id,
                    cal_type,
                    name,
                    color,
                    1 if is_default else 0,
                    1 if is_active else 0,
                    1 if is_visible else 0,
                    gcal_calendar_id,
                    ics_url,
                    sort_order,
                    access_role,
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO calendar (id, type, name, color, is_default, is_active, is_visible,
                                      gcal_calendar_id, ics_url, sort_order)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    type             = excluded.type,
                    name             = excluded.name,
                    color            = excluded.color,
                    is_default       = excluded.is_default,
                    is_active        = excluded.is_active,
                    is_visible       = excluded.is_visible,
                    gcal_calendar_id = excluded.gcal_calendar_id,
                    ics_url          = excluded.ics_url,
                    sort_order       = excluded.sort_order
            """,
                (
                    calendar_id,
                    cal_type,
                    name,
                    color,
                    1 if is_default else 0,
                    1 if is_active else 0,
                    1 if is_visible else 0,
                    gcal_calendar_id,
                    ics_url,
                    sort_order,
                ),
            )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"upsert_calendar failed: {e}")
        return False


def set_calendar_default(calendar_id: str) -> bool:
    """지정 캘린더를 기본값으로 설정하고 나머지를 해제합니다."""
    conn = db_manager.get_connection()
    if conn is None:
        logger.error("set_calendar_default: DB 연결 실패")
        return False
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM calendar WHERE id = ?", (calendar_id,))
        if not cur.fetchone():
            logger.error(f"set_calendar_default: calendar not found: {calendar_id}")
            return False
        cur.execute("UPDATE calendar SET is_default = 0")
        cur.execute("UPDATE calendar SET is_default = 1 WHERE id = ?", (calendar_id,))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"set_calendar_default failed: {e}")
        return False


def set_calendar_visible(calendar_id: str, is_visible: bool) -> bool:
    conn = db_manager.get_connection()
    if conn is None:
        logger.error("set_calendar_visible: DB 연결 실패")
        return False
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE calendar SET is_visible = ? WHERE id = ?",
            (1 if is_visible else 0, calendar_id),
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        logger.error(f"set_calendar_visible failed: {e}")
        return False


def update_calendar_access_role(calendar_id: str, access_role: str) -> bool:
    """캘린더의 access_role 컬럼만 업데이트합니다."""
    conn = db_manager.get_connection()
    if conn is None:
        return False
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE calendar SET access_role = ? WHERE id = ?",
            (access_role or None, calendar_id),
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        logger.error("update_calendar_access_role failed: %s", e)
        return False


def set_calendar_active(calendar_id: str, is_active: bool) -> bool:
    conn = db_manager.get_connection()
    if conn is None:
        logger.error("set_calendar_active: DB 연결 실패")
        return False
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE calendar SET is_active = ? WHERE id = ?",
            (1 if is_active else 0, calendar_id),
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        logger.error(f"set_calendar_active failed: {e}")
        return False


def set_calendar_color(calendar_id: str, color: str) -> bool:
    conn = db_manager.get_connection()
    if conn is None:
        logger.error("set_calendar_color: DB 연결 실패")
        return False
    cur = conn.cursor()
    try:
        cur.execute("UPDATE calendar SET color = ? WHERE id = ?", (color, calendar_id))
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        logger.error(f"set_calendar_color failed: {e}")
        return False


def rename_calendar(calendar_id: str, name: str) -> bool:
    conn = db_manager.get_connection()
    if conn is None:
        logger.error("rename_calendar: DB 연결 실패")
        return False
    cur = conn.cursor()
    try:
        cur.execute("UPDATE calendar SET name = ? WHERE id = ?", (name, calendar_id))
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        logger.error(f"rename_calendar failed: {e}")
        return False


def update_ics_last_fetched(calendar_id: str) -> bool:
    conn = db_manager.get_connection()
    if conn is None:
        logger.error("update_ics_last_fetched: DB 연결 실패")
        return False
    cur = conn.cursor()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            "UPDATE calendar SET ics_last_fetched = ? WHERE id = ?",
            (now, calendar_id),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"update_ics_last_fetched failed: {e}")
        return False


def delete_calendar(calendar_id: str) -> bool:
    """캘린더를 삭제합니다. 해당 캘린더의 태스크들은 GCal 연동이 안전하게 해제되고 calendar_id는 NULL로 초기화됩니다."""
    conn = db_manager.get_connection()
    if conn is None:
        logger.error("delete_calendar: DB 연결 실패")
        return False
    cur = conn.cursor()
    try:
        # gcal 캘린더인 경우 gcal_target_calendar_id도 지워서 phantom push 방지
        cur.execute("SELECT gcal_calendar_id FROM calendar WHERE id = ?", (calendar_id,))
        row = cur.fetchone()
        raw_gcal_id = (row[0] or "").strip() if row else ""

        # 캘린더에 연동된 태스크들의 GCal 링크 끊기 및 연동 정보 초기화
        cur.execute(
            """
            UPDATE unified_task
            SET gcal_event_id = NULL,
                gcal_source_calendar_id = NULL,
                gcal_target_calendar_id = NULL,
                gcal_sync_mode = 'local_owned',
                gcal_dirty = 0,
                gcal_sync_error = NULL,
                gcal_last_synced_at = NULL,
                gcal_remote_updated_at = NULL,
                calendar_id = NULL
            WHERE calendar_id = ?
               OR (gcal_target_calendar_id IS NOT NULL AND gcal_target_calendar_id = ?)
               OR (gcal_source_calendar_id IS NOT NULL AND gcal_source_calendar_id = ?)
            """,
            (
                calendar_id,
                raw_gcal_id if raw_gcal_id else None,
                raw_gcal_id if raw_gcal_id else None,
            ),
        )

        cur.execute("DELETE FROM calendar WHERE id = ?", (calendar_id,))
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        logger.error(f"delete_calendar failed: {e}")
        conn.rollback()
        return False


# ---------------------------------------------------------------------------
# MIGRATION: gcal_subscription → calendar
# ---------------------------------------------------------------------------


def migrate_from_gcal_subscription(settings=None) -> bool:
    """
    gcal_subscription 테이블을 calendar 테이블로 마이그레이션합니다.
    이미 calendar 레코드가 있으면 건너뜁니다.

    settings: QSettings 인스턴스 (gcal_calendar_id 기본값 확인용)
    """
    conn = db_manager.get_connection()
    if conn is None:
        logger.error("migrate_from_gcal_subscription: DB 연결 실패")
        return False
    cur = conn.cursor()

    # 이미 마이그레이션 됐으면 스킵
    cur.execute("SELECT COUNT(*) FROM calendar")
    if cur.fetchone()[0] > 0:
        return True

    logger.info("Migrating gcal_subscription → calendar table...")

    # QSettings에서 기본 캘린더 ID 읽기
    # "primary" 는 Google API 별칭이므로 DB 저장/비교에는 None 으로 처리한다.
    default_gcal_id = None
    if settings is not None:
        _raw = settings.value("gcal_calendar_id", None)
        if _raw and str(_raw).strip() and str(_raw).strip() != "primary":
            default_gcal_id = str(_raw).strip()

    try:
        cur.execute(
            "SELECT * FROM gcal_subscription ORDER BY is_primary DESC, is_active DESC, summary ASC"
        )
        subs = cur.fetchall()
        cols = [d[0] for d in cur.description]

        gcal_enabled = True
        if settings is not None:
            gcal_enabled = is_gcal_enabled(settings)

        for palette_idx, row in enumerate(subs):
            sub = dict(zip(cols, row, strict=False))
            gcal_id = sub["calendar_id"]
            cal_id = make_gcal_id(gcal_id)
            is_default = (gcal_id == default_gcal_id) or bool(sub.get("is_primary"))
            color = _COLOR_PALETTE[palette_idx % len(_COLOR_PALETTE)]

            cur.execute(
                """
                INSERT OR IGNORE INTO calendar
                    (id, type, name, color, is_default, is_active, is_visible, gcal_calendar_id, sort_order, access_role)
                VALUES (?, 'gcal', ?, ?, ?, ?, 1, ?, ?, ?)
            """,
                (
                    cal_id,
                    sub.get("summary") or gcal_id,
                    color,
                    1 if is_default else 0,
                    sub.get("is_active", 1),
                    gcal_id,
                    palette_idx,
                    sub.get("access_role") or None,
                ),
            )

        # GCal 활성화 상태이고, gcal_subscription에 기본 캘린더가 없는 경우 보완
        # "primary" 는 Google API 별칭이지 실제 캘린더 ID가 아니므로 DB에 저장하지 않는다.
        # 실제 ID(이메일 등)가 gcal_subscription 에서 마이그레이션됐으면 이미 row 가 존재한다.
        if gcal_enabled and subs and default_gcal_id != "primary":
            default_cal_id = make_gcal_id(default_gcal_id)
            cur.execute("SELECT id FROM calendar WHERE id = ?", (default_cal_id,))
            if not cur.fetchone():
                # 이미 기본 gcal 캘린더가 다른 ID로 존재하면 생성 생략
                cur.execute("SELECT COUNT(*) FROM calendar WHERE is_default = 1 AND type = 'gcal'")
                has_default_gcal = cur.fetchone()[0] > 0
                if not has_default_gcal:
                    cur.execute(
                        """
                        INSERT OR IGNORE INTO calendar
                            (id, type, name, color, is_default, is_active, is_visible, gcal_calendar_id, sort_order)
                        VALUES (?, 'gcal', ?, ?, 1, 1, 1, ?, 0)
                    """,
                        (default_cal_id, default_gcal_id, DEFAULT_CALENDAR_COLOR, default_gcal_id),
                    )

        # 기본 캘린더가 하나도 없으면 로컬 "기본" 캘린더 생성 (GCal 미사용 또는 구독 목록 없는 경우)
        cur.execute("SELECT COUNT(*) FROM calendar WHERE is_default = 1")
        if cur.fetchone()[0] == 0:
            cur.execute(
                """
                INSERT OR IGNORE INTO calendar
                    (id, type, name, color, is_default, is_active, is_visible, sort_order)
                VALUES ('local::기본', 'local', '기본', ?, 1, 1, 1, 0)
            """,
                (DEFAULT_CALENDAR_COLOR,),
            )

        # unified_task.calendar_id 채우기
        # GCal 이벤트: gcal_source_calendar_id 기반
        cur.execute("""
            UPDATE unified_task
            SET calendar_id = 'gcal::' || gcal_source_calendar_id
            WHERE gcal_source_calendar_id IS NOT NULL
              AND gcal_source_calendar_id != ''
              AND calendar_id IS NULL
        """)

        # 나머지 (로컬 태스크): 기본 캘린더로 귀속
        cur.execute("SELECT id FROM calendar WHERE is_default = 1 LIMIT 1")
        row = cur.fetchone()
        fallback_id = row[0] if row else "local::기본"
        cur.execute(
            """
            UPDATE unified_task
            SET calendar_id = ?
            WHERE calendar_id IS NULL
        """,
            (fallback_id,),
        )

        conn.commit()
        logger.info("Migration complete.")
        return True

    except Exception as e:
        logger.error(f"migrate_from_gcal_subscription failed: {e}")
        return False

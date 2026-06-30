# legacy DB module: suppress style-only lints (try/except/pass migration guards, late re-export import)
# ruff: noqa: SIM105, E402

import logging
import os
import sqlite3
import threading

from calendar_app.app_paths import DB_PATH, LOG_PATH


def _build_logging_handlers():
    handlers = [logging.StreamHandler()]
    try:
        handlers.insert(0, logging.FileHandler(LOG_PATH, encoding="utf-8", errors="strict"))
    except OSError as exc:
        logging.getLogger(__name__).warning("File logging disabled for %s: %s", LOG_PATH, exc)
    return handlers


# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=_build_logging_handlers(),
)

logger = logging.getLogger("Database")


class ConnectionWrapper:
    """sqlite3.Connection을 감싸서 close() 호출을 무시합니다."""

    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        # 싱글톤 연결이므로 명시적인 close()를 무시합니다.
        pass

    def safe_execute(self, sql, params=None, commit=True):
        return safe_db_execute(self._conn, sql, params, commit)

    def safe_fetch_all(self, sql, params=None):
        return safe_db_fetch_all(self._conn, sql, params)

    def safe_fetch_one(self, sql, params=None):
        return safe_db_fetch_one(self._conn, sql, params)


def get_table_columns(cursor, table_name):
    try:
        cursor.execute(f"PRAGMA table_info({table_name})")
        return {row[1] for row in cursor.fetchall()}
    except Exception:
        return set()


def safe_db_execute(conn, sql, params=None, commit=True):
    """Execute a query safely with error handling and optional rollback."""
    if not conn:
        return False
    try:
        cur = conn.cursor()
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        if commit:
            conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"DB Execute Error: {e}\nSQL: {sql}\nParams: {params}")
        if commit:
            try:
                conn.rollback()
            except Exception:
                pass
        return False
    except Exception as e:
        logger.exception(f"Unexpected DB Error: {e}")
        return False


def safe_db_fetch_all(conn, sql, params=None):
    """Fetch all rows safely with error handling."""
    if not conn:
        return []
    try:
        cur = conn.cursor()
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        return cur.fetchall()
    except sqlite3.Error as e:
        logger.error(f"DB Fetch All Error: {e}\nSQL: {sql}\nParams: {params}")
        return []
    except Exception:
        logger.exception("Unexpected DB Fetch All Error")
        return []


def safe_db_fetch_one(conn, sql, params=None):
    """Fetch one row safely with error handling."""
    if not conn:
        return None
    try:
        cur = conn.cursor()
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        return cur.fetchone()
    except sqlite3.Error as e:
        logger.error(f"DB Fetch One Error: {e}\nSQL: {sql}\nParams: {params}")
        return None
    except Exception:
        logger.exception("Unexpected DB Fetch One Error")
        return None


def initialize_unified_database():
    """
    일정과 일반업무를 통합한 unified_task 테이블을 생성하고,
    일반업무 유형별 기간 처리를 지원합니다.
    """
    try:
        conn = db_manager.get_connection()
        if not conn:
            logger.error("Failed to get database connection during initialization.")
            return False

        cur = conn.cursor()
        cur.execute("""

            CREATE TABLE IF NOT EXISTS unified_task (

                id INTEGER PRIMARY KEY AUTOINCREMENT,



                -- 湲곕낯 ?뺣낫

                name TEXT NOT NULL,

                type TEXT NOT NULL DEFAULT 'schedule',  -- 'schedule' ?먮뒗 'routine'

                priority TEXT DEFAULT 'normal',

                status TEXT DEFAULT 'in_progress',



                -- ?쇱떆 ?뺣낫

                deadline TEXT,                          -- ?쒖옉?쇱떆 (?쇱젙) ?먮뒗 ?섑뻾湲곗???(?쇰컲?낅Т)

                end_date TEXT,                          -- 醫낅즺?쇱떆

                alarm_time TEXT,                        -- ?뚮엺 ?쒓컙

                recurrence TEXT,                        -- 諛섎났 ?ㅼ젙



                -- ?쇰컲?낅Т ?꾩슜 ?꾨뱶

                template_id INTEGER,                    -- routine_template 李몄“

                target_date TEXT,                       -- ?쇰컲?낅Т ?섑뻾 湲곗???

                cycle_type TEXT,                        -- 二쇨린: weekly, monthly, quarterly, half_yearly, yearly

                period_start TEXT,                      -- 湲곌컙 ?쒖옉??(二???遺꾧린/諛섍린/?꾩쓽 泥ル궇)

                period_end TEXT,                        -- 湲곌컙 醫낅즺??(二???遺꾧린/諛섍린/?꾩쓽 留덉?留됰궇)

                series_id TEXT,                         -- 諛섎났 ?앹꽦 臾묒쓬 ?앹떇??

                series_order INTEGER,                   -- ?쒕━利??댁꽌 ?쒕쾲 (1-based)

                series_total INTEGER,                   -- ?쒕━利??앸컲 媛쒖닔



                -- ?꾨즺 ?곹깭 (?쇰컲?낅Т??

                is_completed INTEGER DEFAULT 0,

                completed_at TEXT,



                -- ?쒓컖???붿냼

                bg_color TEXT,

                icon TEXT,



                -- 硫붾え 諛?遺媛 ?뺣낫

                description TEXT,

                memo TEXT,

                location TEXT,                          -- ?μ냼 (異붽?)

                assignee TEXT,                          -- ?대떦???뺣낫 (異붽?)



                -- 援ш? 罹섎┛???곕룞

                all_day INTEGER DEFAULT 0,              -- 醫낆씪 ?쇱젙 ?щ?

                gcal_event_id TEXT,

                gcal_source_calendar_id TEXT,

                gcal_source_summary TEXT,

                gcal_target_calendar_id TEXT,

                gcal_sync_mode TEXT DEFAULT 'local_owned', -- local_owned | remote_mirror | unknown

                gcal_dirty INTEGER DEFAULT 1,

                gcal_last_synced_at TEXT,

                gcal_remote_updated_at TEXT,

                gcal_sync_error TEXT,

                updated_at TEXT DEFAULT (datetime('now', 'localtime')),



                -- ??꾩뒪?ы봽

                created_at TEXT DEFAULT (datetime('now', 'localtime')),



                FOREIGN KEY (template_id) REFERENCES routine_template(id) ON DELETE SET NULL

            )

        """)

        # 2. worklog (湲곗〈 ?좎?)

        cur.execute("""

            CREATE TABLE IF NOT EXISTS worklog (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                task_id INTEGER,

                task_type TEXT,                         -- 'schedule' ?먮뒗 'routine'

                duration_seconds INTEGER,

                logged_at TEXT DEFAULT (datetime('now', 'localtime'))

            )

        """)

        cur.execute("""

            CREATE TABLE IF NOT EXISTS gcal_delete_queue (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                gcal_event_id TEXT NOT NULL,

                gcal_calendar_id TEXT,

                local_task_id INTEGER,

                created_at TEXT DEFAULT (datetime('now', 'localtime')),

                last_error TEXT,

                retry_count INTEGER DEFAULT 0,

                next_retry_at TEXT,

                last_attempt_at TEXT

            )

        """)

        cur.execute("""

            CREATE TABLE IF NOT EXISTS gcal_deleted_task_archive (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                original_task_id INTEGER,

                gcal_event_id TEXT,

                name TEXT,

                deadline TEXT,

                end_date TEXT,

                description TEXT,

                location TEXT,

                all_day INTEGER DEFAULT 0,

                archived_reason TEXT,

                archived_at TEXT DEFAULT (datetime('now', 'localtime')),

                snapshot_json TEXT

            )

        """)

        cur.execute("""

            CREATE TABLE IF NOT EXISTS gcal_sync_conflict_queue (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                local_task_id INTEGER,

                gcal_event_id TEXT,

                gcal_calendar_id TEXT,

                conflict_kind TEXT DEFAULT 'remote_overwrite',

                local_snapshot_json TEXT,

                remote_snapshot_json TEXT,

                is_resolved INTEGER DEFAULT 0,

                resolution TEXT,

                created_at TEXT DEFAULT (datetime('now', 'localtime')),

                resolved_at TEXT

            )

        """)

        # 2-1. fired_alarms (Persistence for alarms)

        cur.execute("""

            CREATE TABLE IF NOT EXISTS fired_alarms (

                task_id INTEGER,

                offset_mins INTEGER,

                fired_at TEXT DEFAULT (datetime('now', 'localtime')),

                PRIMARY KEY (task_id, offset_mins),

                FOREIGN KEY (task_id) REFERENCES unified_task(id) ON DELETE CASCADE

            )

        """)

        cur.execute("""

            CREATE TABLE IF NOT EXISTS gcal_subscription (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                calendar_id TEXT NOT NULL UNIQUE,

                summary TEXT,

                time_zone TEXT,

                access_role TEXT,

                is_active INTEGER DEFAULT 1,

                is_primary INTEGER DEFAULT 0,

                is_external INTEGER DEFAULT 1,

                last_error TEXT,

                last_seen_at TEXT,

                created_at TEXT DEFAULT (datetime('now', 'localtime')),

                updated_at TEXT DEFAULT (datetime('now', 'localtime'))

            )

        """)

        # calendar: 硫??罹섎┛???듯빀 愿由??뚯씠釉?(gcal / local / ics)

        cur.execute("""

            CREATE TABLE IF NOT EXISTS calendar (

                id               TEXT PRIMARY KEY,

                type             TEXT NOT NULL DEFAULT 'local',

                name             TEXT NOT NULL,

                color            TEXT NOT NULL DEFAULT '{DEFAULT_CALENDAR_COLOR}',

                is_default       INTEGER DEFAULT 0,

                is_active        INTEGER DEFAULT 1,

                is_visible       INTEGER DEFAULT 1,

                gcal_calendar_id TEXT,

                ics_url          TEXT,

                ics_last_fetched TEXT,

                sort_order       INTEGER DEFAULT 0,

                access_role      TEXT,

                created_at       TEXT DEFAULT (datetime('now', 'localtime'))

            )

        """)

        # 3. task_directive (吏?쒖궗??- 湲곗〈 ?좎?)

        cur.execute("""

            CREATE TABLE IF NOT EXISTS task_directive (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                content TEXT NOT NULL,

                details TEXT,

                requester TEXT,

                deadline TEXT,

                status TEXT DEFAULT 'in_progress',

                bg_color TEXT

            )

        """)

        # 4. routine_template (?쇰컲?낅Т ?쒗뵆由?

        cur.execute("""

            CREATE TABLE IF NOT EXISTS routine_template (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                name TEXT NOT NULL,

                cycle_type TEXT NOT NULL,               -- weekly, monthly, quarterly, half_yearly, yearly

                description TEXT,

                is_active INTEGER DEFAULT 1,

                priority TEXT DEFAULT 'normal',

                icon TEXT,

                bg_color TEXT,

                alarm_time TEXT,                        -- 湲곕낯 ?뚮엺 ?쒓컙

                location TEXT,                          -- 湲곕낯 ?μ냼

                assignee TEXT,                          -- 湲곕낯 ?대떦??

                created_at TEXT DEFAULT (datetime('now', 'localtime'))

            )

        """)

        # 4-1. template_step (?덇굅??吏?먯슜)

        cur.execute("""

            CREATE TABLE IF NOT EXISTS template_step (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                template_id INTEGER NOT NULL,

                step_name TEXT NOT NULL,

                step_order INTEGER DEFAULT 0,

                FOREIGN KEY (template_id) REFERENCES routine_template(id) ON DELETE CASCADE

            )

        """)

        # 5. checklist_template (泥댄겕由ъ뒪???쒗뵆由?

        cur.execute("""

            CREATE TABLE IF NOT EXISTS checklist_template (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                name TEXT NOT NULL,

                description TEXT,

                category TEXT,

                checklist_type TEXT DEFAULT 'list',

                is_active INTEGER DEFAULT 1,

                created_at TEXT DEFAULT (datetime('now', 'localtime')),

                updated_at TEXT DEFAULT (datetime('now', 'localtime'))

            )

        """)

        # 6. checklist_item (泥댄겕由ъ뒪????ぉ ?뺤쓽)

        cur.execute("""

            CREATE TABLE IF NOT EXISTS checklist_item (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                checklist_id INTEGER NOT NULL,

                item_text TEXT NOT NULL,

                item_description TEXT,

                item_guide TEXT,

                item_order INTEGER DEFAULT 0,

                is_required INTEGER DEFAULT 0,

                FOREIGN KEY (checklist_id) REFERENCES checklist_template(id) ON DELETE CASCADE

            )

        """)

        # 7. task_checklist_link (?ㅼ젣 ?섑뻾 泥댄겕由ъ뒪???곌껐)

        cur.execute("""

            CREATE TABLE IF NOT EXISTS task_checklist_link (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                owner_type TEXT NOT NULL,               -- 'schedule' ?먮뒗 'routine'

                owner_id INTEGER NOT NULL,              -- unified_task.id 李몄“

                item_text TEXT NOT NULL,

                item_order INTEGER DEFAULT 0,

                display_type TEXT DEFAULT 'list',

                is_completed INTEGER DEFAULT 0,

                completed_at TEXT

            )

        """)

        # 8. Missing columns for unified_task (when upgrading from older versions)

        unified_task_cols = get_table_columns(cur, "unified_task")

        full_unified_cols = [
            ("name", "TEXT"),
            ("type", "TEXT DEFAULT 'schedule'"),
            ("priority", "TEXT DEFAULT 'normal'"),
            ("status", "TEXT DEFAULT 'in_progress'"),
            ("deadline", "TEXT"),
            ("end_date", "TEXT"),
            ("alarm_time", "TEXT"),
            ("recurrence", "TEXT"),
            ("template_id", "INTEGER"),
            ("target_date", "TEXT"),
            ("cycle_type", "TEXT"),
            ("period_start", "TEXT"),
            ("period_end", "TEXT"),
            ("series_id", "TEXT"),
            ("series_order", "INTEGER"),
            ("series_total", "INTEGER"),
            ("is_completed", "INTEGER DEFAULT 0"),
            ("completed_at", "TEXT"),
            ("bg_color", "TEXT"),
            ("icon", "TEXT"),
            ("description", "TEXT"),
            ("memo", "TEXT"),
            ("location", "TEXT"),
            ("assignee", "TEXT"),
            ("all_day", "INTEGER DEFAULT 0"),
            ("gcal_event_id", "TEXT"),
            ("gcal_source_calendar_id", "TEXT"),
            ("gcal_source_summary", "TEXT"),
            ("gcal_target_calendar_id", "TEXT"),
            ("gcal_sync_mode", "TEXT DEFAULT 'local_owned'"),
            ("gcal_dirty", "INTEGER DEFAULT 1"),
            ("gcal_last_synced_at", "TEXT"),
            ("gcal_remote_updated_at", "TEXT"),
            ("gcal_sync_error", "TEXT"),
            ("updated_at", "TEXT"),
            ("created_at", "TEXT DEFAULT (datetime('now', 'localtime'))"),
            ("calendar_id", "TEXT"),
            # GCal recurring event support (Phase 3 - item 2)
            ("gcal_recurring_series_id", "TEXT"),
            ("gcal_instance_original_start", "TEXT"),
            ("gcal_recurrence_rule", "TEXT"),
            # Attendee / attachment sync (Phase 3 - item 9)
            ("attendees_json", "TEXT"),
            ("attachments_json", "TEXT"),
            # task tags (routine classification)
            ("tags", "TEXT"),
        ]

        added_gcal_sync_mode = False

        for col_name, col_type in full_unified_cols:
            if col_name not in unified_task_cols:
                try:
                    cur.execute(f"ALTER TABLE unified_task ADD COLUMN {col_name} {col_type}")
                    logger.info(f"Added column {col_name} to unified_task")
                    if col_name == "gcal_sync_mode":
                        added_gcal_sync_mode = True
                except sqlite3.OperationalError as e:
                    logger.warning(f"Could not add column {col_name}: {e}")

        # Missing columns for worklog
        worklog_cols = get_table_columns(cur, "worklog")
        if "task_type" not in worklog_cols:
            try:
                cur.execute("ALTER TABLE worklog ADD COLUMN task_type TEXT")
            except sqlite3.OperationalError:
                pass

        # 9. Missing columns for task_directive

        directive_cols = get_table_columns(cur, "task_directive")

        missing_directive_cols = [
            ("content", "TEXT"),
            ("details", "TEXT"),
            ("requester", "TEXT"),
            ("receiver_name", "TEXT"),
            ("deadline", "TEXT"),
            ("status", "TEXT DEFAULT 'in_progress'"),
            ("bg_color", "TEXT"),
            ("memo", "TEXT"),
            ("priority", "TEXT DEFAULT 'normal'"),
        ]

        for col_name, col_type in missing_directive_cols:
            if col_name not in directive_cols:
                try:
                    cur.execute(f"ALTER TABLE task_directive ADD COLUMN {col_name} {col_type}")

                    logger.info(f"Added column {col_name} to task_directive")

                except sqlite3.OperationalError:
                    pass

        directive_cols = get_table_columns(cur, "task_directive")

        if "receiver_name" in directive_cols and "requester" in directive_cols:
            cur.execute(
                "UPDATE task_directive "
                "SET receiver_name = COALESCE(NULLIF(receiver_name, ''), requester) "
                "WHERE COALESCE(receiver_name, '') = '' AND COALESCE(requester, '') != ''"
            )

        if "memo" in directive_cols and "details" in directive_cols:
            cur.execute(
                "UPDATE task_directive "
                "SET memo = COALESCE(NULLIF(memo, ''), details) "
                "WHERE COALESCE(memo, '') = '' AND COALESCE(details, '') != ''"
            )

        delete_queue_cols = get_table_columns(cur, "gcal_delete_queue")

        for col_name, col_type in [
            ("gcal_calendar_id", "TEXT"),
            ("next_retry_at", "TEXT"),
            ("last_attempt_at", "TEXT"),
            ("recurring_scope", "TEXT"),
        ]:
            if col_name not in delete_queue_cols:
                try:
                    cur.execute(f"ALTER TABLE gcal_delete_queue ADD COLUMN {col_name} {col_type}")

                    logger.info(f"Added column {col_name} to gcal_delete_queue")

                except sqlite3.OperationalError:
                    pass

        # ?몃뜳??異붽? (議고쉶 ?깅뒫 理쒖쟻??

        conflict_queue_cols = get_table_columns(cur, "gcal_sync_conflict_queue")

        for col_name, col_type in [
            ("gcal_calendar_id", "TEXT"),
            ("conflict_kind", "TEXT DEFAULT 'remote_overwrite'"),
            ("local_snapshot_json", "TEXT"),
            ("remote_snapshot_json", "TEXT"),
            ("is_resolved", "INTEGER DEFAULT 0"),
            ("resolution", "TEXT"),
            ("resolved_at", "TEXT"),
        ]:
            if col_name not in conflict_queue_cols:
                try:
                    cur.execute(
                        f"ALTER TABLE gcal_sync_conflict_queue ADD COLUMN {col_name} {col_type}"
                    )

                    logger.info(f"Added column {col_name} to gcal_sync_conflict_queue")

                except sqlite3.OperationalError:
                    pass

        subscription_cols = get_table_columns(cur, "gcal_subscription")

        for col_name, col_type in [
            ("summary", "TEXT"),
            ("time_zone", "TEXT"),
            ("access_role", "TEXT"),
            ("is_active", "INTEGER DEFAULT 1"),
            ("is_primary", "INTEGER DEFAULT 0"),
            ("is_external", "INTEGER DEFAULT 1"),
            ("last_error", "TEXT"),
            ("last_seen_at", "TEXT"),
            ("created_at", "TEXT"),
            ("updated_at", "TEXT"),
        ]:
            if col_name not in subscription_cols:
                try:
                    cur.execute(f"ALTER TABLE gcal_subscription ADD COLUMN {col_name} {col_type}")

                    logger.info(f"Added column {col_name} to gcal_subscription")

                except sqlite3.OperationalError:
                    pass

        # calendar 테이블 컬럼 마이그레이션
        calendar_cols = get_table_columns(cur, "calendar")
        if "access_role" not in calendar_cols:
            try:
                cur.execute("ALTER TABLE calendar ADD COLUMN access_role TEXT")
                logger.info("Added column access_role to calendar")
            except sqlite3.OperationalError:
                pass

        # Backfill calendar.access_role from gcal_subscription for rows migrated without it
        try:
            cur.execute("""
                UPDATE calendar
                SET access_role = (
                    SELECT gs.access_role FROM gcal_subscription gs
                    WHERE gs.calendar_id = calendar.gcal_calendar_id
                    LIMIT 1
                )
                WHERE type = 'gcal'
                  AND (access_role IS NULL OR access_role = '')
                  AND gcal_calendar_id IS NOT NULL
                  AND gcal_calendar_id != ''
            """)
            if cur.rowcount:
                logger.info("Backfilled access_role for %d gcal calendar row(s)", cur.rowcount)
        except Exception:
            pass

        # 시작 시 복구: access_role='owner'/'writer' 인 gcal 캘린더가 is_active=0 으로
        # 잘못 저장된 경우 강제로 재활성화한다.
        # (is_active=0 은 GCal sync 비활성화를 뜻하며 편집 권한 제거가 아님)
        try:
            cur.execute("""
                UPDATE calendar
                SET is_active = 1
                WHERE type = 'gcal'
                  AND is_active = 0
                  AND access_role IN ('owner', 'writer')
            """)
            if cur.rowcount:
                logger.info("Restored is_active=1 for %d writable gcal calendar(s)", cur.rowcount)
        except Exception:
            pass

        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_unified_task_type_deadline ON unified_task (type, deadline)"
        )

        # Calendar-aware unique index for Google event linkage.

        for idx_name in ("idx_unified_task_gcal_id", "idx_unified_task_gcal_calendar_event"):
            try:
                cur.execute(f"DROP INDEX IF EXISTS {idx_name}")

            except sqlite3.OperationalError:
                pass

        cur.execute("""

            CREATE UNIQUE INDEX IF NOT EXISTS idx_unified_task_gcal_calendar_event

            ON unified_task (

                COALESCE(NULLIF(trim(gcal_source_calendar_id), ''), NULLIF(trim(gcal_target_calendar_id), ''), 'primary'),

                gcal_event_id

            )

            WHERE gcal_event_id IS NOT NULL AND gcal_event_id != ''

        """)

        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_unified_task_gcal_dirty ON unified_task (gcal_dirty)"
        )

        cur.execute("CREATE INDEX IF NOT EXISTS idx_unified_task_status ON unified_task (status)")

        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_unified_task_target_date ON unified_task (target_date)"
        )

        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_unified_task_series_id ON unified_task (series_id, series_order)"
        )

        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_gcal_sync_conflict_resolved ON gcal_sync_conflict_queue (is_resolved, created_at)"
        )

        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_gcal_sync_conflict_event ON gcal_sync_conflict_queue (gcal_event_id, gcal_calendar_id)"
        )

        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_gcal_delete_queue_event_id ON gcal_delete_queue (gcal_event_id)"
        )

        if "gcal_calendar_id" in get_table_columns(cur, "gcal_delete_queue"):
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_gcal_delete_queue_calendar_id ON gcal_delete_queue (gcal_calendar_id)"
            )

        if "next_retry_at" in get_table_columns(cur, "gcal_delete_queue"):
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_gcal_delete_queue_next_retry ON gcal_delete_queue (next_retry_at)"
            )

        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_gcal_deleted_archive_event_id ON gcal_deleted_task_archive (gcal_event_id)"
        )

        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_gcal_subscription_calendar_id ON gcal_subscription (calendar_id)"
        )

        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_gcal_subscription_active ON gcal_subscription (is_active)"
        )

        cur.execute("CREATE INDEX IF NOT EXISTS idx_calendar_type ON calendar (type)")

        cur.execute("CREATE INDEX IF NOT EXISTS idx_calendar_visible ON calendar (is_visible)")

        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_unified_task_calendar_id ON unified_task (calendar_id)"
        )

        cur.execute("CREATE INDEX IF NOT EXISTS idx_fired_alarms_task_id ON fired_alarms (task_id)")

        # ?깅뒫 理쒖쟻?? 異붽? 蹂듯빀 ?몃뜳??

        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_unified_task_routine_period ON unified_task (type, cycle_type, period_start, period_end)"
        )

        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_checklist_link_owner_id ON task_checklist_link (owner_id, item_order)"
        )

        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_unified_task_schedule_dates ON unified_task (type, deadline, end_date)"
        )

        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_unified_task_schedule_overlap ON unified_task (type, deadline, end_date, target_date)"
        )

        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_unified_task_type_target_date ON unified_task (type, target_date)"
        )

        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_task_directive_deadline_order ON task_directive (deadline, id)"
        )

        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_task_directive_status_deadline ON task_directive (status, deadline)"
        )

        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_checklist_link_owner_completed ON task_checklist_link (owner_type, owner_id, is_completed)"
        )

        # gcal_recurring_series: GCal 반복 일정 시리즈 메타데이터 테이블 (item 2)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS gcal_recurring_series (
                id               TEXT PRIMARY KEY,
                gcal_calendar_id TEXT,
                title            TEXT,
                rrule            TEXT,
                first_instance   TEXT,
                last_fetched_at  TEXT,
                created_at       TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_gcal_recurring_series_cal ON gcal_recurring_series (gcal_calendar_id)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_unified_task_recurring_series ON unified_task (gcal_recurring_series_id)"
        )

        # Legacy status normalization

        cur.execute("UPDATE unified_task SET status='completed' WHERE status='done'")

        cur.execute(
            "UPDATE unified_task SET status='deferred' WHERE status IN ('overdue', 'canceled')"
        )

        cur.execute("""

            UPDATE unified_task

            SET gcal_dirty = CASE

                WHEN gcal_dirty IS NULL AND (gcal_event_id IS NULL OR trim(gcal_event_id) = '') THEN 1

                WHEN gcal_dirty IS NULL THEN 0

                ELSE gcal_dirty

            END

        """)

        if "gcal_sync_mode" in get_table_columns(cur, "unified_task"):
            if "gcal_target_calendar_id" in get_table_columns(cur, "unified_task"):
                cur.execute("""

                    UPDATE unified_task

                    SET gcal_target_calendar_id = COALESCE(

                        NULLIF(trim(gcal_target_calendar_id), ''),

                        NULLIF(trim(gcal_source_calendar_id), ''),

                        gcal_target_calendar_id

                    )

                    WHERE COALESCE(trim(gcal_event_id), '') != ''

                """)

            cur.execute("""

                UPDATE unified_task

                SET gcal_sync_mode = CASE

                    WHEN COALESCE(trim(gcal_source_calendar_id), '') != '' THEN 'remote_mirror'

                    WHEN COALESCE(trim(gcal_sync_mode), '') = '' THEN 'local_owned'

                    ELSE gcal_sync_mode

                END

            """)

            if added_gcal_sync_mode:
                # One-time safety migration for previously detached data:

                # if a row is dirty but has no gcal_event_id and no source marker, we cannot

                # reliably infer ownership. Keep it out of automatic push until user edits it.

                cur.execute("""

                    UPDATE unified_task

                    SET gcal_sync_mode = 'unknown'

                    WHERE (gcal_event_id IS NULL OR trim(gcal_event_id) = '')

                      AND COALESCE(gcal_dirty, 1) = 1

                      AND COALESCE(trim(gcal_source_calendar_id), '') = ''

                      AND COALESCE(trim(gcal_sync_mode), 'local_owned') = 'local_owned'

                """)

        if "updated_at" in get_table_columns(cur, "unified_task"):
            cur.execute("""

                UPDATE unified_task

                SET updated_at = COALESCE(updated_at, created_at, datetime('now', 'localtime'))

            """)

        cur.execute("UPDATE task_directive SET status='completed' WHERE status='done'")

        cur.execute(
            "UPDATE task_directive SET status='deferred' WHERE status IN ('overdue', 'canceled')"
        )

        # --- 湲곗〈 ?뚯씠釉?留덉씠洹몃젅?댁뀡 濡쒖쭅 ---

        # 猷⑦떞 ?덇굅???뚯씠釉??먮뒗 ?쇱젙 ?덇굅???뚯씠釉붿씠 ?덈뒗 寃쎌슦 留덉씠洹몃젅?댁뀡 ?쒕룄

        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('special_task', 'routine_task')"
        )

        if cur.fetchone():
            logger.info("Checking for data migration to unified_task...")

            # special_task ?뚯씠釉?議댁옱 ?щ? ?뺤씤

            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='special_task'")

            if cur.fetchone():
                st_cols = get_table_columns(cur, "special_task")

                # Expressions for possibly missing columns

                priority_st = (
                    "COALESCE(priority, 'normal')" if "priority" in st_cols else "'normal'"
                )

                status_st = "COALESCE(status, 'pending')" if "status" in st_cols else "'pending'"

                deadline_st = "deadline" if "deadline" in st_cols else "NULL"

                end_date_st = "end_date" if "end_date" in st_cols else "NULL"

                alarm_time_st = "alarm_time" if "alarm_time" in st_cols else "NULL"

                recurrence_st = "recurrence" if "recurrence" in st_cols else "NULL"

                bg_color_st = "bg_color" if "bg_color" in st_cols else "NULL"

                icon_st = "icon" if "icon" in st_cols else "NULL"

                gcal_st = "gcal_event_id" if "gcal_event_id" in st_cols else "NULL"

                created_st = (
                    "COALESCE(created_at, datetime('now', 'localtime'))"
                    if "created_at" in st_cols
                    else "datetime('now', 'localtime')"
                )

                cur.execute(f"""

                    INSERT OR IGNORE INTO unified_task (

                        id, name, type, priority, status, deadline, end_date,

                        alarm_time, recurrence, bg_color, icon, gcal_event_id, created_at

                    )

                    SELECT

                        id, name, 'schedule',

                        {priority_st},

                        {status_st},

                        {deadline_st},

                        {end_date_st},

                        {alarm_time_st},

                        {recurrence_st},

                        {bg_color_st},

                        {icon_st},

                        {gcal_st},

                        {created_st}

                    FROM special_task

                """)

                logger.info(f"Migrated {cur.rowcount} records from special_task")

            # routine_task ?뚯씠釉?議댁옱 ?щ? ?뺤씤

            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='routine_task'")

            if cur.fetchone():
                # ID 異⑸룎 諛⑹?瑜??꾪븳 offset 怨꾩궛

                cur.execute("SELECT COALESCE(MAX(id), 0) FROM unified_task")

                max_id = cur.fetchone()[0]

                rt_cols = get_table_columns(cur, "routine_task")

                # 而щ읆 議댁옱 ?щ????곕씪 SELECT 臾??숈쟻 ?앹꽦

                template_id_expr = "template_id" if "template_id" in rt_cols else "NULL"

                target_date_expr = "target_date" if "target_date" in rt_cols else "deadline"

                cycle_type_expr = "cycle_type" if "cycle_type" in rt_cols else "'monthly'"

                priority_expr = (
                    "COALESCE(priority, 'normal')" if "priority" in rt_cols else "'normal'"
                )

                icon_expr = "icon" if "icon" in rt_cols else "NULL"

                bg_color_expr = "bg_color" if "bg_color" in rt_cols else "NULL"

                alarm_time_expr = "alarm_time" if "alarm_time" in rt_cols else "NULL"

                description_expr = "description" if "description" in rt_cols else "NULL"

                memo_expr = "memo" if "memo" in rt_cols else "NULL"

                recurrence_expr = "recurrence" if "recurrence" in rt_cols else "NULL"

                is_completed_expr = "is_completed" if "is_completed" in rt_cols else "0"

                completed_at_expr = "completed_at" if "completed_at" in rt_cols else "NULL"

                cur.execute(f"""

                    INSERT OR IGNORE INTO unified_task (

                        id, name, type, template_id, target_date, cycle_type,

                        priority, icon, bg_color, alarm_time, description, memo,

                        recurrence, is_completed, completed_at, deadline

                    )

                    SELECT

                        id + {max_id},

                        name,

                        'routine',

                        {template_id_expr},

                        {target_date_expr},

                        {cycle_type_expr},

                        {priority_expr},

                        {icon_expr},

                        {bg_color_expr},

                        {alarm_time_expr},

                        {description_expr},

                        {memo_expr},

                        {recurrence_expr},

                        {is_completed_expr},

                        {completed_at_expr},

                        {target_date_expr}

                    FROM routine_task

                """)

                routine_inserted_count = cur.rowcount

                logger.info(f"Migrated {routine_inserted_count} records from routine_task")

                # task_checklist_link??owner_id ?낅뜲?댄듃

                # Only shift checklist owner_ids when routine rows were actually
                # migrated. Without this guard the UPDATE ran on every startup,
                # corrupting owner_ids (owner_id += max_id each boot) and orphaning
                # routine checklists. routine_task is an empty legacy table for
                # already-migrated users, so this now correctly skips.
                if routine_inserted_count > 0:
                    cur.execute(
                        f"UPDATE task_checklist_link SET owner_id = owner_id + {max_id} WHERE owner_type = 'routine'"
                    )

        # checklist_template ?? ??

        checklist_template_cols = get_table_columns(cur, "checklist_template")

        for col in [
            ("category", "TEXT"),
            ("checklist_type", "TEXT DEFAULT 'list'"),
            ("is_active", "INTEGER DEFAULT 1"),
            ("updated_at", "TEXT DEFAULT (datetime('now', 'localtime'))"),
        ]:
            if col[0] not in checklist_template_cols:
                try:
                    cur.execute(f"ALTER TABLE checklist_template ADD COLUMN {col[0]} {col[1]}")

                except sqlite3.OperationalError:
                    pass

        # routine_template??alarm_time 而щ읆 異붽? (?녿뒗 寃쎌슦)

        tmpl_cols = get_table_columns(cur, "routine_template")

        if "alarm_time" not in tmpl_cols:
            try:
                cur.execute("ALTER TABLE routine_template ADD COLUMN alarm_time TEXT")

            except sqlite3.OperationalError:
                pass

        # checklist_template ?? ??

        checklist_template_cols = get_table_columns(cur, "checklist_template")

        for col in [
            ("category", "TEXT"),
            ("checklist_type", "TEXT DEFAULT 'list'"),
            ("is_active", "INTEGER DEFAULT 1"),
            ("updated_at", "TEXT DEFAULT (datetime('now', 'localtime'))"),
        ]:
            if col[0] not in checklist_template_cols:
                try:
                    cur.execute(f"ALTER TABLE checklist_template ADD COLUMN {col[0]} {col[1]}")

                except sqlite3.OperationalError:
                    pass

        # task_checklist_link display_type ?? ??

        tcl_cols = get_table_columns(cur, "task_checklist_link")

        if "display_type" not in tcl_cols:
            try:
                cur.execute(
                    "ALTER TABLE task_checklist_link ADD COLUMN display_type TEXT DEFAULT 'list'"
                )

            except sqlite3.OperationalError:
                pass

        # checklist_item ?? ?? 而щ읆 異붽?

        checklist_item_cols = get_table_columns(cur, "checklist_item")

        for col in [
            ("item_description", "TEXT"),
            ("item_guide", "TEXT"),
            ("is_required", "INTEGER DEFAULT 0"),
        ]:
            if col[0] not in checklist_item_cols:
                try:
                    cur.execute(f"ALTER TABLE checklist_item ADD COLUMN {col[0]} {col[1]}")

                except sqlite3.OperationalError:
                    pass

        # 湲곗〈 routine ????곗씠?곗쓽 period_start, period_end ?먮룞 怨꾩궛

        cur.execute("""

            SELECT id, target_date, cycle_type

            FROM unified_task

            WHERE type='routine' AND (period_start IS NULL OR period_end IS NULL)

        """)

        for task_id, target_date, cycle_type in cur.fetchall():
            if target_date:
                period_start, period_end = calculate_period_bounds(target_date, cycle_type)

                cur.execute(
                    """

                    UPDATE unified_task

                    SET period_start=?, period_end=?

                    WHERE id=?

                """,
                    (period_start, period_end, task_id),
                )

        # Auto-fix: misclassified schedule->routine
        try:
            cur.execute("""
                UPDATE unified_task
                SET type = 'routine'
                WHERE type = 'schedule'
                  AND cycle_type IS NOT NULL
                  AND trim(cycle_type) != ''

            """)
            if cur.rowcount:
                logger.info("Auto-migrated %d schedule->routine task(s)", cur.rowcount)
        except Exception:
            pass

        conn.commit()

        # conn.close()  <-- Singleton ?대?濡??レ? ?딆쓬

        logger.info("Unified database initialized successfully.")

        return True

    except Exception as e:
        logger.error(f"Unified database initialization failed: {e}")

        import traceback

        logger.error(traceback.format_exc())

        return False


# ?⑥씪 援ы쁽? period_utils.py???덉쓬. ?섏쐞 ?명솚?깆쓣 ?꾪빐 ?ш린??re-export.

from calendar_app.infrastructure.db.period_utils import calculate_period_bounds  # noqa: F401


class ThreadLocalDatabaseManager:
    """Use one SQLite connection per thread to avoid cross-thread instability."""

    def __init__(self):
        self._connections = {}

        self._lock = threading.RLock()

    def _create_connection(self):
        db_dir = os.path.dirname(DB_PATH)

        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)

        conn.row_factory = sqlite3.Row

        conn.execute("PRAGMA busy_timeout = 10000")

        return conn

    def get_connection(self):
        thread_id = threading.get_ident()

        with self._lock:
            record = self._connections.get(thread_id)

            if record is not None:
                db_path, conn = record

                if db_path == DB_PATH:
                    return ConnectionWrapper(conn)

                try:
                    conn.close()

                except sqlite3.Error:
                    pass

                self._connections.pop(thread_id, None)

            try:
                conn = self._create_connection()

                conn.execute("PRAGMA foreign_keys = ON")

                conn.execute("PRAGMA journal_mode = WAL")

                conn.execute("PRAGMA synchronous = NORMAL")

                self._connections[thread_id] = (DB_PATH, conn)

                # logger.info(f"Database connection established: {DB_PATH} (WAL mode enabled)")

                return ConnectionWrapper(conn)

            except sqlite3.Error as e:
                logger.error(f"Failed to connect to database: {e}")

                return None

    def close_connection(self):
        thread_id = threading.get_ident()

        with self._lock:
            record = self._connections.pop(thread_id, None)

        if record:
            _, conn = record

            conn.close()

            logger.info("Database connection closed for thread %s.", thread_id)

    def close_all_connections(self):
        with self._lock:
            records = list(self._connections.items())

            self._connections.clear()

        for thread_id, (_, conn) in records:
            try:
                conn.close()

            except sqlite3.Error:
                pass

            logger.info("Database connection closed for thread %s.", thread_id)


class DatabaseManager(ThreadLocalDatabaseManager):
    """Compatibility wrapper for DatabaseManager."""

    pass


db_manager = DatabaseManager()


if __name__ == "__main__":
    initialize_unified_database()

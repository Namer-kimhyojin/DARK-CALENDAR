export const SCHEMA = [
  `CREATE TABLE IF NOT EXISTS board_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL, body TEXT NOT NULL, nickname TEXT NOT NULL,
    category TEXT NOT NULL CHECK(category IN ('bug','feature','ui','other')),
    app_version TEXT NOT NULL DEFAULT '', platform TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'received' CHECK(status IN ('received','reviewing','planned','done','closed')),
    admin_reply TEXT NOT NULL DEFAULT '',
    password_salt TEXT NOT NULL, password_hash TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1
  )`,
  `CREATE INDEX IF NOT EXISTS board_requests_status_created ON board_requests(status, created_at DESC)`,
  `CREATE TABLE IF NOT EXISTS board_rate_limits (bucket TEXT PRIMARY KEY, hits INTEGER NOT NULL, expires_at INTEGER NOT NULL)`,
  `CREATE INDEX IF NOT EXISTS board_rate_limits_expiry ON board_rate_limits(expires_at)`,
  `CREATE TABLE IF NOT EXISTS board_admin_sessions (token_hash TEXT PRIMARY KEY, expires_at INTEGER NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS board_images (
    id TEXT PRIMARY KEY, request_id INTEGER NOT NULL REFERENCES board_requests(id),
    object_key TEXT NOT NULL UNIQUE, content_type TEXT NOT NULL, size INTEGER NOT NULL,
    width INTEGER NOT NULL, height INTEGER NOT NULL, digest TEXT NOT NULL,
    position INTEGER NOT NULL, created_at TEXT NOT NULL
  )`,
  `CREATE INDEX IF NOT EXISTS board_images_request ON board_images(request_id, position)`,
  `CREATE TABLE IF NOT EXISTS board_image_cleanup (object_key TEXT PRIMARY KEY, ready_at INTEGER NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS board_revision_guard (token TEXT PRIMARY KEY, matches INTEGER NOT NULL CHECK(matches=1))`,
];

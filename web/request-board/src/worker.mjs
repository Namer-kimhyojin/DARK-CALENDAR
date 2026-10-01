import { SCHEMA } from "./schema.mjs";
import { ImageError, IMAGE_COUNT, requestWithImages } from "./images.mjs";

const HOME = "https://namer-kimhyojin.github.io/DARK-CALENDAR/";
const CATEGORIES = ["bug", "feature", "ui", "other"];
const STATUSES = ["received", "reviewing", "planned", "done", "closed"];
const PUBLIC_COLUMNS = "id,title,body,nickname,category,app_version,platform,status,admin_reply,created_at,updated_at,revision";
const schemaReady = new WeakMap();
const encoder = new TextEncoder();
const hex = (bytes) => Array.from(new Uint8Array(bytes), (byte) => byte.toString(16).padStart(2, "0")).join("");
const unhex = (value) => Uint8Array.from(value.match(/../g) || [], (pair) => parseInt(pair, 16));
const randomHex = (size = 24) => hex(crypto.getRandomValues(new Uint8Array(size)));
export const sha256 = async (value) => hex(await crypto.subtle.digest("SHA-256", encoder.encode(value)));

class BoardError extends Error {
  constructor(status, code) { super(code); this.status = status; this.code = code; }
}
const fail = (status, code) => { throw new BoardError(status, code); };
export function equalSecret(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let difference = 0;
  for (let i = 0; i < a.length; i++) difference |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return difference === 0;
}
export async function passwordHash(password, salt, pepper) {
  const digest = await sha256(`${pepper}\0${password}`);
  const key = await crypto.subtle.importKey("raw", encoder.encode(digest), "PBKDF2", false, ["deriveBits"]);
  return hex(await crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt: unhex(salt), iterations: 100000 }, key, 256));
}
function field(value, min, max, code) {
  if (typeof value !== "string") fail(400, code);
  const text = value.trim();
  if (text.length < min || text.length > max || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/u.test(text)) fail(400, code);
  return text;
}
export function validatePost(input, editing = false) {
  if (!input || typeof input !== "object" || Array.isArray(input)) fail(400, "invalid_request");
  const allowed = ["title", "body", "nickname", "category", "appVersion", "platform", "password", "website", "idempotencyKey", "revision", "removeImages"];
  if (Object.keys(input).some((key) => !allowed.includes(key))) fail(400, "invalid_request");
  if (input.website) fail(400, "invalid_request");
  const result = {
    title: field(input.title, 3, 100, "invalid_title"),
    body: field(input.body, 10, 5000, "invalid_body"),
    nickname: field(input.nickname || "방문자", 1, 30, "invalid_nickname"),
    category: input.category,
    appVersion: field(input.appVersion || "", 0, 30, "invalid_version"),
    platform: field(input.platform || "", 0, 60, "invalid_platform"),
    password: field(input.password, 8, 128, "invalid_password"),
  };
  if (!CATEGORIES.includes(result.category)) fail(400, "invalid_category");
  if (!editing && !/^[a-f0-9-]{36}$/i.test(input.idempotencyKey || "")) fail(400, "invalid_request");
  if (editing && (!Number.isSafeInteger(input.revision) || input.revision < 1)) fail(400, "invalid_request");
  const removed = input.removeImages || [];
  if (!Array.isArray(removed) || removed.length > IMAGE_COUNT || new Set(removed).size !== removed.length || removed.some(id => typeof id !== "string" || !/^[a-f0-9]{48}$/.test(id)) || (!editing && removed.length)) fail(400, "invalid_request");
  result.removeImages = removed;
  return result;
}
function publicPost(row) {
  if (!row) return null;
  const post = {};
  PUBLIC_COLUMNS.split(",").forEach((key) => { post[key] = row[key]; });
  return post;
}
async function initialize(db) {
  if (!schemaReady.has(db)) {
    const ready = db.batch(SCHEMA.map((sql) => db.prepare(sql))).catch((error) => { schemaReady.delete(db); throw error; });
    schemaReady.set(db, ready);
  }
  await schemaReady.get(db);
}
function origins(request, env) {
  const allowed = new Set([new URL(HOME).origin, new URL(request.url).origin]);
  if (env.DEV_MODE === "true") allowed.add("http://127.0.0.1:8765");
  return allowed;
}
function response(data, status, origin, headers = {}) {
  const common = {
    "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "Vary": "Origin",
    ...headers,
  };
  if (origin) common["Access-Control-Allow-Origin"] = origin;
  return new Response(JSON.stringify(data), { status, headers: common });
}
async function inputJson(request) {
  if (!(request.headers.get("Content-Type") || "").toLowerCase().startsWith("application/json")) fail(415, "json_required");
  if (Number(request.headers.get("Content-Length")) > 32768) fail(413, "too_large");
  const reader = request.body?.getReader();
  if (!reader) fail(400, "invalid_request");
  const chunks = []; let length = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    length += value.byteLength;
    if (length > 32768) { await reader.cancel(); fail(413, "too_large"); }
    chunks.push(value);
  }
  const bytes = new Uint8Array(length); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  try { return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)); }
  catch { fail(400, "invalid_request"); }
}
async function rateLimit(db, request, env, operation, maximum, duration) {
  const now = Math.floor(Date.now() / 1000);
  const ip = request.headers.get("CF-Connecting-IP") || request.headers.get("X-Real-IP") || "unknown";
  const fingerprint = await sha256(`${env.BOARD_PASSWORD_PEPPER}\0${ip}`);
  const bucket = `${operation}:${fingerprint}:${Math.floor(now / duration)}`;
  const counter = await db.prepare("INSERT INTO board_rate_limits(bucket,hits,expires_at) VALUES(?,1,?) ON CONFLICT(bucket) DO UPDATE SET hits=hits+1 RETURNING hits")
    .bind(bucket, now + duration * 2).first();
  if (counter.hits > maximum) fail(429, "rate_limited");
  await db.prepare("DELETE FROM board_rate_limits WHERE expires_at < ?").bind(now).run();
}
async function authorizeAdmin(request, db) {
  const token = /^Bearer ([a-f0-9]{64})$/.exec(request.headers.get("Authorization") || "")?.[1];
  if (!token) fail(401, "unauthorized");
  const session = await db.prepare("SELECT expires_at FROM board_admin_sessions WHERE token_hash=?").bind(await sha256(token)).first();
  if (!session || session.expires_at < Date.now()) fail(401, "unauthorized");
}
async function findPost(db, id, privateFields = false) {
  if (!Number.isSafeInteger(id) || id < 1) fail(404, "not_found");
  const row = await db.prepare(`SELECT ${privateFields ? "*" : PUBLIC_COLUMNS} FROM board_requests WHERE id=?`).bind(id).first();
  if (!row) fail(404, "not_found");
  return privateFields ? row : (await enrichPosts(db, [publicPost(row)]))[0];
}
async function enrichPosts(db, posts) {
  if (!posts.length) return posts;
  const images = await db.prepare(`SELECT id,request_id,content_type,size,width,height FROM board_images WHERE request_id IN (${posts.map(() => "?").join(",")}) ORDER BY position,id`).bind(...posts.map(post => post.id)).all();
  return posts.map(post => ({ ...post, images: images.results.filter(image => image.request_id === post.id).map(({ request_id, ...image }) => ({ ...image, url: `/api/images/${image.id}` })) }));
}
async function imageRows(db, id) { return (await db.prepare("SELECT * FROM board_images WHERE request_id=? ORDER BY position,id").bind(id).all()).results; }
async function contentInput(request) {
  return (request.headers.get("Content-Type") || "").toLowerCase().startsWith("multipart/form-data;") ? requestWithImages(request) : { data: await inputJson(request), images: [] };
}
async function drainCleanup(env) {
  if (!env.BUCKET) return;
  try {
    const rows = (await env.DB.prepare("SELECT object_key FROM board_image_cleanup WHERE ready_at<=? LIMIT 12").bind(Date.now()).all()).results;
    if (!rows.length) return;
    await env.BUCKET.delete(rows.map(row => row.object_key));
    await env.DB.batch(rows.map(row => env.DB.prepare("DELETE FROM board_image_cleanup WHERE object_key=?").bind(row.object_key)));
  } catch { /* Keep the durable cleanup queue for a subsequent request. */ }
}
async function stageImages(env, images) {
  if (!images.length) return [];
  if (!env.BUCKET) fail(503, "image_unavailable");
  const staged = [];
  for (const image of images) {
    const id = randomHex(), objectKey = `request-board/images/${id}`;
    const digest = hex(await crypto.subtle.digest("SHA-256", image.bytes));
    staged.push({ ...image, id, objectKey, digest });
  }
  await env.DB.batch(staged.map(image => env.DB.prepare("INSERT INTO board_image_cleanup(object_key,ready_at) VALUES(?,?)").bind(image.objectKey, Date.now() + 3600000)));
  try {
    for (const image of staged) {
      const stored = await env.BUCKET.put(image.objectKey, image.bytes, { httpMetadata: { contentType: image.type } });
      if (!stored) fail(503, "image_unavailable");
    }
    return staged;
  } catch (error) { await discardStaged(env, staged); throw error; }
}
async function discardStaged(env, staged) {
  if (!staged.length) return;
  await env.DB.batch(staged.map(image => env.DB.prepare("UPDATE board_image_cleanup SET ready_at=0 WHERE object_key=?").bind(image.objectKey)));
  await drainCleanup(env);
}
function imageInsert(db, image, ownerExpression, owner, position) {
  return db.prepare(`INSERT INTO board_images(id,request_id,object_key,content_type,size,width,height,digest,position,created_at) VALUES(?,${ownerExpression},?,?,?,?,?,?,?,?)`)
    .bind(image.id, owner, image.objectKey, image.type, image.size, image.width, image.height, image.digest, position, new Date().toISOString());
}
async function deletePost(env, id) {
  await env.DB.batch([
    env.DB.prepare("INSERT OR REPLACE INTO board_image_cleanup(object_key,ready_at) SELECT object_key,0 FROM board_images WHERE request_id=?").bind(id),
    env.DB.prepare("DELETE FROM board_images WHERE request_id=?").bind(id),
    env.DB.prepare("DELETE FROM board_requests WHERE id=?").bind(id),
  ]);
  await drainCleanup(env);
}
async function repeatedPost(db, key, post, env, images) {
  const previous = await db.prepare("SELECT * FROM board_requests WHERE idempotency_key=?").bind(key).first();
  if (!previous) return null;
  if (previous.title !== post.title || previous.body !== post.body || previous.nickname !== post.nickname || previous.category !== post.category || previous.app_version !== post.appVersion || previous.platform !== post.platform || !equalSecret(await passwordHash(post.password, previous.password_salt, env.BOARD_PASSWORD_PEPPER), previous.password_hash)) fail(409, "conflict");
  const attached = await imageRows(db, previous.id);
  if (attached.length !== images.length) fail(409, "conflict");
  for (let index = 0; index < images.length; index++) if (attached[index].digest !== hex(await crypto.subtle.digest("SHA-256", images[index].bytes))) fail(409, "conflict");
  return (await enrichPosts(db, [publicPost(previous)]))[0];
}
async function route(request, env) {
  const url = new URL(request.url), path = url.pathname.replace(/\/$/, "");
  const origin = request.headers.get("Origin");
  if (origin && !origins(request, env).has(origin)) fail(403, "origin_denied");
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: {
      ...(origin ? { "Access-Control-Allow-Origin": origin } : {}),
      "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization", "Access-Control-Max-Age": "600", "Vary": "Origin",
    } });
  }
  if (path === "") return Response.redirect(`${HOME}#requests`, 302);
  if (!path.startsWith("/api/")) fail(404, "not_found");
  if (!env.DB || !env.BOARD_PASSWORD_PEPPER || !/^[a-f0-9]{64}$/.test(env.ADMIN_PASSWORD_HASH || "")) fail(503, "unavailable");
  await initialize(env.DB);
  await drainCleanup(env);
  const db = env.DB;
  if (path === "/api/health" && request.method === "GET") return response({ service: "air-calendar-request-board", schemaVersion: 2, ready: true, imagesReady: Boolean(env.BUCKET) }, 200, origin);
  const imageId = /^\/api\/images\/([a-f0-9]{48})$/.exec(path)?.[1];
  if (imageId && request.method === "GET") {
    const row = await db.prepare("SELECT object_key,content_type FROM board_images WHERE id=?").bind(imageId).first();
    if (!row) fail(404, "not_found"); if (!env.BUCKET) fail(503, "image_unavailable");
    const image = await env.BUCKET.get(row.object_key); if (!image) fail(404, "not_found");
    return new Response(image.body, { headers: { "Content-Type": row.content_type, "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; sandbox", "Content-Disposition": "inline", "Vary": "Origin", ...(origin ? { "Access-Control-Allow-Origin": origin } : {}) } });
  }
  if (path === "/api/requests" && request.method === "GET") {
    const category = url.searchParams.get("category") || "all", status = url.searchParams.get("status") || "all";
    const q = (url.searchParams.get("q") || "").trim().slice(0, 100);
    if (category !== "all" && !CATEGORIES.includes(category)) fail(400, "invalid_category");
    if (status !== "all" && !STATUSES.includes(status)) fail(400, "invalid_status");
    const page = Math.max(1, Math.min(10000, parseInt(url.searchParams.get("page") || "1", 10) || 1));
    const clauses = [], values = [];
    if (category !== "all") { clauses.push("category=?"); values.push(category); }
    if (status !== "all") { clauses.push("status=?"); values.push(status); }
    if (q) { clauses.push("(title LIKE ? ESCAPE '\\' OR body LIKE ? ESCAPE '\\')"); const escaped = `%${q.replace(/[\\%_]/g, "\\$&")}%`; values.push(escaped, escaped); }
    const where = clauses.length ? ` WHERE ${clauses.join(" AND ")}` : "";
    const results = await db.batch([
      db.prepare(`SELECT ${PUBLIC_COLUMNS} FROM board_requests${where} ORDER BY id DESC LIMIT 12 OFFSET ?`).bind(...values, (page - 1) * 12),
      db.prepare(`SELECT COUNT(*) AS total FROM board_requests${where}`).bind(...values),
      db.prepare("SELECT status,COUNT(*) AS count FROM board_requests GROUP BY status"),
    ]);
    const stats = Object.fromEntries(STATUSES.map((key) => [key, 0]));
    results[2].results.forEach((row) => { stats[row.status] = row.count; });
    return response({ items: await enrichPosts(db, results[0].results.map(publicPost)), total: results[1].results[0].total, page, pageSize: 12, stats }, 200, origin);
  }
  if (path === "/api/requests" && request.method === "POST") {
    const { data, images } = await contentInput(request), post = validatePost(data);
    await rateLimit(db, request, env, "create", 20, 3600);
    const previous = await repeatedPost(db, data.idempotencyKey, post, env, images);
    if (previous) return response({ item: previous }, 200, origin);
    const salt = randomHex(), digest = await passwordHash(post.password, salt, env.BOARD_PASSWORD_PEPPER), now = new Date().toISOString();
    const staged = await stageImages(env, images);
    try {
      await db.batch([
        db.prepare("INSERT INTO board_requests(title,body,nickname,category,app_version,platform,password_salt,password_hash,idempotency_key,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)")
          .bind(post.title, post.body, post.nickname, post.category, post.appVersion, post.platform, salt, digest, data.idempotencyKey, now, now),
        ...staged.map((image, index) => imageInsert(db, image, "(SELECT id FROM board_requests WHERE idempotency_key=?)", data.idempotencyKey, index)),
        ...staged.map(image => db.prepare("DELETE FROM board_image_cleanup WHERE object_key=?").bind(image.objectKey)),
      ]);
    } catch (error) {
      await discardStaged(env, staged);
      const duplicate = await repeatedPost(db, data.idempotencyKey, post, env, images);
      if (duplicate) return response({ item: duplicate }, 200, origin);
      throw error;
    }
    const inserted = await db.prepare(`SELECT ${PUBLIC_COLUMNS} FROM board_requests WHERE idempotency_key=?`).bind(data.idempotencyKey).first();
    return response({ item: (await enrichPosts(db, [publicPost(inserted)]))[0] }, 201, origin);
  }
  if (path === "/api/admin/login" && request.method === "POST") {
    await rateLimit(db, request, env, "admin-login", 8, 900);
    const data = await inputJson(request), password = field(data.password, 8, 128, "unauthorized");
    if (!equalSecret(await sha256(password), env.ADMIN_PASSWORD_HASH)) fail(401, "unauthorized");
    const token = randomHex(32), expiresAt = Date.now() + 3600000;
    await db.batch([
      db.prepare("DELETE FROM board_admin_sessions WHERE expires_at < ?").bind(Date.now()),
      db.prepare("INSERT INTO board_admin_sessions(token_hash,expires_at) VALUES(?,?)").bind(await sha256(token), expiresAt),
    ]);
    return response({ token, expiresAt }, 200, origin);
  }
  if (path === "/api/admin/logout" && request.method === "POST") {
    await authorizeAdmin(request, db);
    await db.prepare("DELETE FROM board_admin_sessions WHERE token_hash=?").bind(await sha256(request.headers.get("Authorization").slice(7))).run();
    return response({ ok: true }, 200, origin);
  }
  const adminId = /^\/api\/admin\/requests\/(\d+)$/.exec(path)?.[1];
  if (adminId && ["PATCH", "DELETE"].includes(request.method)) {
    await authorizeAdmin(request, db);
    await findPost(db, Number(adminId));
    if (request.method === "DELETE") {
      await deletePost(env, Number(adminId));
      return response({ ok: true }, 200, origin);
    }
    const data = await inputJson(request);
    if (!STATUSES.includes(data.status)) fail(400, "invalid_status");
    const reply = field(data.reply || "", 0, 3000, "invalid_reply");
    await db.prepare("UPDATE board_requests SET status=?,admin_reply=?,updated_at=?,revision=revision+1 WHERE id=?").bind(data.status, reply, new Date().toISOString(), Number(adminId)).run();
    return response({ item: await findPost(db, Number(adminId)) }, 200, origin);
  }
  const id = /^\/api\/requests\/(\d+)$/.exec(path)?.[1];
  if (id) {
    if (request.method === "GET") return response({ item: await findPost(db, Number(id)) }, 200, origin);
    if (["PATCH", "DELETE"].includes(request.method)) {
      await rateLimit(db, request, env, "edit-password", 30, 900);
      const row = await findPost(db, Number(id), true), { data, images } = await contentInput(request);
      const password = field(data.password, 8, 128, "invalid_password");
      if (!equalSecret(await passwordHash(password, row.password_salt, env.BOARD_PASSWORD_PEPPER), row.password_hash)) fail(403, "wrong_password");
      if (request.method === "DELETE") {
        await deletePost(env, Number(id));
        return response({ ok: true }, 200, origin);
      }
      const post = validatePost(data, true);
      if (row.revision !== data.revision) fail(409, "conflict");
      const current = await imageRows(db, Number(id)), removed = current.filter(image => post.removeImages.includes(image.id));
      if (removed.length !== post.removeImages.length) fail(400, "invalid_request");
      if (current.length - removed.length + images.length > IMAGE_COUNT) fail(400, "too_many_images");
      const staged = await stageImages(env, images), retained = current.filter(image => !post.removeImages.includes(image.id)), guard = randomHex();
      try {
        await db.batch([
          // A failed CHECK aborts the entire transaction before any image/content changes.
          db.prepare("INSERT INTO board_revision_guard(token,matches) VALUES(?,(SELECT COUNT(*) FROM board_requests WHERE id=? AND revision=?))").bind(guard, Number(id), data.revision),
          ...removed.map(image => db.prepare("INSERT OR REPLACE INTO board_image_cleanup(object_key,ready_at) VALUES(?,0)").bind(image.object_key)),
          ...removed.map(image => db.prepare("DELETE FROM board_images WHERE id=? AND request_id=?").bind(image.id, Number(id))),
          ...retained.map((image, index) => db.prepare("UPDATE board_images SET position=? WHERE id=?").bind(index, image.id)),
          ...staged.map((image, index) => imageInsert(db, image, "?", Number(id), retained.length + index)),
          ...staged.map(image => db.prepare("DELETE FROM board_image_cleanup WHERE object_key=?").bind(image.objectKey)),
          db.prepare("UPDATE board_requests SET title=?,body=?,nickname=?,category=?,app_version=?,platform=?,updated_at=?,revision=revision+1 WHERE id=? AND revision=?")
            .bind(post.title, post.body, post.nickname, post.category, post.appVersion, post.platform, new Date().toISOString(), Number(id), data.revision),
          db.prepare("DELETE FROM board_revision_guard WHERE token=?").bind(guard),
        ]);
      } catch (error) { await discardStaged(env, staged); const latest = await findPost(db, Number(id), true); if (latest.revision !== data.revision) fail(409, "conflict"); throw error; }
      await drainCleanup(env);
      return response({ item: await findPost(db, Number(id)) }, 200, origin);
    }
  }
  fail(404, "not_found");
}

export default {
  async fetch(request, env) {
    try { return await route(request, env); }
    catch (error) {
      const origin = request.headers.get("Origin"), allowed = origins(request, env).has(origin) ? origin : null;
      const known = error instanceof BoardError || error instanceof ImageError;
      return response({ error: known ? (error.code || error.message) : "unavailable" }, known ? error.status : 503, allowed, error.status === 429 ? { "Retry-After": "900" } : {});
    }
  },
};

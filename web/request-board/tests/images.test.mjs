import test from "node:test";
import assert from "node:assert/strict";
import worker, { sha256 } from "../src/worker.mjs";
import { inspectImage, IMAGE_LIMIT } from "../src/images.mjs";
import { database } from "../scripts/sqlite-adapter.mjs";
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aA1sAAAAASUVORK5CYII=", "base64");
async function fixture() {
  const objects = new Map();
  const BUCKET = { failPut: false, failDelete: false,
    async put(key, value) { objects.set(key, new Uint8Array(value)); if (this.failPut) throw new Error("Simulated upload failure after storage"); return { key }; },
    async get(key) { return objects.has(key) ? { body: objects.get(key) } : null; },
    async delete(keys) { if (this.failDelete) throw new Error("Simulated transient delete failure"); for (const key of Array.isArray(keys) ? keys : [keys]) objects.delete(key); },
  };
  const DB = database(), env = { DB, BUCKET, BOARD_PASSWORD_PEPPER: "image-test-pepper", ADMIN_PASSWORD_HASH: await sha256("image-test-admin") };
  const post = overrides => ({ title: "이미지 첨부 테스트", body: "오류가 발생하는 화면 이미지를 첨부합니다.", nickname: "테스터", category: "bug", password: "author-password", idempotencyKey: crypto.randomUUID(), ...overrides });
  async function send(path, method = "GET", data, files = [], token) {
    let body, headers = { Origin: "https://namer-kimhyojin.github.io", "CF-Connecting-IP": "198.51.100.30", ...(token ? { Authorization: `Bearer ${token}` } : {}) };
    if (files.length) { body = new FormData(); body.set("payload", JSON.stringify(data)); files.forEach(file => body.append("images", new Blob([file.bytes || PNG], { type: file.type || "image/png" }), "screenshot.png")); }
    else if (data) { body = JSON.stringify(data); headers["Content-Type"] = "application/json"; }
    const result = await worker.fetch(new Request(`https://board.example${path}`, { method, headers, ...(body ? { body } : {}) }), env);
    const image = (result.headers.get("Content-Type") || "").startsWith("image/");
    return { status: result.status, headers: result.headers, body: image ? new Uint8Array(await result.arrayBuffer()) : await result.json() };
  }
  return { DB, BUCKET, objects, env, post, send };
}
test("images persist with posts, retry is idempotent and public bytes match", async () => {
  const { send, post, objects } = await fixture(), payload = post();
  const created = await send("/api/requests", "POST", payload, [{}, {}]); assert.equal(created.status, 201);
  assert.equal(created.body.item.images.length, 2); assert.equal(objects.size, 2);
  const image = created.body.item.images[0]; assert.equal(image.width, 1); assert(!("object_key" in image));
  const original = await send(image.url); assert.equal(original.status, 200); assert.equal(original.headers.get("X-Content-Type-Options"), "nosniff"); assert.deepEqual(original.body, new Uint8Array(PNG));
  const retry = await send("/api/requests", "POST", payload, [{}, {}]); assert.equal(retry.status, 200); assert.equal(retry.body.item.id, created.body.item.id); assert.equal(objects.size, 2);
  assert.equal((await send("/api/requests", "POST", payload, [{}])).status, 409);
  assert.equal((await send("/api/requests")).body.items[0].images.length, 2);
});
test("author image replacement is password protected and deletion removes stored bytes", async () => {
  const { send, post, objects } = await fixture(); const created = (await send("/api/requests", "POST", post(), [{}])).body.item;
  const changes = post({ revision: 1, removeImages: [created.images[0].id] });
  assert.equal((await send(`/api/requests/${created.id}`, "PATCH", { ...changes, password: "wrong-password" }, [{}])).status, 403); assert.equal(objects.size, 1);
  const updated = await send(`/api/requests/${created.id}`, "PATCH", changes, [{}]); assert.equal(updated.status, 200); assert.equal(updated.body.item.revision, 2); assert.equal(objects.size, 1); assert.notEqual(updated.body.item.images[0].id, created.images[0].id);
  assert.equal((await send(created.images[0].url)).status, 404);
  assert.equal((await send(`/api/requests/${created.id}`, "DELETE", { password: "author-password" })).status, 200); assert.equal(objects.size, 0); assert.equal((await send(updated.body.item.images[0].url)).status, 404);
});
test("count, type, dimensions, size and foreign attachment removal are rejected", async () => {
  const { send, post, objects } = await fixture();
  assert.equal((await send("/api/requests", "POST", post(), [{}, {}, {}, {}])).body.error, "too_many_images");
  assert.equal((await send("/api/requests", "POST", post(), [{ bytes: Buffer.from("<svg onload='alert(1)'/>") }])).body.error, "invalid_image");
  assert.equal((await send("/api/requests", "POST", post(), [{ type: "image/jpeg" }])).body.error, "invalid_image");
  assert.equal((await send("/api/requests", "POST", post(), [{ bytes: Buffer.alloc(IMAGE_LIMIT + 1) }])).body.error, "image_too_large");
  const huge = Buffer.from(PNG); huge.writeUInt32BE(9000, 16); assert.throws(() => inspectImage(huge, "image/png"), /image_dimensions/);
  const one = (await send("/api/requests", "POST", post(), [{}, {}, {}])).body.item;
  const two = (await send("/api/requests", "POST", post(), [{}])).body.item;
  assert.equal((await send(`/api/requests/${one.id}`, "PATCH", post({ revision: 1 }), [{}])).body.error, "too_many_images");
  assert.equal((await send(`/api/requests/${one.id}`, "PATCH", post({ revision: 1, removeImages: [two.images[0].id] }))).status, 400); assert.equal(objects.size, 4);
});
test("concurrent edits reject stale revisions and roll back image changes", async () => {
  const { send, post, objects, DB } = await fixture(); const item = (await send("/api/requests", "POST", post())).body.item;
  const results = await Promise.all([send(`/api/requests/${item.id}`, "PATCH", post({ title: "첫 번째 동시 수정", revision: 1 }), [{}]), send(`/api/requests/${item.id}`, "PATCH", post({ title: "두 번째 동시 수정", revision: 1 }), [{}])]);
  assert.deepEqual(results.map(result => result.status).sort(), [200, 409]); assert.equal(objects.size, 1); assert.equal((await send(`/api/requests/${item.id}`)).body.item.images.length, 1); assert.equal(DB.sqlite.prepare("SELECT COUNT(*) AS total FROM board_revision_guard").get().total, 0);
});
test("failed uploads and interrupted cleanup recover without exposing orphaned bytes", async () => {
  const { send, post, objects, BUCKET, DB } = await fixture();
  BUCKET.failPut = true; const failed = await send("/api/requests", "POST", post(), [{}]); assert.equal(failed.status, 503); assert.equal(objects.size, 0); assert.equal((await send("/api/requests")).body.total, 0);
  BUCKET.failPut = false; const item = (await send("/api/requests", "POST", post(), [{}])).body.item;
  BUCKET.failDelete = true; assert.equal((await send(`/api/requests/${item.id}`, "DELETE", { password: "author-password" })).status, 200); assert.equal(objects.size, 1); assert.equal((await send(item.images[0].url)).status, 404); assert.equal(DB.sqlite.prepare("SELECT COUNT(*) AS total FROM board_image_cleanup").get().total, 1);
  BUCKET.failDelete = false; await send("/api/health"); assert.equal(objects.size, 0); assert.equal(DB.sqlite.prepare("SELECT COUNT(*) AS total FROM board_image_cleanup").get().total, 0);
});
test("administrator deletion removes images and missing bucket leaves text-only posts working", async () => {
  const { send, post, env, objects } = await fixture(); const item = (await send("/api/requests", "POST", post(), [{}])).body.item;
  const login = await send("/api/admin/login", "POST", { password: "image-test-admin" }); assert.equal((await send(`/api/admin/requests/${item.id}`, "DELETE", null, [], login.body.token)).status, 200); assert.equal(objects.size, 0);
  delete env.BUCKET; assert.equal((await send("/api/requests", "POST", post(), [{}])).body.error, "image_unavailable"); assert.equal((await send("/api/requests", "POST", post())).status, 201);
});

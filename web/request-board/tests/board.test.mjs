import test from "node:test";
import assert from "node:assert/strict";
import worker, { sha256 } from "../src/worker.mjs";
import { database } from "../scripts/sqlite-adapter.mjs";

const ORIGIN = "https://namer-kimhyojin.github.io";
async function fixture() {
  const DB = database();
  const env = { DB, BOARD_PASSWORD_PEPPER: "test-private-pepper", ADMIN_PASSWORD_HASH: await sha256("admin-password-for-tests") };
  const send = async (path = "/api/requests", method = "GET", data, headers = {}) => {
    const response = await worker.fetch(new Request(`https://board.example${path}`, { method, headers: { Origin: ORIGIN, "Content-Type": "application/json", "CF-Connecting-IP": "198.51.100.10", ...headers }, ...(data ? { body: JSON.stringify(data) } : {}) }), env);
    const body = response.status === 204 ? null : await response.json();
    return { status: response.status, headers: response.headers, body };
  };
  const post = (overrides = {}) => ({ title: "주간 보기 수정 요청", body: "주간 보기의 일정이 더 잘 보였으면 좋겠습니다.", nickname: "테스터", category: "ui", password: "author-password", appVersion: "3.7.8", platform: "Windows 11", idempotencyKey: crypto.randomUUID(), ...overrides });
  return { DB, env, send, post };
}

test("create/read/edit/delete persists in SQL and never exposes credentials", async () => {
  const { DB, send, post } = await fixture();
  const created = await send("/api/requests", "POST", post());
  assert.equal(created.status, 201);
  const item = created.body.item;
  assert.equal(item.status, "received");
  assert.equal(JSON.stringify(item).includes("password"), false);
  const row = DB.sqlite.prepare("SELECT * FROM board_requests").get();
  assert.notEqual(row.password_hash, "author-password");
  assert.equal(row.password_hash.length, 64);
  const wrong = await send(`/api/requests/${item.id}`, "DELETE", { password: "wrong-password" });
  assert.equal(wrong.status, 403);
  assert.equal((await send(`/api/requests/${item.id}`)).status, 200);
  const edited = await send(`/api/requests/${item.id}`, "PATCH", post({ title: "수정된 요청 제목", revision: item.revision }));
  assert.equal(edited.status, 200);
  assert.equal(edited.body.item.revision, 2);
  assert.equal((await send(`/api/requests/${item.id}`, "PATCH", post({ revision: 1 }))).status, 409);
  assert.equal((await send(`/api/requests/${item.id}`, "DELETE", { password: "author-password" })).status, 200);
  assert.equal((await send(`/api/requests/${item.id}`)).status, 404);
  assert.equal((await send()).body.total, 0);
});

test("admin sessions protect status/reply updates and logout revokes access", async () => {
  const { send, post } = await fixture();
  const { item } = (await send("/api/requests", "POST", post())).body;
  const route = `/api/admin/requests/${item.id}`;
  assert.equal((await send(route, "PATCH", { status: "done", reply: "반영" })).status, 401);
  assert.equal((await send("/api/admin/login", "POST", { password: "wrong-admin-password" })).status, 401);
  const login = await send("/api/admin/login", "POST", { password: "admin-password-for-tests" });
  assert.equal(login.status, 200);
  const authorization = { Authorization: `Bearer ${login.body.token}` };
  const updated = await send(route, "PATCH", { status: "reviewing", reply: "확인하고 있습니다." }, authorization);
  assert.equal(updated.status, 200);
  assert.equal(updated.body.item.admin_reply, "확인하고 있습니다.");
  assert.equal((await send(`/api/requests/${item.id}`, "PATCH", post({ revision: 2, status: "done" }))).status, 400);
  assert.equal((await send("/api/admin/logout", "POST", {}, authorization)).status, 200);
  assert.equal((await send(route, "DELETE", {}, authorization)).status, 401);
});

test("filters, pagination, literal wildcards and SQL-like input behave correctly", async () => {
  const { DB, send, post } = await fixture();
  await send("/api/requests", "POST", post({ title: "크기를 50% 조절하면 발생하는 오류", category: "bug" }));
  await send("/api/requests", "POST", post({ title: "색상 선택 기능을 제안합니다.", category: "feature" }));
  assert.equal((await send("/api/requests?category=bug")).body.total, 1);
  assert.equal((await send("/api/requests?q=50%25")).body.total, 1);
  assert.equal((await send("/api/requests?q=%25")).body.total, 1);
  assert.equal((await send("/api/requests?q=%27%20OR%201%3D1--")).body.total, 0);
  assert.equal((await send("/api/requests?category=invalid")).status, 400);
  DB.sqlite.prepare("UPDATE board_requests SET status='done' WHERE category='bug'").run();
  const results = (await send()).body;
  assert.equal(results.stats.done, 1);
  assert.equal((await send("/api/requests?page=2")).body.items.length, 0);
});

test("idempotent retry does not create duplicate records", async () => {
  const { send, post } = await fixture(); const input = post();
  const first = await send("/api/requests", "POST", input);
  const retry = await send("/api/requests", "POST", input);
  assert.equal(first.body.item.id, retry.body.item.id);
  assert.equal((await send()).body.total, 1);
  assert.equal((await send("/api/requests", "POST", { ...input, body: "다른 내용으로 동일한 키를 재사용합니다." })).status, 409);
});

test("origin, content type, payload size, weak passwords and spam traps are rejected", async () => {
  const { send, post, env } = await fixture();
  assert.equal((await send("/api/requests", "POST", post(), { Origin: "https://evil.example" })).status, 403);
  const preflight = await send("/api/requests", "OPTIONS");
  assert.equal(preflight.status, 204);
  assert.equal(preflight.headers.get("Access-Control-Allow-Origin"), ORIGIN);
  assert.equal((await send("/api/requests", "POST", post(), { "Content-Type": "text/plain" })).status, 415);
  assert.equal((await send("/api/requests", "POST", post({ password: "short" }))).status, 400);
  assert.equal((await send("/api/requests", "POST", post({ website: "spam.example" }))).status, 400);
  assert.equal((await send("/api/requests", "POST", post({ body: "a".repeat(40000) }))).status, 413);
  delete env.BOARD_PASSWORD_PEPPER;
  assert.equal((await send()).status, 503);
});

test("password retries are throttled with a durable SQL counter", async () => {
  const { send, post } = await fixture();
  const id = (await send("/api/requests", "POST", post())).body.item.id;
  for (let attempt = 0; attempt < 30; attempt++) assert.equal((await send(`/api/requests/${id}`, "DELETE", { password: "wrong-password" })).status, 403);
  const blocked = await send(`/api/requests/${id}`, "DELETE", { password: "author-password" });
  assert.equal(blocked.status, 429);
  assert.equal(blocked.headers.get("Retry-After"), "900");
});

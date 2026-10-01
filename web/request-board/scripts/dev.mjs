import { createServer } from "node:http";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import worker, { sha256 } from "../src/worker.mjs";
import { database } from "./sqlite-adapter.mjs";
import { localBucket } from "./local-bucket.mjs";
await mkdir(new URL("../.local/", import.meta.url), { recursive: true });
const env = { DB: database(fileURLToPath(new URL("../.local/board.db", import.meta.url))), BUCKET: localBucket(new URL("../.local/images/", import.meta.url)), DEV_MODE: "true", BOARD_PASSWORD_PEPPER: "local-development-only-pepper", ADMIN_PASSWORD_HASH: await sha256("development-admin-only") };
const port = Number(process.env.PORT || 8787);
createServer(async (incoming, outgoing) => {
  const chunks = []; for await (const chunk of incoming) chunks.push(chunk);
  const headers = new Headers(incoming.headers);
  headers.set("CF-Connecting-IP", incoming.socket.remoteAddress || "127.0.0.1");
  const body = Buffer.concat(chunks);
  const request = new Request(`http://127.0.0.1:${port}${incoming.url}`, { method: incoming.method, headers, ...(["GET", "HEAD"].includes(incoming.method) ? {} : { body }) });
  const result = await worker.fetch(request, env);
  outgoing.writeHead(result.status, Object.fromEntries(result.headers)); outgoing.end(Buffer.from(await result.arrayBuffer()));
}).listen(port, "127.0.0.1", () => console.log(`Local board API listening on http://127.0.0.1:${port}`));

import { mkdir, readFile, writeFile } from "node:fs/promises";
import { SCHEMA } from "../src/schema.mjs";
const source = await readFile(new URL("../src/worker.mjs", import.meta.url), "utf8");
const output = source.replace('import { SCHEMA } from "./schema.mjs";', `const SCHEMA = ${JSON.stringify(SCHEMA)};`);
const directory = new URL("../dist/server/", import.meta.url);
await mkdir(directory, { recursive: true });
await writeFile(new URL("index.js", directory), output, "utf8");
await writeFile(new URL("wrangler.json", directory), JSON.stringify({ name: "air-calendar-request-board", main: "index.js", compatibility_date: "2026-10-01" }, null, 2) + "\n", "utf8");
console.log("Built dist/server/index.js");

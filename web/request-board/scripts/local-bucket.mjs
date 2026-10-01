import { mkdir, readFile, writeFile, unlink } from "node:fs/promises";
import { createHash } from "node:crypto";
export function localBucket(directory) {
  const path = key => new URL(createHash("sha256").update(key).digest("hex") + ".blob", directory);
  return {
    async put(key, bytes) { await mkdir(directory, { recursive: true }); await writeFile(path(key), bytes); return { key, size: bytes.length }; },
    async get(key) { try { const bytes = await readFile(path(key)); return { body: bytes }; } catch (error) { if (error.code === "ENOENT") return null; throw error; } },
    async delete(keys) { for (const key of Array.isArray(keys) ? keys : [keys]) { try { await unlink(path(key)); } catch (error) { if (error.code !== "ENOENT") throw error; } } },
  };
}

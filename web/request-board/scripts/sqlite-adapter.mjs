import { DatabaseSync } from "node:sqlite";

export function database(path = ":memory:") {
  const sqlite = new DatabaseSync(path);
  class Statement {
    constructor(sql, values = []) { this.sql = sql; this.values = values; }
    bind(...values) { return new Statement(this.sql, values); }
    async first() { return sqlite.prepare(this.sql).get(...this.values) || null; }
    async all() { return { success: true, results: sqlite.prepare(this.sql).all(...this.values) }; }
    async run() {
      const result = sqlite.prepare(this.sql).run(...this.values);
      return { success: true, meta: { changes: Number(result.changes), last_row_id: Number(result.lastInsertRowid) } };
    }
    execute() {
      const statement = sqlite.prepare(this.sql);
      const results = statement.all(...this.values);
      return { success: true, results, meta: { changes: Number(sqlite.prepare("SELECT changes() AS count").get().count) } };
    }
  }
  return {
    sqlite,
    prepare: (sql) => new Statement(sql),
    async batch(statements) {
      sqlite.exec("BEGIN");
      try { const results = statements.map((statement) => statement.execute()); sqlite.exec("COMMIT"); return results; }
      catch (error) { sqlite.exec("ROLLBACK"); throw error; }
    },
  };
}

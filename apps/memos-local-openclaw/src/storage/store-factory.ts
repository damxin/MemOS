import { SqliteStore } from "./sqlite";
import { PostgresStore } from "./postgres";
import type { MemosLocalConfig, Logger } from "../types";
import * as path from "path";

export type StorageStore = SqliteStore | PostgresStore;

export interface StorageOptions {
  dbPath?: string;
  databaseUrl?: string;
  pgSchema?: string;
}

export async function createStore(
  config: StorageOptions,
  log: Logger,
  stateDir: string
): Promise<StorageStore> {
  if (config.databaseUrl) {
    // Use PostgreSQL
    log.info(`[store-factory] Creating PostgreSQL store (schema: ${config.pgSchema ?? "public"})`);
    const store = new PostgresStore(config.databaseUrl, log, config.pgSchema);
    await store.initialize();
    return store;
  }

  // Fall back to SQLite
  const dbPath = config.dbPath ?? path.join(stateDir, "memos-local", "memos.db");
  log.info(`[store-factory] Creating SQLite store at: ${dbPath}`);
  return new SqliteStore(dbPath, log);
}

export function isPostgresStore(store: StorageStore): store is PostgresStore {
  return store instanceof PostgresStore;
}

export function isSqliteStore(store: StorageStore): store is SqliteStore {
  return store instanceof SqliteStore;
}

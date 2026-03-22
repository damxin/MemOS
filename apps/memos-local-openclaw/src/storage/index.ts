/**
 * Storage module re-exports
 *
 * For direct usage:
 * - SQLite: `import { SqliteStore } from "./sqlite"`
 * - PostgreSQL: `import { PostgresStore } from "./postgres"`
 * - Factory (auto-select based on config): `import { createStore } from "./store-factory"`
 */
export { SqliteStore } from "./sqlite";
export { PostgresStore } from "./postgres";
export { createStore, isPostgresStore, isSqliteStore, type StorageStore, type StorageOptions } from "./store-factory";

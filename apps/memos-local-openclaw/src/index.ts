import { v4 as uuid } from "uuid";
import { buildContext } from "./config";
import { ensureSqliteBinding } from "./storage/ensure-binding";
import { isPostgresStore } from "./storage/store-factory";
import { SqliteStore } from "./storage/sqlite";
import { PostgresStore } from "./storage/postgres";
import { Embedder } from "./embedding";
import { IngestWorker } from "./ingest/worker";
import { RecallEngine } from "./recall/engine";
import { captureMessages } from "./capture";
import { createMemorySearchTool, createMemoryTimelineTool, createMemoryGetTool } from "./tools";
import type { MemosLocalConfig, ToolDefinition, Logger } from "./types";

export interface MemosLocalPlugin {
  id: string;
  tools: ToolDefinition[];
  onConversationTurn: (messages: Array<{ role: string; content: string }>, sessionKey?: string, owner?: string) => void;
  /** Wait for all pending ingest operations to complete. */
  flush: () => Promise<void>;
  shutdown: () => Promise<void>;
}

export interface PluginInitOptions {
  stateDir?: string;
  workspaceDir?: string;
  config?: Partial<MemosLocalConfig>;
  log?: Logger;
}

/**
 * Initialize the memos-local plugin.
 *
 * Typical usage inside OpenClaw plugin lifecycle:
 *
 * ```ts
 * import { initPlugin } from "@memos/local-openclaw";
 *
 * export default function activate(ctx) {
 *   const plugin = initPlugin({
 *     stateDir: ctx.stateDir,
 *     workspaceDir: ctx.workspaceDir,
 *     config: ctx.pluginConfig,
 *     log: ctx.log,
 *   });
 *   ctx.registerTools(plugin.tools);
 *   ctx.onConversationTurn((msgs, session) => {
 *     plugin.onConversationTurn(msgs, session);
 *   });
 *   ctx.onDeactivate(() => plugin.shutdown());
 * }
 * ```
 */
export function initPlugin(opts: PluginInitOptions = {}): MemosLocalPlugin {
  const stateDir = opts.stateDir ?? defaultStateDir();
  const workspaceDir = opts.workspaceDir ?? process.cwd();
  const ctx = buildContext(stateDir, workspaceDir, opts.config, opts.log);

  ctx.log.info("Initializing memos-local plugin...");

  // Only ensure SQLite binding when using SQLite (not PostgreSQL)
  if (!ctx.config.storage?.databaseUrl) {
    ensureSqliteBinding(ctx.log);
  }

  const store = createStoreSync(ctx.config.storage!, ctx.log, stateDir);
  const embedder = new Embedder(ctx.config.embedding, ctx.log);
  
  // Use type assertion since both SqliteStore and PostgresStore implement the same interface
  // The consumer classes (IngestWorker, RecallEngine, tools) expect SqliteStore but we support both
  const worker = new IngestWorker(store as unknown as SqliteStore, embedder, ctx);
  const engine = new RecallEngine(store as unknown as SqliteStore, embedder, ctx);

  const tools: ToolDefinition[] = [
    createMemorySearchTool(engine),
    createMemoryTimelineTool(store as unknown as SqliteStore),
    createMemoryGetTool(store as unknown as SqliteStore),
  ];

  const dbInfo = ctx.config.storage?.databaseUrl
    ? `PostgreSQL (${ctx.config.storage.databaseUrl.replace(/\/\/.*:.*@/, "//***@")})`
    : `SQLite (${ctx.config.storage?.dbPath})`;
  ctx.log.info(`Plugin ready. DB: ${dbInfo}, Embedding: ${embedder.provider}`);

  return {
    id: "memos-local",

    tools,

    onConversationTurn(
      messages: Array<{ role: string; content: string }>,
      sessionKey?: string,
      owner?: string,
    ): void {
      const session = sessionKey ?? "default";
      const turnId = uuid();
      const tag = ctx.config.capture?.evidenceWrapperTag ?? "STORED_MEMORY";

      const captured = captureMessages(messages, session, turnId, tag, ctx.log, owner);
      if (captured.length > 0) {
        worker.enqueue(captured);
      }
    },

    async flush(): Promise<void> {
      await worker.flush();
    },

    async shutdown(): Promise<void> {
      ctx.log.info("Shutting down memos-local plugin...");
      await worker.flush();
      if (isPostgresStore(store)) {
        await store.close();
      } else {
        store.close();
      }
    },
  };
}

/**
 * Synchronous store creation for SQLite.
 * PostgreSQL store creation is async, but we handle it via initialization check.
 */
function createStoreSync(storage: MemosLocalConfig["storage"], log: Logger, stateDir: string): SqliteStore | PostgresStore {
  if (storage?.databaseUrl) {
    // For PostgreSQL, we create the store but it needs async initialization
    // The initialization is done lazily on first use
    // This is a simplification - in production you'd want proper async init
    log.info("[store-factory] PostgreSQL store created (async init deferred)");
    const store = new PostgresStore(storage.databaseUrl, log, storage.pgSchema);
    // Initialize asynchronously in background
    store.initialize().catch((err: Error) => {
      log.error("[store-factory] PostgreSQL init failed:", err);
    });
    return store;
  }

  // SQLite is synchronous
  const dbPath = storage?.dbPath ?? `${stateDir}/memos-local/memos.db`;
  log.info(`[store-factory] Creating SQLite store at: ${dbPath}`);
  return new SqliteStore(dbPath, log);
}

function defaultStateDir(): string {
  const home = process.env.HOME ?? process.env.USERPROFILE ?? "/tmp";
  return `${home}/.openclaw`;
}

// Re-export types for consumers
export type { MemosLocalConfig, ToolDefinition, SearchResult, SearchHit, TimelineResult, GetResult } from "./types";

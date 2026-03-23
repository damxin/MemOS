# memos-local-openclaw PostgreSQL 支持完整方案

## 1. 现状分析

### 当前架构
```
index.ts
  └── new SqliteStore(dbPath, log)     ← 硬编码 SQLite
       ├── better-sqlite3              ← SQLite 驱动
       ├── FTS5 (trigram)             ← 全文搜索
       └── 内存向量搜索                 ← 暴力余弦相似度
```

### SqliteStore 核心功能 (1596 行)
| 模块 | 主要方法 | 技术实现 |
|------|---------|---------|
| **Chunks** | `addChunk`, `getChunk`, `ftsSearch`, `getNeighborChunks` | SQLite + FTS5 |
| **Embeddings** | `addEmbedding`, `getAllEmbeddings`, `vectorSearch` | SQLite BLOB + 内存计算 |
| **Tasks** | `addTask`, `getTask`, `getTasksBySkillStatus` | SQLite |
| **Skills** | `addSkill`, `getSkill`, `searchSkills`, `getSkillEmbeddings` | SQLite + FTS |
| **API Logs** | `recordApiLog`, `getApiLogs` | SQLite |
| **Deduplication** | `markDedupStatus`, `recordMergeHit` | SQLite |
| **Migrations** | `migrate()` (20+ 次迁移) | ALTER TABLE |

### 当前配置
```typescript
// config.ts
storage: {
  dbPath: string  // SQLite 文件路径
}
```

---

## 2. 目标架构

```
┌─────────────────────────────────────────────────────────────┐
│                        index.ts                             │
│                   (无需修改调用方)                           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    StorageBackend                            │
│                    (接口抽象层)                              │
├─────────────────────────────────────────────────────────────┤
│  + addChunk()        + getChunk()         + ftsSearch()    │
│  + addEmbedding()    + vectorSearch()     + addTask()      │
│  + addSkill()        + searchSkills()     + migrate()      │
│  + ... (所有公共方法)                                      │
└─────────────────────────────────────────────────────────────┘
                    │                       │
          ┌─────────┴─────────┐   ┌────────┴────────┐
          ▼                   ▼                   ▼
   ┌─────────────┐    ┌─────────────┐   ┌─────────────────┐
   │ SqliteStore │    │ PostgresStore│   │ FutureBackends  │
   │  (保留)      │    │   (新增)     │   │                 │
   └─────────────┘    └─────────────┘   └─────────────────┘
```

---

## 3. 接口设计

### 3.1 StorageBackend 接口

```typescript
// src/storage/base.ts

import type {
  Chunk, ChunkRef, Task, TaskStatus,
  Skill, SkillVisibility, SkillVersion,
  SearchHit, SkillSearchHit, VectorHit,
  Logger, TimelineEntry
} from "../types";

export interface StorageConfig {
  type: "sqlite" | "postgres";
}

export interface SqliteConfig extends StorageConfig {
  type: "sqlite";
  dbPath: string;
}

export interface PostgresConfig extends StorageConfig {
  type: "postgres";
  host: string;
  port: number;
  database: string;
  user: string;
  password: string;
  ssl?: boolean;
}

export type StorageBackendConfig = SqliteConfig | PostgresConfig;

export interface SearchOptions {
  ownerFilter?: string[];   // 记忆隔离
  limit?: number;
  offset?: number;
  scope?: "self" | "public" | "mix";  // 技能搜索范围
}

export interface VectorSearchOptions extends SearchOptions {
  topK: number;
  queryVector: number[];
  maxChunks?: number;  // 限制搜索范围
}

export interface StorageBackend {
  /** 初始化/迁移 */
  migrate(): void;
  close(): Promise<void>;

  // ─── Chunks ───────────────────────────────────────
  addChunk(chunk: Omit<Chunk, "id">, owner: string): string;
  getChunk(chunkId: string): Chunk | null;
  getChunkForOwners(chunkId: string, owners: string[]): Chunk | null;
  getChunksByRef(ref: ChunkRef, owners?: string[]): Chunk | null;
  getNeighborChunks(sessionKey: string, turnId: string, seq: number, window: number, owners?: string[]): Chunk[];
  ftsSearch(query: string, limit: number, owners?: string[]): Array<{ chunkId: string; score: number }>;
  updateChunkSummaryAndContent(chunkId: string, summary: string, appendContent: string): void;

  // ─── Embeddings ────────────────────────────────────
  addEmbedding(chunkId: string, vector: number[], dimensions: number): void;
  getChunkEmbedding(chunkId: string): { vector: number[]; dimensions: number } | null;
  getAllEmbeddings(owners?: string[]): Array<{ chunkId: string; vector: number[] }>;
  getRecentEmbeddings(maxChunks: number, owners?: string[]): Array<{ chunkId: string; vector: number[] }>;
  vectorSearch(queryVec: number[], topK: number, maxChunks?: number, owners?: string[]): VectorHit[];
  deleteStaleEmbeddings(beforeTimestamp: number): number;

  // ─── Tasks ─────────────────────────────────────────
  addTask(task: Omit<Task, "id">, owner: string): string;
  getTask(taskId: string): Task | null;
  getTasks(limit: number, offset: number, status?: TaskStatus, owner?: string): Task[];
  updateTaskStatus(taskId: string, status: TaskStatus, endedAt?: number): void;
  getTasksBySkillStatus(statuses: string[]): Task[];
  setTaskSkillMeta(taskId: string, meta: { skillStatus: string; skillReason: string }): void;
  getTasksByChunk(chunkId: string): Task[];

  // ─── Skills ────────────────────────────────────────
  addSkill(skill: Omit<Skill, "id" | "createdAt" | "updatedAt">, owner: string): string;
  getSkill(skillId: string): Skill | null;
  getSkillByName(name: string): Skill | null;
  updateSkill(skillId: string, updates: Partial<Skill>): void;
  deleteSkill(skillId: string): void;
  archiveSkill(skillId: string): void;
  searchSkills(query: string, limit: number, scope: "self" | "public" | "mix", owner: string): SkillSearchHit[];
  getSkillEmbedding(skillId: string): number[] | null;
  getSkillEmbeddings(scope: "self" | "public" | "mix", owner: string): Array<{ skillId: string; vector: number[] }>;
  skillFtsSearch(query: string, limit: number, scope: "self" | "public" | "mix", owner: string): Array<{ skillId: string; score: number }>;
  addSkillVersion(skillId: string, version: Omit<SkillVersion, "skillId">): void;
  getSkillVersions(skillId: string): SkillVersion[];
  getSkillVersion(skillId: string, version: number): SkillVersion | null;
  getLatestSkillVersion(skillId: string): SkillVersion | null;

  // ─── Timeline ──────────────────────────────────────
  getTimeline(limit: number, owners?: string[]): TimelineEntry[];

  // ─── Dedup ────────────────────────────────────────
  markDedupStatus(chunkId: string, status: "duplicate" | "merged", targetChunkId: string | null, reason: string): void;
  getDedupCandidates(hash: string, threshold: number): Chunk[];
  recordMergeHit(chunkId: string, action: "DUPLICATE" | "UPDATE", reason: string, oldSummary?: string, newSummary?: string): void;

  // ─── API Logs ──────────────────────────────────────
  recordApiLog(toolName: string, input: unknown, output: string, durationMs: number, success: boolean): void;
  getApiLogs(limit?: number, offset?: number, toolFilter?: string): {
    logs: Array<{ id: number; toolName: string; input: string; output: string; durationMs: number; success: boolean; calledAt: number }>;
    total: number;
  };
  getApiLogToolNames(): string[];

  // ─── 管理 ──────────────────────────────────────────
  getStats(): {
    chunkCount: number;
    taskCount: number;
    skillCount: number;
    embeddingCount: number;
  };
}
```

### 3.2 向量搜索接口（可插拔）

```typescript
// src/storage/vector-backend.ts

export interface VectorSearchResult {
  chunkId: string;
  score: number;
}

export interface VectorBackend {
  /** 初始化向量存储 */
  initialize(dimensions: number): Promise<void>;

  /** 批量插入向量 */
  upsertVectors(items: Array<{ id: string; vector: number[]; metadata?: Record<string, unknown> }>): Promise<void>;

  /** 向量相似度搜索 */
  search(queryVector: number[], topK: number, filter?: Record<string, unknown>): Promise<VectorSearchResult[]>;

  /** 删除向量 */
  deleteVectors(ids: string[]): Promise<void>;

  /** 关闭连接 */
  close(): Promise<void>;
}

// 内置实现
export class InMemoryVectorBackend implements VectorBackend { ... }     // 当前暴力搜索
export class PgVectorBackend implements VectorBackend { ... }          // 新增 pgvector
export class QdrantBackend implements VectorBackend { ... }             // 未来扩展
```

---

## 4. PostgreSQL 实现细节

### 4.1 数据库 Schema

```sql
-- Chunks 表
CREATE TABLE chunks (
  id          TEXT PRIMARY KEY,
  session_key TEXT NOT NULL,
  turn_id     TEXT NOT NULL,
  seq         INTEGER NOT NULL,
  role        TEXT NOT NULL,
  content     TEXT NOT NULL,
  kind        TEXT NOT NULL DEFAULT 'paragraph',
  summary     TEXT NOT NULL DEFAULT '',
  task_id     TEXT,
  content_hash TEXT,
  owner       TEXT NOT NULL DEFAULT 'agent:main',
  dedup_status TEXT DEFAULT 'active',
  dedup_target TEXT,
  dedup_reason TEXT,
  created_at  INTEGER NOT NULL,
  updated_at  INTEGER NOT NULL
);

-- 索引
CREATE INDEX idx_chunks_session ON chunks(session_key);
CREATE INDEX idx_chunks_owner ON chunks(owner);           -- 多智能体隔离
CREATE INDEX idx_chunks_task ON chunks(task_id);
CREATE INDEX idx_chunks_created ON chunks(created_at);

-- FTS 全文搜索 (使用 pg_trgm + GIN)
CREATE INDEX idx_chunks_fts ON chunks USING GIN (summary gin_trgm_ops, content gin_trgm_ops);

-- Embeddings 表 (使用 pgvector)
CREATE TABLE embeddings (
  chunk_id    TEXT PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
  vector      VECTOR(dimensions) NOT NULL,  -- pgvector 类型
  dimensions  INTEGER NOT NULL,
  updated_at  INTEGER NOT NULL
);

-- 向量索引 (HNSW - 高性能ANN)
CREATE INDEX idx_embeddings_hnsw ON embeddings USING HNSW (vector vector_cosine_ops);

-- Tasks 表
CREATE TABLE tasks (
  id           TEXT PRIMARY KEY,
  session_key  TEXT NOT NULL,
  title        TEXT NOT NULL DEFAULT '',
  summary      TEXT NOT NULL DEFAULT '',
  status       TEXT NOT NULL DEFAULT 'active',
  skill_status TEXT,
  skill_reason TEXT,
  owner        TEXT NOT NULL DEFAULT 'agent:main',
  started_at   INTEGER NOT NULL,
  ended_at     INTEGER,
  updated_at   INTEGER NOT NULL
);

CREATE INDEX idx_tasks_owner ON tasks(owner);
CREATE INDEX idx_tasks_status ON tasks(status);

-- Skills 表
CREATE TABLE skills (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL UNIQUE,
  title         TEXT NOT NULL,
  content       TEXT NOT NULL,
  guide         TEXT,
  visibility    TEXT NOT NULL DEFAULT 'private',  -- 'private' | 'public'
  status        TEXT NOT NULL DEFAULT 'draft',
  quality_score REAL,
  owner         TEXT NOT NULL DEFAULT 'agent:main',
  created_at    INTEGER NOT NULL,
  updated_at    INTEGER NOT NULL
);

CREATE INDEX idx_skills_owner ON skills(owner);
CREATE INDEX idx_skills_visibility ON skills(visibility);  -- 共享技能查询
CREATE INDEX idx_skills_fts ON skills USING GIN (title gin_trgm_ops, content gin_trgm_ops);

-- Skill Versions 表
CREATE TABLE skill_versions (
  skill_id       TEXT REFERENCES skills(id) ON DELETE CASCADE,
  version        INTEGER NOT NULL,
  content        TEXT NOT NULL,
  guide          TEXT,
  change_summary TEXT,
  quality_score  REAL,
  created_at     INTEGER NOT NULL,
  PRIMARY KEY (skill_id, version)
);

-- Skill Embeddings
CREATE TABLE skill_embeddings (
  skill_id    TEXT REFERENCES skills(id) ON DELETE CASCADE,
  version     INTEGER NOT NULL,
  vector      VECTOR(dimensions) NOT NULL,
  dimensions  INTEGER NOT NULL,
  updated_at  INTEGER NOT NULL,
  PRIMARY KEY (skill_id, version)
);

CREATE INDEX idx_skill_embeddings_hnsw ON skill_embeddings USING HNSW (vector vector_cosine_ops);

-- API Logs 表
CREATE TABLE api_logs (
  id          SERIAL PRIMARY KEY,
  tool_name   TEXT NOT NULL,
  input_data  TEXT,
  output_data TEXT,
  duration_ms INTEGER NOT NULL,
  success     INTEGER NOT NULL DEFAULT 1,
  called_at   INTEGER NOT NULL
);

CREATE INDEX idx_api_logs_tool ON api_logs(tool_name);
CREATE INDEX idx_api_logs_called ON api_logs(called_at);

-- Merge History 表
CREATE TABLE merge_history (
  id            SERIAL PRIMARY KEY,
  chunk_id      TEXT NOT NULL,
  action        TEXT NOT NULL,  -- 'DUPLICATE' | 'UPDATE'
  reason        TEXT,
  old_summary   TEXT,
  new_summary   TEXT,
  at            INTEGER NOT NULL
);

-- Viewer Events 表
CREATE TABLE viewer_events (
  id          SERIAL PRIMARY KEY,
  event_type  TEXT NOT NULL,
  created_at  INTEGER NOT NULL
);

CREATE INDEX idx_viewer_events_created ON viewer_events(created_at);
CREATE INDEX idx_viewer_events_type ON viewer_events(event_type);
```

### 4.2 全文搜索实现

**方案 A: pg_trgm (推荐)**
```sql
-- 启用扩展
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 相似度搜索
SELECT id, similarity(content, 'query') AS score
FROM chunks
WHERE content % 'query'  -- trigram 相似度
ORDER BY score DESC
LIMIT 20;
```

**方案 B: tsvector (可选扩展)**
```sql
-- 适用于结构化文本
ALTER TABLE chunks ADD COLUMN search_vector tsvector
  GENERATED ALWAYS AS (to_tsvector('simple', summary || ' ' || content)) STORED;
CREATE INDEX idx_chunks_ts ON chunks USING GIN(search_vector);
```

### 4.3 向量搜索实现 (pgvector)

```typescript
// src/storage/postgres/pgvector-backend.ts

import { Pool } from "pg";
import type { VectorBackend } from "../vector-backend";
import type { VectorSearchResult } from "../vector-backend";

export class PgVectorBackend implements VectorBackend {
  private pool: Pool;
  private dimensions: number;

  constructor(config: {
    host: string;
    port: number;
    database: string;
    user: string;
    password: string;
  }) {
    this.pool = new Pool(config);
    this.dimensions = 0; // 动态获取
  }

  async initialize(dimensions: number): Promise<void> {
    this.dimensions = dimensions;
    // 启用 pgvector 扩展
    await this.pool.query(`CREATE EXTENSION IF NOT EXISTS vector`);
  }

  async upsertVectors(items: Array<{ id: string; vector: number[] }>): Promise<void> {
    const values = items.map(({ id, vector }) =>
      `('${id}', '[${vector.join(",")}]'::vector)`).join(",");

    await this.pool.query(`
      INSERT INTO embeddings (chunk_id, vector, dimensions, updated_at)
      VALUES ${values}
      ON CONFLICT (chunk_id) DO UPDATE SET
        vector = EXCLUDED.vector,
        updated_at = EXCLUDED.updated_at
    `);
  }

  async search(
    queryVector: number[],
    topK: number,
    filter?: Record<string, unknown>
  ): Promise<VectorSearchResult[]> {
    const filterClause = filter?.owner
      ? `AND e.chunk_id IN (SELECT id FROM chunks WHERE owner = '${filter.owner}')`
      : "";

    const result = await this.pool.query(`
      SELECT e.chunk_id, (e.vector <=> $1::vector) AS similarity
      FROM embeddings e
      JOIN chunks c ON c.id = e.chunk_id
      WHERE 1=1 ${filterClause}
      ORDER BY e.vector <=> $1::vector
      LIMIT ${topK}
    `, [`[${queryVector.join(",")}]`]);

    return result.rows.map(row => ({
      chunkId: row.chunk_id,
      score: 1 - parseFloat(row.similarity), // 转换为相似度 (pgvector 返回距离)
    }));
  }

  async close(): Promise<void> {
    await this.pool.end();
  }
}
```

---

## 5. 配置修改

### 5.1 新配置结构

```typescript
// src/types.ts

export interface StorageConfigBase {
  // 公共配置
}

export interface SqliteStorageConfig extends StorageConfigBase {
  type: "sqlite";
  dbPath: string;
}

export interface PostgresStorageConfig extends StorageConfigBase {
  type: "postgres";
  host: string;
  port: number;
  database: string;
  username: string;    // 注意：不用 user，避免与 User 类型冲突
  password: string;
  ssl?: boolean;
  poolSize?: number;   // 连接池大小
  dimensions?: number; // 向量维度，默认 1024
}

export type StorageConfig = SqliteStorageConfig | PostgresStorageConfig;

export interface MemosLocalConfig {
  storage: StorageConfig;  // 修改点：原来是 { dbPath: string }
  // ... 其他配置不变
}
```

### 5.2 配置解析修改

```typescript
// src/config.ts

export function resolveConfig(raw: Partial<MemosLocalConfig> | undefined, stateDir: string): MemosLocalConfig {
  const storage = raw?.storage;

  let resolvedStorage: StorageConfig;
  if (!storage) {
    // 默认 SQLite
    resolvedStorage = {
      type: "sqlite",
      dbPath: path.join(stateDir, "memos-local", "memos.db"),
    };
  } else if (storage.type === "postgres") {
    resolvedStorage = {
      type: "postgres",
      host: storage.host,
      port: storage.port ?? 5432,
      database: storage.database,
      username: storage.username,
      password: storage.password,
      ssl: storage.ssl ?? false,
      poolSize: storage.poolSize ?? 10,
      dimensions: storage.dimensions ?? 1024,
    };
  } else {
    // SQLite (向后兼容)
    resolvedStorage = {
      type: "sqlite",
      dbPath: (storage as SqliteStorageConfig).dbPath
        ?? path.join(stateDir, "memos-local", "memos.db"),
    };
  }

  return {
    ...cfg,
    storage: resolvedStorage,
    // ... 其他配置
  };
}
```

---

## 6. 工厂模式创建 Store

```typescript
// src/storage/factory.ts

import type { StorageBackend, StorageConfig, PostgresConfig } from "./base";
import { SqliteStore } from "./sqlite/sqlite-store";
import { PostgresStore } from "./postgres/postgres-store";

export function createStorageBackend(config: StorageConfig, log: Logger): StorageBackend {
  switch (config.type) {
    case "sqlite":
      return new SqliteStore(config.dbPath, log);
    case "postgres":
      return new PostgresStore(config as PostgresConfig, log);
    default:
      throw new Error(`Unknown storage type: ${(config as any).type}`);
  }
}
```

---

## 7. 文件修改清单

### 7.1 新增文件

```
src/storage/
├── base.ts                      # StorageBackend 接口定义
├── factory.ts                   # 存储工厂
├── vector-backend.ts            # 向量搜索接口
│
├── sqlite/
│   ├── sqlite-store.ts          # 重命名自 sqlite.ts (1596行)
│   ├── index.ts                # 导出
│   └── migrations/             # SQLite 迁移脚本 (如需要)
│
└── postgres/
    ├── postgres-store.ts        # PostgreSQL 实现 (新)
    ├── pgvector-backend.ts      # pgvector 向量后端
    ├── schema.sql               # PostgreSQL DDL 脚本
    └── index.ts                # 导出
```

### 7.2 修改文件

| 文件 | 修改内容 |
|------|---------|
| `src/types.ts` | 添加 `SqliteStorageConfig`, `PostgresStorageConfig`, `StorageConfig` 类型 |
| `src/config.ts` | 修改 `resolveConfig()` 支持新配置格式 |
| `src/storage/index.ts` | 导出 `createStorageBackend` 工厂函数 |
| `src/index.ts` | 使用工厂创建 store |
| `index.ts` | 使用工厂创建 store |
| `openclaw.plugin.json` | 添加 PostgreSQL 配置 schema |

### 7.3 openclaw.plugin.json 配置示例

```json
{
  "config": {
    "storage": {
      "type": "postgres",
      "host": "${MEMOS_PG_HOST}",
      "port": 5432,
      "database": "memos_local",
      "username": "${MEMOS_PG_USER}",
      "password": "${MEMOS_PG_PASSWORD}",
      "ssl": false,
      "dimensions": 1024
    }
  }
}
```

---

## 8. 数据迁移方案

### 8.1 SQLite → PostgreSQL 迁移脚本

```typescript
// scripts/migrate-sqlite-to-postgres.ts

import { SqliteStore } from "../src/storage/sqlite/sqlite-store";
import { PostgresStore } from "../src/storage/postgres/postgres-store";
import type { Logger } from "../src/types";

export async function migrateSqliteToPostgres(
  sqlitePath: string,
  pgConfig: PostgresConfig,
  log: Logger
): Promise<{ chunks: number; tasks: number; skills: number }> {
  // 1. 打开源 (SQLite)
  const sqlite = new SqliteStore(sqlitePath, log);

  // 2. 创建目标 (PostgreSQL)
  const postgres = new PostgresStore(pgConfig, log);
  await postgres.migrate(); // 创建表结构

  // 3. 迁移 Chunks
  log.info("Migrating chunks...");
  let chunkCount = 0;
  const BATCH = 100;
  let offset = 0;

  while (true) {
    const chunks = (sqlite as any).db
      .prepare("SELECT * FROM chunks LIMIT ? OFFSET ?")
      .all(BATCH, offset);

    if (chunks.length === 0) break;

    for (const chunk of chunks) {
      postgres.addChunk({
        sessionKey: chunk.session_key,
        turnId: chunk.turn_id,
        seq: chunk.seq,
        role: chunk.role,
        content: chunk.content,
        kind: chunk.kind,
        summary: chunk.summary,
        taskId: chunk.task_id,
        contentHash: chunk.content_hash,
        dedupStatus: chunk.dedup_status,
        dedupTarget: chunk.dedup_target,
        dedupReason: chunk.dedup_reason,
        createdAt: chunk.created_at,
        updatedAt: chunk.updated_at,
      }, chunk.owner);
      chunkCount++;
    }

    offset += BATCH;
    log.info(`  Migrated ${chunkCount} chunks...`);
  }

  // 4. 迁移 Embeddings (批量)
  log.info("Migrating embeddings...");
  const embeddings = (sqlite as any).db
    .prepare("SELECT * FROM embeddings")
    .all();

  for (const emb of embeddings) {
    postgres.addEmbedding(emb.chunk_id, JSON.parse(emb.vector), emb.dimensions);
  }
  log.info(`  Migrated ${embeddings.length} embeddings`);

  // 5. 迁移 Tasks
  log.info("Migrating tasks...");
  let taskCount = 0;
  const tasks = (sqlite as any).db
    .prepare("SELECT * FROM tasks")
    .all();

  for (const task of tasks) {
    postgres.addTask({
      sessionKey: task.session_key,
      title: task.title,
      summary: task.summary,
      status: task.status,
      skillStatus: task.skill_status,
      skillReason: task.skill_reason,
      startedAt: task.started_at,
      endedAt: task.ended_at,
      updatedAt: task.updated_at,
    }, task.owner);
    taskCount++;
  }
  log.info(`  Migrated ${taskCount} tasks`);

  // 6. 迁移 Skills
  log.info("Migrating skills...");
  let skillCount = 0;
  const skills = (sqlite as any).db
    .prepare("SELECT * FROM skills")
    .all();

  for (const skill of skills) {
    postgres.addSkill({
      name: skill.name,
      title: skill.title,
      content: skill.content,
      guide: skill.guide,
      visibility: skill.visibility,
      status: skill.status,
      qualityScore: skill.quality_score,
    }, skill.owner);
    skillCount++;
  }
  log.info(`  Migrated ${skillCount} skills`);

  // 7. 关闭连接
  sqlite.close();
  await postgres.close();

  return { chunks: chunkCount, tasks: taskCount, skills: skillCount };
}
```

---

## 9. 测试策略

### 9.1 接口一致性测试

```typescript
// tests/storage/backend一致性.test.ts

import { describe } from "vitest";
import { createStorageBackend } from "../src/storage/factory";
import type { StorageBackend } from "../src/storage/base";

// 所有存储后端必须通过相同测试
function storageBackendTests(name: string, create: () => StorageBackend) {
  describe(`${name} backend`, () => {
    let store: StorageBackend;

    beforeEach(() => {
      store = create();
      store.migrate();
    });

    afterEach(() => {
      store.close();
    });

    // ─── Chunk Tests ───
    test("addChunk returns id", async () => {
      const id = store.addChunk({ ...mockChunk }, "agent:test");
      expect(typeof id).toBe("string");
    });

    test("getChunk returns added chunk", async () => {
      const id = store.addChunk({ ...mockChunk }, "agent:test");
      const chunk = store.getChunk(id);
      expect(chunk).not.toBeNull();
      expect(chunk!.content).toBe(mockChunk.content);
    });

    test("owner isolation works", async () => {
      store.addChunk({ ...mockChunk }, "agent:alpha");
      store.addChunk({ ...mockChunk, content: "beta's chunk" }, "agent:beta");

      const alphaChunks = store.ftsSearch("test", 10, ["agent:alpha"]);
      const betaChunks = store.ftsSearch("test", 10, ["agent:beta"]);

      expect(alphaChunks.length).toBe(1);
      expect(betaChunks.length).toBe(1);
    });

    // ... 更多测试
  });
}

// 运行测试
storageBackendTests("SQLite", () => new SqliteStore(":memory:", mockLog));
storageBackendTests("PostgreSQL", () => new PostgresStore(testPgConfig, mockLog));
```

### 9.2 向量搜索精度测试

```typescript
test("pgvector search accuracy", async () => {
  // 添加已知相似度的向量
  store.addChunk({ ... }, "agent:test");
  store.addEmbedding(chunkId1, [1, 0, 0, ...], 1024); // [1,0,0] 向北
  store.addEmbedding(chunkId2, [0, 1, 0, ...], 1024); // [0,1,0] 向东
  store.addEmbedding(chunkId3, [1, 1, 0, ...], 1024); // [1,1,0] 东北

  // 搜索 "北" (应该更接近 [1,0,0])
  const results = store.vectorSearch([1, 0.1, 0, ...], 3);

  expect(results[0].chunkId).toBe(chunkId1); // 最相似
  expect(results[1].score).toBeLessThan(results[0].score);
});
```

---

## 10. 工作量估算

### 阶段 1: 接口抽象 (1-2 天)
- [ ] 定义 `StorageBackend` 接口
- [ ] 定义 `VectorBackend` 接口
- [ ] 创建 `StorageFactory`
- [ ] 迁移现有 `SqliteStore` 到 `src/storage/sqlite/`

### 阶段 2: PostgreSQL 实现 (3-4 天)
- [ ] 创建 `PostgresStore` 类
- [ ] 实现 `PgVectorBackend`
- [ ] 实现全文搜索 (pg_trgm)
- [ ] 移植所有迁移逻辑

### 阶段 3: 配置与集成 (1 天)
- [ ] 更新配置解析
- [ ] 更新 `index.ts` 工厂调用
- [ ] 更新 `openclaw.plugin.json` schema

### 阶段 4: 测试与迁移 (2 天)
- [ ] 编写一致性测试
- [ ] 编写迁移脚本
- [ ] 手动测试
- [ ] 性能基准测试

### 总计: **7-9 人工作日**

---

## 11. 已知风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| pgvector 扩展未安装 | PostgreSQL 无法使用向量 | 启动检查 + 友好错误提示 |
| 向量维度不匹配 | 搜索失败 | 动态获取已有向量维度 |
| 迁移丢数据 | 数据丢失 | 迁移前备份 + 增量验证 |
| 连接池耗尽 | 请求失败 | 配置 poolSize + 超时处理 |

---

## 12. 未来扩展

后续可轻松添加更多后端：

```typescript
// 向量后端扩展
export class QdrantBackend implements VectorBackend { ... }
export class MilvusBackend implements VectorBackend { ... }
export class ChromaBackend implements VectorBackend { ... }

// 存储后端扩展
export class MySQLStore implements StorageBackend { ... }
```

---

*文档版本: 1.0*
*生成时间: 2026-03-21*
*作者: Harley-chan (哈雷酱)*

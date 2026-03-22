import { Pool, type PoolClient, type QueryResult, type QueryResultRow } from "pg";
import { createHash } from "crypto";
import * as fs from "fs";
import * as path from "path";
import type {
  Chunk,
  ChunkRef,
  DedupStatus,
  Task,
  TaskStatus,
  Skill,
  SkillStatus,
  SkillVisibility,
  SkillVersion,
  TaskSkillLink,
  TaskSkillRelation,
  Logger,
} from "../types";

// SQL templates for PostgreSQL
const SQL = {
  // chunks table
  createChunksTable: `
    CREATE TABLE IF NOT EXISTS chunks (
      id          TEXT PRIMARY KEY,
      session_key TEXT NOT NULL,
      turn_id     TEXT NOT NULL,
      seq         INTEGER NOT NULL,
      role        TEXT NOT NULL,
      content     TEXT NOT NULL,
      kind        TEXT NOT NULL DEFAULT 'paragraph',
      summary     TEXT NOT NULL DEFAULT '',
      owner       TEXT NOT NULL DEFAULT 'agent:main',
      dedup_status TEXT NOT NULL DEFAULT 'active',
      dedup_target TEXT,
      dedup_reason TEXT,
      merge_count INTEGER NOT NULL DEFAULT 0,
      last_hit_at BIGINT,
      merge_history TEXT NOT NULL DEFAULT '[]',
      task_id     TEXT,
      skill_id    TEXT,
      content_hash TEXT,
      created_at  BIGINT NOT NULL,
      updated_at  BIGINT NOT NULL
    )
  `,
  createChunksIndexes: `
    CREATE INDEX IF NOT EXISTS idx_chunks_session ON chunks(session_key);
    CREATE INDEX IF NOT EXISTS idx_chunks_turn ON chunks(session_key, turn_id, seq);
    CREATE INDEX IF NOT EXISTS idx_chunks_created ON chunks(created_at);
    CREATE INDEX IF NOT EXISTS idx_chunks_owner ON chunks(owner);
    CREATE INDEX IF NOT EXISTS idx_chunks_dedup_created ON chunks(dedup_status, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_chunks_task ON chunks(task_id);
    CREATE INDEX IF NOT EXISTS idx_chunks_skill ON chunks(skill_id);
  `,

  // chunks full-text search using pg_trgm
  createChunksTrgm: `
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
    CREATE INDEX IF NOT EXISTS idx_chunks_content_trgm ON chunks USING gin (content gin_trgm_ops);
    CREATE INDEX IF NOT EXISTS idx_chunks_summary_trgm ON chunks USING gin (summary gin_trgm_ops);
  `,

  // embeddings table with pgvector
  createEmbeddingsTable: `
    CREATE TABLE IF NOT EXISTS embeddings (
      chunk_id   TEXT PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
      vector     REAL[] NOT NULL,
      dimensions INTEGER NOT NULL,
      updated_at BIGINT NOT NULL
    )
  `,

  // tasks table
  createTasksTable: `
    CREATE TABLE IF NOT EXISTS tasks (
      id          TEXT PRIMARY KEY,
      session_key TEXT NOT NULL,
      title       TEXT NOT NULL DEFAULT '',
      summary     TEXT NOT NULL DEFAULT '',
      status      TEXT NOT NULL DEFAULT 'active',
      owner       TEXT NOT NULL DEFAULT 'agent:main',
      started_at  BIGINT NOT NULL,
      ended_at    BIGINT,
      updated_at  BIGINT NOT NULL
    )
  `,
  createTasksIndexes: `
    CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_key);
    CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
    CREATE INDEX IF NOT EXISTS idx_tasks_owner ON tasks(owner);
  `,

  // viewer_events table
  createViewerEventsTable: `
    CREATE TABLE IF NOT EXISTS viewer_events (
      id         BIGSERIAL PRIMARY KEY,
      event_type TEXT NOT NULL,
      created_at BIGINT NOT NULL
    )
  `,
  createViewerEventsIndexes: `
    CREATE INDEX IF NOT EXISTS idx_viewer_events_created ON viewer_events(created_at);
    CREATE INDEX IF NOT EXISTS idx_viewer_events_type ON viewer_events(event_type);
  `,

  // skills table
  createSkillsTable: `
    CREATE TABLE IF NOT EXISTS skills (
      id              TEXT PRIMARY KEY,
      name            TEXT NOT NULL,
      description     TEXT NOT NULL DEFAULT '',
      status          TEXT NOT NULL DEFAULT 'active',
      visibility      TEXT NOT NULL DEFAULT 'private',
      owner           TEXT NOT NULL DEFAULT 'agent:main',
      installed       INTEGER NOT NULL DEFAULT 0,
      quality_score   REAL,
      latest_version  INTEGER NOT NULL DEFAULT 1,
      created_at      BIGINT NOT NULL,
      updated_at      BIGINT NOT NULL
    )
  `,
  createSkillsIndexes: `
    CREATE INDEX IF NOT EXISTS idx_skills_owner ON skills(owner);
    CREATE INDEX IF NOT EXISTS idx_skills_visibility ON skills(visibility);
    CREATE INDEX IF NOT EXISTS idx_skills_status ON skills(status);
    CREATE INDEX IF NOT EXISTS idx_skills_name_trgm ON skills USING gin (name gin_trgm_ops);
  `,

  // skill_embeddings table
  createSkillEmbeddingsTable: `
    CREATE TABLE IF NOT EXISTS skill_embeddings (
      skill_id   TEXT PRIMARY KEY REFERENCES skills(id) ON DELETE CASCADE,
      vector     REAL[] NOT NULL,
      dimensions INTEGER NOT NULL,
      updated_at BIGINT NOT NULL
    )
  `,

  // skill_versions table
  createSkillVersionsTable: `
    CREATE TABLE IF NOT EXISTS skill_versions (
      id              TEXT PRIMARY KEY,
      skill_id        TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
      version         INTEGER NOT NULL,
      content         TEXT NOT NULL,
      changelog       TEXT NOT NULL DEFAULT '',
      change_summary  TEXT NOT NULL DEFAULT '',
      upgrade_type    TEXT NOT NULL DEFAULT 'major',
      source_task_id  TEXT,
      metrics         TEXT NOT NULL DEFAULT '{}',
      quality_score   REAL,
      created_at      BIGINT NOT NULL,
      UNIQUE(skill_id, version)
    )
  `,

  // task_skills table
  createTaskSkillsTable: `
    CREATE TABLE IF NOT EXISTS task_skills (
      id          TEXT PRIMARY KEY,
      task_id     TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
      skill_id    TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
      relation    TEXT NOT NULL,
      version_at  INTEGER NOT NULL,
      created_at  BIGINT NOT NULL,
      UNIQUE(task_id, skill_id)
    )
  `,

  // api_logs table
  createApiLogsTable: `
    CREATE TABLE IF NOT EXISTS api_logs (
      id          BIGSERIAL PRIMARY KEY,
      tool_name   TEXT NOT NULL,
      input       TEXT NOT NULL,
      output      TEXT NOT NULL,
      duration_ms INTEGER NOT NULL,
      success     BOOLEAN NOT NULL,
      called_at   BIGINT NOT NULL
    )
  `,
  createApiLogsIndexes: `
    CREATE INDEX IF NOT EXISTS idx_api_logs_tool ON api_logs(tool_name);
    CREATE INDEX IF NOT EXISTS idx_api_logs_called ON api_logs(called_at);
  `,

  // merge_history table
  createMergeHistoryTable: `
    CREATE TABLE IF NOT EXISTS merge_history (
      id          BIGSERIAL PRIMARY KEY,
      chunk_id    TEXT NOT NULL,
      action      TEXT NOT NULL,
      reason      TEXT NOT NULL,
      old_summary TEXT,
      new_summary TEXT,
      created_at  BIGINT NOT NULL
    )
  `,
  createMergeHistoryIndexes: `
    CREATE INDEX IF NOT EXISTS idx_merge_history_chunk ON merge_history(chunk_id);
  `,

  // tool_calls table
  createToolCallsTable: `
    CREATE TABLE IF NOT EXISTS tool_calls (
      id          BIGSERIAL PRIMARY KEY,
      tool_name   TEXT NOT NULL,
      duration_ms INTEGER NOT NULL,
      success     BOOLEAN NOT NULL,
      called_at   BIGINT NOT NULL
    )
  `,
  createToolCallsIndexes: `
    CREATE INDEX IF NOT EXISTS idx_tool_calls_called ON tool_calls(called_at);
  `,
};

function contentHash(content: string): string {
  return createHash("sha256").update(content).digest("hex").slice(0, 16);
}

export class PostgresStore {
  private pool: Pool;
  private log: Logger;
  private schema: string;

  constructor(databaseUrl: string, log: Logger, schema: string = "public") {
    this.log = log;
    this.schema = schema;
    this.pool = new Pool({
      connectionString: databaseUrl,
      max: 20,
      idleTimeoutMillis: 30000,
      connectionTimeoutMillis: 5000,
    });
    this.log.info(`[postgres] Connecting to PostgreSQL schema: ${schema}`);
  }

  async initialize(): Promise<void> {
    const client = await this.pool.connect();
    try {
      // Set schema if not public
      if (this.schema !== "public") {
        await client.query(`CREATE SCHEMA IF NOT EXISTS ${this.schema}`);
        await client.query(`SET search_path TO ${this.schema}`);
      }

      // Create all tables and indexes
      await client.query(SQL.createChunksTable);
      await client.query(SQL.createChunksIndexes);
      await client.query(SQL.createChunksTrgm);

      await client.query(SQL.createEmbeddingsTable);

      await client.query(SQL.createTasksTable);
      await client.query(SQL.createTasksIndexes);

      await client.query(SQL.createViewerEventsTable);
      await client.query(SQL.createViewerEventsIndexes);

      await client.query(SQL.createSkillsTable);
      await client.query(SQL.createSkillsIndexes);

      await client.query(SQL.createSkillEmbeddingsTable);
      await client.query(SQL.createSkillVersionsTable);
      await client.query(SQL.createTaskSkillsTable);

      await client.query(SQL.createApiLogsTable);
      await client.query(SQL.createApiLogsIndexes);

      await client.query(SQL.createMergeHistoryTable);
      await client.query(SQL.createMergeHistoryIndexes);

      await client.query(SQL.createToolCallsTable);
      await client.query(SQL.createToolCallsIndexes);

      this.log.debug("[postgres] Database schema initialized");
    } finally {
      client.release();
    }
  }

  // ─── Helper methods ─────────────────────────────────────────────────────────

  private async query<T extends QueryResultRow = QueryResultRow>(sql: string, params?: unknown[]): Promise<QueryResult<T>> {
    const client = await this.pool.connect();
    try {
      return await client.query<T>(sql, params);
    } finally {
      client.release();
    }
  }

  private rowToChunk(row: Record<string, unknown>): Chunk {
    return {
      id: row.id as string,
      sessionKey: row.session_key as string,
      turnId: row.turn_id as string,
      seq: row.seq as number,
      role: row.role as Chunk["role"],
      content: row.content as string,
      kind: (row.kind as Chunk["kind"]) || "paragraph",
      summary: row.summary as string,
      embedding: null,
      taskId: (row.task_id as string) || null,
      skillId: (row.skill_id as string) || null,
      owner: row.owner as string,
      dedupStatus: (row.dedup_status as DedupStatus) || "active",
      dedupTarget: (row.dedup_target as string) || null,
      dedupReason: (row.dedup_reason as string) || null,
      mergeCount: (row.merge_count as number) || 0,
      lastHitAt: (row.last_hit_at as number) || null,
      mergeHistory: (row.merge_history as string) || "[]",
      createdAt: row.created_at as number,
      updatedAt: row.updated_at as number,
    };
  }

  private rowToTask(row: Record<string, unknown>): Task {
    return {
      id: row.id as string,
      sessionKey: row.session_key as string,
      title: row.title as string,
      summary: row.summary as string,
      status: row.status as TaskStatus,
      owner: row.owner as string,
      startedAt: row.started_at as number,
      endedAt: (row.ended_at as number) || null,
      updatedAt: row.updated_at as number,
    };
  }

  private rowToSkill(row: Record<string, unknown>): Skill {
    return {
      id: row.id as string,
      name: row.name as string,
      description: row.description as string,
      version: row.version as number,
      status: row.status as SkillStatus,
      tags: (row.tags as string) || "",
      sourceType: (row.source_type as "task" | "manual") || "manual",
      dirPath: (row.dir_path as string) || "",
      visibility: (row.visibility as SkillVisibility) || "private",
      owner: row.owner as string,
      installed: row.installed as number,
      qualityScore: (row.quality_score as number) || null,
      createdAt: row.created_at as number,
      updatedAt: row.updated_at as number,
    };
  }

  // ─── Chunk operations ───────────────────────────────────────────────────────

  async insertChunk(chunk: Chunk): Promise<void> {
    const sql = `
      INSERT INTO chunks (id, session_key, turn_id, seq, role, content, kind, summary,
        owner, dedup_status, dedup_target, dedup_reason, merge_count, last_hit_at,
        merge_history, task_id, skill_id, content_hash, created_at, updated_at)
      VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20)
      ON CONFLICT (id) DO NOTHING
    `;
    const params = [
      chunk.id,
      chunk.sessionKey,
      chunk.turnId,
      chunk.seq,
      chunk.role,
      chunk.content,
      chunk.kind,
      chunk.summary,
      chunk.owner,
      chunk.dedupStatus,
      chunk.dedupTarget,
      chunk.dedupReason,
      chunk.mergeCount,
      chunk.lastHitAt,
      chunk.mergeHistory,
      chunk.taskId,
      chunk.skillId,
      contentHash(chunk.content),
      chunk.createdAt,
      chunk.updatedAt,
    ];
    await this.query(sql, params);
  }

  async markDedupStatus(
    chunkId: string,
    status: "duplicate" | "merged",
    targetChunkId: string | null,
    reason: string
  ): Promise<void> {
    const sql = `
      UPDATE chunks SET dedup_status = $1, dedup_target = $2, dedup_reason = $3, updated_at = $4
      WHERE id = $5
    `;
    await this.query(sql, [status, targetChunkId, reason, Date.now(), chunkId]);
  }

  async updateSummary(chunkId: string, summary: string): Promise<void> {
    const sql = `UPDATE chunks SET summary = $1, updated_at = $2 WHERE id = $3`;
    await this.query(sql, [summary, Date.now(), chunkId]);
  }

  async upsertEmbedding(chunkId: string, vector: number[]): Promise<void> {
    const sql = `
      INSERT INTO embeddings (chunk_id, vector, dimensions, updated_at)
      VALUES ($1, $2, $3, $4)
      ON CONFLICT (chunk_id) DO UPDATE SET vector = $2, dimensions = $3, updated_at = $4
    `;
    await this.query(sql, [chunkId, vector, vector.length, Date.now()]);
  }

  async deleteEmbedding(chunkId: string): Promise<void> {
    const sql = `DELETE FROM embeddings WHERE chunk_id = $1`;
    await this.query(sql, [chunkId]);
  }

  async getChunk(chunkId: string): Promise<Chunk | null> {
    const sql = `SELECT * FROM chunks WHERE id = $1`;
    const result = await this.query<Record<string, unknown>>(sql, [chunkId]);
    if (result.rows.length === 0) return null;
    return this.rowToChunk(result.rows[0]);
  }

  async getChunkForOwners(chunkId: string, ownerFilter?: string[]): Promise<Chunk | null> {
    if (!ownerFilter || ownerFilter.length === 0) {
      return this.getChunk(chunkId);
    }
    const sql = `SELECT * FROM chunks WHERE id = $1 AND owner = ANY($2)`;
    const result = await this.query<Record<string, unknown>>(sql, [chunkId, ownerFilter]);
    if (result.rows.length === 0) return null;
    return this.rowToChunk(result.rows[0]);
  }

  async getChunksByRef(ref: ChunkRef, ownerFilter?: string[]): Promise<Chunk[]> {
    let sql = `SELECT * FROM chunks WHERE session_key = $1 AND turn_id = $2 AND seq = $3`;
    const params: unknown[] = [ref.sessionKey, ref.turnId, ref.seq];
    if (ownerFilter && ownerFilter.length > 0) {
      sql += ` AND owner = ANY($4)`;
      params.push(ownerFilter);
    }
    const result = await this.query<Record<string, unknown>>(sql, params);
    return result.rows.map((row) => this.rowToChunk(row));
  }

  async getNeighborChunks(
    sessionKey: string,
    turnId: string,
    seq: number,
    window: number,
    ownerFilter?: string[]
  ): Promise<Chunk[]> {
    let sql = `
      SELECT * FROM chunks
      WHERE session_key = $1 AND turn_id = $2 AND seq BETWEEN $3 AND $4
    `;
    const params: unknown[] = [sessionKey, turnId, seq - window, seq + window];
    if (ownerFilter && ownerFilter.length > 0) {
      sql += ` AND owner = ANY($5)`;
      params.push(ownerFilter);
    }
    sql += ` ORDER BY seq`;
    const result = await this.query<Record<string, unknown>>(sql, params);
    return result.rows.map((row) => this.rowToChunk(row));
  }

  async ftsSearch(
    query: string,
    limit: number,
    ownerFilter?: string[]
  ): Promise<Array<{ chunkId: string; score: number }>> {
    // Use pg_trgm for similarity search
    let sql = `
      SELECT id,
        (CASE WHEN length($1) > 3 THEN similarity(content, $1) ELSE 0 END) as score
      FROM chunks
      WHERE dedup_status = 'active'
    `;
    const params: unknown[] = [query];

    if (ownerFilter && ownerFilter.length > 0) {
      sql += ` AND owner = ANY($2)`;
      params.push(ownerFilter);
      sql += ` ORDER BY score DESC LIMIT $3`;
    } else {
      sql += ` ORDER BY score DESC LIMIT $2`;
    }
    params.push(limit);

    const result = await this.query<{ id: string; score: number }>(sql, params);
    return result.rows.map((row) => ({ chunkId: row.id, score: row.score || 0 }));
  }

  async patternSearch(
    patterns: string[],
    opts: { role?: string; limit?: number } = {}
  ): Promise<Array<{ chunkId: string; content: string; role: string; createdAt: number }>> {
    const conditions = patterns.map((p, i) => `content LIKE $${i + 1}`);
    let sql = `SELECT id, content, role, created_at FROM chunks WHERE (${conditions.join(" OR ")})`;
    const params: unknown[] = patterns.map((p) => `%${p}%`);

    if (opts.role) {
      sql += ` AND role = $${params.length + 1}`;
      params.push(opts.role);
    }
    if (opts.limit) {
      sql += ` LIMIT $${params.length + 1}`;
      params.push(opts.limit);
    }

    const result = await this.query<{ id: string; content: string; role: string; created_at: number }>(sql, params);
    return result.rows.map((row) => ({
      chunkId: row.id,
      content: row.content,
      role: row.role,
      createdAt: row.created_at,
    }));
  }

  async getAllEmbeddings(ownerFilter?: string[]): Promise<Array<{ chunkId: string; vector: number[] }>> {
    let sql = `SELECT e.chunk_id, e.vector FROM embeddings e JOIN chunks c ON e.chunk_id = c.id WHERE c.dedup_status = 'active'`;
    const params: unknown[] = [];
    if (ownerFilter && ownerFilter.length > 0) {
      sql += ` AND c.owner = ANY($1)`;
      params.push(ownerFilter);
    }
    const result = await this.query<{ chunk_id: string; vector: number[] }>(sql, params);
    return result.rows.map((row) => ({ chunkId: row.chunk_id, vector: row.vector }));
  }

  async getRecentEmbeddings(
    limit: number,
    ownerFilter?: string[]
  ): Promise<Array<{ chunkId: string; vector: number[] }>> {
    let sql = `
      SELECT e.chunk_id, e.vector FROM embeddings e
      JOIN chunks c ON e.chunk_id = c.id
      WHERE c.dedup_status = 'active'
    `;
    const params: unknown[] = [];
    if (ownerFilter && ownerFilter.length > 0) {
      sql += ` AND c.owner = ANY($1)`;
      params.push(ownerFilter);
    }
    sql += ` ORDER BY e.updated_at DESC LIMIT $${params.length + 1}`;
    params.push(limit);
    const result = await this.query<{ chunk_id: string; vector: number[] }>(sql, params);
    return result.rows.map((row) => ({ chunkId: row.chunk_id, vector: row.vector }));
  }

  async getEmbedding(chunkId: string): Promise<number[] | null> {
    const sql = `SELECT vector FROM embeddings WHERE chunk_id = $1`;
    const result = await this.query<{ vector: number[] }>(sql, [chunkId]);
    if (result.rows.length === 0) return null;
    return result.rows[0].vector;
  }

  async updateChunk(
    chunkId: string,
    fields: { summary?: string; content?: string; role?: string; kind?: string; owner?: string }
  ): Promise<boolean> {
    const updates: string[] = [];
    const params: unknown[] = [];
    let idx = 1;

    if (fields.summary !== undefined) {
      updates.push(`summary = $${idx++}`);
      params.push(fields.summary);
    }
    if (fields.content !== undefined) {
      updates.push(`content = $${idx++}`);
      params.push(fields.content);
    }
    if (fields.role !== undefined) {
      updates.push(`role = $${idx++}`);
      params.push(fields.role);
    }
    if (fields.kind !== undefined) {
      updates.push(`kind = $${idx++}`);
      params.push(fields.kind);
    }
    if (fields.owner !== undefined) {
      updates.push(`owner = $${idx++}`);
      params.push(fields.owner);
    }

    if (updates.length === 0) return false;

    updates.push(`updated_at = $${idx++}`);
    params.push(Date.now());
    params.push(chunkId);

    const sql = `UPDATE chunks SET ${updates.join(", ")} WHERE id = $${idx}`;
    const result = await this.query(sql, params);
    return (result.rowCount ?? 0) > 0;
  }

  async findPollutedUserChunks(): Promise<Array<{ id: string; preview: string; reason: string }>> {
    // Find chunks that appear to be polluted (contain system prompts or tool definitions mixed with user content)
    const sql = `
      SELECT id, SUBSTRING(content, 1, 100) as preview,
        CASE
          WHEN content LIKE '%You are a helpful assistant%' THEN 'likely_system_prompt'
          WHEN content LIKE '%tool_use%' AND content LIKE '%user%' THEN 'mixed_tool_user'
          ELSE 'unknown'
        END as reason
      FROM chunks
      WHERE role = 'user'
        AND (content LIKE '%You are a%' OR content LIKE '%tool_use%')
      LIMIT 50
    `;
    const result = await this.query<{ id: string; preview: string; reason: string }>(sql);
    return result.rows;
  }

  async fixMixedUserChunks(): Promise<number> {
    // This is a placeholder - actual implementation would depend on specific pollution patterns
    this.log.warn("[postgres] fixMixedUserChunks not fully implemented");
    return 0;
  }

  async deleteChunk(chunkId: string): Promise<boolean> {
    const sql = `DELETE FROM chunks WHERE id = $1`;
    const result = await this.query(sql, [chunkId]);
    return (result.rowCount ?? 0) > 0;
  }

  async deleteSession(sessionKey: string): Promise<number> {
    const sql = `DELETE FROM chunks WHERE session_key = $1`;
    const result = await this.query(sql, [sessionKey]);
    return result.rowCount ?? 0;
  }

  async deleteAll(): Promise<number> {
    const sql = `DELETE FROM chunks`;
    const result = await this.query(sql);
    return result.rowCount ?? 0;
  }

  // ─── Task operations ────────────────────────────────────────────────────────

  async deleteTask(taskId: string): Promise<boolean> {
    const sql = `DELETE FROM tasks WHERE id = $1`;
    const result = await this.query(sql, [taskId]);
    return (result.rowCount ?? 0) > 0;
  }

  async deleteSkill(skillId: string): Promise<boolean> {
    const sql = `DELETE FROM skills WHERE id = $1`;
    const result = await this.query(sql, [skillId]);
    return (result.rowCount ?? 0) > 0;
  }

  async insertTask(task: Task): Promise<void> {
    const sql = `
      INSERT INTO tasks (id, session_key, title, summary, status, owner, started_at, ended_at, updated_at)
      VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
      ON CONFLICT (id) DO NOTHING
    `;
    await this.query(sql, [
      task.id,
      task.sessionKey,
      task.title,
      task.summary,
      task.status,
      task.owner,
      task.startedAt,
      task.endedAt,
      task.updatedAt,
    ]);
  }

  async getTask(taskId: string): Promise<Task | null> {
    const sql = `SELECT * FROM tasks WHERE id = $1`;
    const result = await this.query<Record<string, unknown>>(sql, [taskId]);
    if (result.rows.length === 0) return null;
    return this.rowToTask(result.rows[0]);
  }

  async getActiveTask(sessionKey: string, owner?: string): Promise<Task | null> {
    let sql = `SELECT * FROM tasks WHERE session_key = $1 AND status = 'active'`;
    const params: unknown[] = [sessionKey];
    if (owner) {
      sql += ` AND owner = $2`;
      params.push(owner);
    }
    sql += ` ORDER BY started_at DESC LIMIT 1`;
    const result = await this.query<Record<string, unknown>>(sql, params);
    if (result.rows.length === 0) return null;
    return this.rowToTask(result.rows[0]);
  }

  async hasTaskForSession(sessionKey: string): Promise<boolean> {
    const sql = `SELECT 1 FROM tasks WHERE session_key = $1 AND status = 'active' LIMIT 1`;
    const result = await this.query(sql, [sessionKey]);
    return result.rows.length > 0;
  }

  async hasSkillForSessionTask(sessionKey: string): Promise<boolean> {
    const sql = `
      SELECT 1 FROM tasks t
      JOIN task_skills ts ON t.id = ts.task_id
      WHERE t.session_key = $1 AND t.status = 'active'
      LIMIT 1
    `;
    const result = await this.query(sql, [sessionKey]);
    return result.rows.length > 0;
  }

  async getCompletedTasksForSession(sessionKey: string): Promise<Task[]> {
    const sql = `SELECT * FROM tasks WHERE session_key = $1 AND status = 'completed' ORDER BY ended_at DESC`;
    const result = await this.query<Record<string, unknown>>(sql, [sessionKey]);
    return result.rows.map((row) => this.rowToTask(row));
  }

  async getAllActiveTasks(owner?: string): Promise<Task[]> {
    let sql = `SELECT * FROM tasks WHERE status = 'active'`;
    const params: unknown[] = [];
    if (owner) {
      sql += ` AND owner = $1`;
      params.push(owner);
    }
    sql += ` ORDER BY started_at DESC`;
    const result = await this.query<Record<string, unknown>>(sql, params);
    return result.rows.map((row) => this.rowToTask(row));
  }

  async updateTask(
    taskId: string,
    fields: { title?: string; summary?: string; status?: TaskStatus; endedAt?: number }
  ): Promise<boolean> {
    const updates: string[] = [];
    const params: unknown[] = [];
    let idx = 1;

    if (fields.title !== undefined) {
      updates.push(`title = $${idx++}`);
      params.push(fields.title);
    }
    if (fields.summary !== undefined) {
      updates.push(`summary = $${idx++}`);
      params.push(fields.summary);
    }
    if (fields.status !== undefined) {
      updates.push(`status = $${idx++}`);
      params.push(fields.status);
    }
    if (fields.endedAt !== undefined) {
      updates.push(`ended_at = $${idx++}`);
      params.push(fields.endedAt);
    }

    if (updates.length === 0) return false;

    updates.push(`updated_at = $${idx++}`);
    params.push(Date.now());
    params.push(taskId);

    const sql = `UPDATE tasks SET ${updates.join(", ")} WHERE id = $${idx}`;
    const result = await this.query(sql, params);
    return (result.rowCount ?? 0) > 0;
  }

  async getChunksByTask(taskId: string): Promise<Chunk[]> {
    const sql = `SELECT * FROM chunks WHERE task_id = $1 ORDER BY created_at`;
    const result = await this.query<Record<string, unknown>>(sql, [taskId]);
    return result.rows.map((row) => this.rowToChunk(row));
  }

  async listTasks(
    opts: { status?: string; limit?: number; offset?: number; owner?: string } = {}
  ): Promise<{ tasks: Task[]; total: number }> {
    const conditions: string[] = [];
    const params: unknown[] = [];
    let idx = 1;

    if (opts.status) {
      conditions.push(`status = $${idx++}`);
      params.push(opts.status);
    }
    if (opts.owner) {
      conditions.push(`owner = $${idx++}`);
      params.push(opts.owner);
    }

    const whereClause = conditions.length > 0 ? `WHERE ${conditions.join(" AND ")}` : "";

    const countSql = `SELECT COUNT(*) as total FROM tasks ${whereClause}`;
    const countResult = await this.query<{ total: string }>(countSql, params);
    const total = parseInt(countResult.rows[0]?.total || "0", 10);

    let sql = `SELECT * FROM tasks ${whereClause} ORDER BY updated_at DESC`;
    if (opts.limit) {
      sql += ` LIMIT $${idx++}`;
      params.push(opts.limit);
    }
    if (opts.offset) {
      sql += ` OFFSET $${idx++}`;
      params.push(opts.offset);
    }

    const result = await this.query<Record<string, unknown>>(sql, params);
    return { tasks: result.rows.map((row) => this.rowToTask(row)), total };
  }

  async countChunksByTask(taskId: string): Promise<number> {
    const sql = `SELECT COUNT(*) as count FROM chunks WHERE task_id = $1`;
    const result = await this.query<{ count: string }>(sql, [taskId]);
    return parseInt(result.rows[0]?.count || "0", 10);
  }

  async setChunkTaskId(chunkId: string, taskId: string): Promise<void> {
    const sql = `UPDATE chunks SET task_id = $1, updated_at = $2 WHERE id = $3`;
    await this.query(sql, [taskId, Date.now(), chunkId]);
  }

  async getUnassignedChunks(sessionKey: string, owner?: string): Promise<Chunk[]> {
    let sql = `SELECT * FROM chunks WHERE session_key = $1 AND task_id IS NULL AND dedup_status = 'active'`;
    const params: unknown[] = [sessionKey];
    if (owner) {
      sql += ` AND owner = $2`;
      params.push(owner);
    }
    sql += ` ORDER BY created_at DESC`;
    const result = await this.query<Record<string, unknown>>(sql, params);
    return result.rows.map((row) => this.rowToChunk(row));
  }

  async chunkExistsByContent(sessionKey: string, role: string, content: string): Promise<boolean> {
    const hash = contentHash(content);
    const sql = `SELECT 1 FROM chunks WHERE session_key = $1 AND role = $2 AND content_hash = $3 LIMIT 1`;
    const result = await this.query(sql, [sessionKey, role, hash]);
    return result.rows.length > 0;
  }

  async findActiveChunkByHash(content: string, owner?: string): Promise<string | null> {
    const hash = contentHash(content);
    let sql = `SELECT id FROM chunks WHERE content_hash = $1 AND dedup_status = 'active'`;
    const params: unknown[] = [hash];
    if (owner) {
      sql += ` AND owner = $2`;
      params.push(owner);
    }
    sql += ` LIMIT 1`;
    const result = await this.query<{ id: string }>(sql, params);
    return result.rows.length > 0 ? result.rows[0].id : null;
  }

  async getRecentChunkIds(limit: number): Promise<string[]> {
    const sql = `SELECT id FROM chunks WHERE dedup_status = 'active' ORDER BY created_at DESC LIMIT $1`;
    const result = await this.query<{ id: string }>(sql, [limit]);
    return result.rows.map((row) => row.id);
  }

  async countChunks(): Promise<number> {
    const sql = `SELECT COUNT(*) as count FROM chunks WHERE dedup_status = 'active'`;
    const result = await this.query<{ count: string }>(sql);
    return parseInt(result.rows[0]?.count || "0", 10);
  }

  // ─── Skill operations ─────────────────────────────────────────────────────

    async insertSkill(skill: Skill): Promise<void> {
    const sql = `
      INSERT INTO skills (id, name, description, version, status, tags, source_type, dir_path, installed, owner, visibility, quality_score, created_at, updated_at)
      VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
      ON CONFLICT (id) DO NOTHING
    `;
    await this.query(sql, [
      skill.id,
      skill.name,
      skill.description,
      skill.version,
      skill.status,
      skill.tags,
      skill.sourceType,
      skill.dirPath,
      skill.installed,
      skill.owner ?? "agent:main",
      skill.visibility ?? "private",
      skill.qualityScore,
      skill.createdAt,
      skill.updatedAt,
    ]);
  }

  async getSkillByName(name: string): Promise<Skill | null> {
    const sql = `SELECT * FROM skills WHERE name = $1`;
    const result = await this.query<Record<string, unknown>>(sql, [name]);
    if (result.rows.length === 0) return null;
    return this.rowToSkill(result.rows[0]);
  }

  async updateSkill(
    skillId: string,
    fields: {
      description?: string;
      version?: number;
      status?: SkillStatus;
      installed?: number;
      qualityScore?: number | null;
      updatedAt?: number;
    }
  ): Promise<void> {
    const updates: string[] = [];
    const params: unknown[] = [];
    let idx = 1;

    if (fields.description !== undefined) {
      updates.push(`description = $${idx++}`);
      params.push(fields.description);
    }
    if (fields.version !== undefined) {
      updates.push(`latest_version = $${idx++}`);
      params.push(fields.version);
    }
    if (fields.status !== undefined) {
      updates.push(`status = $${idx++}`);
      params.push(fields.status);
    }
    if (fields.installed !== undefined) {
      updates.push(`installed = $${idx++}`);
      params.push(fields.installed);
    }
    if (fields.qualityScore !== undefined) {
      updates.push(`quality_score = $${idx++}`);
      params.push(fields.qualityScore);
    }
    if (fields.updatedAt !== undefined) {
      updates.push(`updated_at = $${idx++}`);
      params.push(fields.updatedAt);
    }

    if (updates.length === 0) return;

    updates.push(`updated_at = $${idx++}`);
    params.push(Date.now());
    params.push(skillId);

    const sql = `UPDATE skills SET ${updates.join(", ")} WHERE id = $${idx}`;
    await this.query(sql, params);
  }

  async listSkills(opts: { status?: string } = {}): Promise<Skill[]> {
    let sql = `SELECT * FROM skills`;
    const params: unknown[] = [];
    if (opts.status) {
      sql += ` WHERE status = $1`;
      params.push(opts.status);
    }
    sql += ` ORDER BY updated_at DESC`;
    const result = await this.query<Record<string, unknown>>(sql, params);
    return result.rows.map((row) => this.rowToSkill(row));
  }

  async setSkillVisibility(skillId: string, visibility: SkillVisibility): Promise<void> {
    const sql = `UPDATE skills SET visibility = $1, updated_at = $2 WHERE id = $3`;
    await this.query(sql, [visibility, Date.now(), skillId]);
  }

  async upsertSkillEmbedding(skillId: string, vector: number[]): Promise<void> {
    const sql = `
      INSERT INTO skill_embeddings (skill_id, vector, dimensions, updated_at)
      VALUES ($1, $2, $3, $4)
      ON CONFLICT (skill_id) DO UPDATE SET vector = $2, dimensions = $3, updated_at = $4
    `;
    await this.query(sql, [skillId, vector, vector.length, Date.now()]);
  }

  async getSkillEmbedding(skillId: string): Promise<number[] | null> {
    const sql = `SELECT vector FROM skill_embeddings WHERE skill_id = $1`;
    const result = await this.query<{ vector: number[] }>(sql, [skillId]);
    if (result.rows.length === 0) return null;
    return result.rows[0].vector;
  }

  async getSkillEmbeddings(
    scope: "self" | "public" | "mix",
    currentOwner: string
  ): Promise<Array<{ skillId: string; vector: number[] }>> {
    let sql = `
      SELECT se.skill_id, se.vector FROM skill_embeddings se
      JOIN skills s ON se.skill_id = s.id WHERE s.status = 'active'
    `;
    const params: unknown[] = [];

    if (scope === "self") {
      sql += ` AND s.owner = $1`;
      params.push(currentOwner);
    } else if (scope === "public") {
      sql += ` AND s.visibility = 'public'`;
    }
    // mix: no additional filter

    const result = await this.query<{ skill_id: string; vector: number[] }>(sql, params);
    return result.rows.map((row) => ({ skillId: row.skill_id, vector: row.vector }));
  }

  async skillFtsSearch(
    query: string,
    limit: number,
    scope: "self" | "public" | "mix",
    currentOwner: string
  ): Promise<Array<{ skillId: string; score: number }>> {
    let sql = `
      SELECT s.id as skill_id,
        (CASE WHEN length($1) > 3 THEN similarity(s.name, $1) ELSE 0 END) as score
      FROM skills s
      WHERE s.status = 'active'
    `;
    const params: unknown[] = [query];

    if (scope === "self") {
      sql += ` AND s.owner = $2`;
      params.push(currentOwner);
    } else if (scope === "public") {
      sql += ` AND s.visibility = 'public'`;
    }

    sql += ` ORDER BY score DESC LIMIT $${params.length + 1}`;
    params.push(limit);

    const result = await this.query<{ skill_id: string; score: number }>(sql, params);
    return result.rows.map((row) => ({ skillId: row.skill_id, score: row.score || 0 }));
  }

  async listPublicSkills(): Promise<Skill[]> {
    const sql = `SELECT * FROM skills WHERE visibility = 'public' AND status = 'active' ORDER BY updated_at DESC`;
    const result = await this.query<Record<string, unknown>>(sql);
    return result.rows.map((row) => this.rowToSkill(row));
  }

  // ─── Skill version operations ─────────────────────────────────────────────

  async insertSkillVersion(sv: SkillVersion): Promise<void> {
    const sql = `
      INSERT INTO skill_versions (id, skill_id, version, content, changelog, change_summary, upgrade_type, source_task_id, metrics, quality_score, created_at)
      VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
      ON CONFLICT (skill_id, version) DO NOTHING
    `;
    await this.query(sql, [
      sv.id,
      sv.skillId,
      sv.version,
      sv.content,
      sv.changelog,
      sv.changeSummary,
      sv.upgradeType,
      sv.sourceTaskId,
      JSON.stringify(sv.metrics),
      sv.qualityScore,
      sv.createdAt,
    ]);
  }

  async getLatestSkillVersion(skillId: string): Promise<SkillVersion | null> {
    const sql = `SELECT * FROM skill_versions WHERE skill_id = $1 ORDER BY version DESC LIMIT 1`;
    const result = await this.query<Record<string, unknown>>(sql, [skillId]);
    if (result.rows.length === 0) return null;
    return this.rowToSkillVersion(result.rows[0]);
  }

  async getSkillVersions(skillId: string): Promise<SkillVersion[]> {
    const sql = `SELECT * FROM skill_versions WHERE skill_id = $1 ORDER BY version DESC`;
    const result = await this.query<Record<string, unknown>>(sql, [skillId]);
    return result.rows.map((row) => this.rowToSkillVersion(row));
  }

  async getSkillVersion(skillId: string, version: number): Promise<SkillVersion | null> {
    const sql = `SELECT * FROM skill_versions WHERE skill_id = $1 AND version = $2`;
    const result = await this.query<Record<string, unknown>>(sql, [skillId, version]);
    if (result.rows.length === 0) return null;
    return this.rowToSkillVersion(result.rows[0]);
  }

  private rowToSkillVersion(row: Record<string, unknown>): SkillVersion {
    return {
      id: row.id as string,
      skillId: row.skill_id as string,
      version: row.version as number,
      content: row.content as string,
      changelog: row.changelog as string,
      changeSummary: row.change_summary as string,
      upgradeType: row.upgrade_type as SkillVersion["upgradeType"],
      sourceTaskId: (row.source_task_id as string) || null,
      metrics: JSON.parse((row.metrics as string) || "{}"),
      qualityScore: (row.quality_score as number) || null,
      createdAt: row.created_at as number,
    };
  }

  // ─── Task-Skill link operations ──────────────────────────────────────────

  async linkTaskSkill(
    taskId: string,
    skillId: string,
    relation: TaskSkillRelation,
    versionAt: number
  ): Promise<void> {
    const id = `${taskId}:${skillId}`;
    const sql = `
      INSERT INTO task_skills (id, task_id, skill_id, relation, version_at, created_at)
      VALUES ($1, $2, $3, $4, $5, $6)
      ON CONFLICT (task_id, skill_id) DO UPDATE SET relation = $4, version_at = $5
    `;
    await this.query(sql, [id, taskId, skillId, relation, versionAt, Date.now()]);
  }

  async getSkillsByTask(
    taskId: string
  ): Promise<Array<{ skill: Skill; relation: TaskSkillRelation; versionAt: number }>> {
    const sql = `
      SELECT s.*, ts.relation, ts.version_at
      FROM task_skills ts
      JOIN skills s ON ts.skill_id = s.id
      WHERE ts.task_id = $1
    `;
    const result = await this.query<Record<string, unknown>>(sql, [taskId]);
    return result.rows.map((row) => ({
      skill: this.rowToSkill(row),
      relation: row.relation as TaskSkillRelation,
      versionAt: row.version_at as number,
    }));
  }

  async getTasksBySkill(skillId: string): Promise<Array<{ task: Task; relation: TaskSkillRelation }>> {
    const sql = `
      SELECT t.*, ts.relation
      FROM task_skills ts
      JOIN tasks t ON ts.task_id = t.id
      WHERE ts.skill_id = $1
    `;
    const result = await this.query<Record<string, unknown>>(sql, [skillId]);
    return result.rows.map((row) => ({
      task: this.rowToTask(row),
      relation: row.relation as TaskSkillRelation,
    }));
  }

  async countSkills(status?: string): Promise<number> {
    let sql = `SELECT COUNT(*) as count FROM skills`;
    const params: unknown[] = [];
    if (status) {
      sql += ` WHERE status = $1`;
      params.push(status);
    }
    const result = await this.query<{ count: string }>(sql, params);
    return parseInt(result.rows[0]?.count || "0", 10);
  }

  async setChunkSkillId(chunkId: string, skillId: string): Promise<void> {
    const sql = `UPDATE chunks SET skill_id = $1, updated_at = $2 WHERE id = $3`;
    await this.query(sql, [skillId, Date.now(), chunkId]);
  }

  // ─── Session/Owner operations ────────────────────────────────────────────

  async getDistinctSessionKeys(): Promise<string[]> {
    const sql = `SELECT DISTINCT session_key FROM chunks ORDER BY MAX(created_at) DESC`;
    const result = await this.query<{ session_key: string }>(sql);
    return result.rows.map((row) => row.session_key);
  }

  async getSessionOwnerMap(sessionKeys: string[]): Promise<Map<string, string>> {
    const sql = `
      SELECT session_key, MAX(owner) as owner
      FROM chunks
      WHERE session_key = ANY($1)
      GROUP BY session_key
    `;
    const result = await this.query<{ session_key: string; owner: string }>(sql, [sessionKeys]);
    const map = new Map<string, string>();
    for (const row of result.rows) {
      map.set(row.session_key, row.owner);
    }
    return map;
  }

  // ─── Metrics and logging ──────────────────────────────────────────────────

  async recordViewerEvent(eventType: string): Promise<void> {
    const sql = `INSERT INTO viewer_events (event_type, created_at) VALUES ($1, $2)`;
    await this.query(sql, [eventType, Date.now()]);
  }

  async getMetrics(days: number): Promise<{
    totalChunks: number;
    totalTasks: number;
    totalSkills: number;
    chunksByDay: Array<{ date: string; count: number }>;
    eventsByType: Array<{ type: string; count: number }>;
  }> {
    const since = Date.now() - days * 24 * 60 * 60 * 1000;

    const totalChunksSql = `SELECT COUNT(*) as count FROM chunks WHERE created_at >= $1`;
    const totalTasksSql = `SELECT COUNT(*) as count FROM tasks WHERE started_at >= $1`;
    const totalSkillsSql = `SELECT COUNT(*) as count FROM skills WHERE created_at >= $1`;

    const [totalChunksResult, totalTasksResult, totalSkillsResult] = await Promise.all([
      this.query<{ count: string }>(totalChunksSql, [since]),
      this.query<{ count: string }>(totalTasksSql, [since]),
      this.query<{ count: string }>(totalSkillsSql, [since]),
    ]);
    const totalChunks = totalChunksResult.rows[0];
    const totalTasks = totalTasksResult.rows[0];
    const totalSkills = totalSkillsResult.rows[0];

    const chunksByDaySql = `
      SELECT TO_CHAR(to_timestamp(created_at/1000), 'YYYY-MM-DD') as date, COUNT(*) as count
      FROM chunks
      WHERE created_at >= $1
      GROUP BY date
      ORDER BY date
    `;
    const chunksByDay = await this.query<{ date: string; count: string }>(chunksByDaySql, [since]);

    const eventsByTypeSql = `
      SELECT event_type as type, COUNT(*) as count
      FROM viewer_events
      WHERE created_at >= $1
      GROUP BY type
    `;
    const eventsByType = await this.query<{ type: string; count: string }>(eventsByTypeSql, [since]);

    return {
      totalChunks: parseInt(totalChunks.count, 10),
      totalTasks: parseInt(totalTasks.count, 10),
      totalSkills: parseInt(totalSkills.count, 10),
      chunksByDay: chunksByDay.rows.map((r) => ({ date: r.date, count: parseInt(r.count, 10) })),
      eventsByType: eventsByType.rows.map((r) => ({ type: r.type, count: parseInt(r.count, 10) })),
    };
  }

  async recordApiLog(
    toolName: string,
    input: unknown,
    output: string,
    durationMs: number,
    success: boolean
  ): Promise<void> {
    const sql = `
      INSERT INTO api_logs (tool_name, input, output, duration_ms, success, called_at)
      VALUES ($1, $2, $3, $4, $5, $6)
    `;
    await this.query(sql, [toolName, JSON.stringify(input), output, durationMs, success, Date.now()]);
  }

  async getApiLogs(
    limit: number = 50,
    offset: number = 0,
    toolFilter?: string
  ): Promise<Array<{
    id: number;
    toolName: string;
    input: unknown;
    output: string;
    durationMs: number;
    success: boolean;
    calledAt: number;
  }>> {
    let sql = `SELECT * FROM api_logs`;
    const params: unknown[] = [];
    let idx = 1;

    if (toolFilter) {
      sql += ` WHERE tool_name = $${idx++}`;
      params.push(toolFilter);
    }

    sql += ` ORDER BY called_at DESC LIMIT $${idx++} OFFSET $${idx++}`;
    params.push(limit, offset);

    const result = await this.query<Record<string, unknown>>(sql, params);
    return result.rows.map((row) => ({
      id: row.id as number,
      toolName: row.tool_name as string,
      input: JSON.parse(row.input as string),
      output: row.output as string,
      durationMs: row.duration_ms as number,
      success: row.success as boolean,
      calledAt: row.called_at as number,
    }));
  }

  async getApiLogToolNames(): Promise<string[]> {
    const sql = `SELECT DISTINCT tool_name FROM api_logs ORDER BY tool_name`;
    const result = await this.query<{ tool_name: string }>(sql);
    return result.rows.map((row) => row.tool_name);
  }

  async recordMergeHit(
    chunkId: string,
    action: "DUPLICATE" | "UPDATE",
    reason: string,
    oldSummary?: string,
    newSummary?: string
  ): Promise<void> {
    const sql = `
      INSERT INTO merge_history (chunk_id, action, reason, old_summary, new_summary, created_at)
      VALUES ($1, $2, $3, $4, $5, $6)
    `;
    await this.query(sql, [chunkId, action, reason, oldSummary ?? null, newSummary ?? null, Date.now()]);
  }

  async updateChunkSummaryAndContent(
    chunkId: string,
    newSummary: string,
    appendContent: string
  ): Promise<void> {
    const sql = `
      UPDATE chunks
      SET summary = $1, content = content || $2, updated_at = $3
      WHERE id = $4
    `;
    await this.query(sql, [newSummary, appendContent, Date.now(), chunkId]);
  }

  async recordToolCall(toolName: string, durationMs: number, success: boolean): Promise<void> {
    const sql = `
      INSERT INTO tool_calls (tool_name, duration_ms, success, called_at)
      VALUES ($1, $2, $3, $4)
    `;
    await this.query(sql, [toolName, durationMs, success, Date.now()]);
  }

  async getToolMetrics(minutes: number): Promise<{
    toolName: string;
    calls: number;
    successes: number;
    failures: number;
    avgDuration: number;
    minDuration: number;
    maxDuration: number;
  }[]> {
    const since = Date.now() - minutes * 60 * 1000;
    const sql = `
      SELECT
        tool_name,
        COUNT(*) as calls,
        SUM(CASE WHEN success THEN 1 ELSE 0 END) as successes,
        SUM(CASE WHEN NOT success THEN 1 ELSE 0 END) as failures,
        AVG(duration_ms) as avg_duration,
        MIN(duration_ms) as min_duration,
        MAX(duration_ms) as max_duration
      FROM tool_calls
      WHERE called_at >= $1
      GROUP BY tool_name
      ORDER BY calls DESC
    `;
    const result = await this.query<Record<string, unknown>>(sql, [since]);
    return result.rows.map((row) => ({
      toolName: row.tool_name as string,
      calls: parseInt(row.calls as string, 10),
      successes: parseInt(row.successes as string, 10),
      failures: parseInt(row.failures as string, 10),
      avgDuration: parseFloat(row.avg_duration as string) || 0,
      minDuration: parseInt(row.min_duration as string, 10),
      maxDuration: parseInt(row.max_duration as string, 10),
    }));
  }

  // ─── Task skill meta ──────────────────────────────────────────────────────

  async setTaskSkillMeta(
    taskId: string,
    meta: { skillStatus: string; skillReason: string }
  ): Promise<void> {
    // PostgreSQL doesn't support JSONB set like SQLite's json_each
    // This would require a separate table or JSONB column
    // For now, log a warning
    this.log.warn("[postgres] setTaskSkillMeta not fully implemented for PostgreSQL");
  }

  async getTasksBySkillStatus(statuses: string[]): Promise<Task[]> {
    const sql = `
      SELECT t.* FROM tasks t
      JOIN task_skills ts ON t.id = ts.task_id
      JOIN skills s ON ts.skill_id = s.id
      WHERE s.status = ANY($1)
      GROUP BY t.id
    `;
    const result = await this.query<Record<string, unknown>>(sql, [statuses]);
    return result.rows.map((row) => this.rowToTask(row));
  }

  // ─── Cleanup ───────────────────────────────────────────────────────────────

  async close(): Promise<void> {
    await this.pool.end();
    this.log.info("[postgres] Connection pool closed");
  }
}

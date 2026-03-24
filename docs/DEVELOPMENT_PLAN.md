# damxin/MemOS Fork 开发方案

## 项目路径

```
/home/memos/                                    ☁️ Cloud Plugin
/home/memoscode/                                📦 MemOS 核心 (Python)
/home/memoscode/apps/memos-local-openclaw/     📍 Local Plugin (参考实现)
```

## 开发目标

整合 Local Plugin 的优点到 MemOS 和 Cloud Plugin，实现：
1. **Hybrid Search** (RRF + MMR + 时间衰减)
2. **Task 摘要 + Skill 进化**
3. **Hub-Client 多 Agent 架构**
4. **Dashboard API**
5. **Cloud Plugin 增强**

---

## Phase 1: pgvector + Hybrid Search

### 目标
将 Local Plugin 的 Hybrid Search 能力整合到 MemOS Python

### 参考实现
```
/home/memoscode/apps/memos-local-openclaw/src/recall/
├── engine.ts (14KB)     — 检索引擎主逻辑
├── rrf.ts              — Reciprocal Rank Fusion
├── mmr.ts              — Maximal Marginal Relevance
└── recency.ts          — 时间衰减
```

### 新增文件

| # | 文件 | 路径 | 说明 |
|---|------|------|------|
| 1.1 | `search/hybrid_search.py` | `/home/memoscode/src/memos/search/` | RRF + MMR 混合搜索 |
| 1.2 | `search/rrf.py` | `/home/memoscode/src/memos/search/` | RRF 实现 |
| 1.3 | `search/mmr.py` | `/home/memoscode/src/memos/search/` | MMR 实现 |
| 1.4 | `search/recency.py` | `/home/memoscode/src/memos/search/` | 时间衰减 |
| 1.5 | `search/__init__.py` | `/home/memoscode/src/memos/search/` | 更新导出 |

### 修改文件

| # | 文件 | 路径 | 说明 |
|---|------|------|------|
| 1.6 | `vec_dbs/pgvector.py` | `/home/memoscode/src/memos/vec_dbs/` | 已有 (654行)，确认完善 |
| 1.7 | `vec_dbs/__init__.py` | `/home/memoscode/src/memos/vec_dbs/` | 更新导出 |
| 1.8 | `vec_dbs/factory.py` | `/home/memoscode/src/memos/vec_dbs/` | 注册 pgvector |

---

## Phase 2: Task 模块

### 目标
将 Local Plugin 的 Task 摘要功能移植到 Python

### 参考实现
```
/home/memoscode/apps/memos-local-openclaw/src/ingest/
├── task-processor.ts (20KB)  — Task 检测 + 摘要 + 存储
└── chunker.ts (6KB)         — 文本分块
```

### 新增文件

| # | 文件 | 路径 | 说明 |
|---|------|------|------|
| 2.1 | `mem_task/__init__.py` | `/home/memoscode/src/memos/mem_task/` | 模块导出 |
| 2.2 | `mem_task/base.py` | `/home/memoscode/src/memos/mem_task/` | Task 数据结构 |
| 2.3 | `mem_task/types.py` | `/home/memoscode/src/memos/mem_task/` | Task 类型定义 |
| 2.4 | `mem_task/summarizer.py` | `/home/memoscode/src/memos/mem_task/` | Task 摘要生成 |
| 2.5 | `mem_task/storage.py` | `/home/memoscode/src/memos/mem_task/` | Task 存储 |
| 2.6 | `mem_task/factory.py` | `/home/memoscode/src/memos/mem_task/` | Task Factory |

---

## Phase 3: Skill 模块

### 目标
将 Local Plugin 的 Skill 生命周期移植到 Python

### 参考实现
```
/home/memoscode/apps/memos-local-openclaw/src/skill/
├── generator.ts (23KB)   — Skill 生成
├── evolver.ts (16KB)    — Skill 进化
├── upgrader.ts (15KB)   — 版本升级
├── evaluator.ts (8KB)   — LLM 评估
├── validator.ts (9KB)    — 验证
└── installer.ts (5KB)   — 安装
```

### 新增文件

| # | 文件 | 路径 | 说明 |
|---|------|------|------|
| 3.1 | `mem_skill/__init__.py` | `/home/memoscode/src/memos/mem_skill/` | 模块导出 |
| 3.2 | `mem_skill/base.py` | `/home/memoscode/src/memos/mem_skill/` | Skill 数据结构 |
| 3.3 | `mem_skill/types.py` | `/home/memoscode/src/memos/mem_skill/` | Skill 类型定义 |
| 3.4 | `mem_skill/generator.py` | `/home/memoscode/src/memos/mem_skill/` | Skill 生成 |
| 3.5 | `mem_skill/evaluator.py` | `/home/memoscode/src/memos/mem_skill/` | Skill 评估 |
| 3.6 | `mem_skill/evolver.py` | `/home/memoscode/src/memos/mem_skill/` | Skill 进化 |
| 3.7 | `mem_skill/upgrader.py` | `/home/memoscode/src/memos/mem_skill/` | Skill 版本升级 |
| 3.8 | `mem_skill/installer.py` | `/home/memoscode/src/memos/mem_skill/` | Skill 安装 |
| 3.9 | `mem_skill/validator.py` | `/home/memoscode/src/memos/mem_skill/` | Skill 验证 |
| 3.10 | `mem_skill/storage.py` | `/home/memoscode/src/memos/mem_skill/` | Skill 存储 |
| 3.11 | `mem_skill/factory.py` | `/home/memoscode/src/memos/mem_skill/` | Skill Factory |

---

## Phase 4: Ingest Pipeline

### 目标
增强记忆摄入流程，添加智能去重和 LLM 判断

### 参考实现
```
/home/memoscode/apps/memos-local-openclaw/src/ingest/
├── dedup.ts            — 智能去重
├── chunker.ts          — 文本分块
└── worker.ts          — 异步 Worker

/home/memoscode/apps/memos-local-openclaw/src/shared/
└── llm-call.ts        — LLM 调用
```

### 新增文件

| # | 文件 | 路径 | 说明 |
|---|------|------|------|
| 4.1 | `mem_ingest/__init__.py` | `/home/memoscode/src/memos/mem_ingest/` | 模块导出 |
| 4.2 | `mem_ingest/dedup.py` | `/home/memoscode/src/memos/mem_ingest/` | 智能去重 |
| 4.3 | `mem_ingest/llm_judge.py` | `/home/memoscode/src/memos/mem_ingest/` | LLM 判断 |
| 4.4 | `mem_ingest/chunker.py` | `/home/memoscode/src/memos/mem_ingest/` | 文本分块 |
| 4.5 | `mem_ingest/pipeline.py` | `/home/memoscode/src/memos/mem_ingest/` | Ingest Pipeline |

---

## Phase 5: Hub-Client 架构

### 目标
将 Local Plugin 的 Hub-Client 多 Agent 架构移植到 Python

### 参考实现
```
/home/memoscode/apps/memos-local-openclaw/src/hub/
├── server.ts (52KB)     — Hub Server
├── user-manager.ts (6KB) — User 管理
└── auth.ts (2KB)        — 认证

/home/memoscode/apps/memos-local-openclaw/src/client/
└── index.ts            — Client SDK
```

### 新增文件

| # | 文件 | 路径 | 说明 |
|---|------|------|------|
| 5.1 | `mem_hub/__init__.py` | `/home/memoscode/src/memos/mem_hub/` | 模块导出 |
| 5.2 | `mem_hub/server.py` | `/home/memoscode/src/memos/mem_hub/` | Hub Server |
| 5.3 | `mem_hub/user_manager.py` | `/home/memoscode/src/memos/mem_hub/` | User 管理 |
| 5.4 | `mem_hub/auth.py` | `/home/memoscode/src/memos/mem_hub/` | 认证 |
| 5.5 | `mem_hub/client.py` | `/home/memoscode/src/memos/mem_hub/` | Client SDK |
| 5.6 | `mem_hub/models.py` | `/home/memoscode/src/memos/mem_hub/` | 数据模型 |

---

## Phase 6: Dashboard API

### 目标
提供 Dashboard 所需的 API

### 参考实现
```
/home/memoscode/apps/memos-local-openclaw/src/viewer/
└── server.ts (198KB)   — Dashboard Server
```

### 新增文件

| # | 文件 | 路径 | 说明 |
|---|------|------|------|
| 6.1 | `api/dashboard/__init__.py` | `/home/memoscode/src/memos/api/dashboard/` | 模块导出 |
| 6.2 | `api/dashboard/memories.py` | `/home/memoscode/src/memos/api/dashboard/` | Memories API |
| 6.3 | `api/dashboard/tasks.py` | `/home/memoscode/src/memos/api/dashboard/` | Tasks API |
| 6.4 | `api/dashboard/skills.py` | `/home/memoscode/src/memos/api/dashboard/` | Skills API |
| 6.5 | `api/dashboard/analytics.py` | `/home/memoscode/src/memos/api/dashboard/` | Analytics API |
| 6.6 | `api/dashboard/logs.py` | `/home/memoscode/src/memos/api/dashboard/` | Logs API |
| 6.7 | `api/dashboard/import_api.py` | `/home/memoscode/src/memos/api/dashboard/` | Import API |

---

## Phase 7: Cloud Plugin 增强

### 目标
将 Local Plugin 的能力扩展到 Cloud Plugin

### 路径
```
/home/memos/  (MemOS-Cloud-OpenClaw-Plugin)
```

### 新增文件

| # | 文件 | 路径 | 说明 |
|---|------|------|------|
| 7.1 | `lib/local-api-client.js` | `/home/memos/lib/` | 本地 MemOS API 客户端 |
| 7.2 | `lib/hybrid-search-client.js` | `/home/memos/lib/` | Hybrid Search 客户端 |
| 7.3 | `lib/task-client.js` | `/home/memos/lib/` | Task 客户端 |
| 7.4 | `lib/skill-client.js` | `/home/memos/lib/` | Skill 客户端 |

### 修改文件

| # | 文件 | 路径 | 说明 |
|---|------|------|------|
| 7.5 | `index.js` | `/home/memos/` | 主逻辑增强 |
| 7.6 | `lib/memos-cloud-api.js` | `/home/memos/lib/` | 添加本地调用 |
| 7.7 | `openclaw.plugin.json` | `/home/memos/` | 添加新配置项 |

---

## 测试

### 测试文件清单

| # | 测试文件 | 路径 | 对应模块 |
|---|----------|------|----------|
| T1 | `test_hybrid_search.py` | `/home/memoscode/tests/` | search/ |
| T2 | `test_rrf.py` | `/home/memoscode/tests/` | search/ |
| T3 | `test_mmr.py` | `/home/memoscode/tests/` | search/ |
| T4 | `test_recency.py` | `/home/memoscode/tests/` | search/ |
| T5 | `test_mem_task.py` | `/home/memoscode/tests/` | mem_task/ |
| T6 | `test_mem_skill.py` | `/home/memoscode/tests/` | mem_skill/ |
| T7 | `test_mem_ingest.py` | `/home/memoscode/tests/` | mem_ingest/ |
| T8 | `test_mem_hub.py` | `/home/memoscode/tests/` | mem_hub/ |
| T9 | `test_dashboard_api.py` | `/home/memoscode/tests/` | api/dashboard/ |
| T10 | `test_cloud_plugin.js` | `/home/memos/tests/` | Cloud Plugin |

---

## 开发顺序

```
Step 1: Phase 1 (pgvector + Hybrid Search) — 3-5天
Step 2: Phase 2 + Phase 4 (Task + Ingest) — 3-5天
Step 3: Phase 3 (Skill) — 5-7天
Step 4: Phase 7 (Cloud Plugin 增强) — 3-5天
Step 5: Phase 5 (Hub-Client) — 3-5天
Step 6: Phase 6 (Dashboard API) — 2-3天
Step 7: 测试 — 3-5天

总计: ~20-30天
```

---

## 代码量估算

| Phase | 新增文件 | 代码量 |
|-------|----------|--------|
| Phase 1 | 5 | ~500行 |
| Phase 2 | 6 | ~500行 |
| Phase 3 | 11 | ~1500行 |
| Phase 4 | 5 | ~600行 |
| Phase 5 | 6 | ~1200行 |
| Phase 6 | 7 | ~800行 |
| Phase 7 | 7 | ~750行 |
| **总计** | **47** | **~5850行** |

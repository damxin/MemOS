# OpenClaw 记忆迁移到 MemOS 指南

## 概述

本工具将 OpenClaw 的本地 SQLite 记忆数据库迁移到 MemOS 云/本地服务，实现：
- ✅ 保留所有历史记忆数据
- ✅ 支持批量迁移
- ✅ 保留原始元数据（路径、时间、模型等）
- ✅ 自动创建独立知识库（Memory Cube）

---

## 前置条件

### 1. 安装依赖

```bash
cd /home/memoscode
pip install requests
```

### 2. 准备 MemOS API Key

从 MemOS Dashboard 获取 API Key：
- 云服务：https://memos-dashboard.openmem.net/
- 本地服务：从你的 MemOS 配置中获取

### 3. 确认 OpenClaw 记忆数据库位置

默认位置：`/root/.openclaw/memory/main.sqlite`

查看数据库信息：
```bash
ls -lh /root/.openclaw/memory/
```

---

## 使用方法

### 1. 预览模式（推荐先执行）

查看将要迁移的记忆数据，不实际执行迁移：

```bash
cd /home/memoscode
python scripts/migrate_openclaw_to_memos.py \
  --api-key=mem_your_api_key_here \
  --dry-run \
  --limit 10
```

输出示例：
```
============================================================
OpenClaw → MemOS 记忆迁移工具
============================================================

[1/4] 读取 OpenClaw 记忆数据库：/root/.openclaw/memory/main.sqlite
  总记忆数：1234
  按来源：{'memory': 1200, 'file': 34}
  按模型：{'Qwen/Qwen3-Embedding-4B': 1234}
  最新时间：2026-03-21T10:00:00
  限制迁移：10 条

  [DRY RUN] 仅预览，不执行实际迁移

  预览前 10 条记忆:
  1. [memory/2026-02-01.md] # 2026-02-01 重要约定和规则...
  2. [memory/2026-02-02-2241.md] ## Session: 2026-02-02 22:41:25 UTC...
  ...
```

### 2. 执行迁移

#### 迁移到本地 MemOS 服务

```bash
python scripts/migrate_openclaw_to_memos.py \
  --api-key=mem_your_api_key_here \
  --memos-url=http://100.103.37.32:8000 \
  --user-id=rocket \
  --cube-name="OpenClaw Memories" \
  --batch-size=50
```

#### 迁移到 MemOS 云服务

```bash
python scripts/migrate_openclaw_to_memos.py \
  --api-key=mem_your_api_key_here \
  --memos-url=https://memos.memtensor.cn/api/openmem/v1 \
  --user-id=your_user_id \
  --cube-name="OpenClaw Memories"
```

#### 测试迁移（仅前 100 条）

```bash
python scripts/migrate_openclaw_to_memos.py \
  --api-key=mem_your_api_key_here \
  --limit 100
```

---

## 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--source` | `/root/.openclaw/memory/main.sqlite` | OpenClaw SQLite 数据库路径 |
| `--memos-url` | `http://100.103.37.32:8000` | MemOS API 地址 |
| `--api-key` | **必填** | MemOS API Key |
| `--user-id` | `openclaw-migrated` | MemOS 用户 ID |
| `--cube-name` | `OpenClaw Memories` | 目标知识库名称 |
| `--batch-size` | `50` | 每批次迁移数量 |
| `--dry-run` | 否 | 仅预览，不实际迁移 |
| `--limit` | 无 | 仅迁移前 N 条记忆（测试用） |

---

## 迁移后验证

### 1. 检查 MemOS 知识库

访问 MemOS Dashboard 或使用 API 查看：

```bash
curl -X GET "http://100.103.37.32:8000/api/openmem/v1/product/search" \
  -H "Authorization: Bearer mem_your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "rocket",
    "query": "openclaw",
    "limit": 5
  }'
```

### 2. 检查记忆标签

迁移的记忆会自动添加以下标签：
- `openclaw` - 标识来源
- `migrated` - 标识迁移数据
- `memory`/`file` - 原始来源类型

### 3. 检查元数据

每条记忆包含以下元数据：
- `original_id` - OpenClaw 原始 ID
- `original_path` - 原始文件路径
- `migrated_at` - 迁移时间
- `embedding_model` - 原始嵌入模型

---

## 故障排除

### 问题 1: API 连接失败

**错误**: `Connection refused` 或 `Timeout`

**解决**:
1. 确认 MemOS 服务正在运行
2. 检查防火墙设置
3. 验证 URL 是否正确

```bash
# 测试 API 连通性
curl http://100.103.37.32:8000/health
```

### 问题 2: API Key 无效

**错误**: `401 Unauthorized`

**解决**:
1. 确认 API Key 正确
2. 检查 API Key 是否过期
3. 重新生成 API Key

### 问题 3: 数据库文件不存在

**错误**: `unable to open database file`

**解决**:
```bash
# 确认数据库文件存在
ls -lh /root/.openclaw/memory/

# 如果有多个数据库，选择正确的
# main.sqlite - 主记忆
# code.sqlite - 代码记忆
# social.sqlite - 社交记忆
```

### 问题 4: 迁移中断

**解决**: 工具支持断点续传，重新运行即可。已迁移的记忆不会重复。

---

## 高级用法

### 迁移多个数据库

OpenClaw 可能有多个记忆数据库：

```bash
# 迁移主记忆
python scripts/migrate_openclaw_to_memos.py \
  --source=/root/.openclaw/memory/main.sqlite \
  --cube-name="OpenClaw Main" \
  --api-key=...

# 迁移代码记忆
python scripts/migrate_openclaw_to_memos.py \
  --source=/root/.openclaw/memory/code.sqlite \
  --cube-name="OpenClaw Code" \
  --api-key=...

# 迁移社交记忆
python scripts/migrate_openclaw_to_memos.py \
  --source=/root/.openclaw/memory/social.sqlite \
  --cube-name="OpenClaw Social" \
  --api-key=...
```

### 自定义批次大小

对于大量记忆，调整批次大小优化性能：

```bash
# 小批次（稳定）
--batch-size=20

# 大批次（快速）
--batch-size=100
```

### 保留向量嵌入

当前版本会重新生成向量嵌入（通过 MemOS）。如果需要保留原始嵌入，需要修改脚本直接使用 MemOS 的批量导入 API。

---

## 数据映射

| OpenClaw 字段 | MemOS 字段 | 说明 |
|--------------|-----------|------|
| `chunks.text` | `content` | 记忆内容 |
| `chunks.path` | `metadata.original_path` | 原始路径 |
| `chunks.id` | `metadata.original_id` | 原始 ID |
| `chunks.updated_at` | `metadata.migrated_at` | 迁移时间 |
| `chunks.source` | `tags` | 来源标签 |
| `chunks.model` | `metadata.embedding_model` | 嵌入模型 |

---

## 安全注意事项

1. **API Key 安全**: 不要在命令行中直接暴露 API Key，使用环境变量：
   ```bash
   export MEMOS_API_KEY=mem_your_key_here
   python scripts/migrate_openclaw_to_memos.py --api-key=$MEMOS_API_KEY
   ```

2. **备份数据库**: 迁移前备份 OpenClaw 数据库：
   ```bash
   cp /root/.openclaw/memory/main.sqlite /root/.openclaw/memory/main.sqlite.backup
   ```

3. **测试环境**: 先在测试环境验证，确认无误后再迁移生产数据。

---

## 技术支持

如有问题，请提供：
1. 完整的错误信息
2. 使用的命令参数
3. OpenClaw 和 MemOS 版本信息

---

*最后更新：2026-03-21*

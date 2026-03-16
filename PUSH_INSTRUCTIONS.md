# GitHub 推送指南

## 🚀 快速推送

在终端中执行：

```bash
cd /home/damxin/openclaw/memos/MemOS

# 方式1: 使用 GitHub CLI (推荐)
gh auth login
# 按提示完成浏览器认证
git push origin main

# 方式2: 使用 Personal Access Token
# 1. 访问 https://github.com/settings/tokens/new
# 2. 勾选 'repo' 权限，生成 Token
# 3. 使用 Token 推送:
git push https://damxin:YOUR_TOKEN@github.com/damxin/MemOS.git main

# 方式3: 使用 SSH (如果已配置)
git remote set-url origin git@github.com:damxin/MemOS.git
git push origin main
```

## 📊 当前状态

```
9945b98 chore: remove deployment scripts and temporary files
de5cb00 feat: update Docker configs to use 1panel-network and add deployment scripts
5e170d9 feat: add Docker Compose with PostgreSQL + pgvector + 1panel-network
af75142 feat: add PostgreSQL + pgvector vector storage backend
```

**领先远程**: 4 个提交

## 🗂️ 保留的核心文件

- `src/memos/vec_dbs/pgvector.py` (20,673 bytes) - pgvector 实现
- `src/memos/configs/vec_db.py` - PgVectorVecDBConfig 配置类
- `src/memos/vec_dbs/factory.py` - pgvector 后端注册
- `docker/docker-compose.yml` - 1panel-network 配置
- `pyproject.toml` - pgvector 依赖
- `.env` - 环境变量配置

## ✅ 清理的临时文件

- ✅ `deploy.sh`, `check-network.sh`, `push-to-github.sh`, `github-push.sh`
- ✅ `docker-compose.yml` (根目录), `.env.docker`
- ✅ `docker/postgres/init/`
- ✅ 临时文档文件 (PUSH-GUIDE.md, DEPLOYMENT_STATUS.md 等)

---

**执行完推送后，访问**: https://github.com/damxin/MemOS 查看更新

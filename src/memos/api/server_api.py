import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.staticfiles import StaticFiles

from memos.api.exceptions import APIExceptionHandler
from memos.api.middleware.request_context import RequestContextMiddleware
from memos.api.routers.server_router import router as server_router


load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="MemOS Server REST APIs",
    description="A REST API for managing multiple users with MemOS Server.",
    version="1.0.1",
)

app.mount("/download", StaticFiles(directory=os.getenv("FILE_LOCAL_PATH")), name="static_mapping")

app.add_middleware(RequestContextMiddleware, source="server_api")


@app.on_event("startup")
async def print_env_config():
    """打印所有关键环境变量，方便启动时确认配置"""
    print("=" * 60, flush=True)
    print("🚀 MemOS 启动配置检查", flush=True)
    print("=" * 60, flush=True)

    # 向量数据库配置
    print("📦 向量数据库配置:", flush=True)
    vec_backend = os.getenv("VECTOR_DB_BACKEND", os.getenv("MEMOS_VEC_DB_BACKEND", "未设置"))
    print(f"  VECTOR_DB_BACKEND: {vec_backend}", flush=True)

    if vec_backend == "pgvector" or os.getenv("PGVECTOR_HOST"):
        print(f"  PGVECTOR_HOST: {os.getenv('PGVECTOR_HOST', '未设置')}", flush=True)
        print(f"  PGVECTOR_PORT: {os.getenv('PGVECTOR_PORT', '未设置')}", flush=True)
        print(f"  PGVECTOR_DATABASE: {os.getenv('PGVECTOR_DATABASE', '未设置')}", flush=True)
        print(f"  PGVECTOR_USER: {os.getenv('PGVECTOR_USER', '未设置')}", flush=True)
        print(f"  PGVECTOR_PASSWORD: {'***' if os.getenv('PGVECTOR_PASSWORD') else '未设置'}", flush=True)
        print(f"  PGVECTOR_DIMENSION: {os.getenv('PGVECTOR_DIMENSION', '未设置')}", flush=True)

    # 嵌入模型配置
    print("🧠 嵌入模型配置:", flush=True)
    embed_api_base = os.getenv("MOS_EMBEDDER_API_BASE", "未设置")
    embed_model = os.getenv("MOS_EMBEDDER_MODEL", "未设置")
    embed_api_key = os.getenv("MOS_EMBEDDER_API_KEY", "")
    print(f"  MOS_EMBEDDER_API_BASE: {embed_api_base}", flush=True)
    print(f"  MOS_EMBEDDER_MODEL: {embed_model}", flush=True)
    print(f"  MOS_EMBEDDER_API_KEY: {'***' + embed_api_key[-4:] if len(embed_api_key) > 4 else '未设置'}", flush=True)

    # LLM配置
    print("💬 LLM配置:", flush=True)
    print(f"  OPENAI_API_BASE: {os.getenv('OPENAI_API_BASE', '未设置')}", flush=True)
    openai_key = os.getenv("OPENAI_API_KEY", "")
    print(f"  OPENAI_API_KEY: {'***' + openai_key[-4:] if len(openai_key) > 4 else '未设置'}", flush=True)
    print(f"  MOS_CHAT_MODEL: {os.getenv('MOS_CHAT_MODEL', '未设置')}", flush=True)

    # RabbitMQ配置
    print("🐰 RabbitMQ配置:", flush=True)
    print(f"  MEMOS_ENABLE_RABBITMQ: {os.getenv('MEMOS_ENABLE_RABBITMQ', '未设置')}", flush=True)
    print(f"  MEMSCHEDULER_RABBITMQ_HOST_NAME: {os.getenv('MEMSCHEDULER_RABBITMQ_HOST_NAME', '未设置')}", flush=True)

    # Neo4j配置
    print("🕸️ Neo4j配置:", flush=True)
    print(f"  NEO4J_URI: {os.getenv('NEO4J_URI', '未设置')}", flush=True)
    neo4j_password = os.getenv("NEO4J_PASSWORD", "")
    print(f"  NEO4J_PASSWORD: {'***' if neo4j_password else '未设置'}", flush=True)

    # 其他关键配置
    print("⚙️ 其他配置:", flush=True)
    print(f"  MOS_USER_ID: {os.getenv('MOS_USER_ID', '未设置')}", flush=True)
    print(f"  MOS_TEXT_MEM_TYPE: {os.getenv('MOS_TEXT_MEM_TYPE', '未设置')}", flush=True)
    print(f"  MOS_TOP_K: {os.getenv('MOS_TOP_K', '未设置')}", flush=True)

    print("=" * 60, flush=True)
    print("✅ 配置检查完成，请确认以上配置是否正确", flush=True)
    print("=" * 60, flush=True)


# Include routers
app.include_router(server_router)

# Request validation failed
app.exception_handler(RequestValidationError)(APIExceptionHandler.validation_error_handler)
# Invalid business code parameters
app.exception_handler(ValueError)(APIExceptionHandler.value_error_handler)
# Business layer manual exception
app.exception_handler(HTTPException)(APIExceptionHandler.http_error_handler)
# Fallback for unknown errors
app.exception_handler(Exception)(APIExceptionHandler.global_exception_handler)


if __name__ == "__main__":
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    uvicorn.run("memos.api.server_api:app", host="0.0.0.0", port=args.port, workers=args.workers)

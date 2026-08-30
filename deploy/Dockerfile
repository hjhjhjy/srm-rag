# ---------- 后端镜像：Python 3.11-slim + uvicorn ----------
FROM python:3.11-slim AS backend

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先装依赖（利用层缓存）
COPY backend/pyproject.toml ./pyproject.toml
RUN pip install --upgrade pip && \
    # torch 走 CPU 索引，避免拉取 2.5GB 的 CUDA 版本
    pip install torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install fastapi uvicorn[standard] pydantic pydantic-settings httpx \
    sqlalchemy scikit-learn numpy jieba slowapi prometheus-client structlog \
    "python-jose[cryptography]" "passlib[bcrypt]" python-docx \
    sentence-transformers psycopg2-binary rank-bm25 chromadb

# 复制源码
COPY backend/ ./

# 运行时数据卷（知识库索引 / SQLite）挂载到 /app/app/data
RUN mkdir -p /app/app/data

EXPOSE 8000
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"]

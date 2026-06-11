# ============================================================
# DeepAgent Chat — Docker 多阶段构建
# ============================================================
# 构建阶段
FROM python:3.12-slim AS builder

WORKDIR /build

# 编译依赖（chromadb onnx 需要 gcc，cryptography 需要 libffi-dev）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# ============================================================
# 运行阶段
FROM python:3.12-slim

WORKDIR /app

# 运行时系统依赖
#   libsqlite3-0  — chromadb
#   libmagic1     — python-magic（文件上传 MIME 检测）
#   libmagic-mgc  — magic byte 数据库
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsqlite3-0 \
    libmagic1 \
    libmagic-mgc \
    && rm -rf /var/lib/apt/lists/*

# 从构建阶段复制已安装的包到公共路径（避免 /root 目录 700 权限限制）
COPY --from=builder /root/.local /usr/local
ENV PATH=/usr/local/bin:$PATH

# 复制项目代码
COPY . .

# 创建非 root 用户（uid=1000），降低沙箱逃逸风险
RUN useradd -m -u 1000 appuser \
    && chown -R appuser:appuser /app

# 运行时数据目录（挂载为 volume）
RUN mkdir -p /data/uploads /data/chroma_data /data/instance /data/logs \
    && chown -R appuser:appuser /data

# 默认使用 SQLite，可通过环境变量切换为 MySQL
ENV FLASK_ENV=production
ENV DATABASE_URL=sqlite:////data/instance/app.db
ENV UPLOAD_DIR=/data/uploads
ENV CHROMA_PERSIST_DIR=/data/chroma_data
ENV SANDBOX_DIR=/app/sandbox

# 入口脚本：启动时自动修复 /data 权限，然后降权到 appuser 运行
ENTRYPOINT ["python", "/app/entrypoint.py"]

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000')" || exit 1

# 使用 Waitress 生产服务器（多线程）
EXPOSE 5000
CMD ["waitress-serve", "--host=0.0.0.0", "--port=5001", "--threads=20", "run:app"]

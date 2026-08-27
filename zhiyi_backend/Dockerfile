# =============================================================================
# 智医 (ZhiYi) — 后端 Dockerfile
# 基层医疗AI辅助诊疗平台
# =============================================================================

FROM python:3.13-slim

# 系统依赖 + UTF-8 locale
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    locales \
    && echo "en_US.UTF-8 UTF-8" > /etc/locale.gen \
    && locale-gen en_US.UTF-8 \
    && rm -rf /var/lib/apt/lists/*
ENV LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8 \
    PYTHONIOENCODING=utf-8 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制源码
COPY app/ ./app/

# 非 root 运行
RUN useradd --create-home --uid 10001 appuser
USER appuser

# 暴露端口
EXPOSE 8000

# 启动
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
# pip 源可配置：默认官方 PyPI（海外机器友好），
# 国内机器可构建时指定 --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
# 或 docker-compose 里设环境变量 PIP_INDEX_URL
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install --no-cache-dir -r requirements.txt -i ${PIP_INDEX_URL}
COPY app ./app
ENV PTGEN_PASSWORD=ptgen2024 \
    PTGEN_CACHE_DIR=/app/cache
EXPOSE 8737
HEALTHCHECK --interval=60s --timeout=10s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8737/healthz', timeout=8).status==200 else 1)" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8737", "--workers", "2"]

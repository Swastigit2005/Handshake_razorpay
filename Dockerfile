# One command to a running console:
#   docker build -t handshake . && docker run -p 8000:8000 handshake
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HS_PAYMENTS=sim \
    HS_BUYERS=heuristic \
    HS_DEMO_MODE=1 \
    PORT=8000

WORKDIR /app

COPY pyproject.toml README.md ./
COPY handshake ./handshake
COPY assets ./assets

RUN pip install --upgrade pip && pip install ".[console,live,dev]"

RUN mkdir -p /app/runs /app/data && \
    useradd --create-home --uid 10001 handshake && \
    chown -R handshake:handshake /app
USER handshake

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=4s --start-period=8s --retries=3 \
  CMD python -c "import urllib.request,os,sys; \
url='http://127.0.0.1:'+os.environ.get('PORT','8000')+'/healthz'; \
sys.exit(0 if urllib.request.urlopen(url, timeout=3).status==200 else 1)"

CMD ["sh", "-c", "python -m uvicorn handshake.server.app:app --host 0.0.0.0 --port ${PORT:-8000}"]

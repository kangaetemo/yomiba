# Yomiba backend: one uvicorn process, one worker (see PRODUCTION.md).
# The SQLite DB and covers live on the /data volume, never in the image.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Fixed uid so the host can own the bind-mounted /data directory.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin yomiba \
    && mkdir -p /data && chown yomiba:yomiba /data
USER yomiba

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=4).status == 200 else 1)"

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

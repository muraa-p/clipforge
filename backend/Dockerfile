# ClipForge engine — the part that downloads + encodes (cannot run on Vercel).
#
# Build from the repo's clipforge/backend directory:
#   docker build -t clipforge-engine ./backend
#   docker run -p 8000:8000 -e CLIPFORGE_ACCESS_TOKEN=secret \
#     -v clipforge-data:/app/data clipforge-engine
#
# Or, from the clipforge/ root:  docker compose up -d
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# FFmpeg is the only external binary we need; yt-dlp ships as a Python library.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY app ./app

# Run as an unprivileged user; the named volume is chowned below.
RUN useradd --create-home --uid 10001 clipforge \
    && mkdir -p /app/data \
    && chown -R clipforge:clipforge /app
USER clipforge

EXPOSE 8000

# The engine holds its job queue in-process, so a single worker is required
# (concurrency is provided by background threads, capped by
# CLIPFORGE_MAX_CONCURRENT_JOBS). --proxy-headers makes it correct behind a
# reverse proxy / tunnel.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status==200 else 1)"

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*", \
     "--timeout-keep-alive", "30"]

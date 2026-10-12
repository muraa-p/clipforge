"""ClipForge API — a free, fully local video→short generator."""

from __future__ import annotations

import mimetypes
import os
import re
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

# Windows consoles default to cp1252; log messages include unicode (…, →).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from . import bins, llm, pipeline, store, transcribe
from .jobs import manager
from .config import ASPECT_PRESETS, DEFAULT_FRAME_MODE, FRAME_MODES, OUTPUT_DIR


def _cleanup_janitor() -> None:
    """Periodically delete stale sources/outputs on long-running deployments."""
    while True:
        time.sleep(1800)
        try:
            store.cleanup_old()
        except Exception:  # noqa: BLE001 - never let the janitor die
            pass


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        store.cleanup_old()
    except Exception:  # noqa: BLE001
        pass
    threading.Thread(target=_cleanup_janitor, name="janitor", daemon=True).start()
    yield


app = FastAPI(title="ClipForge", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Optional shared secret. Set CLIPFORGE_ACCESS_TOKEN before exposing this API
# through a tunnel; the frontend sends it as a header (and ?token= on media).
ACCESS_TOKEN = os.environ.get("CLIPFORGE_ACCESS_TOKEN", "").strip()


@app.middleware("http")
async def require_token(request: Request, call_next):
    # Health stays public so uptime checks / Docker healthchecks work.
    if (
        ACCESS_TOKEN
        and request.url.path.startswith("/api")
        and request.url.path != "/api/health"
    ):
        supplied = request.headers.get("x-clipforge-token") or request.query_params.get("token")
        if supplied != ACCESS_TOKEN:
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
    return await call_next(request)

VIDEO_MIME = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".mov": "video/quicktime",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".ass": "text/plain",
    ".vtt": "text/vtt",
}


class AiConfig(BaseModel):
    """Bring-your-own-key AI analysis config (all fields optional)."""

    provider: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None


class AnalyzeRequest(BaseModel):
    url: str = Field(..., min_length=4)
    clip_seconds: int | None = Field(default=None, ge=8, le=120)
    max_candidates: int | None = Field(default=None, ge=1, le=20)
    use_ai: bool = Field(default=True)
    ai: AiConfig | None = Field(default=None)


class RenderRequest(BaseModel):
    video_id: str
    start: float = Field(..., ge=0)
    end: float = Field(..., gt=0)
    aspect: str = Field(default="9:16")
    mode: str = Field(default="blur")
    captions: bool = Field(default=True)


# --------------------------------------------------------------------------- #
# Status
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health() -> dict[str, object]:
    ffmpeg = bins.find_ffmpeg()
    return {
        "ok": True,
        "ffmpeg": bins.ffmpeg_version(ffmpeg) if ffmpeg else None,
        "ffmpeg_installed": ffmpeg is not None,
        "yt_dlp": True,
        "whisper": transcribe.whisper_available(),
        "llm": llm.describe(),
        "aspects": list(ASPECT_PRESETS.keys()),
        "modes": list(FRAME_MODES),
    }


@app.get("/api/providers")
def providers() -> dict[str, object]:
    """Free/pluggable AI providers the UI can offer (bring your own key)."""
    return {"presets": llm.presets_for_ui()}


@app.get("/")
def root() -> dict[str, object]:
    return {
        "message": "ClipForge API. POST /api/analyze with {url} to start.",
        "docs": "/docs",
    }


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #
@app.post("/api/analyze")
def start_analyze(request: AnalyzeRequest) -> dict[str, object]:
    if not manager.has_capacity():
        raise HTTPException(429, "Engine is busy — too many jobs queued. Try again shortly.")
    job = manager.create("analyze")
    manager.spawn(
        job,
        lambda j: pipeline.analyse_url(
            j,
            url=request.url.strip(),
            clip_seconds=request.clip_seconds,
            max_candidates=request.max_candidates,
            use_ai=request.use_ai,
            ai_override=request.ai.model_dump() if request.ai else None,
        ),
    )
    return {"job_id": job.id}


@app.post("/api/render")
def start_render(request: RenderRequest) -> dict[str, object]:
    if request.aspect not in ASPECT_PRESETS:
        raise HTTPException(400, f"aspect must be one of {list(ASPECT_PRESETS)}")
    if request.mode not in FRAME_MODES:
        raise HTTPException(400, f"mode must be one of {FRAME_MODES}")
    if request.end <= request.start:
        raise HTTPException(400, "end must be greater than start")
    if not manager.has_capacity():
        raise HTTPException(429, "Engine is busy — too many jobs queued. Try again shortly.")

    job = manager.create("render")
    manager.spawn(
        job,
        lambda j: pipeline.render_clip(
            j,
            video_id=request.video_id,
            start=request.start,
            end=request.end,
            aspect=request.aspect,
            mode=request.mode,
            captions=request.captions,
        ),
    )
    return {"job_id": job.id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, object]:
    job = manager.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job.to_dict()


@app.get("/api/records/{video_id}")
def get_record(video_id: str) -> dict[str, object]:
    record = store.load_record(video_id)
    if not record:
        raise HTTPException(404, "record not found")
    return record


# --------------------------------------------------------------------------- #
# Media (with HTTP Range so <video> can seek in the browser)
# --------------------------------------------------------------------------- #
def _mime_for(path: Path) -> str:
    return VIDEO_MIME.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _stream_file(path: Path, request: Request, media_type: str) -> Response:
    size = path.stat().st_size
    range_header = request.headers.get("range")

    if range_header:
        match = re.match(r"bytes=(\d*)-(\d*)", range_header)
        if match:
            start_str, end_str = match.groups()
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else size - 1
            end = max(start, min(end, size - 1))
            length = end - start + 1

            def iterator():
                with open(path, "rb") as handle:
                    handle.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = handle.read(min(1024 * 256, remaining))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk

            return StreamingResponse(
                iterator(),
                status_code=206,
                media_type=media_type,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{size}",
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(length),
                },
            )

    return FileResponse(path, media_type=media_type, headers={"Accept-Ranges": "bytes"})


@app.get("/api/media/{video_id}/{filename}")
def media(video_id: str, filename: str, request: Request) -> Response:
    target = store.video_dir(video_id) / os.path.basename(filename)
    _require_file(target, "source media not found")
    return _stream_file(target, request, _mime_for(target))


def _resolve_output(filename: str) -> Path:
    # ``filename`` may contain a sub-directory (video_id-slug-stamp/short.mp4).
    target = (OUTPUT_DIR / filename).resolve()
    root = OUTPUT_DIR.resolve()
    if root != target and root not in target.parents:
        raise HTTPException(404, "output not found")
    return target


@app.get("/api/output/{video_id}/{filename:path}")
def output(video_id: str, filename: str, request: Request) -> Response:
    target = _resolve_output(filename)
    _require_file(target, "output not found")
    return _stream_file(target, request, _mime_for(target))


def _require_file(path: Path, message: str) -> None:
    if not path.exists() or not path.is_file():
        raise HTTPException(404, message)


# --------------------------------------------------------------------------- #
# Launcher
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
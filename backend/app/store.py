"""Tiny on-disk record store for analysed videos."""

from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from .config import DATA_TTL_HOURS, OUTPUT_DIR, VIDEOS_DIR


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def safe_slug(text: str, fallback: str = "clip") -> str:
    text = re.sub(r"[^\w\s-]", "", text or "").strip().lower()
    text = re.sub(r"[\s_-]+", "-", text)
    return (text[:48] or fallback).strip("-") or fallback


def video_dir(video_id: str) -> Path:
    path = VIDEOS_DIR / video_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def record_path(video_id: str) -> Path:
    return video_dir(video_id) / "record.json"


def save_record(video_id: str, record: dict[str, Any]) -> None:
    record = {**record, "id": video_id, "updated_at": time.time()}
    record_path(video_id).write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_record(video_id: str) -> dict[str, Any] | None:
    path = record_path(video_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def cleanup_old(ttl_hours: float | None = None) -> int:
    """Delete source/output folders older than the TTL. Returns how many went.

    Keeps a long-running public engine from filling its disk. ``0`` disables it.
    """
    ttl = DATA_TTL_HOURS if ttl_hours is None else ttl_hours
    if ttl <= 0:
        return 0
    cutoff = time.time() - ttl * 3600
    removed = 0
    for root in (VIDEOS_DIR, OUTPUT_DIR):
        if not root.exists():
            continue
        for entry in root.iterdir():
            try:
                if entry.is_dir() and entry.stat().st_mtime < cutoff:
                    shutil.rmtree(entry, ignore_errors=True)
                    removed += 1
            except OSError:
                continue
    return removed

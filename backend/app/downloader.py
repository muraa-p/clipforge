"""Thin wrapper around yt-dlp (free, open-source) for metadata, media and subs.

yt-dlp supports 1000+ sites (YouTube, TikTok, Instagram, X, Vimeo, ...). It is
invoked as a Python library, so no separate executable is needed.
"""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import yt_dlp  # type: ignore

from .bins import find_ffmpeg
from .config import COOKIES_FILE_ENV, MAX_SOURCE_HEIGHT, SUBTITLE_LANGS

Hook = Callable[[float, str], None]


def assert_public_url(url: str) -> None:
    """Reject non-http(s) and private/loopback hosts (basic SSRF guard).

    yt-dlp only fetches media pages, but when the engine is exposed publicly we
    don't want it used to probe the host's own network.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http(s) video links are supported.")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("That link has no host name.")
    if host == "localhost" or host.endswith(".local") or host.endswith(".internal"):
        raise ValueError("Local addresses are not allowed.")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return  # a normal hostname; let yt-dlp resolve it
    if not ip.is_global:
        raise ValueError("Private or reserved addresses are not allowed.")


def _base_opts(ffmpeg_path: str | None = None) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 3,
        "socket_timeout": 30,
        "http_headers": {"User-Agent": "Mozilla/5.0 ClipForge/0.1"},
    }
    cookies = Path(COOKIES_FILE_ENV)
    if cookies.exists():
        opts["cookiefile"] = str(cookies)
    if ffmpeg_path:
        opts["ffmpeg_location"] = str(Path(ffmpeg_path).parent)
    return opts


def sanitize_info(info: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": info.get("title") or "Untitled video",
        "uploader": info.get("uploader") or info.get("channel") or "Unknown",
        "thumbnail": info.get("thumbnail"),
        "duration": float(info.get("duration") or 0),
        "webpage_url": info.get("webpage_url") or info.get("original_url") or "",
        "extractor": info.get("extractor_key") or "unknown",
        "view_count": info.get("view_count"),
    }


def probe(url: str) -> dict[str, Any]:
    """Fetch metadata without downloading the video."""
    with yt_dlp.YoutubeDL(_base_opts()) as ydl:
        info = ydl.extract_info(url, download=False)
        return sanitize_info(info)


def download(
    url: str,
    out_dir: Path,
    report: Hook | None = None,
) -> Path:
    """Download a reasonable-quality local MP4 (<=1080p) into ``out_dir``."""
    ffmpeg = find_ffmpeg()

    def progress_hook(data: dict[str, Any]) -> None:
        if report is None:
            return
        if data.get("status") == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            done = data.get("downloaded_bytes") or 0
            if total:
                report(min(0.98, done / total), "Downloading video…")

    opts: dict[str, Any] = _base_opts(ffmpeg)
    opts.update(
        {
            "format": (
                "bestvideo[height<={maxh}][ext=mp4]+bestaudio[ext=m4a]"
                "/best[height<={maxh}][ext=mp4]"
                "/best[height<={maxh}]/best"
            ).format(maxh=MAX_SOURCE_HEIGHT),
            "merge_output_format": "mp4",
            "outtmpl": str(out_dir / "source.%(ext)s"),
            "restrictfilenames": True,
            "progress_hooks": [progress_hook],
        }
    )

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

    candidates = list(out_dir.glob("source.*"))
    if not candidates:
        # Some postprocessing renames; fall back to whatever yt-dlp produced.
        candidates = [p for p in out_dir.iterdir() if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov")]
    if not candidates:
        raise RuntimeError(f"Download finished with no media file for: {url}")

    best = max(candidates, key=lambda p: p.stat().st_size)
    # Normalise extension to .mp4 where possible (yt-dlp merges to mp4 already).
    if best.suffix.lower() != ".mp4":
        renamed = best.with_suffix(".mp4")
        if not renamed.exists():
            best.rename(renamed)
            best = renamed
    return best


def fetch_captions(url: str, out_dir: Path, report: Hook | None = None) -> list[Path]:
    """Download the best available subtitle track as WebVTT, if any.

    Prefers manual subtitles, falls back to automatic captions (e.g. YouTube).
    """
    opts: dict[str, Any] = _base_opts()
    opts.update(
        {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": SUBTITLE_LANGS,
            "subtitlesformat": "vtt",
            "outtmpl": str(out_dir / "subs.%(ext)s"),
        }
    )
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
    except Exception:  # noqa: BLE001 - subs are optional
        if report:
            report(0.0, "No captions available")
        return []

    vtt_files = sorted(out_dir.glob("subs*.vtt"))
    if report and vtt_files:
        report(1.0, f"Captions: {vtt_files[0].name}")
    return vtt_files
"""Locate (and if necessary download) the free external binaries we rely on.

ClipForge needs exactly one external program: **FFmpeg** (LGPL/GPL, free).
We look for it in this order:

  1. ``CLIPFORGE_FFMPEG`` / ``FFMPEG_BINARY`` environment variables
  2. the system ``PATH``
  3. ``backend/bin/ffmpeg(.exe)`` (downloaded by :func:`ensure_ffmpeg`)
  4. the ``imageio-ffmpeg`` Python wheel (bundles a static ffmpeg)

``yt-dlp`` is used as a Python library, so no separate binary is required.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from .config import BIN_DIR

FFMPEG_URLS = {
    "win32": "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    "linux": "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
    "darwin": "https://evermeet.cx/ffmpeg/getrelease/zip",
}

_EXE = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"


def _is_executable(path: str | os.PathLike[str] | None) -> bool:
    if not path:
        return False
    p = Path(path)
    return p.exists() and (os.name == "nt" or os.access(p, os.X_OK))


def find_ffmpeg() -> str | None:
    """Return a usable ffmpeg path or ``None``."""
    for env_name in ("CLIPFORGE_FFMPEG", "FFMPEG_BINARY", "FFMPEG_PATH"):
        candidate = os.environ.get(env_name)
        if _is_executable(candidate):
            return str(candidate)

    on_path = shutil.which("ffmpeg")
    if on_path:
        return on_path

    local = BIN_DIR / _EXE
    if _is_executable(local):
        return str(local)

    try:  # optional bundled binary (pip install imageio-ffmpeg)
        import imageio_ffmpeg  # type: ignore

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if _is_executable(bundled):
            return str(bundled)
    except Exception:
        pass

    return None


def _download(url: str, dest: Path, log=print) -> Path:
    log(f"Downloading {url}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url) as response, open(tmp, "wb") as handle:
        total = int(response.headers.get("Content-Length") or 0)
        read = 0
        while True:
            chunk = response.read(1024 * 256)
            if not chunk:
                break
            handle.write(chunk)
            read += len(chunk)
            if total:
                pct = read * 100 // total
                log(f"  {pct:3d}%  ({read // 1_048_576} MiB)")
    tmp.replace(dest)
    return dest


def _extract_ffmpeg(archive: Path, log=print) -> Path:
    target = BIN_DIR / _EXE
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as zf:
            members = [m for m in zf.namelist() if Path(m).name == _EXE]
            if not members:
                raise RuntimeError("ffmpeg executable not found inside archive")
            with zf.open(members[0]) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
    elif archive.suffix == ".xz":
        with tarfile.open(archive) as tf:
            members = [m for m in tf.getmembers() if Path(m.name).name == _EXE]
            if not members:
                raise RuntimeError("ffmpeg executable not found inside archive")
            extracted = tf.extractfile(members[0])
            if extracted is None:
                raise RuntimeError("could not read ffmpeg from archive")
            with open(target, "wb") as dst:
                shutil.copyfileobj(extracted, dst)
    else:  # pragma: no cover - guard rail
        raise RuntimeError(f"Unsupported archive type: {archive.suffix}")

    target.chmod(target.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    log(f"ffmpeg installed at {target}")
    return target


def install_ffmpeg(log=print) -> str:
    """Download a free static FFmpeg build into ``backend/bin``."""
    platform = {"nt": "win32"}.get(os.name, os.name)
    url = FFMPEG_URLS.get(platform)
    if not url:
        raise RuntimeError(
            "Automatic FFmpeg install is only supported on Windows, Linux and macOS.\n"
            "Install FFmpeg manually and set CLIPFORGE_FFMPEG=/path/to/ffmpeg"
        )

    suffix = ".zip" if platform in ("win32", "darwin") else ".xz"
    archive = BIN_DIR / f"ffmpeg-download{suffix}"
    _download(url, archive, log=log)
    try:
        return str(_extract_ffmpeg(archive, log=log))
    finally:
        archive.unlink(missing_ok=True)


def ensure_ffmpeg(log=print) -> str:
    existing = find_ffmpeg()
    if existing:
        return existing
    return install_ffmpeg(log=log)


def ffmpeg_version(ffmpeg: str) -> str:
    try:
        out = subprocess.run(
            [ffmpeg, "-version"], capture_output=True, text=True, timeout=20
        )
        return out.stdout.splitlines()[0] if out.stdout else "unknown"
    except Exception as exc:  # pragma: no cover - diagnostics only
        return f"unavailable ({exc})"

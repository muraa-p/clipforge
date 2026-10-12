"""Central configuration and filesystem paths for ClipForge.

Everything here is intentionally free / offline friendly:
  * data + binaries live next to the backend, nothing is uploaded anywhere
  * all tunables can be overridden with environment variables
"""

from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
BACKEND_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.environ.get("CLIPFORGE_DATA_DIR", str(BACKEND_DIR / "data")))
BIN_DIR = Path(os.environ.get("CLIPFORGE_BIN_DIR", str(BACKEND_DIR / "bin")))
VIDEOS_DIR = DATA_DIR / "videos"
OUTPUT_DIR = DATA_DIR / "output"
COOKIES_FILE = DATA_DIR / "cookies.txt"

for _directory in (DATA_DIR, BIN_DIR, VIDEOS_DIR, OUTPUT_DIR):
    _directory.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------- #
# Sourcing
# --------------------------------------------------------------------------- #
# Keep source resolution sane so CPU-only machines stay fast.
MAX_SOURCE_HEIGHT = int(os.environ.get("CLIPFORGE_MAX_HEIGHT", "1080"))

# Optional cookie jar for sites that require a login (Instagram / Facebook / X ...).
# Drop a Netscape-format cookies.txt at data/cookies.txt and it is used automatically.
COOKIES_FILE_ENV = os.environ.get("CLIPFORGE_COOKIES", str(COOKIES_FILE))

# Preferred caption languages, in priority order.
SUBTITLE_LANGS = [
    lang.strip()
    for lang in os.environ.get("CLIPFORGE_SUBTITLE_LANGS", "en,en-US,en-GB").split(",")
    if lang.strip()
]

# --------------------------------------------------------------------------- #
# Clipping
# --------------------------------------------------------------------------- #
DEFAULT_CLIP_SECONDS = int(os.environ.get("CLIPFORGE_CLIP_SECONDS", "45"))
MIN_CLIP_SECONDS = 8
MAX_CLIP_SECONDS = 120
MAX_CANDIDATES = int(os.environ.get("CLIPFORGE_MAX_CANDIDATES", "8"))

# name -> (width, height)
ASPECT_PRESETS: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "4:5": (1080, 1350),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
}
DEFAULT_ASPECT = "9:16"

# "crop" = fill the frame (center crop), "blur" = fit + blurred background.
FRAME_MODES = ("crop", "blur")
DEFAULT_FRAME_MODE = "blur"

# --------------------------------------------------------------------------- #
# Encoding
# --------------------------------------------------------------------------- #
VIDEO_CODEC_ARGS = [
    "-c:v", "libx264",
    "-preset", os.environ.get("CLIPFORGE_X264_PRESET", "veryfast"),
    "-crf", os.environ.get("CLIPFORGE_X264_CRF", "20"),
    "-pix_fmt", "yuv420p",
    "-profile:v", "high",
    "-r", "30",
]
AUDIO_CODEC_ARGS = ["-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "44100"]
OUTPUT_MOVFLAGS = ["-movflags", "+faststart"]

# Subtitle burn-in
CAPTION_FONT = os.environ.get("CLIPFORGE_FONT", "Arial")
CAPTION_MAX_CHARS_PER_LINE = 20
CAPTION_MAX_LINES = 2

# --------------------------------------------------------------------------- #
# Public-deployment safety
# --------------------------------------------------------------------------- #
# Each job is CPU/IO heavy, so cap how many run at once; extras stay "queued".
MAX_CONCURRENT_JOBS = int(os.environ.get("CLIPFORGE_MAX_CONCURRENT_JOBS", "2"))
# Reject brand-new jobs once this many are queued/running (HTTP 429).
MAX_QUEUED_JOBS = int(os.environ.get("CLIPFORGE_MAX_QUEUED_JOBS", "8"))
# Auto-delete downloaded sources + rendered shorts older than this many hours
# so a long-running public engine can't fill its disk (0 disables cleanup).
DATA_TTL_HOURS = float(os.environ.get("CLIPFORGE_DATA_TTL_HOURS", "24"))


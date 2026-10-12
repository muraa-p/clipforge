"""FFmpeg commands: clipping, vertical reframing and caption burn-in."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable

from .captions import build_ass
from .config import (
    ASPECT_PRESETS,
    AUDIO_CODEC_ARGS,
    OUTPUT_MOVFLAGS,
    VIDEO_CODEC_ARGS,
)

Hook = Callable[[float, str], None]

_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def probe_duration(media_path: str | Path, ffmpeg: str) -> float:
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(media_path)],
        capture_output=True,
        text=True,
    )
    match = _DURATION_RE.search(result.stderr)
    if not match:
        return 0.0
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _build_filter(width: int, height: int, mode: str, ass_name: str | None) -> str:
    if mode == "crop":
        # Fill the frame with a center crop.
        chain = (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}"
        )
    else:  # "blur" — fit video over a blurred, stretched background
        chain = (
            f"[0:v]split=2[bg][fg];"
            f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},gblur=sigma=30:steps=2[bgblur];"
            f"[fg]scale={width}:{height}:force_original_aspect_ratio=decrease[fgfit];"
            f"[bgblur][fgfit]overlay=(W-w)/2:(H-h)/2"
        )

    # ass= path is resolved relative to the process CWD, which callers set to
    # the output directory — avoids Windows path-escape pain. It must be part
    # of the same chain (before the final label).
    if ass_name:
        chain += f",ass={ass_name}"
    chain += "[vout]"
    return chain


def _supports_subtitles_filter(ffmpeg: str) -> bool:
    try:
        out = subprocess.run(
            [ffmpeg, "-hide_banner", "-filters"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return "subtitles" in out.stdout or "ass" in out.stdout
    except Exception:  # noqa: BLE001
        return False


def render_clip(
    *,
    source: str | Path,
    out_dir: Path,
    start: float,
    end: float,
    ffmpeg: str,
    aspect: str = "9:16",
    mode: str = "blur",
    captions: bool = True,
    cues: list | None = None,
    output_basename: str = "short",
    report: Hook | None = None,
) -> dict[str, object]:
    """Cut [start, end) from the source and export a vertical short.

    Returns ``{"file": Path, "captions_burned": bool}``.
    """
    source = Path(source)
    out_dir.mkdir(parents=True, exist_ok=True)
    duration = max(0.0, end - start)

    width, height = ASPECT_PRESETS.get(aspect, ASPECT_PRESETS["9:16"])
    output_path = out_dir / f"{output_basename}.mp4"

    ass_name: str | None = None
    if captions and cues:
        ass_name = f"{output_basename}.ass"
        ass_text = build_ass(list(cues), start, end, width, height)
        (out_dir / ass_name).write_text(ass_text, encoding="utf-8")

    captures = _supports_subtitles_filter(ffmpeg)
    if ass_name and not captures:
        ass_name = None

    filter_complex = _build_filter(width, height, mode, ass_name)

    command: list[str] = [
        ffmpeg, "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-ss", f"{start:.3f}", "-t", f"{duration:.3f}",
        "-i", str(source),
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "0:a:0?",
        *VIDEO_CODEC_ARGS,
        *AUDIO_CODEC_ARGS,
        *OUTPUT_MOVFLAGS,
        "-progress", "pipe:1", "-nostats",
        str(output_path),
    ]

    # stderr goes to a log file: reading stdout in the loop while stderr fills
    # its pipe would deadlock once the 64 KiB pipe buffer is full.
    log_path = out_dir / f"{output_basename}.ffmpeg.log"
    with open(log_path, "w", encoding="utf-8", errors="replace") as log_file:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=log_file,
            text=True,
            cwd=str(out_dir),  # so relative ass= paths resolve here
        )

        assert process.stdout is not None
        for line in process.stdout:
            line = line.strip()
            if line.startswith("out_time_ms="):
                current = float(line.split("=", 1)[1]) / 1_000_000.0
                if duration > 0 and report:
                    report(min(0.99, current / duration), f"Rendering… {current:.0f}s/{duration:.0f}s")

        process.wait()

    if process.returncode != 0:
        tail = ""
        if log_path.exists():
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-1500:]
        raise RuntimeError(
            f"FFmpeg failed (exit {process.returncode}).\n{tail}"
        )

    if report:
        report(1.0, "Rendering done")
    return {"file": output_path, "captions_burned": bool(ass_name)}


def export_thumbnail(source: str | Path, out_dir: Path, ffmpeg: str, at: float) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    thumb = out_dir / "thumbnail.jpg"
    subprocess.run(
        [
            ffmpeg, "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-ss", f"{max(0.0, at):.2f}",
            "-i", str(source),
            "-frames:v", "1",
            "-vf", "scale=480:-2",
            str(thumb),
        ],
        check=False,
    )
    return thumb if thumb.exists() else source
"""Subtitle handling: WebVTT parsing, cue helpers and ASS burn-in generation."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

from .config import (
    CAPTION_FONT,
    CAPTION_MAX_CHARS_PER_LINE,
    CAPTION_MAX_LINES,
)

_TIMESTAMP = re.compile(
    r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?"
)
_TAGS = re.compile(r"<[^>]+>")
_CUE_LINE = re.compile(r"-->")


@dataclass
class Cue:
    start: float
    end: float
    text: str

    def to_dict(self) -> dict[str, object]:
        return {"start": self.start, "end": self.end, "text": self.text}


def parse_timestamp(value: str) -> float | None:
    match = _TIMESTAMP.search(value)
    if not match:
        return None
    hours, minutes, seconds, fraction = match.groups()
    total = int(minutes) * 60 + int(seconds)
    if hours:
        total += int(hours) * 3600
    if fraction:
        total += int(fraction.ljust(3, "0")) / 1000.0
    return float(total)


def _clean(text: str) -> str:
    text = _TAGS.sub("", text)
    text = html.unescape(text)
    text = text.replace("\u200b", "").replace("\ufeff", "")
    return re.sub(r"\s+", " ", text).strip()


def parse_vtt(content: str) -> list[Cue]:
    """Parse WebVTT content into a clean list of cues.

    Handles the messy realities of YouTube auto-captions: cue settings,
    inline styling tags, entity escapes and duplicated rolling lines.
    """
    cues: list[Cue] = []
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    index = 0

    while index < len(lines):
        line = lines[index].strip()
        if _CUE_LINE.search(line):
            start = parse_timestamp(line.split("-->")[0])
            end = parse_timestamp(line.split("-->")[1]) if "-->" in line else None
            index += 1
            buffer: list[str] = []
            while index < len(lines) and lines[index].strip():
                buffer.append(lines[index])
                index += 1
            text = _clean(" ".join(buffer))
            if start is not None and end is not None and text:
                cues.append(Cue(start=start, end=end, text=text))
        else:
            index += 1

    return dedupe_cues(cues)


def dedupe_cues(cues: list[Cue]) -> list[Cue]:
    """Drop rolled-up duplicates and merge overlapping identical text."""
    cleaned: list[Cue] = []
    for cue in cues:
        if cleaned:
            previous = cleaned[-1]
            if cue.text == previous.text:
                previous.end = max(previous.end, cue.end)
                continue
            # YouTube's rolling captions repeat a growing prefix; keep the longest.
            if cue.text.startswith(previous.text) and cue.start - previous.end < 1.0:
                cleaned[-1] = Cue(previous.start, max(previous.end, cue.end), cue.text)
                continue
        cleaned.append(Cue(cue.start, cue.end, cue.text))

    # Re-normalise: ensure chronological order and non-negative durations.
    cleaned.sort(key=lambda c: c.start)
    for cue in cleaned:
        if cue.end <= cue.start:
            cue.end = cue.start + 1.0
    return cleaned


def find_vtt_files(directory: Path) -> list[Path]:
    return sorted(directory.glob("*.vtt"))


def load_cues_from_dir(directory: Path) -> list[Cue]:
    for path in find_vtt_files(directory):
        try:
            return parse_vtt(path.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    return []


# --------------------------------------------------------------------------- #
# ASS subtitle generation (burned in with FFmpeg's subtitles filter)
# --------------------------------------------------------------------------- #
def _wrap(text: str, width: int = CAPTION_MAX_CHARS_PER_LINE) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:d}:{minutes:02d}:{secs:05.2f}"


def _escape_ass(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def build_ass(
    cues: list[Cue],
    clip_start: float,
    clip_end: float,
    width: int,
    height: int,
    font: str = CAPTION_FONT,
    font_size: int | None = None,
    margin_v: int | None = None,
) -> str:
    """Build an ASS subtitle file for a clip, with times relative to the clip."""
    font_size = font_size or max(36, int(height * 0.048))
    margin_v = margin_v or int(height * 0.11)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Short,{font},{font_size},&H00FFFFFF,&H000000FF,&H00141414,&H96000000,-1,0,0,0,100,100,0.6,0,1,{max(3, font_size // 18)},2,2,{int(width * 0.06)},{int(width * 0.06)},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events: list[str] = []
    for cue in cues:
        if cue.end <= clip_start or cue.start >= clip_end:
            continue
        start = max(cue.start, clip_start) - clip_start
        end = min(cue.end, clip_end) - clip_start
        if end - start < 0.12:
            continue

        lines = _wrap(cue.text)
        # Split very long cues into stacked page(s) of at most MAX_LINES.
        pages = [
            lines[i : i + CAPTION_MAX_LINES]
            for i in range(0, len(lines), CAPTION_MAX_LINES)
        ]
        total = end - start
        for page_index, page in enumerate(pages):
            page_start = start + total * page_index / len(pages)
            page_end = start + total * (page_index + 1) / len(pages)
            text = "\\N".join(_escape_ass(line) for line in page)
            events.append(
                f"Dialogue: 0,{_ass_time(page_start)},{_ass_time(page_end)},"
                f"Short,,0,0,0,,{text}"
            )

    return header + "\n".join(events) + "\n"

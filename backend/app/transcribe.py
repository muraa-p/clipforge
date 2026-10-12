"""Optional local transcription fallback via faster-whisper (100% free).

Not installed by default: ``pip install -r requirements-optional.txt``.
If that is missing we simply fall back to audio-energy-only analysis.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .captions import Cue

Hook = Callable[[float, str], None]


def whisper_available() -> bool:
    try:
        import faster_whisper  # type: ignore  # noqa: F401

        return True
    except ImportError:
        return False


def transcribe(
    media_path: str | Path,
    report: Hook | None = None,
    model_name: str = "base",
) -> list[Cue]:
    """Transcribe media on CPU. First run downloads the small model (~150 MB).

    ``model_name`` values: tiny / base / small / medium are a good
    accuracy-vs-speed trade on a laptop without a GPU.
    """
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper is not installed. Run: pip install -r requirements-optional.txt"
        ) from exc

    if report:
        report(0.0, f"Loading Whisper model '{model_name}' (first run downloads it)…")
    model = WhisperModel(model_name, device="cpu", compute_type="int8")

    if report:
        report(0.05, "Transcribing on CPU…")
    segments, info = model.transcribe(
        str(media_path), beam_size=5, vad_filter=True
    )

    cues: list[Cue] = []
    duration = float(info.duration or 0)
    for segment in segments:
        cues.append(Cue(float(segment.start), float(segment.end), segment.text.strip()))
        if report and duration:
            report(0.05 + 0.95 * min(1.0, float(segment.end) / duration), "Transcribing…")

    return cues
"""Free, offline highlight detection.

No paid APIs, no GPU required. We combine three cheap signals:

  1. **Speech density** – words per second from the caption track. Talking
     continuously tends to be the engaging part of a video.
  2. **Loudness / energy** – windowed RMS of the decoded audio. Laughs,
     shouting, music swells and reactions spike here.
  3. **Hook language** – a hand-written list of phrases people use at the
     start of a good hook ("here's why", "the secret", "most people", ...).

Each sliding window over the timeline gets a percentile-ranked score so the
result is adaptive to the specific video instead of using magic thresholds.
"""

from __future__ import annotations

import array
import bisect
import math
import re
import subprocess
from dataclasses import dataclass, field

from .captions import Cue
from .config import (
    DEFAULT_CLIP_SECONDS,
    MAX_CANDIDATES,
    MAX_CLIP_SECONDS,
    MIN_CLIP_SECONDS,
)

HOOK_PHRASES = [
    "here's", "here is", "the secret", "the truth", "nobody", "everyone",
    "never", "always", "you need", "you should", "you have to", "the biggest",
    "the best", "the worst", "the problem", "the reason", "the trick",
    "most people", "turns out", "believe me", "listen", "imagine", "actually",
    "watch this", "this is why", "why i", "how to", "how i", "numbers",
    "mistake", "shocking", "surprising", "crazy", "insane", "important",
    "remember", "key", "first", "finally", "because", "but", "so",
]
_NUMBER = re.compile(r"\b\d+(?:[.,]\d+)?%?\b")
_QUESTION = re.compile(r"\?")


@dataclass
class Candidate:
    start: float
    end: float
    score: float
    reasons: list[str] = field(default_factory=list)
    text: str = ""
    source: str = "heuristic"

    def to_dict(self) -> dict[str, object]:
        return {
            "start": round(self.start, 2),
            "end": round(self.end, 2),
            "duration": round(self.end - self.start, 2),
            "score": round(self.score, 4),
            "reasons": self.reasons,
            "text": self.text,
            "source": self.source,
        }


# --------------------------------------------------------------------------- #
# Audio energy
# --------------------------------------------------------------------------- #
def decode_pcm(video_path: str, ffmpeg: str, sample_rate: int = 16000) -> array.array:
    """Decode any media file to mono 16-bit PCM using FFmpeg."""
    command = [
        ffmpeg, "-v", "quiet", "-nostdin",
        "-i", video_path,
        "-vn", "-ac", "1", "-ar", str(sample_rate),
        "-f", "s16le", "-",
    ]
    process = subprocess.run(command, capture_output=True, check=False)
    samples = array.array("h")
    payload = process.stdout
    if len(payload) % 2:
        payload = payload[:-1]
    samples.frombytes(payload)
    return samples


def rms_series(
    samples: array.array, sample_rate: int = 16000, window: float = 0.5
) -> list[float]:
    """Return per-window RMS in dBFS (negative numbers, 0 = full scale)."""
    size = max(1, int(sample_rate * window))
    values: list[float] = []
    for start in range(0, len(samples), size):
        chunk = samples[start : start + size]
        if not chunk:
            break
        total = 0.0
        for sample in chunk:
            total += float(sample) * float(sample)
        rms = math.sqrt(total / len(chunk)) / 32768.0
        values.append(20.0 * math.log10(rms) if rms > 1e-7 else -90.0)
    return values


def _resample(series: list[float], from_step: float, to_step: float) -> list[float]:
    if not series:
        return []
    count = max(1, int(len(series) * from_step / to_step))
    out: list[float] = []
    for i in range(count):
        lo = int(i * to_step / from_step)
        hi = max(lo + 1, int((i + 1) * to_step / from_step))
        chunk = series[lo:hi] or [series[min(lo, len(series) - 1)]]
        out.append(sum(chunk) / len(chunk))
    return out


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def _percentile(values: list[float], value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return bisect.bisect_right(ordered, value) / len(ordered)


def _speech_series(cues: list[Cue], duration: float, step: float = 1.0) -> tuple[list[float], list[str]]:
    """Words-per-second and concatenated text per 1s bucket."""
    buckets = max(1, int(math.ceil(duration / step)))
    words = [0.0] * buckets
    text = [""] * buckets
    for cue in cues:
        span = max(0.0, cue.end - cue.start)
        if span <= 0:
            continue
        count = len(cue.text.split())
        per_second = count / span
        first = max(0, int(cue.start // step))
        last = min(buckets - 1, int(cue.end // step))
        for bucket in range(first, last + 1):
            words[bucket] += per_second * step * min(1.0, span / step if span < step else 1.0)
            text[bucket] = (text[bucket] + " " + cue.text).strip()
    return words, text


def _hook_score(text: str) -> tuple[float, list[str]]:
    lowered = text.lower()
    hits: list[str] = []
    for phrase in HOOK_PHRASES:
        if phrase in lowered:
            hits.append(phrase)
    numbers = len(_NUMBER.findall(text))
    questions = len(_QUESTION.findall(text))
    raw = len(hits) + 0.5 * numbers + 0.75 * questions
    return raw, (hits + (["numbers"] if numbers else []) + (["questions"] if questions else []))[:4]


def _snap_to_cues(cues: list[Cue], start: float, end: float, duration: float) -> tuple[float, float]:
    """Grow the window outwards to whole sentences so we never cut mid-word."""
    if not cues:
        return max(0.0, start), min(duration, end)

    for cue in cues:
        if cue.start <= start <= cue.end:
            if start - cue.start < 0.75:
                start = cue.start
            break
        if cue.start > start:
            start = min(cue.start, start + 1.5)
            break

    for cue in reversed(cues):
        if cue.start <= end <= cue.end:
            if cue.end - end < 1.5:
                end = cue.end
            break
        if cue.end < end:
            end = max(cue.end, end - 1.5)
            break

    start = max(0.0, min(start, max(0.0, duration - MIN_CLIP_SECONDS)))
    end = min(duration, max(end, start + MIN_CLIP_SECONDS))
    if end - start > MAX_CLIP_SECONDS:
        end = start + MAX_CLIP_SECONDS
    return start, end


def detect_candidates(
    cues: list[Cue],
    duration: float,
    audio_db: list[float] | None = None,
    clip_seconds: int = DEFAULT_CLIP_SECONDS,
    max_candidates: int = MAX_CANDIDATES,
) -> list[Candidate]:
    """Return ranked, non-overlapping clip candidates."""
    if duration <= 0:
        return []

    clip_seconds = int(max(MIN_CLIP_SECONDS, min(MAX_CLIP_SECONDS, clip_seconds)))
    if duration <= MIN_CLIP_SECONDS:
        text = " ".join(cue.text for cue in cues)
        return [
            Candidate(
                start=0.0,
                end=duration,
                score=1.0,
                reasons=["whole video"],
                text=text[:400],
            )
        ]

    step = 1.0
    speech, bucket_text = _speech_series(cues, duration, step)
    loudness = _resample(audio_db or [], 0.5, step) if audio_db else []
    if loudness and len(loudness) < len(speech):
        loudness += [loudness[-1]] * (len(speech) - len(loudness))

    # Remove the "silent floor" so tiny noise doesn't dominate the ranking.
    floor = None
    if loudness:
        ordered = sorted(loudness)
        floor = ordered[int(len(ordered) * 0.1)]

    window_steps = max(1, int(clip_seconds / step))
    hop = max(1, int(2 / step))
    total_steps = len(speech)

    raw_candidates: list[dict[str, object]] = []
    for begin in range(0, max(1, total_steps - window_steps + 1), hop):
        end_index = min(total_steps, begin + window_steps)
        speech_slice = speech[begin:end_index]
        if not speech_slice:
            continue
        mean_speech = sum(speech_slice) / len(speech_slice)
        coverage = sum(1 for value in speech_slice if value > 0.05) / len(speech_slice)

        if loudness:
            loud_slice = loudness[begin:end_index]
            loud_mean = sum(loud_slice) / len(loud_slice)
            loud_rel = loud_mean - (floor or loud_mean)
        else:
            loud_mean, loud_rel = 0.0, 0.0

        text = " ".join(bucket_text[begin:end_index])
        hook_raw, hook_tags = _hook_score(text)

        start = begin * step
        end = start + clip_seconds
        intro_penalty = 1.0 if start < 5.0 else 0.0
        outro_penalty = 1.0 if end > duration - 5.0 else 0.0

        raw_candidates.append(
            {
                "start": start,
                "end": end,
                "speech": mean_speech,
                "coverage": coverage,
                "loud": loud_mean,
                "loud_rel": loud_rel,
                "hook": hook_raw,
                "hook_tags": hook_tags,
                "text": text,
                "intro_penalty": intro_penalty,
                "outro_penalty": outro_penalty,
            }
        )

    if not raw_candidates:
        return []

    speech_values = [c["speech"] for c in raw_candidates]  # type: ignore[misc]
    loud_values = [c["loud_rel"] for c in raw_candidates]  # type: ignore[misc]
    hook_values = [c["hook"] for c in raw_candidates]  # type: ignore[misc]

    for candidate in raw_candidates:
        speech_rank = _percentile(speech_values, candidate["speech"])  # type: ignore[arg-type]
        loud_rank = _percentile(loud_values, candidate["loud_rel"]) if loudness else 0.5  # type: ignore[arg-type]
        hook_rank = _percentile(hook_values, candidate["hook"]) if any(hook_values) else 0.0  # type: ignore[arg-type]
        coverage = candidate["coverage"]  # type: ignore[assignment]

        score = (
            0.42 * speech_rank
            + 0.24 * loud_rank
            + 0.20 * hook_rank
            + 0.14 * float(coverage)
            - 0.18 * float(candidate["intro_penalty"])
            - 0.12 * float(candidate["outro_penalty"])
        )

        reasons: list[str] = []
        if speech_rank > 0.66:
            reasons.append("dense speech")
        if loudness and loud_rank > 0.66:
            reasons.append("high energy")
        tags = candidate["hook_tags"]  # type: ignore[assignment]
        if tags:
            reasons.append("hook: " + ", ".join(map(str, tags)))
        if not reasons:
            reasons.append("steady talking")
        candidate["score"] = score
        candidate["reasons"] = reasons

    raw_candidates.sort(key=lambda c: c["score"], reverse=True)  # type: ignore[arg-type,return-value]

    # Greedy pick with a small buffer so picks don't just overlap each other.
    picked: list[Candidate] = []
    occupied: list[tuple[float, float]] = []
    for candidate in raw_candidates:
        start = float(candidate["start"])
        end = float(candidate["end"])
        if any(start < o_end + 2 and end > o_start - 2 for o_start, o_end in occupied):
            continue
        snapped_start, snapped_end = _snap_to_cues(cues, start, end, duration)
        picked.append(
            Candidate(
                start=snapped_start,
                end=snapped_end,
                score=float(candidate["score"]),
                reasons=list(candidate["reasons"]),  # type: ignore[arg-type]
                text=" ".join(str(candidate["text"]).split())[:500],
            )
        )
        occupied.append((start, end))
        if len(picked) >= max_candidates:
            break

    return picked


def analyze(
    cues: list[Cue],
    source_path: str,
    duration: float,
    ffmpeg: str,
    clip_seconds: int = DEFAULT_CLIP_SECONDS,
    max_candidates: int = MAX_CANDIDATES,
) -> dict[str, object]:
    """Full heuristic pass. Returns a JSON-serialisable report."""
    audio_db: list[float] = []
    audio_error: str | None = None
    try:
        samples = decode_pcm(source_path, ffmpeg)
        audio_db = rms_series(samples)
    except Exception as exc:  # noqa: BLE001 - audio is optional
        audio_error = str(exc)

    candidates = detect_candidates(
        cues=cues,
        duration=duration,
        audio_db=audio_db,
        clip_seconds=clip_seconds,
        max_candidates=max_candidates,
    )

    used_signal = "captions+audio" if cues and audio_db else ("captions" if cues else "audio")
    return {
        "signal": used_signal,
        "audio_error": audio_error,
        "clip_seconds": clip_seconds,
        "candidates": [candidate.to_dict() for candidate in candidates],
        "cues": [cue.to_dict() for cue in cues],
    }

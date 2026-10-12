"""Job steps: analyse a URL, then render a clip. Both run in a background thread."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from . import analyze as analyze_service
from . import bins, downloader, llm, render as render_service, store, transcribe
from .captions import Cue, load_cues_from_dir
from .config import OUTPUT_DIR
from .jobs import Job, manager


class ClipForgeError(RuntimeError):
    """Friendly error that gets surfaced as job.error."""


def _report(job: Job):
    return manager.reporter(job)


def analyse_url(
    job: Job,
    url: str,
    clip_seconds: int | None = None,
    max_candidates: int | None = None,
    use_ai: bool = True,
    ai_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Download a video, grab/transcribe captions, run heuristic analysis."""
    report = _report(job)
    ffmpeg = bins.ensure_ffmpeg(log=lambda msg: report(None, f"[setup] {msg}"))

    report(1, "Reading link…")
    try:
        downloader.assert_public_url(url)
    except ValueError as exc:
        raise ClipForgeError(str(exc)) from exc
    try:
        info = downloader.probe(url)
    except Exception as exc:  # noqa: BLE001
        raise ClipForgeError(f"Could not read that link. Is it public and correct? ({exc})") from exc

    duration = float(info.get("duration") or 0)

    video_id = store.new_id()
    directory = store.video_dir(video_id)

    report(4, "Downloading video…")
    source = downloader.download(
        url,
        directory,
        report=lambda pct, msg: report(4 + pct * 30, msg),
    )

    if duration <= 0:
        report(35, "Measuring duration…")
        duration = render_service.probe_duration(source, ffmpeg)

    report(35, "Looking for captions…")
    try:
        downloader.fetch_captions(
            url, directory, report=lambda pct, msg: report(None, msg)
        )
    except Exception:  # noqa: BLE001 - captions are best-effort
        pass
    cues = load_cues_from_dir(directory)

    if not cues and transcribe.whisper_available():
        report(38, "No captions — transcribing locally with Whisper…")
        try:
            cues = transcribe.transcribe(source, report=lambda pct, msg: report(38 + pct * 20, msg))
        except Exception as exc:  # noqa: BLE001
            report(58, f"Transcription failed, using audio-only mode ({exc})")
            cues = []
    elif not cues:
        report(58, "No captions — using audio-energy analysis only")

    report(62, "Detecting the best moments…")
    fallback_clip = int(clip_seconds or 45)
    candidate_count = int(max_candidates or 8)
    analysis = analyze_service.analyze(
        cues=cues,
        source_path=str(source),
        duration=duration,
        ffmpeg=ffmpeg,
        clip_seconds=fallback_clip,
        max_candidates=candidate_count,
    )
    analysis["captions_source"] = "transcript" if not cues else "automatic"
    analysis["duration"] = round(duration, 2)
    analysis["ai"] = {"used": False}

    # Optional: let a free-by-key OpenAI-compatible model re-rank the picks.
    if use_ai and llm.is_enabled(ai_override):
        try:
            picks = llm.pick_highlights(
                cues=cues,
                duration=duration,
                clip_seconds=fallback_clip,
                max_candidates=candidate_count,
                report=lambda pct, message: report(72 + pct * 12, message),
                override=ai_override,
            )
        except Exception as exc:  # noqa: BLE001 - always fall back to heuristics
            picks = None
            analysis["ai"] = {"used": False, "error": str(exc)[:240]}

        if picks:
            heuristic = list(analysis.get("candidates", []))

            def overlaps_ai(candidate: dict[str, Any]) -> bool:
                return any(
                    candidate["start"] < pick["end"] - 1
                    and candidate["end"] > pick["start"] + 1
                    for pick in picks
                )

            merged = list(picks) + [c for c in heuristic if not overlaps_ai(c)]
            analysis["candidates"] = merged
            config = llm.describe(ai_override)
            analysis["ai"] = {
                "used": True,
                "provider": config.get("provider"),
                "model": config.get("model"),
            }
            analysis["signal"] = "ai+" + str(analysis.get("signal"))

    record = {
        "url": url,
        "source": source.name,
        "source_path": str(source),  # internal only, never served raw as JSON
        "info": info,
        **analysis,
    }
    # Strip internal path before persisting public fields (server still knows it).
    store.save_record(video_id, {k: v for k, v in record.items() if k != "source_path"})
    record["video_id"] = video_id

    # Cues travel to the UI as plain dicts; cap the payload for long videos.
    all_cues = list(analysis.get("cues", []))
    record["cues"] = all_cues[:3000]
    record["cue_count"] = len(all_cues)
    record.pop("source_path", None)

    return record


def render_clip(
    job: Job,
    video_id: str,
    start: float,
    end: float,
    aspect: str,
    mode: str,
    captions: bool,
) -> dict[str, Any]:
    """Cut a segment and export a vertical short."""
    report = _report(job)
    record = store.load_record(video_id)
    if not record:
        raise ClipForgeError("Video record not found — please analyse the link again.")

    ffmpeg = bins.ensure_ffmpeg(log=lambda msg: report(None, f"[setup] {msg}"))
    directory = store.video_dir(video_id)
    source = directory / str(record["source"])
    if not source.exists():
        raise ClipForgeError("The downloaded source is missing. Re-analyse the link.")

    cues = [
        Cue(float(cue["start"]), float(cue["end"]), str(cue["text"]))
        for cue in record.get("cues", [])
    ]
    start = max(0.0, start)
    end = min(float(record.get("duration") or (start + 60)), max(start + 1.0, end))

    slug = store.safe_slug(str(record["info"].get("title", "short")))
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = _output_dir(video_id, slug, stamp)

    report(2, "Preparing render…")
    result = render_service.render_clip(
        source=source,
        out_dir=out_dir,
        start=start,
        end=end,
        ffmpeg=ffmpeg,
        aspect=aspect,
        mode=mode,
        captions=captions,
        cues=cues,
        output_basename="short",
        report=lambda pct, msg: report(4 + pct * 96, msg),
    )

    output_file: Path = result["file"]
    mid = (start + end) / 2
    render_service.export_thumbnail(source, out_dir, ffmpeg, at=mid)

    return {
        "video_id": video_id,
        "filename": output_file.name,
        "url": f"/api/output/{video_id}/{out_dir.name}/{output_file.name}",
        "thumbnail_url": f"/api/output/{video_id}/{out_dir.name}/thumbnail.jpg",
        "captions_burned": bool(result["captions_burned"]),
        "aspect": aspect,
        "mode": mode,
        "start": round(start, 2),
        "end": round(end, 2),
        "duration": round(end - start, 2),
        "size_bytes": output_file.stat().st_size,
    }


def _output_dir(video_id: str, slug: str, stamp: str) -> Path:
    target = OUTPUT_DIR / f"{video_id}-{slug}-{stamp}"
    target.mkdir(parents=True, exist_ok=True)
    return target
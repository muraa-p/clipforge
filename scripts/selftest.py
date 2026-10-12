"""Self-test: verify ClipForge's core pipeline with a synthetic video.

Builds a 60s fake video (testsrc + a louder mid-section), fake captions with a
dense mid-section, then runs the highlight analysis and a real FFmpeg render.
No real YouTube download involved — pure offline verification.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

# Windows consoles default to cp1252; make our unicode output safe.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass

from app import analyze, bins, render  # noqa: E402
from app.captions import Cue  # noqa: E402

WORK = BACKEND / "data" / "selftest"

FAKE_VTT = """WEBVTT

00:00:00.000 --> 00:00:06.000
hello and welcome to this video today we are going to talk about something

00:00:18.000 --> 00:00:22.000
here is why most people never succeed at this task and I think this matters

00:00:22.000 --> 00:00:27.000
the secret everyone misses is actually the biggest mistake you can avoid

00:00:27.000 --> 00:00:34.000
watch this closely because the trick here turns out to be surprisingly simple

00:00:34.000 --> 00:00:40.000
imagine if you could remember the key first step and never forget it again

00:00:45.000 --> 00:00:52.000
so that is the basics of it and next week we continue

00:00:53.000 --> 00:00:58.000
thank you for watching please like and subscribe
"""


def run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd[:3])}…\n{result.stderr[-800:]}")


def build_fake_video(ffmpeg: str) -> Path:
    WORK.mkdir(parents=True, exist_ok=True)
    video = WORK / "synth-source.mp4"
    if video.exists():
        return video

    # 60s picture, audio that is quiet except a loud burst at 20–32s
    run(
        [
            ffmpeg, "-y", "-v", "quiet",
            "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=60",
            "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=44100:duration=60",
            "-filter:a", "volume=0.04,volume=enable='between(t,20,32)':volume=0.9",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
            "-c:a", "aac", "-shortest",
            str(video),
        ]
    )
    return video


def write_vtt() -> Path:
    path = WORK / "subs.en.vtt"
    path.write_text(FAKE_VTT, encoding="utf-8")
    return path


def main() -> int:
    print("==> Ensuring FFmpeg (downloads once if missing)…")
    ffmpeg = bins.ensure_ffmpeg(log=print)

    print("==> Building synthetic 60s video with a loud 20–32s burst…")
    video = build_fake_video(ffmpeg)
    vtt = write_vtt()
    cues = __import__("app.captions", fromlist=["parse_vtt"]).parse_vtt(vtt.read_text(encoding="utf-8"))
    print(f"    built {video.name} ({video.stat().st_size // 1024} KiB), {len(cues)} cues")

    print("==> Running heuristic analysis…")
    result = analyze.analyze(
        cues=cues,
        source_path=str(video),
        duration=60.0,
        ffmpeg=ffmpeg,
        clip_seconds=15,
        max_candidates=5,
    )
    candidates = result["candidates"]
    for candidate in candidates:
        print(f"    cand {candidate['start']:5.1f}–{candidate['end']:5.1f}s "
              f"score={candidate['score']:.3f} reasons={candidate['reasons']}")

    if not candidates:
        print("FAIL: no candidates produced"); return 1

    best = candidates[0]
    overlap = max(0.0, min(best["end"], 34.0) - max(best["start"], 18.0))
    print(f"    best candidate overlaps the engineered 'good' region (18–34s) by {overlap:.1f}s")
    if overlap < 8:
        print("FAIL: best candidate is not in the engineered highlight region"); return 1

    print("==> Rendering a 9:16 clip with captions…")
    out_dir = WORK / "rendered"
    output = render.render_clip(
        source=video,
        out_dir=out_dir,
        start=float(best["start"]),
        end=float(best["end"]),
        ffmpeg=ffmpeg,
        aspect="9:16",
        mode="blur",
        captions=True,
        cues=cues,
        output_basename="short",
    )
    out_file: Path = output["file"]
    print(f"    wrote {out_file.name} ({out_file.stat().st_size // 1024} KiB)")

    probe = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(out_file)],
        capture_output=True, text=True,
    )
    stderr = probe.stderr
    import re

    resolution = re.findall(r"(\d{3,4})x(\d{3,4})", stderr)
    h264 = "h264" in stderr
    print(f"    probe → resolution {resolution}, h264={h264}")
    if resolution != [("1080", "1920")] and resolution != [("1920", "1080")]:
        print(f"FAIL: unexpected resolution {resolution}"); return 1
    if not h264:
        print("FAIL: output is not H.264"); return 1

    print("\n✅ Self-test passed: analysis finds the highlight, render produces a vertical short.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
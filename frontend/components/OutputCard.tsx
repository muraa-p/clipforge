"use client";

import type { RenderResult } from "@/lib/types";
import { absoluteUrl, downloadOutput, fmtTime } from "@/lib/api";

interface Props {
  result: RenderResult;
  onNew: () => void;
}

export default function OutputCard({ result, onNew }: Props) {
  return (
    <section className="card output-card">
      <div className="output-head">
        <h3>✨ Your short is ready</h3>
        <span className="badge badge-green">
          {fmtTime(result.duration)} · {result.aspect} ·{" "}
          {result.captions_burned ? "captions" : "no captions"}
        </span>
      </div>

      <video className="player" src={absoluteUrl(result.url)} controls autoPlay muted />

      <div className="output-actions">
        <a className="btn btn-primary" href={downloadOutput(result)} download>
          ⬇ Download mp4 ({(result.size_bytes / 1048576).toFixed(1)} MB)
        </a>
        <button className="btn btn-ghost" onClick={onNew}>
          Make another
        </button>
      </div>

      <p className="muted small">
        Cut from {fmtTime(result.start)} to {fmtTime(result.end)} of the original.
        Rendered entirely on your machine — nothing was uploaded.
      </p>
    </section>
  );
}
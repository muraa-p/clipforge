"use client";

import type { Candidate } from "@/lib/types";
import { fmtTime } from "@/lib/api";

interface Props {
  candidates: Candidate[];
  onPick: (candidate: Candidate) => void;
}

export default function CandidateList({ candidates, onPick }: Props) {
  if (candidates.length === 0) {
    return (
      <p className="muted">
        No strong candidates found — use the manual trim below instead.
      </p>
    );
  }

  return (
    <div className="candidate-list">
      {candidates.map((candidate, index) => {
        const pct = Math.round(candidate.score * 100);
        return (
          <div className="candidate" key={`${candidate.start}-${candidate.end}-${index}`}>
            <div className="candidate-rank">#{index + 1}</div>
            <div className="candidate-body">
              <div className="candidate-head">
                <span className="candidate-time">
                  {fmtTime(candidate.start)} → {fmtTime(candidate.end)}
                  <em>{fmtTime(candidate.duration)}</em>
                </span>
                <span className="score">
                  <span className="score-bar">
                    <span style={{ width: `${pct}%` }} />
                  </span>
                  {pct}%
                </span>
              </div>
              {candidate.title && <p className="candidate-title">{candidate.title}</p>}
              <p className="candidate-text">{candidate.text || "—"}</p>
              <div className="chips">
                {candidate.source === "ai" && (
                  <span className="chip chip-ai">✨ AI pick</span>
                )}
                {candidate.reasons.map((reason) => (
                  <span className="chip" key={reason}>
                    {reason}
                  </span>
                ))}
              </div>
            </div>
            <button className="btn btn-ghost" onClick={() => onPick(candidate)}>
              Use this
            </button>
          </div>
        );
      })}
    </div>
  );
}
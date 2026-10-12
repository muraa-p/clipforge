"use client";

import { fmtTime } from "@/lib/api";

interface Props {
  duration: number;
  start: number;
  end: number;
  onChange: (start: number, end: number) => void;
  aspects: string[];
  modes: string[];
  aspect: string;
  onAspect: (value: string) => void;
  mode: string;
  onMode: (value: string) => void;
  captions: boolean;
  onCaptions: (value: boolean) => void;
  onGenerate: () => void;
}

const LENGTHS = [15, 30, 45, 60];

export default function TrimPanel({
  duration,
  start,
  end,
  onChange,
  aspects,
  modes,
  aspect,
  onAspect,
  mode,
  onMode,
  captions,
  onCaptions,
  onGenerate,
}: Props) {
  const valid = end - start >= 5 && end <= duration;
  const total = Math.max(0, duration);

  const setStart = (value: number) => {
    const clamped = Math.min(Math.max(0, value), end - 5, total);
    onChange(clamped, end);
  };

  const setEnd = (value: number) => {
    const clamped = Math.min(Math.max(start + 5, value), total);
    onChange(start, clamped);
  };

  const applyLength = (length: number) => {
    const newEnd = Math.min(start + length, total);
    onChange(start, newEnd);
  };

  return (
    <section className="card trim-panel">
      <h3>Trim your clip</h3>

      <div className="duration-readout">
        <span className="duration-big">{fmtTime(end - start)}</span>
        <span className="muted">of {fmtTime(total)}</span>
      </div>

      <div className="range-row">
        <label>Start</label>
        <input
          type="range"
          min={0}
          max={Math.max(1, total)}
          step={0.5}
          value={Math.min(start, total)}
          onChange={(event) => setStart(Number(event.target.value))}
        />
        <span className="range-value">{fmtTime(start)}</span>
      </div>

      <div className="range-row">
        <label>End</label>
        <input
          type="range"
          min={0}
          max={Math.max(1, total)}
          step={0.5}
          value={Math.min(end, total)}
          onChange={(event) => setEnd(Number(event.target.value))}
        />
        <span className="range-value">{fmtTime(end)}</span>
      </div>

      <div className="row">
        <div className="seg" role="group" aria-label="Quick lengths">
          {LENGTHS.map((length) => (
            <button
              key={length}
              className={`seg-btn${end - start === length ? " active" : ""}`}
              onClick={() => applyLength(length)}
            >
              {length}s
            </button>
          ))}
        </div>
      </div>

      <div className="grid-3">
        <label className="field">
          <span>Frame</span>
          <select value={aspect} onChange={(event) => onAspect(event.target.value)}>
            {aspects.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Style</span>
          <select value={mode} onChange={(event) => onMode(event.target.value)}>
            {modes.map((m) => (
              <option key={m} value={m}>
                {m === "blur" ? "Blurred bg" : "Center crop"}
              </option>
            ))}
          </select>
        </label>

        <label className="field toggle-field">
          <span>Captions</span>
          <span className="switches">
            <button
              className={`switch-slot${captions ? " on" : ""}`}
              onClick={() => onCaptions(!captions)}
              aria-pressed={captions}
            >
              <span className="knob" />
            </button>
            <em className="muted">{captions ? "on" : "off"}</em>
          </span>
        </label>
      </div>

      <button
        className="btn btn-primary btn-big"
        onClick={onGenerate}
        disabled={!valid}
        title={valid ? "Generate the short" : "Pick at least 5 seconds within the video"}
      >
        ⚡ Generate short
      </button>
    </section>
  );
}
"use client";

import { useEffect, useMemo, useState } from "react";
import * as api from "@/lib/api";
import type { ProviderPreset } from "@/lib/types";
import type { AppSettings } from "@/lib/settings";
import { FALLBACK_PRESETS } from "@/lib/providers";

interface Props {
  open: boolean;
  onClose: () => void;
  settings: AppSettings;
  onSave: (next: AppSettings) => void;
}

type TestState =
  | { kind: "idle" }
  | { kind: "testing" }
  | { kind: "ok"; detail: string }
  | { kind: "error"; detail: string };

export default function SettingsPanel({ open, onClose, settings, onSave }: Props) {
  const [draft, setDraft] = useState<AppSettings>(settings);
  const [presets, setPresets] = useState<ProviderPreset[]>(FALLBACK_PRESETS);
  const [test, setTest] = useState<TestState>({ kind: "idle" });

  // Reset the form whenever the panel opens.
  useEffect(() => {
    if (open) {
      setDraft(settings);
      setTest({ kind: "idle" });
    }
  }, [open, settings]);

  // Try to load the live preset list from the engine.
  useEffect(() => {
    if (!open) return;
    let alive = true;
    api
      .getProviders()
      .then((data) => {
        if (alive && data.presets?.length) setPresets(data.presets);
      })
      .catch(() => {
        /* engine may be offline; the fallback list is fine */
      });
    return () => {
      alive = false;
    };
  }, [open]);

  const selected = useMemo(
    () => presets.find((p) => p.id === draft.ai.provider) ?? null,
    [presets, draft.ai.provider]
  );

  if (!open) return null;

  const setAi = (patch: Partial<AppSettings["ai"]>) =>
    setDraft((d) => ({ ...d, ai: { ...d.ai, ...patch } }));

  function onProviderChange(id: string) {
    const preset = presets.find((p) => p.id === id) ?? null;
    setAi({
      provider: id,
      baseUrl: id && id !== "custom" ? preset?.base_url ?? "" : draft.ai.baseUrl,
      model: id && id !== "custom" ? preset?.model ?? "" : draft.ai.model,
    });
  }

  async function runTest() {
    setTest({ kind: "testing" });
    try {
      const health = await api.probeBackend(draft.backendUrl, draft.accessToken);
      const bits = [
        health.ffmpeg_installed ? "FFmpeg ready" : "FFmpeg missing",
        health.whisper ? "whisper on" : "whisper off",
      ];
      if (draft.ai.provider && draft.ai.provider !== "off") {
        bits.push(`AI: ${draft.ai.provider}`);
      }
      setTest({ kind: "ok", detail: bits.join(" · ") });
    } catch (err) {
      setTest({
        kind: "error",
        detail: err instanceof Error ? err.message : String(err),
      });
    }
  }

  function handleSave() {
    onSave(draft);
    onClose();
  }

  const needsKey =
    selected?.needs_key ??
    (draft.ai.provider !== "" && draft.ai.provider !== "custom");

  return (
    <div className="modal-overlay" onMouseDown={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label="Settings"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="modal-head">
          <h2>⚙️ Settings</h2>
          <button className="btn btn-ghost small" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        <div className="modal-body">
          <section className="settings-section">
            <h3>Engine</h3>
            <p className="muted small">
              Where the video work runs — your PC (default) or a tunnel/VM URL.
              Leave blank to use this page&apos;s own origin.
            </p>
            <label className="field">
              <span>Backend URL</span>
              <input
                type="url"
                value={draft.backendUrl}
                placeholder="http://127.0.0.1:8000  — or  https://your-tunnel.trycloudflare.com"
                onChange={(event) =>
                  setDraft((d) => ({ ...d, backendUrl: event.target.value }))
                }
              />
            </label>
            <label className="field">
              <span>Access token (optional)</span>
              <input
                type="password"
                value={draft.accessToken}
                placeholder="only if you set CLIPFORGE_ACCESS_TOKEN"
                onChange={(event) =>
                  setDraft((d) => ({ ...d, accessToken: event.target.value }))
                }
              />
            </label>
            <div className="settings-row">
              <button className="btn btn-ghost small" onClick={runTest} disabled={test.kind === "testing"}>
                {test.kind === "testing" ? "Testing…" : "Test connection"}
              </button>
              {test.kind === "ok" && (
                <span className="badge badge-green">● Connected · {test.detail}</span>
              )}
              {test.kind === "error" && (
                <span className="badge badge-red">● {test.detail}</span>
              )}
            </div>
          </section>

          <section className="settings-section">
            <h3>✨ AI highlight picking (optional)</h3>
            <p className="muted small">
              Off by default — ClipForge already works with free offline
              heuristics, no AI and no keys. Turn this on to let a model re-rank
              the picks. Your key is stored only in this browser and sent
              straight to your own engine.
            </p>
            <label className="field">
              <span>Provider</span>
              <select
                value={draft.ai.provider}
                onChange={(event) => onProviderChange(event.target.value)}
              >
                <option value="">Off — offline heuristics only</option>
                {presets.map((preset) => (
                  <option key={preset.id} value={preset.id}>
                    {preset.label}
                  </option>
                ))}
              </select>
            </label>

            {draft.ai.provider && (
              <>
                {needsKey && (
                  <label className="field">
                    <span>
                      API key
                      {selected?.signup && (
                        <>
                          {" · "}
                          <a href={selected.signup} target="_blank" rel="noreferrer">
                            get a free key ↗
                          </a>
                        </>
                      )}
                    </span>
                    <input
                      type="password"
                      value={draft.ai.apiKey}
                      placeholder="paste your key"
                      onChange={(event) => setAi({ apiKey: event.target.value })}
                    />
                  </label>
                )}
                <label className="field">
                  <span>Model</span>
                  <input
                    type="text"
                    value={draft.ai.model}
                    placeholder={selected?.model ?? "model name"}
                    onChange={(event) => setAi({ model: event.target.value })}
                  />
                </label>
                <label className="field">
                  <span>Base URL</span>
                  <input
                    type="url"
                    value={draft.ai.baseUrl}
                    placeholder={selected?.base_url ?? "https://api.example.com/v1"}
                    onChange={(event) => setAi({ baseUrl: event.target.value })}
                  />
                </label>
                {draft.ai.provider === "opencode" && (
                  <p className="muted small">
                    OpenCode Zen&apos;s free models are gated to the OpenCode app,
                    so this needs a paid Console key. Prefer Groq/Gemini/Cerebras
                    for a free key.
                  </p>
                )}
              </>
            )}
          </section>
        </div>

        <div className="modal-foot">
          <button className="btn btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={handleSave}>
            Save
          </button>
        </div>
      </div>
    </div>
  );
}

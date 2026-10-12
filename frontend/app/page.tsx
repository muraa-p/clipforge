"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api";
import type {
  AnalysisResult,
  Health,
  JobStatus,
  ProviderPreset,
  RenderResult,
} from "@/lib/types";
import { loadSettings, saveSettings, useSettings } from "@/lib/settings";
import { FALLBACK_PRESETS } from "@/lib/providers";
import CandidateList from "@/components/CandidateList";
import TrimPanel from "@/components/TrimPanel";
import OutputCard from "@/components/OutputCard";
import SettingsPanel from "@/components/SettingsPanel";

type Phase = "idle" | "analyzing" | "ready" | "rendering" | "done";

// -------------------------------------------------------------------------- //
// Poll a job until it finishes.
// -------------------------------------------------------------------------- //
function useJobStatus(jobId: string | null, intervalMs = 1200) {
  const [status, setStatus] = useState<JobStatus | null>(null);

  useEffect(() => {
    if (!jobId) {
      setStatus(null);
      return;
    }
    const id = jobId;
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | undefined;

    async function tick() {
      try {
        const data = await api.getJob(id);
        if (cancelled) return;
        setStatus(data);
        if (data.status === "done" || data.status === "error") {
          if (timer) clearInterval(timer);
        }
      } catch {
        /* transient network hiccup — try again */
      }
    }

    void tick();
    timer = setInterval(tick, intervalMs);
    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
  }, [jobId, intervalMs]);

  return status;
}

export default function Page() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);

  const [url, setUrl] = useState("");
  const [clipSeconds, setClipSeconds] = useState(45);
  const [useAi, setUseAi] = useState(true);

  const settings = useSettings();
  const [mounted, setMounted] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [providers, setProviders] = useState<ProviderPreset[]>(FALLBACK_PRESETS);

  const [health, setHealth] = useState<Health | null>(null);

  const [analyzeJobId, setAnalyzeJobId] = useState<string | null>(null);
  const [renderJobId, setRenderJobId] = useState<string | null>(null);

  const analyzeJob = useJobStatus(analyzeJobId);
  const renderJob = useJobStatus(renderJobId);

  const [record, setRecord] = useState<AnalysisResult | null>(null);
  const [renderResult, setRenderResult] = useState<RenderResult | null>(null);

  const [selection, setSelection] = useState<{ start: number; end: number } | null>(null);
  const [aspect, setAspect] = useState("9:16");
  const [mode, setMode] = useState("blur");
  const [captions, setCaptions] = useState(true);

  // Load persisted settings once on the client.
  useEffect(() => {
    loadSettings();
    setMounted(true);
  }, []);

  // Health badge — probe the engine, re-running when its URL/token changes.
  useEffect(() => {
    let alive = true;
    api
      .getHealth()
      .then((data) => {
        if (!alive) return;
        setHealth(data);
        if (data.ai_providers?.length) setProviders(data.ai_providers);
      })
      .catch(() => {
        if (alive) setHealth(null);
      });
    return () => {
      alive = false;
    };
  }, [settings.backendUrl, settings.accessToken]);

  const reset = useCallback(() => {
    setPhase("idle");
    setError(null);
    setRecord(null);
    setRenderResult(null);
    setSelection(null);
    setAnalyzeJobId(null);
    setRenderJobId(null);
  }, []);

  // Analyze completion
  useEffect(() => {
    if (!analyzeJob) return;
    if (analyzeJob.status === "done" && analyzeJob.result) {
      const result = analyzeJob.result as unknown as AnalysisResult;
      setRecord(result);
      setPhase("ready");
      const first = result.candidates?.[0];
      setSelection(
        first
          ? { start: first.start, end: first.end }
          : { start: 0, end: Math.min(60, result.duration) }
      );
    } else if (analyzeJob.status === "error") {
      setError(analyzeJob.error ?? "Analysis failed.");
      setPhase("idle");
    }
  }, [analyzeJob]);

  // Render completion
  useEffect(() => {
    if (!renderJob) return;
    if (renderJob.status === "done" && renderJob.result) {
      setRenderResult(renderJob.result as RenderResult);
      setPhase("done");
      setRenderJobId(null);
    } else if (renderJob.status === "error") {
      setError(renderJob.error ?? "Render failed.");
      setPhase("ready");
      setRenderJobId(null);
    }
  }, [renderJob]);

  const handleAnalyze = useCallback(
    async (event?: FormEvent) => {
      event?.preventDefault();
      const trimmed = url.trim();
      if (!trimmed) return;
      setError(null);
      setRecord(null);
      setRenderResult(null);
      setSelection(null);
      setPhase("analyzing");
      const ai = settings.ai.provider
        ? {
            provider: settings.ai.provider,
            base_url: settings.ai.baseUrl || undefined,
            model: settings.ai.model || undefined,
            api_key: settings.ai.apiKey || undefined,
          }
        : undefined;
      try {
        const { job_id } = await api.startAnalyze(trimmed, clipSeconds, useAi, ai);
        setAnalyzeJobId(job_id);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        setPhase("idle");
      }
    },
    [url, clipSeconds, useAi, settings]
  );

  const handleRender = useCallback(async () => {
    if (!record || !selection) return;
    setError(null);
    setRenderResult(null);
    setPhase("rendering");
    try {
      const { job_id } = await api.startRender({
        video_id: record.video_id,
        start: selection.start,
        end: selection.end,
        aspect,
        mode,
        captions,
      });
      setRenderJobId(job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setPhase("ready");
    }
  }, [record, selection, aspect, mode, captions]);

  const pickCandidate = useCallback((candidate: AnalysisResult["candidates"][number]) => {
    setSelection({ start: candidate.start, end: candidate.end });
    document.getElementById("trim-panel")?.scrollIntoView({ behavior: "smooth" });
  }, []);

  const ffmpegOk = health?.ffmpeg_installed;

  const activeProvider =
    settings.ai.provider || (health?.llm?.enabled ? health.llm.provider ?? "" : "");
  const aiModel = settings.ai.provider
    ? settings.ai.model ||
      providers.find((p) => p.id === settings.ai.provider)?.model ||
      ""
    : health?.llm?.model ?? "";
  const aiAvailable = Boolean(activeProvider);

  return (
    <div className="page">
      <header className="site-header">
        <div className="header-inner">
          <div className="brand">
            <span className="logo">✂️</span>
            <span>
              <strong>ClipForge</strong>
              <em>free · local · no watermarks</em>
            </span>
          </div>
          <div className="header-right">
            {!mounted ? (
              <span className="badge">● connecting…</span>
            ) : health ? (
              <span className="badge badge-green">● Engine connected</span>
            ) : (
              <span
                className="badge badge-amber"
                title="Open Settings and set the backend URL"
              >
                ● Engine offline
              </span>
            )}
            {ffmpegOk && <span className="badge badge-green">● FFmpeg ready</span>}
            {record && (
              <button className="btn btn-ghost small" onClick={reset}>
                ↺ New analysis
              </button>
            )}
            <button
              className="btn btn-ghost small"
              onClick={() => setSettingsOpen(true)}
            >
              ⚙ Settings
            </button>
          </div>
        </div>
      </header>

      <main className="wrap">
        <section className="hero">
          <h1>Turn any video link into a <span className="gradient">short</span>.</h1>
          <p className="sub">
            Paste a link — YouTube, TikTok, Instagram, X, Vimeo and 1000+ more.
            ClipForge downloads it, finds the best moments with free heuristics,
            and exports a vertical short. No subscriptions, no API bills, no watermarks.
          </p>

          <form className="searchbar" onSubmit={handleAnalyze}>
            <input
              className="search-input"
              type="url"
              placeholder="Paste a video link here…  e.g. https://www.youtube.com/watch?v=…"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              disabled={phase === "analyzing" || phase === "rendering"}
            />
            <button className="btn btn-primary" type="submit" disabled={!url.trim() || phase === "analyzing" || phase === "rendering"}>
              {phase === "analyzing" ? "Analyzing…" : "Analyze"}
            </button>
          </form>

          <div className="clip-length-row">
            <label htmlFor="clip-seconds">Short length</label>
            <select
              id="clip-seconds"
              value={clipSeconds}
              onChange={(event) => setClipSeconds(Number(event.target.value))}
              disabled={phase !== "idle"}
            >
              {[15, 30, 45, 60, 90].map((s) => (
                <option key={s} value={s}>
                  {s}s
                </option>
              ))}
            </select>

            <span className="divider" />

            {aiAvailable ? (
              <label className="ai-toggle" htmlFor="use-ai">
                <input
                  id="use-ai"
                  type="checkbox"
                  checked={useAi}
                  onChange={(event) => setUseAi(event.target.checked)}
                  disabled={phase !== "idle"}
                />
                ✨ Smart picks ({activeProvider}
                {aiModel ? `: ${aiModel}` : ""})
              </label>
            ) : (
              <button
                type="button"
                className="link-btn"
                onClick={() => setSettingsOpen(true)}
                title="Add a free AI key (optional)"
              >
                ✨ AI off — free local heuristics · add a key
              </button>
            )}
          </div>
        </section>

        {mounted && !health && (
          <div className="banner-info">
            <strong>Engine not connected. </strong>
            Start ClipForge on your machine, or open{" "}
            <button
              type="button"
              className="link-btn"
              onClick={() => setSettingsOpen(true)}
            >
              Settings
            </button>{" "}
            and set your backend URL (e.g. a tunnel URL).
          </div>
        )}

        {error && (
          <div className="banner-error">
            <strong>Oops: </strong>
            {error}
          </div>
        )}

        {phase === "analyzing" && analyzeJob && (
          <JobCard job={analyzeJob} title="Analyzing your link" />
        )}

        {phase === "rendering" && renderJob && (
          <JobCard job={renderJob} title="Rendering your short" />
        )}

        {phase === "ready" && record && (
          <>
            <div className="source-grid">
              <section className="card source-card">
                <h3>Source</h3>
                <video
                  className="player"
                  src={api.mediaUrl(record.video_id, record.source)}
                  controls
                  preload="metadata"
                />
                <div className="meta">
                  <h4>{record.info?.title}</h4>
                  <p className="muted">
                    {record.info?.uploader} · {api.fmtTime(record.duration)} ·{" "}
                    via {record.info?.extractor}
                  </p>
                  <div className="chips">
                    <span className="chip">
                      captions: {record.captions_source}
                    </span>
                    <span className="chip">
                      signal: {record.signal}
                    </span>
                    <span className="chip">cues: {record.cue_count}</span>
                    {record.ai?.used && (
                      <span className="chip chip-ai">
                        ✨ AI: {record.ai.model}
                      </span>
                    )}
                  </div>
                  {record.ai?.error && (
                    <p className="muted small">
                      AI unavailable, used heuristics: {record.ai.error}
                    </p>
                  )}
                </div>
              </section>

              <section className="card">
                <h3>✨ Auto-picked highlights</h3>
                <CandidateList
                  candidates={record.candidates ?? []}
                  onPick={pickCandidate}
                />
              </section>
            </div>

            <div id="trim-panel">
              <TrimPanel
                duration={record.duration}
                start={selection?.start ?? 0}
                end={selection?.end ?? Math.min(60, record.duration)}
                onChange={(start, end) => setSelection({ start, end })}
                aspects={["9:16", "4:5", "1:1", "16:9"]}
                modes={["blur", "crop"]}
                aspect={aspect}
                onAspect={setAspect}
                mode={mode}
                onMode={setMode}
                captions={captions}
                onCaptions={setCaptions}
                onGenerate={handleRender}
              />
            </div>
          </>
        )}

        {phase === "done" && renderResult && (
          <OutputCard result={renderResult} onNew={reset} />
        )}

        {phase === "idle" && !record && (
          <section className="howto">
            <div className="howto-card">
              <h3>1 · Paste a link</h3>
              <p>
                Any public video URL. Cookies for login-only sites can be added in{" "}
                <code>backend/data/cookies.txt</code>.
              </p>
            </div>
            <div className="howto-card">
              <h3>2 · We find the good parts</h3>
              <p>
                Free heuristics score speech density, audio energy and hook
                language — no paid AI, everything runs on your machine.
              </p>
            </div>
            <div className="howto-card">
              <h3>3 · Pick, trim, export</h3>
              <p>
                Accept an auto-pick or fine-tune start/end, then export a
                9:16 short with burnt-in captions.
              </p>
            </div>
          </section>
        )}
      </main>

      <footer className="footer">
        <p>
          ClipForge uses yt-dlp, FFmpeg and a few heuristics — all free and
          open source. Downloading content you don&apos;t own may violate
          platform terms; use it on your own videos or with permission.
        </p>
      </footer>

      <SettingsPanel
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        settings={settings}
        onSave={saveSettings}
      />
    </div>
  );
}

// -------------------------------------------------------------------------- //
function JobCard({ job, title }: { job: JobStatus; title: string }) {
  const done = job.status === "done";
  const failed = job.status === "error";
  return (
    <section className="card job-card">
      <div className="job-head">
        <h3>{failed ? "Something went wrong" : done ? "Finished" : title}</h3>
        <span className={`badge ${failed ? "badge-red" : done ? "badge-green" : "badge-blue"}`}>
          {failed ? job.error : `${Math.round(job.progress)}%`}
        </span>
      </div>
      {!failed && (
        <>
          <div className="progress">
            <div
              className="progress-fill"
              style={{ width: `${Math.max(2, job.progress)}%` }}
            />
          </div>
          <p className="muted small">{job.message}</p>
        </>
      )}
      {failed && <p className="muted small">{job.error}</p>}
    </section>
  );
}
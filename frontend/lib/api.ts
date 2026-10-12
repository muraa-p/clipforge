import {
  effectiveBackendUrl,
  effectiveToken,
  getSettings,
} from "./settings";
import type {
  AiConfig,
  AnalysisResult,
  Health,
  JobStatus,
  ProviderPreset,
  RenderResult,
} from "./types";

function withToken(url: string): string {
  const token = effectiveToken();
  if (!token) return url;
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}token=${encodeURIComponent(token)}`;
}

function authHeaders(): Record<string, string> {
  const token = effectiveToken();
  return token ? { "X-ClipForge-Token": token } : {};
}

async function parseError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data?.detail === "string") return data.detail;
    if (data?.detail) return JSON.stringify(data.detail);
  } catch {
    /* not json */
  }
  return `${res.status} ${res.statusText}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const base = effectiveBackendUrl(getSettings());
  let res: Response;
  try {
    res = await fetch(`${base}${path}`, {
      ...init,
      headers: { ...authHeaders(), ...(init?.headers ?? {}) },
    });
  } catch {
    throw new Error(
      `Can't reach the engine at ${base}. Start the backend and/or set the URL in Settings.`
    );
  }
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as T;
}

export const apiGet = <T>(path: string) => request<T>(path, { cache: "no-store" });

export const apiPost = <T>(path: string, body: unknown) =>
  request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const getHealth = () => apiGet<Health>("/api/health");

export const getProviders = () =>
  apiGet<{ presets: ProviderPreset[] }>("/api/providers");

/** Test an explicit engine URL/token without saving settings first. */
export async function probeBackend(
  backendUrl: string,
  token: string
): Promise<Health> {
  const base = (backendUrl || "http://127.0.0.1:8000").replace(/\/+$/, "");
  let res: Response;
  try {
    res = await fetch(`${base}/api/health`, {
      cache: "no-store",
      headers: token ? { "X-ClipForge-Token": token } : {},
    });
  } catch {
    throw new Error(`Nothing responded at ${base}.`);
  }
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as Health;
}

export const startAnalyze = (
  url: string,
  clipSeconds?: number,
  useAi = true,
  ai?: AiConfig
) =>
  apiPost<{ job_id: string }>("/api/analyze", {
    url,
    clip_seconds: clipSeconds,
    use_ai: useAi,
    ...(ai ? { ai } : {}),
  });

export const startRender = (body: {
  video_id: string;
  start: number;
  end: number;
  aspect: string;
  mode: string;
  captions: boolean;
}) => apiPost<{ job_id: string }>("/api/render", body);

export const getJob = (jobId: string) => apiGet<JobStatus>(`/api/jobs/${jobId}`);

export const getRecord = (videoId: string) =>
  apiGet<AnalysisResult>(`/api/records/${videoId}`);

export const mediaUrl = (videoId: string, filename: string) =>
  withToken(
    `${effectiveBackendUrl(getSettings())}/api/media/${videoId}/${filename}`
  );

export const absoluteUrl = (relative: string) =>
  withToken(`${effectiveBackendUrl(getSettings())}${relative}`);

export const downloadOutput = (result: RenderResult) => absoluteUrl(result.url);

export const fmtTime = (seconds: number): string => {
  const s = Math.max(0, Math.round(seconds));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r.toString().padStart(2, "0")}`;
};

export interface Cue {
  start: number;
  end: number;
  text: string;
}

export interface Candidate {
  start: number;
  end: number;
  duration: number;
  score: number;
  reasons: string[];
  text: string;
  source?: "ai" | "heuristic";
  title?: string;
}

export interface VideoInfo {
  title: string;
  uploader: string;
  thumbnail?: string | null;
  duration: number;
  webpage_url?: string;
  extractor?: string;
  view_count?: number | null;
}

export interface AnalysisResult {
  video_id: string;
  url: string;
  source: string;
  info: VideoInfo;
  signal: string;
  captions_source: string;
  duration: number;
  clip_seconds: number;
  cue_count: number;
  cues: Cue[];
  candidates: Candidate[];
  audio_error?: string | null;
  ai?: {
    used: boolean;
    provider?: string | null;
    model?: string | null;
    error?: string;
  };
}

export type JobStatusState = "queued" | "running" | "done" | "error";

export interface JobStatus {
  id: string;
  kind: "analyze" | "render";
  status: JobStatusState;
  progress: number;
  message: string;
  result?: AnalysisResult | RenderResult | null;
  error?: string | null;
}

export interface RenderResult {
  video_id: string;
  filename: string;
  url: string;
  thumbnail_url: string;
  captions_burned: boolean;
  aspect: string;
  mode: string;
  start: number;
  end: number;
  duration: number;
  size_bytes: number;
}

export interface AiConfig {
  provider?: string;
  base_url?: string;
  model?: string;
  api_key?: string;
}

export interface ProviderPreset {
  id: string;
  label: string;
  base_url: string;
  model: string;
  needs_key: boolean;
  signup?: string | null;
}

export interface Health {
  ok: boolean;
  ffmpeg: string | null;
  ffmpeg_installed: boolean;
  whisper: boolean;
  llm: {
    enabled: boolean;
    provider: string | null;
    model: string | null;
    key_configured: boolean;
  };
  ai_providers?: ProviderPreset[];
  aspects: string[];
  modes: string[];
}
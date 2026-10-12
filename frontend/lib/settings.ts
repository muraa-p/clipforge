"use client";

import { useSyncExternalStore } from "react";

/**
 * Runtime, browser-local settings.
 *
 * These let a *deployed* frontend (e.g. on Vercel) connect to whatever engine
 * the user runs, and let the user supply their own AI key ("bring your own
 * key"). Everything lives in localStorage; nothing is sent to the host.
 */

export interface AiSettings {
  /** "" = no AI (offline heuristics only). */
  provider: string;
  baseUrl: string;
  model: string;
  apiKey: string;
}

export interface AppSettings {
  /** Engine URL. Empty = fall back to NEXT_PUBLIC_API_BASE or 127.0.0.1:8000. */
  backendUrl: string;
  accessToken: string;
  ai: AiSettings;
}

const STORAGE_KEY = "clipforge.settings.v1";

export const DEFAULT_SETTINGS: AppSettings = {
  backendUrl: process.env.NEXT_PUBLIC_API_BASE ?? "",
  accessToken: process.env.NEXT_PUBLIC_ACCESS_TOKEN ?? "",
  ai: { provider: "", baseUrl: "", model: "", apiKey: "" },
};

let current: AppSettings = DEFAULT_SETTINGS;
const listeners = new Set<() => void>();

function str(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function normalize(raw: unknown): AppSettings {
  const value = (raw ?? {}) as Partial<AppSettings>;
  const ai = (value.ai ?? {}) as Partial<AiSettings>;
  return {
    backendUrl: str(value.backendUrl, DEFAULT_SETTINGS.backendUrl),
    accessToken: str(value.accessToken),
    ai: {
      provider: str(ai.provider),
      baseUrl: str(ai.baseUrl),
      model: str(ai.model),
      apiKey: str(ai.apiKey),
    },
  };
}

export function getSettings(): AppSettings {
  return current;
}

function emit(): void {
  listeners.forEach((fn) => fn());
}

/** Read persisted settings. Safe to call during a client effect. */
export function loadSettings(): AppSettings {
  if (typeof window === "undefined") return current;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) current = normalize(JSON.parse(raw));
  } catch {
    /* ignore malformed storage */
  }
  emit();
  return current;
}

export function saveSettings(next: AppSettings): void {
  current = normalize(next);
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(current));
    } catch {
      /* storage may be disabled */
    }
  }
  emit();
}

export function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

/** Reactive settings for components. SSR snapshot is the default. */
export function useSettings(): AppSettings {
  return useSyncExternalStore(subscribe, getSettings, () => DEFAULT_SETTINGS);
}

export function effectiveBackendUrl(settings: AppSettings = current): string {
  return (settings.backendUrl || "http://127.0.0.1:8000").replace(/\/+$/, "");
}

export function effectiveToken(settings: AppSettings = current): string {
  return settings.accessToken || "";
}

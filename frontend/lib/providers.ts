import type { ProviderPreset } from "./types";

/**
 * Fallback provider list, mirroring the backend presets. Used so the Settings
 * UI still works when the engine can't be reached; it's replaced by
 * `/api/providers` as soon as the backend answers.
 */
export const FALLBACK_PRESETS: ProviderPreset[] = [
  {
    id: "groq",
    label: "Groq — fast, free tier",
    base_url: "https://api.groq.com/openai/v1",
    model: "llama-3.3-70b-versatile",
    needs_key: true,
    signup: "https://console.groq.com/keys",
  },
  {
    id: "cerebras",
    label: "Cerebras — free tier",
    base_url: "https://api.cerebras.ai/v1",
    model: "llama3.1-8b",
    needs_key: true,
    signup: "https://cloud.cerebras.ai/",
  },
  {
    id: "gemini",
    label: "Google Gemini — free tier",
    base_url: "https://generativelanguage.googleapis.com/v1beta/openai",
    model: "gemini-2.0-flash",
    needs_key: true,
    signup: "https://aistudio.google.com/app/apikey",
  },
  {
    id: "mistral",
    label: "Mistral — free tier",
    base_url: "https://api.mistral.ai/v1",
    model: "mistral-small-latest",
    needs_key: true,
    signup: "https://console.mistral.ai/api-keys",
  },
  {
    id: "openrouter",
    label: "OpenRouter — free models",
    base_url: "https://openrouter.ai/api/v1",
    model: "meta-llama/llama-3.3-70b-instruct:free",
    needs_key: true,
    signup: "https://openrouter.ai/keys",
  },
  {
    id: "ollama",
    label: "Ollama — local, no key",
    base_url: "http://127.0.0.1:11434/v1",
    model: "llama3.1",
    needs_key: false,
    signup: "https://ollama.com/download",
  },
  {
    id: "opencode",
    label: "OpenCode Zen — paid key",
    base_url: "https://opencode.ai/inference/openai/v1",
    model: "glm-5.1",
    needs_key: true,
    signup: "https://opencode.ai/console",
  },
  {
    id: "custom",
    label: "Custom OpenAI-compatible endpoint",
    base_url: "",
    model: "",
    needs_key: false,
    signup: null,
  },
];

"""Optional, pluggable LLM analysis provider.

ClipForge works fully **without any AI** — the default analysis is 100% offline
heuristics (see ``analyze.py``). This module lets an *optional* OpenAI-compatible
endpoint re-rank and pick highlights, then falls back to heuristics automatically
on any error, timeout, missing key or rate limit.

The provider can be configured two ways:

1. **Per request** (what the web UI does — "bring your own key"). The
   ``/api/analyze`` endpoint accepts an ``ai`` object:
   ``{"provider": "groq", "api_key": "gsk_...", "model": "..."}``.
2. **Environment variables** (for headless / server use):
   ``CLIPFORGE_LLM_PROVIDER``, ``CLIPFORGE_LLM_BASE_URL``,
   ``CLIPFORGE_LLM_MODEL``, ``CLIPFORGE_LLM_API_KEY``.

Presets cover providers with genuinely free tiers (no card), plus local Ollama
and OpenCode Zen (paid key):

    groq, cerebras, gemini, mistral, openrouter, ollama, opencode, custom

Note: OpenCode Zen's *free* models are gated to the OpenCode app ("FreeTierError"),
so calling them from here needs a paid Console key.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Callable

from .captions import Cue

# ``label``/``signup`` power the UI dropdown; ``needs_key`` drives whether the
# provider counts as "configured" without an API key (Ollama / custom local do).
PRESETS: dict[str, dict[str, Any]] = {
    "groq": {
        "label": "Groq — fast, free tier",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "key_env": "GROQ_API_KEY",
        "needs_key": True,
        "signup": "https://console.groq.com/keys",
    },
    "cerebras": {
        "label": "Cerebras — free tier",
        "base_url": "https://api.cerebras.ai/v1",
        "model": "llama3.1-8b",
        "key_env": "CEREBRAS_API_KEY",
        "needs_key": True,
        "signup": "https://cloud.cerebras.ai/",
    },
    "gemini": {
        "label": "Google Gemini — free tier",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.0-flash",
        "key_env": "GEMINI_API_KEY",
        "needs_key": True,
        "signup": "https://aistudio.google.com/app/apikey",
    },
    "mistral": {
        "label": "Mistral — free tier",
        "base_url": "https://api.mistral.ai/v1",
        "model": "mistral-small-latest",
        "key_env": "MISTRAL_API_KEY",
        "needs_key": True,
        "signup": "https://console.mistral.ai/api-keys",
    },
    "openrouter": {
        "label": "OpenRouter — free models",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
        "key_env": "OPENROUTER_API_KEY",
        "needs_key": True,
        "signup": "https://openrouter.ai/keys",
    },
    "ollama": {
        "label": "Ollama — local, no key",
        "base_url": "http://127.0.0.1:11434/v1",
        "model": "llama3.1",
        "key_env": None,
        "needs_key": False,
        "signup": "https://ollama.com/download",
    },
    "opencode": {
        "label": "OpenCode Zen — paid key",
        "base_url": "https://opencode.ai/inference/openai/v1",
        "model": "glm-5.1",
        "key_env": "OPENCODE_CONSOLE_TOKEN",
        "needs_key": True,
        "signup": "https://opencode.ai/console",
    },
}

MAX_TRANSCRIPT_CHARS = 14000

# Values that mean "no AI — use the offline heuristics".
_DISABLED = {"", "off", "none", "heuristic", "heuristics", "false", "no"}


class LLMError(RuntimeError):
    pass


def presets_for_ui() -> list[dict[str, Any]]:
    """Public preset list for the frontend provider dropdown."""
    items: list[dict[str, Any]] = []
    for pid, preset in PRESETS.items():
        items.append(
            {
                "id": pid,
                "label": preset["label"],
                "base_url": preset["base_url"],
                "model": preset["model"],
                "needs_key": bool(preset.get("needs_key", True)),
                "signup": preset.get("signup"),
            }
        )
    items.append(
        {
            "id": "custom",
            "label": "Custom OpenAI-compatible endpoint",
            "base_url": "",
            "model": "",
            "needs_key": False,
            "signup": None,
        }
    )
    return items


def _clean(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def resolve_config(override: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Return the active provider config, or ``None`` when AI is off.

    ``override`` (from the request body) takes priority over environment vars.
    """
    override = override or {}
    provider = (_clean(override.get("provider")) or _clean(os.environ.get("CLIPFORGE_LLM_PROVIDER"))).lower()
    if provider in _DISABLED:
        return None

    base_url = _clean(override.get("base_url")) or _clean(os.environ.get("CLIPFORGE_LLM_BASE_URL"))
    model = _clean(override.get("model")) or _clean(os.environ.get("CLIPFORGE_LLM_MODEL"))
    api_key = _clean(override.get("api_key")) or _clean(os.environ.get("CLIPFORGE_LLM_API_KEY"))

    preset = PRESETS.get(provider) if provider else None
    if provider and provider != "custom" and preset is None:
        return None  # unknown provider name
    if preset is not None:
        base_url = base_url or str(preset["base_url"])
        model = model or str(preset["model"])
        key_env = preset.get("key_env")
        if not api_key and key_env:
            api_key = _clean(os.environ.get(str(key_env)))

    if not base_url:
        return None

    return {
        "provider": provider or "custom",
        "base_url": base_url.rstrip("/"),
        "model": model or "gpt-4o-mini",
        "api_key": api_key,
        "preset": preset,
        "timeout": int(os.environ.get("CLIPFORGE_LLM_TIMEOUT", "60")),
    }


def _needs_key(config: dict[str, Any]) -> bool:
    provider = config["provider"]
    if provider == "ollama":
        return False
    preset = config.get("preset")
    if preset is None:
        return False  # custom endpoint (e.g. local LM Studio) may not need a key
    return bool(preset.get("needs_key", True))


def describe(override: dict[str, Any] | None = None) -> dict[str, Any]:
    """Configuration summary (never exposes the key)."""
    config = resolve_config(override)
    if not config:
        return {"enabled": False, "provider": None, "model": None, "key_configured": False}
    return {
        "enabled": bool(config["api_key"]) or not _needs_key(config),
        "provider": config["provider"],
        "model": config["model"],
        "key_configured": bool(config["api_key"]),
    }


def is_enabled(override: dict[str, Any] | None = None) -> bool:
    return bool(describe(override)["enabled"])


# --------------------------------------------------------------------------- #
# Prompting
# --------------------------------------------------------------------------- #
def _format_transcript(cues: list[Cue]) -> str:
    lines: list[str] = []
    used = 0
    for cue in cues:
        line = f"[{cue.start:.1f}-{cue.end:.1f}] {cue.text}".strip()
        if used + len(line) > MAX_TRANSCRIPT_CHARS:
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines)


def _system_prompt(clip_seconds: int, max_candidates: int) -> str:
    return (
        "You are an expert short-form video editor who cuts viral vertical shorts "
        "(TikTok/Reels/YouTube Shorts). You are given a timestamped transcript. "
        f"Choose up to {max_candidates} self-contained highlights, each about "
        f"{clip_seconds} seconds long, that would make a great short: a strong hook "
        "in the first seconds, a complete thought or payoff, and no long silences. "
        "Prefer surprising, emotional, useful or funny moments; avoid intros, "
        "outros, sponsor reads and rambling. "
        "Respond with ONLY a JSON object, no prose, shaped exactly like: "
        '{"picks":[{"start":<seconds>,"end":<seconds>,"title":"<short title>",'
        '"reason":"<why this works>"}]}'
    )


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise LLMError("Model did not return JSON")
    return json.loads(match.group(0))


def _post(config: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{config['base_url']}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['api_key']}" if config["api_key"] else "Bearer none",
            "User-Agent": "ClipForge/0.1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=config["timeout"]) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise LLMError(f"HTTP {exc.code}: {body}") from exc
    except Exception as exc:  # noqa: BLE001
        raise LLMError(str(exc)) from exc


def pick_highlights(
    cues: list[Cue],
    duration: float,
    clip_seconds: int,
    max_candidates: int,
    report: Callable[[float, str], None] | None = None,
    override: dict[str, Any] | None = None,
) -> list[dict[str, Any]] | None:
    """Ask the LLM for highlights. Returns ``None`` when AI is not configured.

    Raises :class:`LLMError` on failure so the caller can fall back to heuristics.
    """
    config = resolve_config(override)
    if not config or not is_enabled(override) or not cues:
        return None

    if report:
        report(0.1, f"Asking {config['provider']} ({config['model']}) for picks…")

    payload = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": _system_prompt(clip_seconds, max_candidates)},
            {
                "role": "user",
                "content": f"Video length: {duration:.0f}s.\n\nTranscript:\n"
                + _format_transcript(cues),
            },
        ],
        "temperature": 0.3,
        "max_tokens": 900,
    }

    data = _post(config, payload)
    choices = data.get("choices") or []
    if not choices:
        raise LLMError(f"Unexpected response: {str(data)[:300]}")
    content = choices[0].get("message", {}).get("content") or ""
    parsed = _extract_json(content)

    picks: list[dict[str, Any]] = []
    for raw in parsed.get("picks", [])[:max_candidates]:
        try:
            start = float(raw["start"])
            end = float(raw["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if end <= start:
            continue
        start = max(0.0, min(start, max(0.0, duration - 1)))
        end = max(start + 3.0, min(end, duration))
        if end - start > 120:
            end = start + 120
        excerpt = " ".join(
            cue.text for cue in cues if cue.start >= start - 1 and cue.end <= end + 1
        )
        picks.append(
            {
                "start": round(start, 2),
                "end": round(end, 2),
                "duration": round(end - start, 2),
                "score": 1.0 - 0.05 * len(picks),
                "reasons": [str(raw.get("reason") or "AI pick")],
                "title": str(raw.get("title") or ""),
                "text": excerpt[:500],
                "source": "ai",
            }
        )

    if report:
        report(1.0, f"AI suggested {len(picks)} highlight(s)")
    return picks

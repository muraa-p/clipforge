# ✂️ ClipForge

Paste a video link → get a vertical short. **100% free** — no subscriptions, no
watermarks. The analysis runs offline with **no AI at all** by default; if you
want smarter picks you can optionally add your own **free** AI key (bring your
own key).

| Piece | Tool | Cost |
|---|---|---|
| Fetch videos + captions | [yt-dlp](https://github.com/yt-dlp/yt-dlp) (open source) | free |
| Cut / crop / encode / captions | [FFmpeg](https://ffmpeg.org) (open source) | free |
| Find the good parts | Built-in heuristics (speech density + audio energy + hook language) | free, **no AI**, no GPU |
| Smarter picks (optional) | Any free OpenAI-compatible model — *you* bring the key | free tier |
| Transcribe videos with no captions | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (optional) | free |
| UI + API | Next.js + FastAPI | free |

---

## Quick start (Windows / macOS / Linux)

```powershell
# 1. one-time setup: Python venv, deps, and frontend packages
./scripts/setup.ps1        # (or bash scripts/setup.sh)

# 2. run both servers in separate terminals
./scripts/run-backend.ps1   # → http://127.0.0.1:8000
./scripts/run-frontend.ps1  # → http://localhost:3000
```

Open **http://localhost:3000**, paste any video link (YouTube, TikTok, Instagram,
X, Vimeo, …), hit **Analyze**, then pick a highlight or trim manually and hit
**Generate short**.

> On the very first analyze, ClipForge downloads a static FFmpeg build
> (~90 MB) into `backend/bin/` automatically. If you already have FFmpeg on
> your PATH it will use that instead.

---

## How the "analysis" works (no paid AI)

1. yt-dlp downloads the video (≤1080p, mp4) and its captions.
2. If there are no captions and you installed the optional Whisper extra, it
   transcribes locally on your CPU.
3. Heuristics score every sliding window of the timeline:
   - **Speech density** — words per second from captions
   - **Audio energy** — windowed loudness decoded with FFmpeg
   - **Hook language** — phrases like *"here's why"*, *"most people"*,
     *"never"*, and question/number usage
4. Scores are **percentile-ranked per video**, so detections adapt to each
   video instead of using fixed thresholds. Windows get snapped to sentence
   boundaries so clips never cut mid-word.

---

## Manual trim & options

- **Frame:** `9:16` (TikTok/Reels/Shorts), `4:5`, `1:1`, `16:9`
- **Style:** `blur` (video centered over a blurred background) or `crop`
  (full-bleed center crop)
- **Captions:** burn styled captions into the video (on/off)

---

## Optional extras

```powershell
# Local transcription for videos with no caption track (e.g. some TikTok/IG files)
& .\backend\.venv\Scripts\pip install -r .\backend\requirements-optional.txt
```

- **Login-only sites** (Instagram, Facebook, X): export your browser cookies
  to Netscape format and save them as `backend/data/cookies.txt`.
- **Speed:** render quality is tuned for a laptop CPU. Set
  `CLIPFORGE_X264_PRESET=ultrafast` to render faster, or
  `CLIPFORGE_MAX_HEIGHT=720` to download smaller sources.
- **API:** the backend exposes a small REST API — see `http://127.0.0.1:8000/docs`.

---

## AI highlight picking (optional — **off by default**)

ClipForge works with **no AI at all**: the offline heuristics are the default and
need no key, no account and no GPU. If you'd like a model to re-rank the picks,
add a **free** key straight in the UI (**⚙ Settings → AI highlight picking**) —
it's stored only in your browser and sent to your own engine. For headless use,
set environment variables instead.

Every option is OpenAI-compatible, so any of these works:

| Preset | Get a free key |
|---|---|
| `groq` | https://console.groq.com/keys |
| `cerebras` | https://cloud.cerebras.ai/ |
| `gemini` | https://aistudio.google.com/app/apikey |
| `mistral` | https://console.mistral.ai/api-keys |
| `openrouter` | https://openrouter.ai/keys (pick a `:free` model) |
| `ollama` | local — no key |
| `opencode` | OpenCode Zen — **paid** key required |

Headless / server config (same presets, via env):

```powershell
$env:CLIPFORGE_LLM_PROVIDER = "groq"
$env:GROQ_API_KEY = "gsk_..."
```

Or point at anything OpenAI-compatible: `CLIPFORGE_LLM_BASE_URL`,
`CLIPFORGE_LLM_MODEL`, `CLIPFORGE_LLM_API_KEY`.

If the key is missing, rate-limited, or the request fails, ClipForge **falls
back to the heuristics automatically** — you never lose the feature.

> **OpenCode Zen:** its free models are gated to the OpenCode app itself
> (`403 FreeTierError: "OpenCode's free tier can only be used from within
> OpenCode"`), so using them here needs a paid Console key. And remember an LLM
> only replaces the *picking* step — it does **not** reduce your machine's load
> for downloading/encoding, which always runs on the engine.

---

## Use it from anywhere: UI on Vercel, engine wherever you want

> 📘 **Step-by-step, free, always-on deployment (Oracle Always Free, GCP
> free tier, HF Spaces, Docker): see [`DEPLOY.md`](DEPLOY.md).**

ClipForge splits in two:

- **UI** — a static Next.js app. Host it free on Vercel; it's just a search bar
  that talks to your engine.
- **Engine** — FastAPI + yt-dlp + FFmpeg. This is the heavy part and must run on a
  machine that's **on** (your PC, a free-tier VM, a home server…).

### 1. Deploy the UI to Vercel (free)

1. Import this repo on Vercel.
2. Set **Root Directory** to `frontend` (or `clipforge/frontend` if ClipForge
   lives inside another repo). Next.js is auto-detected.
3. Deploy. No env vars needed.

Open the deployed URL, click **⚙ Settings**, and set your **Backend URL** (and
**Access token** if the engine has one). Settings live in the browser, so you can
point one deployment at different engines.

### 2. Run the engine

**Option A — your PC + a free tunnel** (laptop must be on):

```powershell
$env:CLIPFORGE_ACCESS_TOKEN = "some-long-random-secret"
./scripts/run-backend.ps1
./scripts/tunnel-cloudflared.ps1   # prints https://*.trycloudflare.com
```

Paste that URL into the UI's **Backend URL**, and the same secret into
**Access token**.

**Option B — always on, laptop off** (Docker on a free-tier VM / home server):

```bash
# from the clipforge/ folder; put CLIPFORGE_ACCESS_TOKEN=... in a .env file
docker compose up -d
```

Then set **Backend URL** to `http://<host>:8000` (or front it with a tunnel /
HTTPS). The engine can also read a free AI key from env (see above).

### Security

Set `CLIPFORGE_ACCESS_TOKEN` any time the engine is reachable off your machine —
the UI sends it as a header (and `?token=` on video URLs). Without it, anyone with
the URL can drive your engine. Tailscale `serve` keeps access private to your own
devices and needs no token.

Public engines are throttled and self-cleaning out of the box:
`CLIPFORGE_MAX_CONCURRENT_JOBS` (default 2), `CLIPFORGE_MAX_QUEUED_JOBS`
(default 8 → HTTP 429 past that), and `CLIPFORGE_DATA_TTL_HOURS` (default 24,
deletes old sources/outputs). Only `http(s)` links are accepted and private /
loopback hosts are blocked; `/api/health` stays public for uptime checks.

### Honest limits

Free serverless can't host the **engine** (FFmpeg renders exceed the time limits
and datacenter IPs get bot-blocked by YouTube), so the engine has to run somewhere
that stays on. The UI, however, can be online 24/7 for free.

---

## Project layout

```
clipforge/
├─ backend/               # the engine (download + encode) — run it anywhere
│  ├─ app/
│  │  ├─ main.py          # FastAPI routes (analyze / render / jobs / media / providers)
│  │  ├─ pipeline.py      # analyse & render job steps
│  │  ├─ analyze.py       # free highlight heuristics (no AI)
│  │  ├─ llm.py           # optional AI picks — presets + per-request (BYOK) config
│  │  ├─ downloader.py    # yt-dlp wrapper
│  │  ├─ captions.py      # VTT parsing + ASS burn-in generation
│  │  ├─ render.py        # FFmpeg cut / reframe / encode
│  │  ├─ transcribe.py    # optional faster-whisper fallback
│  │  ├─ bins.py          # auto-install FFmpeg
│  │  └─ jobs.py / store.py
│  ├─ Dockerfile          # containerize the engine (free VM / home server)
│  └─ requirements*.txt
├─ frontend/              # Next.js UI — deploy to Vercel
│  ├─ app/page.tsx        # search bar + the whole flow
│  ├─ components/         # CandidateList, TrimPanel, OutputCard, SettingsPanel
│  ├─ lib/settings.ts     # browser-local engine URL / token / AI key (BYOK)
│  ├─ lib/api.ts, providers.ts, types.ts
│  └─ vercel.json, .env.example
├─ docker-compose.yml     # one-command engine
├─ DEPLOY.md              # free always-on deploy guide (Vercel + VM)
├─ LICENSE                # MIT
└─ scripts/               # setup, run, tunnel + deploy helpers
```

---

## Notes & deets

- Everything is local by default. No video, caption or transcript ever leaves
  your PC unless *you* enable AI — and then only the text transcript is sent, to
  the provider *you* chose, with the key *you* entered.
- Your AI key and settings live only in your browser (`localStorage`) and are
  sent only to your own engine.
- yt-dlp is updated constantly; bump it with
  `pip install -U yt-dlp` if a site stops working.
- Downloading content you don't own may violate the platform's terms of
  service. Use ClipForge on your own videos or content you have permission for.
- First-run Whisper transcription downloads a ~150 MB model once. It's slow-ish
  on laptops without a GPU (that's the only tradeoff — it's still free).
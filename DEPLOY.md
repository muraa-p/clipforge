# 🚀 Deploying ClipForge (free, always-on)

> Source: **https://github.com/muraa-p/clipforge**

ClipForge is two pieces, and only one of them needs a machine that stays on:

| Piece | What it does | Where it lives | Always on? |
|---|---|---|---|
| **UI** (Next.js) | the page you click on | **Vercel** — free, 24/7 | ✅ free |
| **Engine** (FastAPI + yt-dlp + FFmpeg) | downloads + encodes | a small **always-on** box | needs a host |

Free serverless (Vercel/Netlify functions) **cannot** run the engine: renders
take minutes and datacenter IPs get bot-blocked by YouTube. So the engine needs a
real always-on host. This guide uses only **free** options — no paid tiers.

> Results: a public UI URL you can open from any device, pointed at an engine
> that stays up even when your laptop is closed.

---

## 0. Pick an engine host

| Option | Cost | Specs | Effort | Notes |
|---|---|---|---|---|
| **Oracle Cloud Always Free** ⭐ | free forever | up to 4 ARM cores / 24 GB RAM | medium | best for FFmpeg; card needed only for ID verification |
| **Google Cloud free `e2-micro`** | free tier | 1 shared vCPU / 1 GB | medium | tight but works for short clips |
| **Hugging Face Spaces (Docker)** | free CPU | 2 vCPU / 16 GB | low | public by default + sleeps when idle; check their ToS |
| **Any Docker box** (home server, NAS, Pi, old laptop) | free | — | low | needs your network reachable (tunnel helps) |
| **Your PC + tunnel** | free | — | low | ❌ *not always-on* — only while the PC is on |

Everything below is **free**. You only need an account on whichever host you pick.

---

## 1. Deploy the UI to Vercel (2 minutes)

### Option A — CLI (no Git needed)

From the `frontend` folder (repo root for the dedicated repo):

```bash
vercel login                 # once
vercel deploy --prod --yes --project clipforge
```

Vercel prints your production URL (e.g. `https://clipforge.vercel.app`).

### Option B — Dashboard (Git)

1. Push this repo to GitHub.
2. In Vercel → **Add New → Project** → import the repo.
3. Set **Root Directory** to `frontend` (this repo's layout — use
   `clipforge/frontend` if you kept ClipForge inside another repo). Next.js is
   auto-detected.
4. **Deploy**. No environment variables are required.

Either way the UI is a static app that reads its engine address from the
browser, so you never redeploy it to point at a new engine.

---

## 2. Run the engine, always on

### Option A — Oracle Cloud Always Free ⭐ (recommended)

1. Create a free Oracle Cloud account (card is used for identity only; Always
   Free resources are not charged).
2. **Create instance** → image **Ubuntu 24.04**, shape **VM.Standard.A1.Flex**
   (Ampere ARM, up to 4 OCPU / 24 GB — all free).
3. Under **Add SSH keys**, let Oracle generate a key pair and download it.
4. Expand **Show advanced options → Management → Cloud-init / user data** and
   paste the whole contents of [`scripts/cloud-init.yaml`](scripts/cloud-init.yaml).
5. Create it. In the VCN's **Security List**, add ingress rules from
   `0.0.0.0/0` for TCP ports **80**, **443** and **8000**.
6. Wait ~3 minutes. The bootstrap prints your token and URLs to the boot log;
   over SSH you can check them:

   ```bash
   ssh -i <key> ubuntu@<public-ip>
   sudo cat /opt/clipforge/.env        # shows CLIPFORGE_ACCESS_TOKEN
   # the script also prints an https://<public-ip>.sslip.io URL — use that one
   curl https://<public-ip>.sslip.io/api/health
   ```

Prefer to do it by hand instead of cloud-init? SSH in and run:

```bash
curl -fsSL https://raw.githubusercontent.com/muraa-p/clipforge/main/scripts/deploy-engine.sh | bash
# or, from an existing clone (repo root):
bash scripts/deploy-engine.sh
```

The script installs Docker, clones the source, generates a strong token, writes
`.env`, and starts the engine with `restart: unless-stopped`. It also stands up a
**free HTTPS front door** (Caddy + a Let's Encrypt cert for
`<your-ip>.sslip.io`) so the HTTPS Vercel UI can call it — no domain required.

### Option B — Google Cloud free `e2-micro`

1. Create a VM: **Ubuntu 24.04**, machine type **e2-micro**, region
   `us-west1` / `us-central1` / `us-east1` (the free-tier regions).
2. Allow HTTP traffic (or add a firewall rule for TCP `8000`).
3. SSH in (browser SSH works) and run the same one-liner as above.
4. 1 GB RAM is enough for 45–60 s shorts; for longer clips set
   `CLIPFORGE_MAX_HEIGHT=720` in `/opt/clipforge/.env`.

### Option C — Hugging Face Spaces (easiest, with caveats)

HF Spaces can run a Docker app for free (2 vCPU / 16 GB):

1. Create a **Space** → SDK **Docker** → **Blank**.
2. Add these files to the Space repo:
   - `Dockerfile` (copy `clipforge/backend/Dockerfile`, but make the final
     command listen on `$PORT`, e.g. `--port ${PORT:-7860}` and `EXPOSE 7860`).
   - the `backend/app` folder and `requirements.txt`.
3. In Space **Settings → Variables and secrets**, add a secret
   `CLIPFORGE_ACCESS_TOKEN`.
4. The Space gives you an HTTPS URL like
   `https://<user>-<space>.hf.space` → that's your engine URL.

Caveats: free Spaces are **public** and **sleep after inactivity** (first request
after sleeping is slow), and HF may not permit pure-infra workloads — check their
terms before relying on it.

### Option D — any Docker host you own

On a home server, NAS or Raspberry Pi:

```bash
git clone https://github.com/muraa-p/clipforge.git
cd clipforge
cp .env.example .env          # set CLIPFORGE_ACCESS_TOKEN
docker compose up -d --build
```

Expose it with a tunnel if your network isn't public:

```bash
cloudflared tunnel --url http://localhost:8000      # or: tailscale serve
```

### Option E — your PC + tunnel (only while the PC is on)

```powershell
$env:CLIPFORGE_ACCESS_TOKEN = "some-long-random-secret"
./scripts/run-backend.ps1
./scripts/tunnel-cloudflared.ps1     # prints https://*.trycloudflare.com
```

---

## 3. Point the UI at the engine

1. Open your Vercel URL.
2. Click **⚙ Settings**.
3. **Engine URL** → your engine address. Use the **`https://…`** URL the deploy
   script printed (e.g. `https://203.0.113.7.sslip.io`) — an `https` page can't
   call a plain `http://` engine.
4. **Access token** → the `CLIPFORGE_ACCESS_TOKEN` from step 2.
5. (Optional) **AI highlight picking** → paste a free key (Groq/Gemini/…).

Both values are stored in **your browser only** — the engine URL and token never
leave your device except to talk to your own engine.

---

## 4. HTTPS (already handled — plus alternatives)

The Vercel UI is served over HTTPS, and browsers block an HTTPS page from calling
a plain `http://` engine ("mixed content"). `scripts/deploy-engine.sh` **sets this
up for you**: it starts a [Caddy](https://caddyserver.com) reverse proxy that
obtains a free Let's Encrypt certificate for `<your-ip>.sslip.io` (a wildcard DNS
service — you don't need to own a domain). Just open inbound TCP **80** and
**443**, then use the `https://<your-ip>.sslip.io` URL.

Other ways to get HTTPS, if you prefer:

- **Cloudflare Tunnel** on the engine box:
  ```bash
  cloudflared tunnel --url http://localhost:8000
  ```
  Use the printed `https://…trycloudflare.com` URL as the Engine URL.
- **Tailscale** (`tailscale serve`) keeps the engine private to your devices —
  the best choice if you're the only user.
- **Caddy** reverse proxy for a real domain + automatic TLS.

---

## Operations

```bash
docker compose logs -f            # tail logs
docker compose up -d --build      # apply updates (after git pull)
docker compose down               # stop
docker compose ps                 # status
```

### Built-in safety (already on)

Public engines are throttled and self-cleaning out of the box:

| Env var | Default | Purpose |
|---|---|---|
| `CLIPFORGE_ACCESS_TOKEN` | *(empty)* | shared secret the UI must send |
| `CLIPFORGE_MAX_CONCURRENT_JOBS` | `2` | jobs that run at once (rest stay queued) |
| `CLIPFORGE_MAX_QUEUED_JOBS` | `8` | reject new jobs past this (HTTP 429) |
| `CLIPFORGE_DATA_TTL_HOURS` | `24` | delete old sources/outputs (0 = keep) |

Also enforced: `http(s)`-only links with private/loopback hosts blocked (basic
SSRF guard), `/api/health` left public for uptime checks, and safe path handling
on all media/output routes.

**Always set `CLIPFORGE_ACCESS_TOKEN` when the engine is reachable off your
machine.** Without it anyone with the URL can drive your engine.

---

## Cost

| Item | Cost |
|---|---|
| Vercel UI | free |
| Oracle/GCP free VM | free |
| yt-dlp, FFmpeg, heuristics | free, offline |
| Optional AI | free tier, your own key, falls back automatically |

---

## Troubleshooting

- **UI says "Engine offline"** — check `curl http://<ip>:8000/api/health`
  returns `{"ok": true}`; confirm the port is open in the cloud firewall and that
  the Engine URL in Settings has no trailing slash.
- **401 in the UI** — the token in Settings doesn't match
  `CLIPFORGE_ACCESS_TOKEN`.
- **Mixed-content / CORS error** — the page is HTTPS but the engine is HTTP. Put
  the engine behind HTTPS (Cloudflare/Tailscale/Caddy).
- **"Could not read that link"** — the site needs login; drop a Netscape
  `cookies.txt` at `backend/data/cookies.txt` (mounted at `/app/data` in Docker).
- **YouTube blocks the download** — datacenter IPs are sometimes rate-limited;
  try again later, raise the source quality/format, or host the engine on a
  residential connection.
- **Renders are slow / OOM on 1 GB** — set `CLIPFORGE_MAX_HEIGHT=720` and
  `CLIPFORGE_X264_PRESET=veryfast`.

# muse2api

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?logo=python" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker" alt="Docker" />
  <img src="https://img.shields.io/badge/API-OpenAI%20%7C%20Anthropic%20Compatible-green" alt="OpenAI & Anthropic Compatible" />
  <img src="https://img.shields.io/badge/License-MIT-orange" alt="MIT License" />
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey" alt="Platform" />
</p>

<p align="center">
  <b>OpenAI- and Anthropic-compatible API for <a href="https://muse.ai/">muse.ai</a>: chat, image generation, video generation, Claude Code & Agent SDK support, multi-account pool, and automatic session renewal.</b>
</p>

> **Fork notice:** This is a fork of [czg86389-hub/muse2api](https://github.com/czg86389-hub/muse2api). The upstream is a solid Linux/Docker tool. This fork adds everything listed below that the upstream doesn't have — most notably **working tool calls** (the upstream documents this as permanently unsupported). All core reverse-engineering credit goes to the original author and the [LINUX DO](https://linux.do/) community.

---

## What this fork adds (upstream doesn't have these)

| Feature | Status in upstream | This fork |
|---|---|---|
| **Tool calling** (`tool_calls`, function calling) | ❌ Documented unsupported — muse.ai refuses prompt injection | ✅ **Solved via Jev** (TypeSafe free, no key) |
| **Anthropic Messages API** (`POST /v1/messages`) | ❌ Not present | ✅ Claude Code, Agent SDK, Anthropic SDKs |
| **Windows native support** | ❌ Linux/Docker only | ✅ Auto-detects Chrome/Edge, `start-windows.bat` |
| **Bilingual EN/ZH admin UI** | ❌ Chinese-only UI | ✅ Full i18n toggle, EN default |
| **Streaming tool_calls via SSE** | ❌ N/A | ✅ SSE keepalive prevents client timeouts |
| **Media bulk delete** | ✅ Added in upstream Oct 2026 | ✅ Synced + bilingual i18n |

---

## What it does

muse2api wraps [muse.ai](https://muse.ai/)'s web interface as a drop-in OpenAI- and Anthropic-compatible REST API. Any client that speaks OpenAI's API or Anthropic's Messages API works with no code changes — including agentic clients like Claude Code, omp, Cline, and Cursor that depend on tool calls.

| Capability | Endpoint | Note |
|---|---|---|
| Chat (OpenAI format, streaming + sync) | `POST /v1/chat/completions` | |
| **Tool calls / function calling** | `POST /v1/chat/completions` | **via Jev — this fork only** |
| Messages (Anthropic format, streaming + sync) | `POST /v1/messages` | **this fork only** |
| Image generation | `POST /v1/images/generations` | |
| Image editing | `POST /v1/images/edits` | |
| Video generation | `POST /v1/videos` | |
| Video status polling | `GET /v1/videos/{task_id}` | |
| Token counting | `POST /v1/messages/count_tokens` | |
| Serve generated media | `GET /v1/media/{filename}` | |

### How tool calling works

muse.ai's assistant refuses to emit pseudo-tool-call JSON when asked via prompt injection — the upstream project verified this and marked it unsupported. This fork bypasses it entirely:

1. **Round 1:** [Jev](https://docs.typesafe.ai) (TypeSafe System One model, free via OpenCode — `Authorization: Bearer public`, no signup) reads the conversation and tool definitions, picks the right tool, and fills its arguments. Returns `tool_calls` in ~1s without touching muse.ai.
2. **Round 2:** The agent calls the real function and sends the result back. muse2api injects it as a natural assistant turn in the prompt — muse.ai responds as if it already had the data, no protocol visible.

Tested with: Claude Code, omp (oh-my-pi), Cline, Cursor, Anthropic SDK.

Features:

- Multi-account pool: import multiple muse.ai accounts; requests are load-balanced and automatically fail over.
- Auto session renewal: a background keepalive hits `/api/session` every 15 min to renew cookies before they expire (solves the 48 h Meta cookie limit).
- Anti-bot stealth: two-layer JS injection (puppeteer-extra 16 evasions + dynamic hardware/canvas/audio overrides matched to your real Chrome version).
- Windows support: auto-detects Chrome/Edge, no WSL needed; `start-windows.bat` double-click launch.
- Admin web UI: live account status, quota, one-click keepalive, media library, API testing, online upgrade.
---

## Quick start

> **New here?** Read the full [Installation Guide](INSTALLATION.md), which covers every platform step by step with screenshots.

### Docker (Linux / VPS)

```bash
git clone https://github.com/its-benjamin/muse2api.git
cd muse2api
cp .env.example .env          # optional: set MUSE2API_KEY
docker compose up -d
# Admin panel: http://<YOUR_IP>:18610
```

### Linux bare-metal

```bash
sudo apt-get install -y chromium python3 python3-pip python3-venv
git clone https://github.com/its-benjamin/muse2api.git
cd muse2api
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python run.py
```

### Windows (local, no server needed)

```
1. Install Python 3.10+ (tick "Add python.exe to PATH")
2. Install Chrome or Edge (already installed on most Windows machines)
3. Download this repo -> double-click start-windows.bat
4. Open http://127.0.0.1:18610 in your browser
5. Import your muse.ai account using the Chrome extension or Tampermonkey script
6. Start using the API
```

---

## Import your muse.ai account

You need to give muse2api your muse.ai session cookies. Two ways:

### Option A: Chrome / Edge extension (easiest)

1. Open `chrome://extensions` -> enable Developer mode
2. Click Load unpacked -> select the `extension/` folder in this repo
3. Log in to [muse.ai](https://muse.ai/)
4. Click the extension icon -> enter your service URL + `MUSE2API_KEY` -> Read and import

### Option B: Tampermonkey userscript (Firefox / Safari / no dev mode)

1. Install [Tampermonkey](https://www.tampermonkey.net/)
2. Create a new script, paste `tools/muse2api_cookie_importer.user.js`, save
3. Open [muse.ai](https://muse.ai/) -> click the "Import to muse2api" button

> See [INSTALLATION.md § Importing your account](INSTALLATION.md#importing-your-muse-ai-account) for screenshots and troubleshooting.

---

## API usage

All endpoints require:
```http
Authorization: Bearer <YOUR_MUSE2API_KEY>
```

### Chat

```bash
curl -X POST http://localhost:18610/v1/chat/completions \
  -H "Authorization: Bearer m2a_your_key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "muse-spark",
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": false
  }'
```

### Anthropic Messages API (Claude Code & Claude Agent SDK)

Use with Claude Code in the terminal:
```bash
export ANTHROPIC_BASE_URL="http://localhost:18610"
export ANTHROPIC_API_KEY="m2a_your_key"
claude
```

Use with the Anthropic Python SDK:
```python
import anthropic

client = anthropic.Anthropic(
    base_url="http://localhost:18610",
    api_key="m2a_your_key",
)

response = client.messages.create(
    model="claude-3-5-sonnet",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.content[0].text)
```

Use with curl:
```bash
curl -X POST http://localhost:18610/v1/messages \
  -H "x-api-key: m2a_your_key" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3-5-sonnet",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```
### Image generation

```bash
curl -X POST http://localhost:18610/v1/images/generations \
  -H "Authorization: Bearer m2a_your_key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "muse-image",
    "prompt": "A futuristic city skyline at sunset, 8K",
    "size": "16:9",
    "response_format": "url"
  }'
```

### Video generation (async)

```bash
# Step 1 — create task
curl -X POST http://localhost:18610/v1/videos \
  -H "Authorization: Bearer m2a_your_key" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Ocean waves crashing on rocks", "duration": 5, "size": "16:9"}'
# -> {"id": "task_xyz", "status": "queued"}

# Step 2 — poll until done
curl http://localhost:18610/v1/videos/task_xyz \
  -H "Authorization: Bearer m2a_your_key"
# -> {"status": "succeeded", "result": {"url": "http://localhost:18610/v1/media/vid_xyz.mp4"}}
```

Supported model aliases: `gpt-4o`, `gpt-5`, `claude-sonnet-4`, `deepseek-chat`, `muse-spark`, `muse-image`, and more. They all route to the same Muse backend.

---

## Environment variables

Copy `.env.example` to `.env` and edit as needed.

| Variable | Default | Description |
|---|---|---|
| `MUSE2API_KEY` | auto-generated | Admin + API auth key (printed on first start) |
| `MUSE2API_HOST` | `0.0.0.0` | Listen IP (`127.0.0.1` = local only) |
| `MUSE2API_PORT` | `18610` | HTTP port |
| `MUSE2API_PUBLIC_BASE` | _(empty)_ | Public URL prefix (leave empty for auto-detect) |
| `MUSE2API_CHROMIUM` | _(auto)_ | Path to Chrome/Chromium executable |
| `MUSE2API_CDP_PORT` | `19210` | Internal Chrome DevTools port |
| `MUSE2API_CHAT_TIMEOUT` | `300` | Chat timeout in seconds |
| `MUSE2API_IMAGE_TIMEOUT` | `240` | Image generation timeout in seconds |
| `MUSE2API_VIDEO_TIMEOUT` | `600` | Video generation timeout in seconds |
| `MUSE2API_BROWSER_IDLE_MIN` | `0` | Stop browser after N idle minutes to save ~700 MB RAM; `0` = always warm. Recommended: `10`-`15` on low-RAM machines |
| `MUSE2API_KEEPALIVE_DISABLED_ACCOUNTS` | `0` | `1` = run keepalive on manually disabled accounts too |
| `MUSE2API_HTTP2` | `0` | `1` = experimental HTTP/2 via zttp |

---

## Nginx reverse proxy

If you put muse2api behind Nginx, use these settings to prevent 502 errors on long jobs:

```nginx
location / {
    proxy_pass         http://127.0.0.1:18610;
    proxy_read_timeout 600s;
    proxy_send_timeout 600s;
    proxy_buffering    off;
    client_max_body_size 64M;
    proxy_set_header   Host              $host;
    proxy_set_header   X-Real-IP         $remote_addr;
    proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
}
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `/api/session` returns 401 | Cookies expired. Re-import via extension or Tampermonkey |
| `/api/session` returns 403 | Regional block or account permissions issue. Check your VPS egress IP |
| Browser won't start on Windows | Do **not** run as Administrator; Chrome exits immediately when elevated |
| Admin panel unreachable | Check firewall; use `127.0.0.1` in `MUSE2API_HOST` for local-only access |
| High RAM usage (~700 MB) | Set `MUSE2API_BROWSER_IDLE_MIN=10` to free RAM when idle |
| Video/image times out | Raise `MUSE2API_VIDEO_TIMEOUT` / `MUSE2API_IMAGE_TIMEOUT`; check your proxy `proxy_read_timeout` |

See [INSTALLATION.md](INSTALLATION.md) for more detailed troubleshooting.

---

## Project structure

```
muse2api/
├── app.py                  # FastAPI application + all API endpoints
├── engine.py               # Headless browser automation (CDP)
├── cdp.py                  # Minimal Chrome DevTools Protocol client
├── config.py               # Configuration (env vars)
├── run.py                  # Entrypoint (HTTP/1.1 + optional HTTP/2)
├── admin.html              # Web admin UI (EN/ZH bilingual)
├── extension/              # Chrome/Edge cookie import extension
├── tools/
│   ├── muse2api_cookie_importer.user.js   # Tampermonkey userscript
│   └── stealth.min.js                     # Puppeteer-extra stealth bundle
├── deploy/
│   ├── muse2api.service    # systemd service file
│   └── nginx.example.conf  # Nginx reverse proxy config
├── tests/                  # Regression tests (no real account needed)
├── .env.example            # All environment variables with comments
├── docker-compose.yml      # Docker Compose config
├── Dockerfile              # Docker image definition
├── INSTALLATION.md         # Full setup tutorial <- start here
└── CONTRIBUTING.md         # How to contribute
```
```

---

## Security & privacy

- All data (accounts, tasks, media) is stored locally in `data/`. Nothing is sent to third parties.
- This project is for technical research and automation. Use it in compliance with muse.ai's Terms of Service.
- Never commit or share your `.env`, `data/accounts.json`, or admin panel URLs containing your key.

---

## Language toggle

Both the admin panel and the Chrome extension support EN / Chinese toggle (top bar). The preference is saved to `localStorage` and auto-detected from your browser language on first visit.

---

## HTTP/2 (experimental)

Set `MUSE2API_HTTP2=1` to serve HTTP/1.1 + HTTP/2 (h2c) on the same port. Browsers only use H2 over TLS, so you need a TLS reverse proxy in front for browser-facing H2. API clients that support h2c prior-knowledge benefit from header compression and multiplexing.

---

## Contributors

Thanks to everyone who contributed (in PR merge order):

- [@czg86389-hub](https://github.com/czg86389-hub): original author, all core reverse-engineering and architecture
- [@cpt-kenvie](https://github.com/cpt-kenvie) ([PR #2](https://github.com/czg86389-hub/muse2api/pull/2)): Docker Compose `MUSE2API_KEY` fix
- [@CarloCPP](https://github.com/CarloCPP) ([PR #6](https://github.com/czg86389-hub/muse2api/pull/6)): Tampermonkey userscript + keepalive for disabled accounts
- [@djs-91](https://github.com/djs-91) ([PR #9](https://github.com/czg86389-hub/muse2api/pull/9)): fix `base_url` collapsing to bare `/v1` when `MUSE2API_PUBLIC_BASE` is unset
- [@toby-bridges](https://github.com/toby-bridges) ([PR #8](https://github.com/czg86389-hub/muse2api/pull/8)): adapt to muse.ai Chinese UI — fix attachment upload confirmation, Stop detection, video vs cover-image selection
PRs and issues are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Community

This project is affiliated with the [LINUX DO community](https://linux.do/), a sincere, friendly, and professional open-source community.

---

## License

Released under the [MIT License](LICENSE).

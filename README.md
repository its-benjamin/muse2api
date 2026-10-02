# MUSE2API

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?logo=python" alt="Python Version" />
  <img src="https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker" alt="Docker" />
  <img src="https://img.shields.io/badge/API-OpenAI%20Compatible-green" alt="OpenAI API Compatible" />
  <img src="https://img.shields.io/badge/License-MIT-orange" alt="License" />
  <a href="https://linux.do/" target="_blank"><img src="https://img.shields.io/badge/Community-LINUX%20DO-111827?logo=linux&logoColor=white" alt="LINUX DO" /></a>
</p>

<p align="center">
  This open-source project is linked with and endorses <b><a href="https://linux.do/" target="_blank">the LINUX DO community (https://linux.do/)</a></b> — a sincere, friendly, united, professional community
</p>

> 🌟 **Fork Information**: This repository is maintained at **[its-benjamin/muse2api](https://github.com/its-benjamin/muse2api)**. It is an enhanced fork of the original project by **[czg86389-hub/muse2api](https://github.com/czg86389-hub/muse2api)**, bringing native Windows local support, bilingual English/Chinese Web UI, hardened anti-bot stealth, CPU & speed optimizations, universal cookie import formats, and experimental HTTP/2 support. All core architecture and reverse-engineering credits belong to the original upstream author and the **LINUX DO** community.

Wraps the cutting-edge multimodal capabilities of the **[muse.ai](https://muse.ai/)** web app as a standard **OpenAI-compatible RESTful API** via reverse engineering. Headless-browser CDP passthrough, warm-standby WebSocket tunnel reuse, and dynamic session management natively support text chat (2–3s streaming first-token latency), text-to-image, image-edit, text-to-video, and first-frame video, plus multi-account-pool affinity rotation, fully automatic 48-hour session renewal with cloud VM wake/keepalive, and a companion Chrome one-click account-import extension.
---

## Core Features

- **Standard chat API (Chat Completions & Responses API)**
  - Fully compatible with the `/v1/chat/completions` and `/v1/responses` (default in new Codex) protocols.
  - Native SSE streaming typewriter output (`stream=True`) plus sync full responses, with warm-tab and Noise WebSocket tunnel affinity reuse — **first-token latency of just 2–3s in follow-up turns**.
  - Multi-turn context and System Prompt support.
  - Built-in smart model alias mapping: common names like `gpt-4o`, `gpt-5`, `claude-sonnet-4`, `deepseek-chat` route automatically.
- **High-quality image generation & editing (Images Generations & Edits)**
  - Fully compatible `/v1/images/generations` (text-to-image) and `/v1/images/edits` (image-to-image / reference editing) endpoints.
  - Multiple aspect ratios (`1:1`, `16:9`, `9:16`, `4:3`, `3:4`), direct reference-image upload, and clean watermark-free output.
  - Both `url` and `b64_json` return formats, with second-level fast detection of plain-text refusals so queues never deadlock.
  - Image edits return only newly generated media: upload previews and history attachments are excluded, downloads bind to the selected result; unconfirmed reference uploads or prompt sends raise explicit errors instead of silently returning the source image.
- **Text-to-video / image-to-video (Videos)**
  - Native integration with Muse's top video model; duration requests of 5s / 6s / 8s / 10s (final length follows the upstream output) and `9:16` portrait / `16:9` landscape generation.
  - Strict first-frame video creation from an uploaded first-frame reference (Data URL / HTTP URL).
  - Async task architecture (`/v1/videos` to create + `/v1/videos/{task_id}` polling).
  - Built-in media service `/v1/media/{filename}` that persists generated MP4 / WebP assets automatically.
- **Multi-account pool with warm-connection affinity scheduling**
  - Import an unlimited matrix of Muse accounts.
  - Smart dispatch on warm-tab affinity + LRU, balancing 2s-class fast responses with even consumption across accounts.
  - On quota exhaustion or session errors, the account is flagged and traffic fails over to a healthy standby with zero perceived delay.
- **Fully automatic 48h session renewal + cloud VM keepalive**
  - Original background heartbeat coroutine hits `/api/session` directly to renew `hatch_vml` (+48h) and `hatch_sess` (+30d), and calls `/api/hatch/vm/wake` to keep the cloud workspace VM warm.
  - Fully solves the static 48h Meta cookie expiry and VM sleep-disconnect problems — no frequent re-logins.
- **Companion Chrome one-click import extension**
  - No manual F12 cookie hunting: one click on the extension icon extracts the current browser login state (including `HttpOnly` core cookies with real expiry times) and pushes it safely to the pool.
- **Modern dark ops console (Web Console) with live online upgrades**
  - Built-in ready-to-use Web UI: live service health, pool quotas and status, one-click whole-pool keepalive, task progress replay, media library management, and online API debugging.
  - **Live update broadcast + one-click upgrade across all nodes**: when the official GitHub repo publishes a new version or fix, every deployed node's admin panel shows an update banner at the top; clicking **"One-click online upgrade & restart"** pulls the latest code and restarts gracefully (local `.env` config and account data are preserved).

---

## Quick Deploy

### Option 0: Run locally on Windows (no server, double-click to use)

1. Install [Python 3.10+](https://www.python.org/downloads/) (check **Add python.exe to PATH** during setup); having Chrome / Edge installed locally is enough (auto-detected, no manual setup).
2. Download and unzip this repo (or `git clone https://github.com/its-benjamin/muse2api.git`), then double-click **`start-windows.bat`** (Command Prompt) or right-click **`start-windows.ps1`** → *Run with PowerShell`.
   (In a PowerShell terminal, run `.\start-windows.ps1` — or `.\start-windows.bat` — with the `.\` prefix; bare names don't resolve in PowerShell.)
3. On first launch an auto-generated key (`m2a_...`) is printed in the console window; open the admin panel:
   `http://127.0.0.1:18610/?key=<YOUR_MUSE2API_KEY>`
4. Use the Chrome extension in the admin panel to import your muse.ai login state in one click, then start calling the API. Closing the console window stops the service.

> Manual start: `python -m pip install -r requirements.txt`, then
> `python -m uvicorn app:app --host 127.0.0.1 --port 18610`.

---

### Option 1: Docker Compose (recommended, one command out of the box)

1. **Clone the repo and enter the directory**:
   ```bash
   git clone https://github.com/its-benjamin/muse2api.git
   cd muse2api
   ```

2. **Configure environment variables (optional)**:
   ```bash
   cp .env.example .env
   # Edit .env as needed; setting MUSE2API_KEY to your own admin key is recommended
   ```

3. **Start the containers**:
   ```bash
   docker compose up -d
   ```

4. **Open the admin panel**:
   Open in a browser: `http://<YOUR_SERVER_IP>:18610/admin?key=<YOUR_MUSE2API_KEY>`

---

### Option 2: Bare-metal / VPS deploy (Ubuntu / Debian)

1. **Install system dependencies and Chromium**:
   ```bash
   sudo apt-get update
   sudo apt-get install -y chromium fonts-wqy-zenhei python3 python3-pip python3-venv
   ```

2. **Set up a Python virtualenv**:
   ```bash
   cd /opt/muse2api
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure the systemd service**:
   ```bash
   sudo cp deploy/muse2api.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now muse2api
   ```

4. **Nginx reverse-proxy config (important: prevents 502 timeouts and streaming stalls)**:
   If proxying with Nginx / aaPanel / 1Panel, be sure to raise `proxy_read_timeout` to `600s` and turn off `proxy_buffering` (see `deploy/nginx.example.conf`):
   ```nginx
   location / {
       proxy_pass http://127.0.0.1:18610;
       proxy_read_timeout 600s;      # avoid Nginx 502 Bad Gateway on slow image/video jobs
       proxy_send_timeout 600s;
       proxy_buffering off;          # keep SSE chat streaming at 0 delay
       client_max_body_size 64M;     # allow large reference-image uploads
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
   }
   ```

---

## Account Import (Chrome Extension / Tampermonkey)

### Option A: Chrome / Edge Extension

The project ships a dedicated Chrome import extension (in `extension/`), so no more fiddly F12 cookie extraction:

1. Open Chrome / Edge, visit `chrome://extensions`, and turn on **Developer mode** (top-right).
2. Click **Load unpacked** and select the `extension` directory of this project.
3. Log in to [muse.ai](https://muse.ai/) in that browser until the main chat UI appears.
4. Click the extension icon in the toolbar and fill in your service URL (e.g. `http://1.2.3.4:18610`) and `MUSE2API_KEY`.
5. Click **Read and import** — synced into the pool within seconds!

### Option B: Tampermonkey Userscript (cross-browser, no developer mode needed)

For users who prefer not to enable developer mode, or who use Firefox / Safari:

1. Install the [Tampermonkey](https://www.tampermonkey.net/) extension in your browser.
2. Create a new userscript and paste the contents of `tools/muse2api_cookie_importer.user.js`, then save.
3. Open [muse.ai](https://muse.ai/) — a **⚡ Import to muse2api** floating button appears at the bottom-right. Right-click to configure your service URL and API key; left-click to push cookies into the pool (also copies to clipboard as a fallback).

---

## API Examples

All protected endpoints require this header:
```http
Authorization: Bearer <YOUR_MUSE2API_KEY>
```

### 1. Chat Completions

```bash
curl -X POST "http://localhost:18610/v1/chat/completions" \
  -H "Authorization: Bearer m2a_your_secret_key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "muse-spark",
    "messages": [
      {"role": "user", "content": "Write a seven-character quatrain about cyberpunk and neon night rain"}
    ],
    "stream": false
  }'
```

### 2. Text-to-Image (Image Generation)

```bash
curl -X POST "http://localhost:18610/v1/images/generations" \
  -H "Authorization: Bearer m2a_your_secret_key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "muse-image",
    "prompt": "A robotic Shiba Inu in an anti-gravity spacesuit, cinematic lighting, 8k resolution",
    "size": "16:9",
    "response_format": "url"
  }'
```

**Response example**:
```json
{
  "created": 1790148495,
  "data": [
    {
      "revised_prompt": "A robotic Shiba Inu in an anti-gravity spacesuit, cinematic lighting, 8k resolution",
      "url": "http://localhost:18610/v1/media/img_abc123.webp",
      "kind": "image",
      "bytes": 54210
    }
  ]
}
```

### 3. Text-to-Video / Image-to-Video (Videos)

- **Step 1: create the generation task**
  ```bash
  curl -X POST "http://localhost:18610/v1/videos" \
    -H "Authorization: Bearer m2a_your_secret_key" \
    -H "Content-Type: application/json" \
    -d '{
      "prompt": "Golden maple leaves drifting lightly in a breeze, sunlight through the treetops",
      "duration": 5,
      "size": "16:9"
    }'
  ```
  Returns the task ID: `{"id": "task_xyz789", "status": "queued"}`

- **Step 2: poll the task status**
  ```bash
  curl "http://localhost:18610/v1/videos/task_xyz789" \
    -H "Authorization: Bearer m2a_your_secret_key"
  ```
  On completion it returns:
  ```json
  {
    "id": "task_xyz789",
    "status": "succeeded",
    "progress": 100,
    "result": {
      "url": "http://localhost:18610/v1/media/vid_xyz789.mp4"
    }
  }
  ```

---

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `MUSE2API_KEY` | auto-generated | Admin console & API auth key (starts with `m2a_`) |
| `MUSE2API_HOST` | `0.0.0.0` | Listen IP (use `127.0.0.1` to restrict to local machine only) |
| `MUSE2API_PORT` | `18610` | Service port |
| `MUSE2API_PUBLIC_BASE` | empty | Public base URL prefix; when empty the frontend auto-detects the visit origin |
| `MUSE2API_CHROMIUM` | empty (auto-detect) | Browser executable path; leave empty to auto-find Chrome / Edge |
| `MUSE2API_CDP_PORT` | `19210` | Internal CDP debug port |
| `MUSE2API_IMAGE_TIMEOUT` | `240` | Image generation timeout (s) |
| `MUSE2API_VIDEO_TIMEOUT` | `600` | Video generation timeout (s) |
| `MUSE2API_CHAT_TIMEOUT` | `300` | Chat generation timeout (s) |
| `MUSE2API_BROWSER_IDLE_MIN` | `0` | Stop the headless browser after N idle minutes to free ~200-400MB RAM (0 = stay warm for fastest response). Next request relaunches it (~5-10s cold start). Recommended `10`-`15` on local/low-RAM machines. |
| `MUSE2API_HTTP2` | `0` | Experimental HTTP/2 (`1` = serve HTTP/1.1 + HTTP/2 via zttp, needs `pip install zttp`). Browsers only use H2 over TLS, so browser-facing H2 needs a TLS reverse proxy in front. |
---

## 🌐 Language Switching & UI Translations (i18n)

- **One-click Language Toggle**: Both the Web Console and the Chrome Extension include a top-bar toggle button (`EN` / `中文`). Preference is saved to `localStorage` and defaults automatically to your browser language.
- **Easily Adding Translations for New UI Elements**:
  When the repository updates or you add new UI components to `admin.html`:
  1. **Static HTML Elements**: tag the element with `data-i18n="category.key"` (or `data-i18n-ph="category.key"` for placeholders, `data-i18n-title="category.key"` for tooltips):
     ```html
     <button data-i18n="my.button">Default Label</button>
     ```
  2. **Dynamic JS Strings**: use `t('category.key')` or `t('category.key', { param: 'value' })`:
     ```javascript
     toast(t('my.toastMessage'), 'ok');
     ```
  3. **Dictionary Registration**: add the key to both `en` and `zh` objects in the `const I18N = { en: {...}, zh: {...} }` block at the top of `<script>` in `admin.html`.
  4. **Graceful Fallback**: If a key is missing in Chinese, it automatically falls back to the English string; if missing in both, it displays the key itself without crashing.

---

## HTTP/2

- **Native, experimental, opt-in:** set `MUSE2API_HTTP2=1` (or pass `--http zttp --http2` manually).
  Uvicorn then serves HTTP/1.1 + HTTP/2 (h2c prior-knowledge) on the same port — verified live with a raw H2 preface.
  Caveats: experimental (no WebSocket-over-H2; plain WebSocket still runs over H1, which is fine for this app),
  and **browsers only speak H2 over TLS**, so browser-facing H2 needs a TLS reverse proxy in front.
- **Do you need it?** On localhost: no measurable gain. H2 pays off for high-latency remote clients
  (multiplexing, header compression). SSE streaming works over both versions.

## Security & Privacy

- **Zero data exfiltration**: all data (account credentials, task queue, media files) is persisted locally in `data/`, with no third-party telemetry or relay services.
- **Open-source compliance**: this project is for technical exchange, system automation research, and automated testing only. Do not use it in ways that violate the Meta platform ToS or any laws/regulations.

---

## Community Recognition & Links

This project links to and highly endorses the **[LINUX DO community](https://linux.do/)** — thanks for the discussions, feedback, and support:

- [LINUX DO community (https://linux.do/)](https://linux.do/) — an emerging ideal community (sincere, friendly, united, professional; building a community we are proud of)

---

## 👥 Contributors

Thanks to the following developers for code contributions and improvements (in PR merge order):

- 🌟 **[@cpt-kenvie](https://github.com/cpt-kenvie)** ([PR #2](https://github.com/czg86389-hub/muse2api/pull/2)) — Fixed Docker Compose environment variable resolution so `MUSE2API_KEY` reads from `.env` instead of being overridden by the hardcoded example value.
- 🌟 **[@CarloCPP](https://github.com/CarloCPP)** ([PR #6](https://github.com/czg86389-hub/muse2api/pull/6)) — Added the Tampermonkey cookie importer userscript and optional keepalive for disabled accounts (`MUSE2API_KEEPALIVE_DISABLED_ACCOUNTS`).

PRs and issues are welcome — let's make this better together!

---


## License

Released under the [MIT License](LICENSE).


## Media-selection regression test

Fixes uploaded reference images being mistaken for generated results, and downloads being hijacked by other page media.
The test uses an isolated temp Chromium profile and a local synthetic DOM — no Muse access, no account reads, no generation quota consumed.
After installing the project deps and Chromium, run from the repo root:

```bash
python tests/test_media_selection.py
```

If the browser is not on PATH, set `MUSE2API_CHROMIUM` to the executable path.
Covers upload-preview exclusion, result dedup, history-attachment exclusion, exact-source download, video-source pinning,
no global-download fallback, and abort on reference-image read failure. Final image-edit quality still needs verification against the real API.


## v1.5.2: Long image jobs behind reverse proxies/CDNs

The sync OpenAI image endpoints stay compatible, but CDNs/clients may cut long requests off before generation finishes.
Production clients should use short-submit + polling rather than stretching HTTP timeouts and re-generating:

1. `POST /v1/images/tasks`: same JSON as `/v1/images/generations`; pass image-to-image references via `reference_image`; a stable `Idempotency-Key` header is recommended.
2. Receive HTTP 202 with an `id`, then call `GET /v1/images/tasks/{id}` every 3s.
3. On `status=completed` read `url` or `data[0]`; on `status=failed` show `error`. If a status query fails, only retry the query — never re-POST the generation.
4. Same idempotency key + same input returns the original task; same key + different input returns 409; a full queue returns 429. One process shares one browser and accepts at most 8 unfinished image tasks.

The original `/v1/images/generations` JSON and `/v1/images/edits` JSON/multipart endpoints also accept `async=true` to switch to the same async handling. Default sync behavior is unchanged.
`timeout` is the queue + generation wait budget (1–600s); browser init and fetch have their own timeouts; clients should keep polling until a terminal task state.
Task metadata is persisted; image tasks still unfinished at process restart are marked failed, never silently re-generated.
The admin-page image API test now uses task polling as well.

Regression checks (no real generation quota consumed):

```bash
python tests/test_async_images.py
python tests/test_vm_wait.py engine.py --assert
```

Fixed a race where shared-browser exception handling reset other tasks after unlocking; leftover sidebar text such as
`Connecting...` / `Still sending` is no longer treated as evidence that the current image failed within 16s.


## v1.5.3: Account-status anomalies & self-hosted troubleshooting

Keepalive requests originate from the **deploy server's egress**, not from the browser that exported the cookies. The author's server working proves nothing about another server's network, region, proxy config, or the same account session.

- `/api/session HTTP 401`: upstream rejected auth. First confirm the account can log in at muse.ai, then re-import cookies.
- `HTTP 403`: access denied — possibly account permissions, server egress, or regional/access restrictions; **not the same as expired cookies**. Inspect the full error and deployment network; do not blindly re-import over and over.
- `HTTP 429`, `5xx`, timeouts, non-JSON, or no `assigned` in response: this keepalive is unconfirmed — no more false success reports and no overwriting the last confirmed account state; the note shows the diagnosis. A prior `unchecked`/`error` state is never force-flipped to `available`.
- Browser page-load timeouts are no longer treated as auth failure; only explicit auth failures flag an account as abnormal.
- `Available` is the last confirmed result and does not guarantee current reachability; `remaining validity` is a cookie-time estimate, not proof of a live server session. Successful checks no longer extend anything by a flat 48h — renewal follows the cookies actually returned.

After updating to v1.5.3 and restarting, click `Test` on each account to re-confirm. Anomalies recorded by older versions are not unconditionally washed clean. Hover the note for the full error; when reporting, include the HTTP status, version, and deployment environment — **never publish cookies, API keys, or keyed admin-page links**.

Bare-metal Git deploy: `git pull --ff-only`, then restart the service; Docker Compose: `git pull --ff-only && docker compose up -d --build`. Save local customizations first, and keep `.env` and `data/`.

Regression test that uses no real accounts and consumes no quota:

```bash
python tests/test_session_health.py
```

# Installation Guide

This guide covers every step to get muse2api running — from zero to making your first API call.

---

## Table of contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
   - [Windows (local)](#option-1-windows-local-no-server-needed)
   - [Docker / Linux VPS](#option-2-docker-linux-vps-recommended-for-servers)
   - [Linux bare-metal](#option-3-linux-bare-metal)
3. [Importing your muse.ai account](#importing-your-muse-ai-account)
   - [Chrome / Edge extension](#option-a--chrome--edge-extension)
   - [Tampermonkey userscript](#option-b--tampermonkey-userscript)
   - [Manual cookie paste](#option-c--manual-cookie-paste)
4. [Connecting an API client](#connecting-an-api-client)
   - [OpenAI Python SDK](#openai-python-sdk)
   - [Cursor / Continue / VS Code extensions](#cursor--continue--vs-code-extensions)
   - [SillyTavern / other chat UIs](#sillytavern--other-chat-uis)
   - [curl](#curl)
5. [Configuration reference](#configuration-reference)
6. [Nginx reverse proxy](#nginx-reverse-proxy)
7. [Troubleshooting](#troubleshooting)
8. [Updating](#updating)
9. [Uninstalling](#uninstalling)

---

## Prerequisites

| Requirement | Windows | Linux / Docker |
|---|---|---|
| Python | 3.10+ | 3.10+ (or skip — Docker handles it) |
| Browser | Chrome or Edge (auto-detected) | Chromium (`apt install chromium`) |
| Internet | Required | Required |
| muse.ai account | **Required** — free account at [muse.ai](https://muse.ai/) | Same |

> **Do I need a muse.ai Pro/paid account?**  
> No. A free account works. The API wraps the web interface, so whatever the web UI lets you do, the API exposes.

---

## Installation

### Option 1: Windows (local, no server needed)

**Best for:** personal use on your own PC — no server, no Docker, no command line after setup.

**Step 1 — Install Python 3.10+**

1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Download the latest Python 3.x installer
3. Run it and **check "Add python.exe to PATH"** on the first screen
4. Click Install Now

**Step 2 — Install Chrome or Edge**

Chrome and Edge are auto-detected. If you already have either installed, skip this step.

**Step 3 — Download muse2api**

Option A — with Git:
```cmd
git clone https://github.com/its-benjamin/muse2api.git
```

Option B — without Git:
- Click the green **Code** button on GitHub → **Download ZIP**
- Extract the ZIP anywhere (e.g. `C:\muse2api`)

**Step 4 — Launch**

Double-click **`start-windows.bat`** in the extracted folder.

> If Windows Defender SmartScreen warns you, click **More info → Run anyway**. This only appears the first time.

The first launch installs Python packages automatically (takes ~1 minute). You'll see:

```
muse2api started — http://127.0.0.1:18610
Admin key: m2a_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Step 5 — Open the admin panel**

Open your browser and go to:
```
http://127.0.0.1:18610
```

The key is shown in the console window. Copy it and paste it into the admin panel login field.

**⚠️ Important: Do NOT run as Administrator**  
muse2api launches Chrome in the background. Chrome exits immediately when launched from an elevated (Administrator) process. If you see Chrome errors, make sure you're running `start-windows.bat` as a normal user.

---

### Option 2: Docker / Linux VPS (recommended for servers)

**Best for:** always-on VPS deployment, no manual Python setup.

**Step 1 — Install Docker**

```bash
curl -fsSL https://get.docker.com | sh
```

Or follow the official guide at [docs.docker.com/get-docker](https://docs.docker.com/get-docker/).

**Step 2 — Clone and configure**

```bash
git clone https://github.com/its-benjamin/muse2api.git
cd muse2api
cp .env.example .env
```

Edit `.env` to set your own admin key (optional but recommended):
```bash
nano .env
# Set: MUSE2API_KEY=m2a_your_secure_key_here
```

**Step 3 — Start**

```bash
docker compose up -d
```

**Step 4 — Open the admin panel**

```
http://<YOUR_SERVER_IP>:18610
```

Check the logs if you need the auto-generated key:
```bash
docker compose logs muse2api | grep "Admin key"
```

**Step 5 — (Optional) Nginx reverse proxy**

See [Nginx reverse proxy](#nginx-reverse-proxy) below — required if you want HTTPS or a custom domain.

---

### Option 3: Linux bare-metal

**Best for:** VPS without Docker, or custom deployments.

**Step 1 — Install system dependencies**

```bash
sudo apt-get update
sudo apt-get install -y chromium python3 python3-pip python3-venv git
```

**Step 2 — Clone the repo**

```bash
git clone https://github.com/its-benjamin/muse2api.git
cd muse2api
```

**Step 3 — Set up Python environment**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Step 4 — Configure**

```bash
cp .env.example .env
nano .env   # set MUSE2API_KEY and other options
```

**Step 5 — Run as a systemd service (auto-start on reboot)**

```bash
sudo cp deploy/muse2api.service /etc/systemd/system/
# Edit the service file to match your paths:
sudo nano /etc/systemd/system/muse2api.service
sudo systemctl daemon-reload
sudo systemctl enable --now muse2api
```

Check status:
```bash
sudo systemctl status muse2api
journalctl -u muse2api -f
```

Or run manually (for testing):
```bash
source venv/bin/activate
python run.py
```

---

## Importing your muse.ai account

muse2api needs your muse.ai session cookies to act on your behalf. You get these from your browser after logging in. There are three ways:

### Option A — Chrome / Edge extension

This is the easiest method. The extension reads your cookies automatically — no F12, no manual copy-paste.

**Step 1 — Load the extension**

1. Open Chrome or Edge
2. Go to `chrome://extensions`
3. Toggle **Developer mode** on (top-right corner)
4. Click **Load unpacked**
5. Select the `extension` folder inside the muse2api directory

**Step 2 — Log in to muse.ai**

Open [muse.ai](https://muse.ai/) and log in until you see the main chat interface.

**Step 3 — Import**

1. Click the muse2api extension icon in your browser toolbar
2. Fill in:
   - **Service URL**: `http://127.0.0.1:18610` (or your server IP)
   - **API Key**: your `MUSE2API_KEY` from the console
3. Click **Read and import**

You should see a success message. The account now appears in the admin panel.

---

### Option B — Tampermonkey userscript

Use this if you prefer Firefox, Safari, or don't want to enable Developer mode.

**Step 1 — Install Tampermonkey**

- [Chrome/Edge](https://www.tampermonkey.net/)
- [Firefox](https://addons.mozilla.org/en-US/firefox/addon/tampermonkey/)

**Step 2 — Create the userscript**

1. Click the Tampermonkey icon → **Create a new script**
2. Delete the default template
3. Paste the entire contents of `tools/muse2api_cookie_importer.user.js`
4. Press `Ctrl+S` to save

**Step 3 — Import**

1. Open [muse.ai](https://muse.ai/) and log in
2. A floating **⚡ Import to muse2api** button appears at the bottom-right
3. Right-click it to configure your service URL and API key
4. Left-click to import

---

### Option C — Manual cookie paste

If neither extension works, you can paste cookies manually from your browser's DevTools.

**Step 1 — Open DevTools on muse.ai**

1. Open [muse.ai](https://muse.ai/) and log in
2. Press `F12` to open DevTools
3. Go to **Application** tab → **Cookies** → `https://muse.ai`

**Step 2 — Copy the key cookies**

You need at least: `hatch_sess`, `hatch_gw`, `hatch_vml`, `hatch_native_auth_device`

Copy the whole cookie string from the Network tab:
1. Press `F5` to reload
2. In the **Network** tab, click any request to `muse.ai`
3. Find the `Cookie:` request header
4. Copy the entire value

**Step 3 — Import via admin panel**

1. Open the admin panel → **Accounts** → **Add account**
2. Paste the cookie string into the input field
3. Click **Import**

---

## Connecting an API client

Once you have an account imported, you can use any OpenAI-compatible client.

### OpenAI Python SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:18610/v1",
    api_key="m2a_your_key_here",
)

response = client.chat.completions.create(
    model="muse-spark",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
```

For streaming:
```python
with client.chat.completions.stream(
    model="muse-spark",
    messages=[{"role": "user", "content": "Tell me a story"}],
) as stream:
    for chunk in stream:
        print(chunk.choices[0].delta.content or "", end="", flush=True)
```

### Cursor / Continue / VS Code extensions

In the settings for your AI extension:

| Setting | Value |
|---|---|
| API Base URL / Endpoint | `http://127.0.0.1:18610/v1` |
| API Key | your `MUSE2API_KEY` |
| Model | `muse-spark` (or `gpt-4o`, `gpt-4`, etc. — all route to Muse) |

**Cursor:**
- Settings → Models → Add model → Custom
- Base URL: `http://127.0.0.1:18610/v1`
- API Key: your key

**Continue (VS Code):**

Edit `~/.continue/config.json`:
```json
{
  "models": [
    {
      "title": "Muse via muse2api",
      "provider": "openai",
      "model": "muse-spark",
      "apiBase": "http://127.0.0.1:18610/v1",
      "apiKey": "m2a_your_key_here"
    }
  ]
}
```

### SillyTavern / other chat UIs

In SillyTavern:
1. **API**: OpenAI
2. **API URL**: `http://127.0.0.1:18610/v1`
3. **API Key**: your `MUSE2API_KEY`
4. **Model**: `muse-spark`

### curl

```bash
curl http://127.0.0.1:18610/v1/chat/completions \
  -H "Authorization: Bearer m2a_your_key" \
  -H "Content-Type: application/json" \
  -d '{"model":"muse-spark","messages":[{"role":"user","content":"Hi"}]}'
```

---

## Configuration reference

All settings go in `.env` (copy from `.env.example`):

```env
# Required for production — leave blank to auto-generate on first start
MUSE2API_KEY=m2a_your_secure_key_here

# Network
MUSE2API_HOST=0.0.0.0          # 127.0.0.1 = local only
MUSE2API_PORT=18610

# Browser
MUSE2API_CHROMIUM=              # leave blank to auto-detect Chrome/Edge
MUSE2API_CDP_PORT=19210         # internal Chrome DevTools port
MUSE2API_BROWSER_IDLE_MIN=0    # 0 = always warm; 10-15 = free ~700MB when idle

# Timeouts (seconds)
MUSE2API_CHAT_TIMEOUT=300
MUSE2API_IMAGE_TIMEOUT=240
MUSE2API_VIDEO_TIMEOUT=600

# Advanced
MUSE2API_PUBLIC_BASE=           # public URL if behind a reverse proxy
MUSE2API_HTTP2=0                # 1 = experimental HTTP/2
MUSE2API_KEEPALIVE_DISABLED_ACCOUNTS=0  # 1 = also keepalive disabled accounts
```

---

## Nginx reverse proxy

If you're serving muse2api on a VPS behind Nginx (with HTTPS):

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate     /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass          http://127.0.0.1:18610;
        proxy_read_timeout  600s;
        proxy_send_timeout  600s;
        proxy_buffering     off;               # required for SSE streaming
        client_max_body_size 64M;              # for image uploads
        proxy_set_header    Host              $host;
        proxy_set_header    X-Real-IP         $remote_addr;
        proxy_set_header    X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header    X-Forwarded-Proto $scheme;
    }
}
```

Key points:
- `proxy_read_timeout 600s` — prevents 502 on long video/image generation jobs
- `proxy_buffering off` — required for SSE streaming to work correctly
- `client_max_body_size 64M` — allows large reference image uploads

---

## Troubleshooting

### "No accounts available" error from the API

You haven't imported a muse.ai account yet, or all accounts are flagged as unavailable.
→ Open the admin panel → Accounts → Import an account, or click **Test** on existing accounts.

### 401 from `/api/session`

Your cookies expired. muse.ai session cookies last ~48 hours.
→ Log into muse.ai again and re-import via the Chrome extension or Tampermonkey.

### 403 from `/api/session`

Access denied — usually a regional restriction on your VPS's IP, or an account permissions issue.
→ Try a different VPS region or a residential proxy. Re-importing the same cookies won't help.

### Chrome won't launch on Windows

- Make sure you're **not running as Administrator**
- Check that Chrome or Edge is installed
- Try setting `MUSE2API_CHROMIUM` to the full path, e.g. `C:\Program Files\Google\Chrome\Application\chrome.exe`

### High RAM usage (~700 MB)

Chrome uses ~700 MB RSS. To free it when idle:
```env
MUSE2API_BROWSER_IDLE_MIN=10
```
The browser stops after 10 minutes of inactivity. The next request restarts it (~5–10 s cold start).

### Admin panel shows "update available" banner

Click **One-click online upgrade & restart** to pull the latest code and restart. Your `.env` and `data/` are preserved.

Or manually:
```bash
# Git
git pull --ff-only && systemctl restart muse2api

# Docker
git pull --ff-only && docker compose up -d --build
```

### "Still sending" / VM connection timeout

The muse.ai cloud VM that runs your account's browser session was suspended.
→ The service wakes it automatically. If this keeps happening, check that keepalive is running (admin panel → health).

---

## Updating

**Windows (start-windows.bat):**
Pull the latest code (or download the new ZIP) and restart `start-windows.bat`. Your `.env` and `data/` are not touched.

**Docker:**
```bash
git pull --ff-only
docker compose up -d --build
```

**Linux bare-metal:**
```bash
git pull --ff-only
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart muse2api
```

---

## Uninstalling

**Windows:** delete the muse2api folder. Chrome profile is in `muse2api-profiles/` next to the folder — delete that too.

**Docker:**
```bash
docker compose down -v
```

**Linux bare-metal:**
```bash
sudo systemctl disable --now muse2api
sudo rm /etc/systemd/system/muse2api.service
rm -rf /opt/muse2api
```

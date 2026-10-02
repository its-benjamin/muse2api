"""muse2api configuration."""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field

_DEFAULT_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_dotenv():
    """Auto-load the .env file in the project root (never overrides existing env vars)."""
    base = os.environ.get("MUSE2API_HOME") or _DEFAULT_BASE_DIR
    env_path = os.path.join(base, ".env")
    if not os.path.isfile(env_path):
        return
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                k, v = s.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v
    except OSError:
        pass


_load_dotenv()


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _detect_chromium() -> str:
    """Prefer MUSE2API_CHROMIUM; fall back to auto-detecting an installed Chromium/Chrome."""
    configured = os.environ.get("MUSE2API_CHROMIUM", "").strip()
    if configured and (os.path.isfile(configured) or shutil.which(configured)):
        return configured
    local_app = os.environ.get("LOCALAPPDATA", "")
    prog = os.environ.get("ProgramFiles", r"C:\Program Files")
    prog_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    candidates = [
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/snap/bin/chromium",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "chromium",
        "chromium-browser",
        "google-chrome",
        "chrome",
        os.path.join(prog, r"Google\Chrome\Application\chrome.exe"),
        os.path.join(local_app, r"Google\Chrome\Application\chrome.exe"),
        os.path.join(prog, r"Microsoft\Edge\Application\msedge.exe"),
        os.path.join(prog_x86, r"Microsoft\Edge\Application\msedge.exe"),
        os.path.join(prog, r"BraveSoftware\Brave-Browser\Application\brave.exe"),
        "chrome.exe",
        "msedge.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for c in candidates:
        if os.path.isfile(c) or shutil.which(c):
            return c
    return configured or "chromium"


@dataclass
class Config:
    base_dir: str = field(default_factory=lambda: _env("MUSE2API_HOME", _DEFAULT_BASE_DIR))
    host: str = field(default_factory=lambda: _env("MUSE2API_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(_env("MUSE2API_PORT", "18610")))

    # Browser
    chromium: str = field(default_factory=_detect_chromium)
    cdp_port: int = field(default_factory=lambda: int(_env("MUSE2API_CDP_PORT", "19210")))
    home_dir: str = field(default_factory=lambda: _env("MUSE2API_HOME_DIR", os.path.expanduser("~")))
    extra_path: str = field(default_factory=lambda: _env("MUSE2API_EXTRA_PATH", "" if os.name == "nt" else "/snap/bin"))
    site_url: str = field(default_factory=lambda: _env("MUSE2API_SITE", "https://muse.ai/"))
    login_wait: int = field(default_factory=lambda: int(_env("MUSE2API_LOGIN_WAIT", "60")))

    # Browser profile root directory.
    # Gotcha: snap-packaged chromium is confined by AppArmor and can only read/write paths under $HOME.
    # Passing --user-data-dir=/opt/... or /tmp/... does not error but is silently ignored,
    # and the browser falls back to ~/snap/chromium/common/chromium.
    # So it must live under $HOME (avoid dot-prefixed hidden dirs, excluded by the snap home interface).
    profile_root: str = field(
        default_factory=lambda: _env("MUSE2API_PROFILE_ROOT",
                                     os.path.join(os.path.expanduser("~"),
                                                  "muse2api-profiles")))

    # Auth
    api_key: str = field(default_factory=lambda: _env("MUSE2API_KEY", ""))

    # Public base URL (shown as the access URL on the admin page; falls back to the current domain when empty)
    public_base: str = field(
        default_factory=lambda: _env("MUSE2API_PUBLIC_BASE", ""))

    # Allowed origins for cross-origin import API calls (used when the cookie helper script submits from a muse.ai page)
    cors_origins: str = field(
        default_factory=lambda: _env("MUSE2API_CORS_ORIGINS",
                                     "https://muse.ai,https://www.muse.ai"))

    # Generation
    image_timeout: int = field(default_factory=lambda: int(_env("MUSE2API_IMAGE_TIMEOUT", "240")))
    video_timeout: int = field(default_factory=lambda: int(_env("MUSE2API_VIDEO_TIMEOUT", "600")))
    chat_timeout: int = field(default_factory=lambda: int(_env("MUSE2API_CHAT_TIMEOUT", "300")))

    # Browser idle shutdown (minutes of no generations before the headless
    # browser is stopped to free ~200-400MB RAM; 0 = never, browser stays warm).
    # Next request transparently relaunches it (adds ~5-10s cold start once).
    # Local/low-RAM machines: set 10-15. Busy nodes: leave 0 for max speed.
    browser_idle_min: int = field(default_factory=lambda: int(_env("MUSE2API_BROWSER_IDLE_MIN", "0")))

    # Experimental HTTP/2 via uvicorn's zttp parser (MUSE2API_HTTP2=1).
    # Serves H1 + H2 (h2c prior-knowledge) on the same port. Browsers only use
    # H2 over TLS (needs a TLS reverse proxy in front); direct H2 here benefits
    # h2c-capable API clients/proxies.
    http2: bool = field(default_factory=lambda: _env("MUSE2API_HTTP2", "0").strip() != "0")

    # Tool-calling (function calling) protocol adapter switch, **off by default**.
    # Measured behavior: the muse.ai assistant explicitly refuses to emit "pseudo tool calls"
    # (it says it will not output JSON in that format), so force-injecting the protocol only pollutes normal answers.
    # So by default we only keep "parameter compatibility" (clients passing tools do not get a 422); nothing is injected or parsed.
    # If the target model behavior changes, set MUSE2API_TOOL_PROTOCOL=1 to re-enable this adapter.
    tool_protocol: bool = field(
        default_factory=lambda: _env("MUSE2API_TOOL_PROTOCOL", "0").strip() != "0")

    # 保活设置：是否对已禁用的账号执行自动保活，**默认关闭**。
    # 开启后，被管理员在后台手动禁用的账号仍会由后台守护进程执行自动保活与 VM 唤醒，
    # 保持会话活性不失效，但依然不会参与正常业务生图、生视频与对话轮转调度。
    keepalive_disabled_accounts: bool = field(
        default_factory=lambda: _env("MUSE2API_KEEPALIVE_DISABLED_ACCOUNTS", "0").strip() != "0")

    @property
    def data_dir(self) -> str:
        return os.path.join(self.base_dir, "data")

    @property
    def media_dir(self) -> str:
        return os.path.join(self.data_dir, "media")

    @property
    def download_dir(self) -> str:
        return os.path.join(self.data_dir, "downloads")

    @property
    def profile_dir(self) -> str:
        """Browser profile used for generation."""
        return os.path.join(self.profile_root, "generate")

    @property
    def accounts_file(self) -> str:
        return os.path.join(self.data_dir, "accounts.json")

    @property
    def tasks_file(self) -> str:
        return os.path.join(self.data_dir, "tasks.json")

    def ensure_dirs(self):
        for d in (self.base_dir, self.data_dir, self.media_dir, self.download_dir,
                  self.profile_dir):
            os.makedirs(d, exist_ok=True)


CFG = Config()

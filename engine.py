"""Muse generation engine: drives muse.ai with a real web session to complete image/video generation.

NOTE: several DOM-matching regexes keep Chinese alternatives (e.g. 发送, 下载) because muse.ai may render a Chinese-locale UI. Do not remove them during translation cleanup.

Verified flow:
  inject cookies -> open https://muse.ai/ -> locate textarea (placeholder message)
  -> Input.insertText fill -> click "Send"
  -> wait for a new attachment container [data-testid^=hatch-chat-attachment-presentation-]
  -> fetch blob bytes from img/video inside that container -> save to disk
"""
from __future__ import annotations

import base64
import mimetypes
import urllib.request
import json
import logging
import os
import re
import shutil
import subprocess
import time
import uuid

from cdp import CDP, http_json

log = logging.getLogger("muse2api")

ATT_SEL = '[data-testid^="hatch-chat-attachment-presentation-"]'

# Core cookies that decide account life/death (missing or expired = session invalid)
ESSENTIAL_COOKIES = ("hatch_sess", "hatch_gw", "hatch_vml",
                     "hatch_native_auth_device")

# Stealth script injected via Page.addScriptToEvaluateOnNewDocument
# before any page script executes, spoofing automation artifacts
# (navigator.webdriver, window.chrome, plugins, console traps, leak vars).
STEALTH_JS = """(() => {
    const nativeMap = new WeakMap();
    const origToString = Function.prototype.toString;

    function setNative(fn, name) {
        try { Object.defineProperty(fn, 'name', { value: name || fn.name || '', configurable: true }); } catch(e) {}
        nativeMap.set(fn, name || fn.name || '');
        return fn;
    }

    try {
        Function.prototype.toString = function() {
            if (nativeMap.has(this)) {
                const name = nativeMap.get(this);
                return `function ${name}() { [native code] }`;
            }
            return origToString.call(this);
        };
        setNative(Function.prototype.toString, 'toString');
    } catch(e) {}

    // 1. Completely delete webdriver from navigator instance & prototype
    try { delete Navigator.prototype.webdriver; } catch(e) {}
    try { delete navigator.webdriver; } catch(e) {}

    // 2. Realistic window.chrome object
    try {
        window.chrome = {
            runtime: {},
            loadTimes: setNative(function() {}, 'loadTimes'),
            csi: setNative(function() {}, 'csi'),
            app: {}
        };
    } catch(e) {}

    // 3. Plugins array
    try {
        const pluginsData = [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
            { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
        ];
        const pArray = Object.create(PluginArray.prototype);
        pluginsData.forEach((p, idx) => {
            const plugin = Object.create(Plugin.prototype);
            Object.defineProperties(plugin, {
                name: { value: p.name, enumerable: true },
                filename: { value: p.filename, enumerable: true },
                description: { value: p.description, enumerable: true },
                length: { value: 0, enumerable: true }
            });
            Object.defineProperty(plugin, Symbol.toStringTag, { value: 'Plugin' });
            pArray[idx] = plugin;
            pArray[p.name] = plugin;
        });
        Object.defineProperties(pArray, {
            length: { value: pluginsData.length, enumerable: true },
            item: { value: setNative(function(i) { return this[i] || null; }, 'item') },
            namedItem: { value: setNative(function(n) { return this[n] || null; }, 'namedItem') },
            refresh: { value: setNative(function() {}, 'refresh') }
        });
        Object.defineProperty(pArray, Symbol.toStringTag, { value: 'PluginArray' });

        Object.defineProperty(navigator, 'plugins', {
            get: setNative(() => pArray, 'get plugins'),
            configurable: true,
            enumerable: true
        });
    } catch(e) {}

    // 4. Languages
    try {
        Object.defineProperty(navigator, 'languages', {
            get: setNative(() => ['en-US', 'en'], 'get languages'),
            configurable: true,
            enumerable: true
        });
    } catch(e) {}

    // 5. Permissions query consistency
    try {
        const origQuery = window.navigator.permissions.query.bind(window.navigator.permissions);
        window.navigator.permissions.query = setNative((params) => {
            if (params && params.name === 'notifications') {
                return Promise.resolve({ state: Notification.permission, onchange: null });
            }
            return origQuery(params);
        }, 'query');
    } catch(e) {}

    // 6. Console traps mitigation (Runtime.enable side-effect masks)
    try {
        for (const method of ['debug', 'log', 'info', 'warn', 'error']) {
            if (console[method]) {
                const orig = console[method].bind(console);
                console[method] = setNative(function(...args) {
                    try { orig(...args); } catch(e) {}
                }, method);
            }
        }
    } catch(e) {}
    // 7. WebGL unmasked vendor/renderer spoofing (prevents Google SwiftShader / software rasterizer detection)
    try {
        const addWebGL = (proto) => {
            if (!proto) return;
            const oldGetParam = proto.getParameter;
            proto.getParameter = setNative(function(param) {
                if (param === 0x9245) return 'Google Inc. (Intel)';
                if (param === 0x9246) return 'ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)';
                return oldGetParam.apply(this, arguments);
            }, 'getParameter');
        };
        addWebGL(WebGLRenderingContext.prototype);
        if (typeof WebGL2RenderingContext !== 'undefined') addWebGL(WebGL2RenderingContext.prototype);
    } catch(e) {}

    // 8. Hardware metrics consistency (prevents 0 or headless default anomalies)
    try {
        if (!navigator.hardwareConcurrency || navigator.hardwareConcurrency < 2) {
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: setNative(() => 8, 'get hardwareConcurrency') });
        }
        if (!navigator.deviceMemory) {
            Object.defineProperty(navigator, 'deviceMemory', { get: setNative(() => 8, 'get deviceMemory') });
        }
    } catch(e) {}

    // 9. Strip automation leak variables
    const leakPrefixes = ['$cdc_', '$chrome_', '__nightmare', '__selenium', '_Selenium_IDE_Recorder'];
    for (const k of Object.keys(window)) {
        if (leakPrefixes.some(p => k.startsWith(p))) {
            try { delete window[k]; } catch(e) {}
        }
    }
})();"""

class MuseAuthError(RuntimeError):
    pass


class MuseGenerationError(RuntimeError):
    pass


def _is_elevated() -> bool:
    """True when running with Administrator rights (Windows) or as root (POSIX).

    Chrome refuses to stay attached to an elevated launcher: it exits and
    re-spawns de-elevated, leaving our process handle dead and the CDP port
    closed -- every launch then times out with no useful error."""
    if os.name == "nt":
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:  # noqa: BLE001
            return False
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


class MuseEngine:
    def __init__(self, cfg):
        self.cfg = cfg
        self.proc: subprocess.Popen | None = None
        self.browser: CDP | None = None
        self.page: CDP | None = None
        self.current_acc_id: str | None = None
        self._last_http_renew: dict[str, float] = {}
        self._log = None
        self.last_used: float = 0.0  # last time the browser served a generation (for idle shutdown)
        self.idle_stopped_at: float = 0.0  # when idle shutdown last fired (so warmup doesn't undo it)
        self._spawned: bool = False  # True when WE launched the browser (vs reusing a foreign CDP session)
        os.makedirs(cfg.profile_dir, exist_ok=True)

    # ---------------- Browser lifecycle ----------------
    def _debug_url(self):
        return f"http://127.0.0.1:{self.cfg.cdp_port}/json/version"

    def start(self):
        # Every generation path calls start() (always under the caller's lock),
        # so this timestamp doubles as the idle-shutdown clock.
        self.last_used = time.time()
        if self.proc and self.proc.poll() is None and self.browser:
            return
        # Running elevated breaks Chrome badly: the elevated launcher exits and
        # re-spawns the real browser de-elevated ("--do-not-de-elevate"), so our
        # process handle points at a dead process and the CDP port never comes
        # up from our side. Warn loudly instead of failing cryptically later.
        if _is_elevated():
            log.warning("Process is running as Administrator: Chrome will refuse to stay attached "
                        "(it re-spawns de-elevated and the debug port never opens). "
                        "Restart this service from a NON-elevated terminal / do NOT use 'Run as administrator'.")
        env = dict(os.environ)
        env.setdefault("HOME", self.cfg.home_dir)
        env["PATH"] = (self.cfg.extra_path + os.pathsep + env.get("PATH", "")) if self.cfg.extra_path else env.get("PATH", "")
        # NOTE: the browser is intentionally kept warm (see _keepalive_loop in app.py)
        # for ~2s first-byte latency, so it always costs ~200-400MB RSS while running.
        # These flags trim the fat: no extensions/components/audio subsystems.
        args = [
            self.cfg.chromium,
            "--headless=new", "--no-sandbox", "--disable-gpu",
            "--disable-dev-shm-usage", "--disable-background-networking",
            "--disable-extensions", "--disable-component-update", "--mute-audio",
            "--no-first-run", "--no-default-browser-check",
            "--autoplay-policy=no-user-gesture-required",
            "--window-size=1440,2400",
            f"--remote-debugging-port={self.cfg.cdp_port}",
            "--remote-allow-origins=*",
            f"--user-data-dir={self.cfg.profile_dir}",
            "about:blank",
        ]
        # Try to reuse an existing healthy CDP
        if not self.proc:
            try:
                v = http_json(self._debug_url(), timeout=1)
                if v and "webSocketDebuggerUrl" in v:
                    self.browser = CDP(v["webSocketDebuggerUrl"], timeout=180)
                    self._spawned = False
                    return
            except Exception:
                pass

        # Clean up leftover locks
        for lock_name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
            lp = os.path.join(self.cfg.profile_dir, lock_name)
            if os.path.exists(lp) or os.path.islink(lp):
                try:
                    os.unlink(lp)
                except Exception:
                    pass

        os.makedirs(self.cfg.data_dir, exist_ok=True)
        if self._log is not None:  # retry after a failed start: don't leak the old handle
            try:
                self._log.close()
            except Exception:  # noqa: BLE001
                pass
        self._log = open(os.path.join(self.cfg.data_dir, "chromium.log"), "ab", buffering=0)
        cwd_dir = self.cfg.home_dir if (self.cfg.home_dir and os.path.isdir(self.cfg.home_dir)) else None
        # Windows: hide the browser's console window; POSIX: keep defaults.
        popen_kwargs: dict = {}
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            if creationflags:
                popen_kwargs["creationflags"] = creationflags
        self.proc = subprocess.Popen(args, stdout=self._log, stderr=subprocess.STDOUT,
                                     env=env, cwd=cwd_dir, **popen_kwargs)
        last = None
        for _ in range(90):
            try:
                v = http_json(self._debug_url(), timeout=2)
                self.browser = CDP(v["webSocketDebuggerUrl"], timeout=180)
                self._spawned = True
                return
            except Exception as exc:  # noqa: BLE001
                last = exc
                time.sleep(1)
        raise MuseGenerationError(f"Chromium failed to start: {last}")

    def _kill_profile_tree(self):
        """Windows: kill our headless browser tree.

        Chrome's launcher exits while the real browser lives on as a child, so
        our Popen handle is useless. Children do NOT carry our profile path in
        their command line, so: find the real main process (our profile path in
        its cmdline, no --type=... child marker) and taskkill /T it, which takes
        the whole tree down. The dedicated user-data-dir means we can never hit
        the user's own Chrome."""
        # Chrome keeps our path separators verbatim, so match both slash styles.
        prof = self.cfg.profile_dir.replace("'", "''")
        prof_bs = prof.replace("/", "\\")
        ps = (
            "$hit = @(Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" "
            "| Where-Object { ($_.CommandLine -like "
            f"'*{prof}*' -or $_.CommandLine -like '*{prof_bs}*') "
            "-and $_.CommandLine -notlike '*--type=*' }); "
            "$hit | ForEach-Object { taskkill /F /T /PID $_.ProcessId }"
        )
        try:
            subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                           capture_output=True, timeout=30)
        except Exception:  # noqa: BLE001
            pass

    def stop(self):
        for c in (self.page, self.browser):
            if c:
                c.close()
        self.page = self.browser = None
        if self.proc and (self._spawned or self.proc.poll() is None):
            if os.name == "nt" and self._spawned:
                # Chrome's launcher exits while the real browser (child) lives on,
                # so our Popen handle points at a dead process. taskkill /T on it
                # would miss the tree. Instead kill every chrome.exe whose command
                # line references our dedicated profile dir -- that uniquely
                # identifies our browser and never touches the user's own Chrome.
                self._kill_profile_tree()
                try:
                    self.proc.wait(timeout=10)
                except Exception:  # noqa: BLE001
                    pass
            elif self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=10)
                except Exception:  # noqa: BLE001
                    self.proc.kill()
        self.proc = None
        self._spawned = False
        # Release the log handle: on Windows an open file cannot be deleted,
        # which breaks temp-profile cleanup in tests and manual profile wipes.
        if self._log is not None:
            try:
                self._log.close()
            except Exception:  # noqa: BLE001
                pass
            self._log = None

    def stop_if_idle(self, idle_min: int) -> bool:
        """Stop the browser if it served nothing for idle_min minutes. Returns True when stopped.

        Callers MUST hold the generation lock (or otherwise guarantee no request
        is in flight): stopping mid-generation would kill the active page.
        A later start() transparently relaunches. last_used == 0 means the
        browser never ran here, so there is nothing to stop."""
        if not idle_min or idle_min <= 0 or not self.last_used:
            return False
        # Only our own child can be killed; a reused foreign CDP session is left alone.
        if not self._spawned or self.proc is None:
            return False
        if time.time() - self.last_used < idle_min * 60:
            return False
        self.stop()
        self.idle_stopped_at = time.time()
        log.info("Browser idle for %dm, stopped to free RAM; next request will relaunch it", idle_min)
        return True

    # ---------------- Pages ----------------
    def _open_page(self):
        import requests
        try:
            pages = requests.get(f"http://127.0.0.1:{self.cfg.cdp_port}/json/list", timeout=3).json()
            for p in pages:
                if p.get("type") == "page":
                    pid = p.get("id")
                    if pid:
                        requests.get(f"http://127.0.0.1:{self.cfg.cdp_port}/json/close/{pid}", timeout=2)
        except Exception:
            pass

        tgt = requests.put(
            f"http://127.0.0.1:{self.cfg.cdp_port}/json/new?about:blank",
            timeout=10).json()
        page = CDP(tgt["webSocketDebuggerUrl"], timeout=180)
        page.send("Network.enable")
        page.send("Page.enable")
        page.send("Runtime.enable")
        page.send("Browser.setDownloadBehavior",
                  {"behavior": "allow", "downloadPath": self.cfg.download_dir})
        try:
            page.send("Emulation.setUserAgentOverride", {
                "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36",
                "platform": "Win32",
                "userAgentMetadata": {
                    "brands": [
                        {"brand": "Google Chrome", "version": "154"},
                        {"brand": "Chromium", "version": "154"},
                        {"brand": "Not=A?Brand", "version": "24"}
                    ],
                    "fullVersionList": [
                        {"brand": "Google Chrome", "version": "154.0.8037.58"},
                        {"brand": "Chromium", "version": "154.0.8037.58"},
                        {"brand": "Not=A?Brand", "version": "24.0.0.0"}
                    ],
                    "fullVersion": "154.0.8037.58",
                    "platform": "Windows",
                    "platformVersion": "10.0.0",
                    "architecture": "x86",
                    "model": "",
                    "mobile": False,
                    "bitness": "64",
                    "wow64": False
                }
            })
            page.send("Page.addScriptToEvaluateOnNewDocument", {"source": STEALTH_JS})
        except Exception:
            pass
        return page

    @staticmethod
    def renew_session_http(cookies: dict, expires: dict | None = None,
                           wake_vm: bool = True) -> dict:
        """Renew hatch_vml (+48h) / hatch_sess (+30d) / hatch_gw (+1y) via muse.ai/api/session,
        and wake the cloud workspace VM via /api/hatch/vm/wake when needed."""
        import requests
        cur_cookies = dict(cookies or {})
        cur_exp = dict(expires or {})
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
            "Origin": "https://muse.ai",
            "Referer": "https://muse.ai/thread/new",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Cookie": "; ".join(f"{k}={v}" for k, v in cur_cookies.items() if v),
        }
        try:
            r = requests.get("https://muse.ai/api/session", headers=headers,
                             timeout=12, allow_redirects=False)
        except requests.RequestException as exc:
            # Do not echo request content: the exception may carry a credentialed proxy URL.
            raise MuseGenerationError(
                f"/api/session network request failed ({type(exc).__name__}); check server network/proxy and retry") from None
        if r.status_code == 401:
            raise MuseAuthError("Session auth failed (/api/session HTTP 401); confirm login on the official site, then re-import cookies")
        if r.status_code != 200:
            hint = ("Access denied; check server egress/region/access restrictions; this alone does not prove cookies are invalid"
                    if r.status_code == 403 else "Upstream request failed; retry later and check server network")
            raise MuseGenerationError(f"/api/session HTTP {r.status_code}: {hint}")
        try:
            sj = r.json()
        except ValueError:
            raise MuseGenerationError("/api/session HTTP 200 returned non-JSON; session state unconfirmed") from None
        if not isinstance(sj, dict) or sj.get("status") != "assigned":
            raise MuseGenerationError("/api/session HTTP 200 did not return an assigned session; check account/workspace state on the official site")
        for c in r.cookies:
            if c.value:
                cur_cookies[c.name] = c.value
            if c.expires:
                cur_exp[c.name] = int(float(c.expires))
        vm_id = sj.get("vm_id")
        vm_state = sj.get("vm_state")
        wake_ok = False
        if wake_vm and vm_id and vm_state != "DISABLED":
            try:
                headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cur_cookies.items() if v)
                rw = requests.post("https://muse.ai/api/hatch/vm/wake", headers=headers, json={
                    "vm_id": vm_id,
                    "retry_count": 0,
                    "connect_attempt_id": str(uuid.uuid4()),
                }, timeout=8)
                wake_ok = rw.status_code == 200
            except Exception:
                pass
        return {
            "ok": sj.get("status") == "assigned",
            "status": sj.get("status"),
            "vm_id": vm_id,
            "vm_state": vm_state,
            "wake_ok": wake_ok,
            "cookies": cur_cookies,
            "cookies_exp": cur_exp,
        }

    def _apply_cookies(self, page: CDP, cookies: dict, expires: dict | None = None):
        """Inject cookies. Fully clears old-account cookies for isolation, and never passes past-dated expires that would make Chromium drop hatch_vml."""
        try:
            page.send("Network.clearBrowserCookies")
        except Exception:
            pass
        now = time.time()
        for name, value in cookies.items():
            if not value:
                continue
            exp = (expires or {}).get(name)
            try:
                exp_val = float(exp) if exp and float(exp) > now + 3600 else (now + 7 * 86400)
            except (TypeError, ValueError):
                exp_val = now + 7 * 86400
            for dom in (".muse.ai", "muse.ai"):
                params = {
                    "name": name,
                    "value": value,
                    "domain": dom,
                    "path": "/",
                    "secure": True,
                    "expires": exp_val,
                }
                try:
                    page.send("Network.setCookie", params)
                except Exception:  # noqa: BLE001
                    pass

    def read_cookies(self) -> dict[str, dict]:
        """Read cookies back from the current page (**including httpOnly**, which page JS cannot do).

        Returns {name: {"value":..., "expires": unix seconds or -1}}.
        Purpose: muse.ai renews some cookies on visits; reading them back into the pool keeps accounts fresh
        so accounts expire less easily.
        """
        if not self.page:
            return {}
        try:
            msg = self.page.send("Network.getCookies",
                                 {"urls": [self.cfg.site_url]}, timeout=20)
        except Exception:  # noqa: BLE001
            return {}
        out: dict[str, dict] = {}
        for c in (msg.get("result", {}).get("cookies") or []):
            name = c.get("name")
            if not name:
                continue
            try:
                exp = int(float(c.get("expires", -1)))
            except (TypeError, ValueError):
                exp = -1
            out[name] = {"value": c.get("value", ""), "expires": exp}
        return out

    def _wait_ws_ready(self, page: CDP, timeout: float = 15.0) -> bool:
        """Wait until the muse.ai page finishes React hydration and is no longer in the Connecting... state."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                st = page.js("""(function(){
                    if (document.readyState !== 'complete') return 'loading';
                    if (!document.querySelector('textarea')) return 'no-ta';
                    var h = document.querySelector('[data-hatch-shell-hydration-state]');
                    if (h && h.getAttribute('data-hatch-shell-hydration-state') !== 'hydrated') return 'hydrating';
                    var b = document.body ? (document.body.innerText || '') : '';
                    if (b.indexOf('Connecting...') !== -1) return 'connecting';
                    return 'ready';
                })()""")
                if st == "ready":
                    return True
            except Exception:
                pass
            time.sleep(0.08)
        return False

    def reset_thread(self, for_chat: bool = False):
        """Close leftover dialogs and ensure a clean session with a ready WebSocket.
        For plain-text chat (for_chat=True), reuse the existing warm connection for ~2s responses when the hot page has no attachments, no stuck state, and few bubbles."""
        if not self.page:
            return
        try:
            needs_nav = self.page.js("""(function(forChat){
                var d = document.querySelector('[role="dialog"]');
                if (d) {
                    var b = d.querySelector('button[aria-label*="close" i], button');
                    if (b) b.click();
                }
                var scope = document.querySelector('main,[class*="chat-scroll"],[class*="hatch-chat-scroll"]') || document.body;
                var bubbleCount = scope ? scope.querySelectorAll('div[class*="hatch-chat-groupable-bubble"]').length : 0;
                var hasAtts = document.querySelectorAll('[data-testid^="hatch-chat-attachment-presentation-"]').length > 0;
                var hasStop = !!document.querySelector('button[aria-label*="Stop" i]');
                var bodyTxt = document.body ? (document.body.innerText || '') : '';
                var hasStuck = bodyTxt.indexOf('Still sending') !== -1 || bodyTxt.indexOf('Connecting...') !== -1;
                if (hasStop || hasStuck || hasAtts) return true;
                if (forChat) {
                    return bubbleCount >= 24;
                }
                return (window.location.pathname !== '/thread/new') || bubbleCount > 0;
            })(%s)""" % ("true" if for_chat else "false"))
            if needs_nav:
                self.page.send("Page.navigate", {"url": "https://muse.ai/thread/new"})
                t_end = time.time() + 10.0
                while time.time() < t_end:
                    time.sleep(0.08)
                    ready = self.page.js("""(function(){
                        return document.readyState === 'complete'
                            && !!document.querySelector('textarea')
                            && document.querySelectorAll('div[class*="hatch-chat-groupable-bubble"]').length === 0;
                    })()""")
                    if ready:
                        break
                self._wait_ws_ready(self.page, timeout=12.0)
        except Exception:
            pass

    def ensure_page(self, cookies: dict, expires: dict | None = None, account_id: str | None = None):
        if self.page is not None and (account_id is None or getattr(self, "current_acc_id", None) == account_id):
            try:
                if self.page.js("!!document.querySelector('textarea')"):
                    return self.page
            except Exception:
                pass
        if self.page:
            try:
                self.page.close()
            except Exception:
                pass
            self.page = None
        # Only call /api/session on the main path when the last HTTP renewal was over 10 minutes ago, to avoid blocking on every account switch
        last_map = getattr(self, "_last_http_renew", None)
        if last_map is None:
            last_map = {}
            self._last_http_renew = last_map
        now_ts = time.time()
        if not account_id or (now_ts - last_map.get(account_id, 0) > 600):
            try:
                renewed = self.renew_session_http(cookies, expires, wake_vm=True)
                if renewed.get("cookies"):
                    cookies = renewed["cookies"]
                if renewed.get("cookies_exp"):
                    expires = renewed["cookies_exp"]
                if account_id:
                    last_map[account_id] = now_ts
            except MuseAuthError:
                raise
            except Exception as e:
                log.warning("Pre-renewal /api/session failed (continuing with browser load): %s", e)

        page = self._open_page()
        self._apply_cookies(page, cookies, expires)
        page.send("Page.navigate", {"url": "https://muse.ai/thread/new"})
        for _ in range(self.cfg.login_wait * 2):
            time.sleep(0.15)
            try:
                # Check for textarea or dormant composer that activates upon click
                has_ta = page.js("""(function(){
                    var ta = document.querySelector('textarea');
                    if (ta) return true;
                    var c = document.querySelector('[data-hatch-composer-chrome="true"]')
                         || document.querySelector('[data-hatch-composer-root="true"]')
                         || document.querySelector('[data-testid="hatch-composer-placeholder-overlay"]');
                    if (c) { c.click(); }
                    return !!document.querySelector('textarea');
                })()""")
                if has_ta:
                    self.page = page
                    self.current_acc_id = account_id
                    self._wait_ws_ready(page, timeout=15.0)
                    return page
            except Exception:
                pass
        try:
            if page.js("!!document.querySelector('textarea')"):
                self.page = page
                self.current_acc_id = account_id
                self._wait_ws_ready(page, timeout=15.0)
                return page
        except Exception:  # noqa: BLE001
            pass
        # Distinguish "session invalid (kicked back to the login page)" from "page load stuck" so the error hint matches the cause
        try:
            body = (page.js("document.body.innerText.slice(0,1200)") or "").lower()
        except Exception:  # noqa: BLE001
            body = ""
        page.close()
        if re.search(r"log in|sign in|create an account|登录|use another account", body):
            raise MuseAuthError("Session was signed out by muse.ai (possibly squeezed out by another login or flagged by risk control), "
                                "please re-import cookies with the browser extension")
        raise MuseGenerationError("muse.ai page load timed out (chat input never appeared); check server network and retry; session not confirmed invalid")

    def refresh(self, cookies: dict, expires: dict | None = None):
        if self.page:
            self.page.close()
            self.page = None
        return self.ensure_page(cookies, expires)

    # ---------------- Quota (Settings panel) ----------------
    # muse.ai quotas live under the bottom Settings menu -> Settings item -> settings panel's
    # General -> Usage section, shaped like:
    #   Free plan
    #   Weekly limit resets on Sep 30
    #   1% used
    #   Additional tokens / Never expires / 0% used (2B tokens left)
    def _click_point(self, x: int, y: int):
        for t in ("mousePressed", "mouseReleased"):
            self.page.send("Input.dispatchMouseEvent",
                           {"type": t, "x": x, "y": y,
                            "button": "left", "clickCount": 1})

    _CLICK_JS = (
        "(function(){var sel=%s;"
        "var b=[...document.querySelectorAll(sel)]"
        ".filter(function(x){return x.offsetParent!==null;})[0];"
        "if(!b)return null;var r=b.getBoundingClientRect();"
        "return JSON.stringify({x:Math.round(r.x+r.width/2),"
        "y:Math.round(r.y+r.height/2)});})()")

    def quota(self, cookies: dict, expires: dict | None = None) -> dict:
        """Open the Settings panel to read quota. Returns a structured dict; raises when unreadable."""
        self.ensure_page(cookies, expires)
        p = self.page
        time.sleep(1)

        # 1) Click the bottom-left Settings button (aria-label=Settings)
        raw = p.js(self._CLICK_JS % json.dumps('button[aria-label="Settings"]'))
        if not raw:
            raise MuseGenerationError("Settings button not found")
        pt = json.loads(raw)
        self._click_point(pt["x"], pt["y"])
        time.sleep(1.6)

        # 2) Click the Settings item in the popup menu
        raw = p.js(
            "(function(){"
            "var els=[...document.querySelectorAll('div,span,li,[role=menuitem],button')]"
            ".filter(function(e){return e.offsetParent!==null"
            "&&(e.textContent||'').trim()==='Settings'"
            "&&e.getAttribute('aria-label')!=='Settings'"
            "&&e.children.length<=3;});"
            "if(!els.length)return null;"
            "var el=els[els.length-1];var r=el.getBoundingClientRect();"
            "return JSON.stringify({x:Math.round(r.x+r.width/2),"
            "y:Math.round(r.y+r.height/2)});})()")
        if not raw:
            raise MuseGenerationError("Settings menu did not pop up")
        pt = json.loads(raw)
        self._click_point(pt["x"], pt["y"])
        time.sleep(3.0)

        # 3) Read the settings panel text
        txt = ""
        for _ in range(6):
            txt = p.js(
                "(function(){var d=document.querySelector('[role=dialog],[aria-modal=true]');"
                "return d?(d.innerText||''):'';})()") or ""
            if "Usage" in txt or "used" in txt:
                break
            time.sleep(1.2)

        # 4) Close the panel (Escape)
        for t in ("keyDown", "keyUp"):
            p.send("Input.dispatchKeyEvent",
                   {"type": t, "key": "Escape", "code": "Escape",
                    "windowsVirtualKeyCode": 27, "nativeVirtualKeyCode": 27})
        time.sleep(0.5)

        return self._parse_quota(txt)

    @staticmethod
    def _parse_quota(txt: str) -> dict:
        """Parse quota fields from the settings panel text."""
        lines = [ln.strip() for ln in (txt or "").split("\n") if ln.strip()]
        out: dict = {"raw": "\n".join(lines[:40])}
        # Plan name: Free plan / xxx plan
        for ln in lines:
            m = re.match(r"^(.+?)\s*plan$", ln, re.I)
            if m:
                out["plan"] = ln
                break
        # Weekly limit resets on Sep 30
        m = re.search(r"Weekly limit resets? on (.+)", txt or "")
        if m:
            out["weekly_reset"] = m.group(1).strip()
        # Weekly usage: the first "N% used" (appearing after the plan line)
        m = re.search(r"(\d+)%\s*used", txt or "")
        if m:
            out["weekly_used_pct"] = int(m.group(1))
        # Extra tokens: "0% used (2B tokens left)"
        m = re.search(r"(\d+)%\s*used\s*\(([^)]+)\)", txt or "")
        if m:
            out["extra_used_pct"] = int(m.group(1))
            out["extra_left"] = m.group(2).strip()
        if "Never expires" in (txt or ""):
            out["extra_expires"] = "never"
        out["found"] = bool(out.get("plan") or "weekly_used_pct" in out)
        return out

    # ---------------- Attachments (generation results) ----------------
    _ATT_JS = (
        "(function(){"
        "var list = []; var seen = new Set();"
        "function addEl(el, tid){"
        "  if(!el || seen.has(el)) return;"
        "  seen.add(el);"
        "  if(el.closest('form, [class*=chat-user-bubble], [class*=\"group/msg\"]')) return;"
        "  var v = el.querySelector('video') || (el.tagName === 'VIDEO' ? el : null);"
        "  var img = el.querySelector('img') || (el.tagName === 'IMG' ? el : null);"
        "  var isVid = (tid || '').includes('video') || !!v;"
        "  var primary = isVid ? (v || img) : (img || v);"
        "  var src = primary ? (primary.currentSrc || primary.src || '') : '';"
        "  if(src && !seen.has(src)){"
        "    seen.add(src);"
        "    list.push({"
        "      tid: tid || el.getAttribute('data-testid') || (isVid ? 'video' : 'image'),"
        "      hasVideo: !!v,"
        "      hasImg: !!img,"
        "      src: src,"
        "      vSrc: v ? (v.currentSrc || v.src || '') : '',"
        "      iSrc: img ? (img.currentSrc || img.src || '') : '',"
        "      w: primary ? (primary.videoWidth || primary.naturalWidth || 0) : 0,"
        "      h: primary ? (primary.videoHeight || primary.naturalHeight || 0) : 0"
        "    });"
        "  }"
        "}"
        "document.querySelectorAll('[data-testid^=\"hatch-chat-attachment-presentation-\"]').forEach(function(a){ addEl(a, a.getAttribute('data-testid')); });"
        "document.querySelectorAll('div[class*=\"hatch-agent-bubble-bg\"] img, div[class*=\"hatch-agent-bubble-bg\"] video').forEach(function(m){"
        "  var s = m.currentSrc || m.src || '';"
        "  if(s && !s.includes('avatar') && !s.includes('emoji')) addEl(m.parentElement || m, 'agent-media');"
        "});"
        "return JSON.stringify(list);"
        "})()"
    )

    def attachments(self) -> list[dict]:
        try:
            raw = self.page.js(self._ATT_JS)
            return json.loads(raw) if raw else []
        except Exception:  # noqa: BLE001
            return []

    # ---------------- Sending ----------------
    # Check "text really entered the input + Send button really rendered".
    # Both are required: the Send button only renders when React state holds text --
    # its presence proves React actually received the input (not just a DOM value change).
    _SEND_STATE_JS = (
        "(function(){var ta=document.querySelector('textarea');"
        "var b=[...document.querySelectorAll('button,[role=button]')]"
        ".find(function(x){return /发送|send/i.test(x.getAttribute('aria-label')||'');});"
        "return JSON.stringify({v:ta?ta.value:'',btn:b?(b.disabled?2:1):0});})()"
    )

    def _send(self, prompt: str):
        # 1. Ensure the textarea is scrolled into the center of the viewport and truly focused
        try:
            self.page.js("""(function(){
                var ta = document.querySelector('textarea');
                if (!ta) {
                    var c = document.querySelector('[data-hatch-composer-chrome="true"]')
                         || document.querySelector('[data-hatch-composer-root="true"]')
                         || document.querySelector('[data-testid="hatch-composer-placeholder-overlay"]');
                    if (c) c.click();
                    ta = document.querySelector('textarea');
                }
                if (ta) {
                    ta.scrollIntoView({block: 'center', inline: 'nearest'});
                    ta.focus();
                }
            })()""")
        except Exception:
            pass
        time.sleep(0.05)
        rect = self.page.js(
            "(function(){"
            "var t=document.querySelector('textarea');"
            "if(!t){"
            "  var c=document.querySelector('[data-hatch-composer-chrome=\"true\"]')||document.querySelector('[data-testid=\"hatch-composer-placeholder-overlay\"]');"
            "  if(c){ c.click(); t=document.querySelector('textarea'); }"
            "}"
            "if(!t)return null;"
            "var r=t.getBoundingClientRect();"
            "return JSON.stringify({x:Math.round(r.left+r.width/2),"
            "y:Math.round(r.top+r.height/2)});})()")
        if not rect:
            raise MuseGenerationError("Chat input box not found")
        c = json.loads(rect)
        for t in ("mousePressed", "mouseReleased"):
            self.page.send("Input.dispatchMouseEvent",
                           {"type": t, "x": c["x"], "y": c["y"],
                            "button": "left", "clickCount": 1})
        time.sleep(0.03)

        # Fire the React 18 prototype setter plus input/change events to sync the send-button state
        # (for 100KB+ huge contexts from DeepSeek/Codex etc., the prototype setter takes <1s; Input.insertText char-by-char would stall)
        _SETTER_JS = (
            "(function(t){var ta=document.querySelector('textarea');"
            "if(!ta) return 0;"
            "ta.focus();"
            "var s=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set;"
            "s.call(ta,t);"
            "ta.dispatchEvent(new Event('input',{bubbles:true}));"
            "ta.dispatchEvent(new Event('change',{bubbles:true}));"
            "return (ta.value||'').length;})(%s)")
        val_len = self.page.js(_SETTER_JS % json.dumps(prompt)) or 0
        if not val_len and len(prompt) < 500:
            self.page.send("Input.insertText", {"text": prompt})
            self.page.js(_SETTER_JS % json.dumps(prompt))

        # Wait for the send button to be ready, then click it
        clicked = "no-button"
        t_deadline = time.time() + 3.0
        while time.time() < t_deadline:
            res = self.page.js(
                "(function(){var b=[...document.querySelectorAll('button,[role=button]')]"
                ".filter(function(x){return x.offsetParent!==null;})"
                ".find(function(x){return /发送|send/i.test(x.getAttribute('aria-label')||'')"
                "||/发送|send/i.test(x.getAttribute('data-testid')||'')"
                "||/send/i.test(x.innerText||'');});"
                "if(!b)return 'no-button';"
                "if(b.disabled)return 'disabled';"
                "b.click();return 'clicked';})()")
            if res == "clicked":
                clicked = "clicked"
                break
            time.sleep(0.08)

        if clicked != "clicked":
            # Fallback: Ctrl+Enter or plain Enter
            for combo in ({"modifiers": 1}, {}):
                for t in ("keyDown", "char", "keyUp"):
                    params = {"type": t, "key": "Enter", "code": "Enter",
                              "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13,
                              "modifiers": combo.get("modifiers", 0)}
                    if t == "char":
                        params["text"] = "\r"
                        params["unmodifiedText"] = "\r"
                    self.page.send("Input.dispatchKeyEvent", params)
                time.sleep(1.0)
                try:
                    if self.page.js("!(document.querySelector('textarea')||{value:''}).value"):
                        clicked = "enter-sent"
                        break
                except Exception:
                    pass
        time.sleep(0.08 if clicked == "clicked" else 0.25)
        return clicked

    # ---------------- Waiting for generation ----------------
    def _last_attachment(self) -> dict | None:
        atts = self.attachments()
        return atts[-1] if atts else None

    def _scroll_bottom(self):
        """Scroll to the bottom of the chat. Caches the scroll container to avoid heavy full-DOM querySelectorAll style recals."""
        try:
            self.page.js(
                "(function(){"
                "var sc=window.__chatScrollEl;"
                "if(!sc||!document.contains(sc)){"
                "var candidates=document.querySelectorAll('main,[role=\"main\"],div[class*=\"chat\"],div[class*=\"thread\"],div[class*=\"scroll\"],div[class*=\"virtual\"],div[class*=\"messages\"]');"
                "var best=null,maxH=0;"
                "for(var i=0;i<candidates.length;i++){"
                "var el=candidates[i];"
                "if(el.scrollHeight>el.clientHeight+80&&el.scrollHeight>maxH){"
                "best=el;maxH=el.scrollHeight;}"
                "}"
                "window.__chatScrollEl=best||document.scrollingElement||document.body;"
                "sc=window.__chatScrollEl;"
                "}"
                "if(sc)sc.scrollTop=sc.scrollHeight;"
                "var el=document.querySelector('textarea');"
                "if(el)el.scrollIntoView({block:'end'});return 1;})()")
        except Exception:  # noqa: BLE001
            pass

    def _wait_attachment(self, baseline_src: str, timeout: int, expect: str,
                         on_progress=None, base_agent_cnt: int = 0,
                         base_att_cnt: int = 0, stop_event=None, baseline_sources=None) -> dict | None:
        baseline_sources = set(baseline_sources or ()) | {baseline_src}
        deadline = time.time() + timeout
        t_start = time.time()
        stable_src, stable_n = "", 0
        last_txt, txt_stable = "", 0
        while time.time() < deadline:
            if stop_event is not None and stop_event.is_set():
                raise MuseGenerationError("Client disconnected; aborting generation task")
            time.sleep(0.25)
            self._scroll_bottom()
            atts = self.attachments()
            att = atts[-1] if atts else None
            if att:
                src = att.get("src") or ""
                v_src = att.get("vSrc") or ""
                tid = att.get("tid") or ""
                w = att.get("w", 0) or 0
                h = att.get("h", 0) or 0
                has_video = att.get("hasVideo", False)
                if expect == "video":
                    want = has_video or ("video" in tid) or ("video" in src) or ("video" in v_src) or src.endswith((".mp4", ".webm", ".mov"))
                else:
                    want = ("image" in tid) or (not has_video)
                check_src = v_src if (expect == "video" and v_src) else src
                if check_src and check_src not in baseline_sources and want:
                    if w > 0 and h > 0:
                        return att
                    if check_src == stable_src:
                        stable_n += 1
                    else:
                        stable_src, stable_n = check_src, 0
                    if stable_n >= 1:
                        return att
            elapsed = time.time() - t_start
            if on_progress:
                prog = min(92, int(25 + elapsed * 1.0))
                try:
                    on_progress(prog)
                except Exception:
                    pass
            try:
                st_raw = self.page.js("""(function(){
                    var bs=[].slice.call(document.querySelectorAll('div[class*="hatch-chat-groupable-bubble"]'))
                        .filter(function(b){return /hatch-agent-bubble-bg/.test(b.className||'');});
                    var lastTxt = bs.length ? (bs[bs.length-1].innerText||'').trim() : '';
                    var hasStop = !!document.querySelector('button[aria-label*="Stop" i]');
                    var tail = document.body ? (document.body.innerText||'').slice(-700) : '';
                    return JSON.stringify({cnt: bs.length, txt: lastTxt, stop: hasStop, tail: tail});
                })()""")
                st = json.loads(st_raw) if st_raw else {}
            except Exception:
                st = {}
            tail = st.get("tail") or ""
            if re.search(r"额度不足|积分不足|out of credits|达到上限|token limit", tail):
                raise MuseGenerationError("Account quota insufficient")
            # Sidebar/stale connection text does not prove this generation failed.
            # The caller's generation deadline remains the bounded timeout.
            # Fast fail: if the assistant already finished a pure-text reply (no Stop button and no new attachment) that is not a media-generation status report
            cur_cnt = st.get("cnt") or 0
            cur_txt = st.get("txt") or ""
            has_stop = bool(st.get("stop"))
            if cur_cnt > base_agent_cnt and cur_txt and not has_stop and len(atts) <= base_att_cnt:
                # Skip when the text contains media-generation keywords (e.g. .webp, .png, .mp4, imagine_media), which mean media is being produced -- never misread it as a text-only refusal
                is_media_report = bool(re.search(r"\.(?:webp|png|jpe?g|mp4|webm)|imagine_media|deliverable|generated\s+.*image|verified\s+generated|artifact", cur_txt, re.I))
                if not is_media_report:
                    if cur_txt == last_txt:
                        txt_stable += 1
                    else:
                        last_txt, txt_stable = cur_txt, 0
                    if txt_stable >= 15 and elapsed > 8.0:
                        raise MuseGenerationError(f"Model returned only text, no media: {cur_txt[:120]}")
                else:
                    txt_stable = 0
            else:
                txt_stable = 0
        return None

    # ---------------- Fetching bytes ----------------
    _EXTRACT_JS = r"""
    (async function(src, expect){
      try{
        var u = src;
        if(!u) return JSON.stringify({ok:false,err:'no-media-src'});
        var r = await fetch(u);
        if(!r.ok) return JSON.stringify({ok:false,err:'media-http-'+r.status});
        var b = await r.blob();
        var ab = await b.arrayBuffer();
        var bytes = new Uint8Array(ab);
        var s = '';
        for(var i=0; i<bytes.length; i+=65536){
          s += String.fromCharCode.apply(null, bytes.subarray(i, i+65536));
        }
        return JSON.stringify({ok:true, mime:b.type||'', size:b.size, url:u, b64:btoa(s)});
      }catch(e){
        return JSON.stringify({ok:false, err:String(e)});
      }
    })(%s, %s)
    """

    # ---------------- Text / code chat ----------------
    _AGENT_TEXT_JS = (
        "(function(){"
        "var bs=[].slice.call(document.querySelectorAll("
        "'div[class*=\"hatch-chat-groupable-bubble\"]'));"
        "for(var i=bs.length-1;i>=0;i--){"
        "var cs=bs[i].className||'';"
        "if(/hatch-agent-bubble-bg/.test(cs))return bs[i].innerText||'';}"
        "return '';})()"
    )
    _USER_COUNT_JS = (
        "(function(){"
        "var bs=[].slice.call(document.querySelectorAll("
        "'div[class*=\"hatch-chat-groupable-bubble\"]'));"
        "var n=0;for(var i=0;i<bs.length;i++){"
        "if(/chat-user-bubble/.test(bs[i].className||''))n++;}"
        "return String(n);})()"
    )
    _AGENT_COUNT_JS = (
        "(function(){"
        "var bs=[].slice.call(document.querySelectorAll("
        "'div[class*=\"hatch-chat-groupable-bubble\"]'));"
        "var n=0;for(var i=0;i<bs.length;i++){"
        "if(/hatch-agent-bubble-bg/.test(bs[i].className||''))n++;}"
        "return String(n);})()"
    )
    _POLL_CHAT_JS = (
        "(function(){"
        "var sc=window.__chatScrollEl;"
        "if(!sc||!document.contains(sc)){"
        "var candidates=document.querySelectorAll('main,[role=\"main\"],div[class*=\"chat\"],div[class*=\"thread\"],div[class*=\"scroll\"],div[class*=\"virtual\"],div[class*=\"messages\"]');"
        "var best=null,maxH=0;"
        "for(var i=0;i<candidates.length;i++){"
        "var el=candidates[i];"
        "if(el.scrollHeight>el.clientHeight+80&&el.scrollHeight>maxH){"
        "best=el;maxH=el.scrollHeight;}"
        "}"
        "window.__chatScrollEl=best||document.scrollingElement||document.body;"
        "sc=window.__chatScrollEl;"
        "}"
        "if(sc)sc.scrollTop=sc.scrollHeight;"
        "var scope=document.querySelector('main,[class*=\"chat-scroll\"],[class*=\"hatch-chat-scroll\"]')||document.body;"
        "var bs=[].slice.call(scope.querySelectorAll('div[class*=\"hatch-chat-groupable-bubble\"]'))"
        ".filter(function(b){return /hatch-agent-bubble-bg/.test(b.className||'');});"
        "var nonEmpty=bs.filter(function(b){return ((b.innerText||'').trim().length)>0;});"
        "var txt=nonEmpty.length?(nonEmpty[nonEmpty.length-1].innerText||'').trim():'';"
        "var stop=!!document.querySelector('button[aria-label*=\"Stop\" i]');"
        "return JSON.stringify({cnt:nonEmpty.length,total:bs.length,txt:txt,stop:stop});})()"
    )

    def _agent_text(self) -> str:
        """Text of the last assistant bubble (empty string when unavailable)."""
        try:
            return (self.page.js(self._AGENT_TEXT_JS) or "").strip()
        except Exception:  # noqa: BLE001
            return ""

    def _agent_count(self) -> int:
        try:
            return int(self.page.js(self._AGENT_COUNT_JS) or 0)
        except Exception:  # noqa: BLE001
            return 0

    def _user_count(self) -> int:
        try:
            return int(self.page.js(self._USER_COUNT_JS) or 0)
        except Exception:  # noqa: BLE001
            return 0

    def _poll_chat(self) -> tuple[int, str, bool]:
        try:
            raw = self.page.js(self._POLL_CHAT_JS)
            if raw:
                d = json.loads(raw)
                return int(d.get("cnt") or 0), (d.get("txt") or "").strip(), bool(d.get("stop"))
        except Exception:
            pass
        return 0, "", False

    def chat_stream(self, cookies: dict, prompt: str, expires: dict | None = None,
                    timeout: int | None = None, account_id: str | None = None,
                    stop_event=None):
        """Send one message, streaming incremental text via yield."""
        timeout = int(timeout or getattr(self.cfg, "chat_timeout", 300))
        self.ensure_page(cookies, expires, account_id=account_id)
        self.reset_thread(for_chat=True)
        base_agent, base_text, _ = self._poll_chat()
        self._send(prompt)

        t_sent = time.time()
        deadline = t_sent + timeout
        first_token_deadline = min(deadline, t_sent + 40.0)
        sent, last, stable = "", None, 0
        got_first = False

        # Wait for the new reply: single CDP poll merges scroll + bubble detection, 80ms fast response
        while time.time() < first_token_deadline:
            if stop_event is not None and stop_event.is_set():
                return
            time.sleep(0.06)
            cnt, cur, has_stop = self._poll_chat()
            if not cur or (cnt <= base_agent and cur == base_text):
                if time.time() - t_sent > 14.0:
                    try:
                        tail = self.page.js("document.body.innerText.slice(-500)") or ""
                    except Exception:
                        tail = ""
                    if "Still sending" in tail or "Connecting..." in tail:
                        raise MuseGenerationError("云端 VM 连接超时 (Still sending)")
                continue

            delta = cur[len(sent):] if cur.startswith(sent) else cur
            if delta:
                sent = cur
                yield delta
                last = cur
                got_first = True
                break
            if cur and cur != base_text:
                got_first = True
                break
            if time.time() - t_sent > 12.0:
                try:
                    tail = self.page.js("document.body.innerText.slice(-500)") or ""
                except Exception:
                    tail = ""
                if "Still sending" in tail or "Connecting..." in tail:
                    raise MuseGenerationError("Cloud VM connection timed out (Still sending)")

        if not got_first:
            raise MuseGenerationError("Timed out waiting for the first assistant response token")

        # Stream incremental text: finish immediately once text is stable 3 times in a row (~0.3s) with no Stop button, removing the 1.2s tail stall
        sent, last, stable = "", None, 0
        while time.time() < deadline:
            if stop_event is not None and stop_event.is_set():
                return
            time.sleep(0.06)
            cnt, cur, has_stop = self._poll_chat()
            if not cur:
                continue

            if cur != last:
                delta = cur[len(sent):] if cur.startswith(sent) else cur
                if delta:
                    sent = cur
                    yield delta
                last, stable = cur, 0
            else:
                stable += 1
                # Stop 按钮消失说明前端生成彻底结束，连续 3 次（约 0.18s）无新文本即正常退出
                if not has_stop and stable >= 3:
                    return
        raise MuseGenerationError("Timed out waiting for the assistant reply")
    def chat(self, cookies: dict, prompt: str, expires: dict | None = None,
             timeout: int | None = None, account_id: str | None = None) -> str:
        """Send one message and return the full reply text (non-streaming)."""
        out = ""
        for chunk in self.chat_stream(cookies, prompt, expires, timeout, account_id=account_id):
            out += chunk
        return out

    def extract_bytes(self, src: str, expect: str = "image", retries: int = 4):
        last = "unknown"
        for _ in range(retries):
            raw = self.page.js(self._EXTRACT_JS % (json.dumps(src), json.dumps(expect)),
                               await_promise=True, timeout=600)
            try:
                info = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:  # noqa: BLE001
                info = {"ok": False, "err": f"parse failed {str(raw)[:150]}"}
            if info.get("ok"):
                return base64.b64decode(info["b64"]), info.get("mime", ""), info.get("url", "")
            last = info.get("err", "unknown")
            time.sleep(2)
        raise MuseGenerationError(f"Failed to fetch generation result: {last}")

    # ---------------- Download fallback ----------------
    def _download_fallback(self, src: str, timeout: int = 180) -> str | None:
        before = set(os.listdir(self.cfg.download_dir))
        # ponytail: fail closed when the selected result has no local download;
        # never click an unrelated/global button that can return the upload.
        clicked = self.page.js("""(function(src){
            var media=[...document.querySelectorAll('img,video')]
                .find(m=>(m.currentSrc||m.src||'')===src);
            var node=media && media.closest('[data-testid^="hatch-chat-attachment-presentation-"]');
            if(!node) return 'none';
            node=node.closest('[class*="group/widget-presentation"]')||node;
            var b=[...node.querySelectorAll('button,[role=button]')]
                .find(x=>/下载|保存|download/i.test(x.getAttribute('aria-label')||''));
            if(!b) return 'none';
            b.click();return 'ok';
        })(%s)""" % json.dumps(src))
        if clicked == "none":
            return None
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(1.5)
            new = [f for f in (set(os.listdir(self.cfg.download_dir)) - before)
                   if not f.endswith(".crdownload")]
            if new:
                p = os.path.join(self.cfg.download_dir, max(
                    new, key=lambda f: os.path.getmtime(os.path.join(self.cfg.download_dir, f))))
                if os.path.getsize(p) > 0:
                    return p
        return None

    @staticmethod
    def _normalize_image(img: str) -> tuple[str, str]:
        """Normalize image inputs of any shape into (base64_str, mime_type)."""
        if not img:
            return "", "image/png"
        img = str(img).strip()
        if img.startswith("data:"):
            parts = img.split(",", 1)
            mime = "image/png"
            if ";" in parts[0]:
                mime = parts[0].split(";")[0].replace("data:", "").strip()
            return (parts[1].strip() if len(parts) > 1 else ""), mime
        if img.startswith("http://") or img.startswith("https://"):
            try:
                req = urllib.request.Request(img, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = resp.read()
                    mime = resp.headers.get_content_type() or "image/png"
                    return base64.b64encode(data).decode("ascii"), mime
            except Exception as e:
                log.warning("Failed to download remote reference image: %s", e)
                return "", "image/png"
        if os.path.isfile(img):
            try:
                with open(img, "rb") as f:
                    data = f.read()
                    mime = mimetypes.guess_type(img)[0] or "image/png"
                    return base64.b64encode(data).decode("ascii"), mime
            except Exception as e:
                log.warning("Failed to read local reference image: %s", e)
                return "", "image/png"
        return img, "image/png"

    def _clear_attachments(self):
        """Clear leftover attachment thumbnails in the chat input box."""
        try:
            self.page.js(
                "(function(){"
                "var btns=Array.from(document.querySelectorAll('button')).filter(function(b){"
                "return /remove attachment|delete|移除|删除/i.test(b.getAttribute('aria-label')||b.innerText||'');"
                "});"
                "btns.forEach(function(b){b.click();});"
                "var inp=document.querySelector('input[type=\"file\"]');"
                "if(inp) inp.value='';"
                "return btns.length;"
                "})()")
            time.sleep(0.3)
        except Exception:
            pass

    def _attach_image(self, image_data: str):
        """Attach the reference image via DataTransfer; never reuse an old history image."""
        if not image_data:
            return
        b64, mime = self._normalize_image(image_data)
        if not b64:
            raise MuseGenerationError("Failed to read reference image; generation stopped")

        self._clear_attachments()

        _INJECT_JS = """
        (function(b64, mime) {
            try {
                var byteChars = atob(b64);
                var byteNumbers = new Array(byteChars.length);
                for (var i = 0; i < byteChars.length; i++) {
                    byteNumbers[i] = byteChars.charCodeAt(i);
                }
                var byteArray = new Uint8Array(byteNumbers);
                var blob = new Blob([byteArray], {type: mime});
                var ext = mime.split('/')[1] || 'png';
                if (ext === 'jpeg') ext = 'jpg';
                var file = new File([blob], 'reference_image.' + ext, {type: mime});
                var input = document.querySelector('input[type="file"]');
                if (!input) return JSON.stringify({ok: false, err: 'no-file-input'});
                var dt = new DataTransfer();
                dt.items.add(file);
                input.files = dt.files;
                input.dispatchEvent(new Event('change', {bubbles: true}));
                input.dispatchEvent(new Event('input', {bubbles: true}));
                return JSON.stringify({ok: true});
            } catch(e) {
                return JSON.stringify({ok: false, err: String(e)});
            }
        })(%s, %s)
        """
        try:
            raw_res = self.page.js(_INJECT_JS % (json.dumps(b64), json.dumps(mime)))
            res_obj = json.loads(raw_res) if isinstance(raw_res, str) else raw_res
            if not res_obj.get("ok"):
                raise MuseGenerationError("Failed to attach reference image; generation stopped")
        except Exception as e:
            raise MuseGenerationError("Failed to attach reference image; generation stopped") from e

        # Wait for input-box attachment confirmation; a history image does not prove this upload succeeded
        deadline = time.time() + 15.0
        while time.time() < deadline:
            has_attached = self.page.js(
                """(function(){
                var hasBtn = document.querySelector('button[aria-label*="Remove attachment" i]');
                return Boolean(hasBtn);
                })()"""
            )
            if has_attached:
                break
            time.sleep(0.3)
        else:
            raise MuseGenerationError("Reference image upload unconfirmed; generation stopped")
        time.sleep(0.5)
    # ---------------- Main flow ----------------
    def generate(self, cookies: dict, prompt: str, expect: str = "image",
                 timeout: int = 240, expires: dict | None = None, account_id: str | None = None,
                 on_progress=None, reference_image: str | None = None,
                 stop_event=None) -> dict:
        self.ensure_page(cookies, expires, account_id=account_id)
        self.reset_thread(for_chat=False)
        self._scroll_bottom()
        if reference_image:
            self._attach_image(reference_image)
        else:
            self._clear_attachments()
        atts_before = self.attachments()
        baseline_sources = {a.get(k) for a in atts_before for k in ("src", "vSrc", "iSrc") if a.get(k)}
        base = atts_before[-1] if atts_before else {}
        baseline_src = base.get("src") or ""
        base_agent_cnt = self._agent_count()
        if self._send(prompt) not in ("clicked", "enter-sent"):
            raise MuseGenerationError("Prompt send unconfirmed; generation stopped")
        att = self._wait_attachment(
            baseline_src, timeout, expect, on_progress=on_progress,
            base_agent_cnt=base_agent_cnt, base_att_cnt=len(atts_before),
            stop_event=stop_event, baseline_sources=baseline_sources
        )
        if not att:
            self._debug_dump("no-attachment")
            raise MuseGenerationError("Generation timed out waiting for new results")

        os.makedirs(self.cfg.media_dir, exist_ok=True)
        data = mime = url = None
        selected_src = (att.get("vSrc") if expect == "video" else None) or att.get("src") or ""
        try:
            data, mime, url = self.extract_bytes(selected_src, expect=expect)
        except Exception:  # noqa: BLE001
            self._debug_dump("extract-fail")

        if data:
            ext = self._pick_ext(mime, url, expect)
            name = f"{uuid.uuid4().hex}{ext}"
            dst = os.path.join(self.cfg.media_dir, name)
            with open(dst, "wb") as f:
                f.write(data)
            return {"path": dst, "filename": name, "size": len(data), "ext": ext, "mime": mime,
                    "kind": "video" if ext in (".mp4", ".webm", ".mov") else "image",
                    "via": "blob", "attachment": att.get("tid"),
                    "w": att.get("w"), "h": att.get("h")}

        path = self._download_fallback(selected_src)
        if not path:
            raise MuseGenerationError("Generated output but failed to retrieve the file")
        ext = os.path.splitext(path)[1].lower() or ".bin"
        name = f"{uuid.uuid4().hex}{ext}"
        dst = os.path.join(self.cfg.media_dir, name)
        shutil.move(path, dst)
        return {"path": dst, "filename": name, "size": os.path.getsize(dst), "ext": ext, "mime": "",
                "kind": "video" if ext in (".mp4", ".webm", ".mov") else "image",
                "via": "download", "attachment": att.get("tid"),
                "w": att.get("w"), "h": att.get("h")}

    @staticmethod
    def _pick_ext(mime: str, url: str, expect: str) -> str:
        m = (mime or "").lower()
        for key, ext in (("mp4", ".mp4"), ("webm", ".webm"), ("png", ".png"),
                         ("jpeg", ".jpg"), ("jpg", ".jpg"), ("webp", ".webp"),
                         ("gif", ".gif")):
            if key in m:
                return ext
        for e in (".mp4", ".webm", ".png", ".jpg", ".webp"):
            if e in (url or "").lower():
                return e
        return ".mp4" if expect == "video" else ".png"

    def _debug_dump(self, tag: str):
        try:
            info = self.page.js(
                "JSON.stringify({atts:[...document.querySelectorAll('" + ATT_SEL + "')]"
                ".map(function(a){var m=a.querySelector('img,video');return {"
                "tid:a.getAttribute('data-testid'),"
                "src:m?(m.currentSrc||m.src||'').slice(0,60):''};}),"
                "buttons:[...document.querySelectorAll('button,[role=button]')]"
                ".filter(b=>b.offsetParent!==null)"
                ".map(b=>b.getAttribute('aria-label')||b.innerText.trim().slice(0,20))"
                ".filter(Boolean).slice(-40),"
                "tail:document.body.innerText.slice(-500)})")
            with open(os.path.join(self.cfg.data_dir, f"debug-{tag}.json"), "w",
                      encoding="utf-8") as f:
                f.write(str(info))
        except Exception:  # noqa: BLE001
            pass

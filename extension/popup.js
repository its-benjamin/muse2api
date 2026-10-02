/* Muse2API Cookie Import — read muse.ai cookies and POST them to the muse2api service.
 *
 * Key point: use chrome.cookies instead of document.cookie.
 * The 4 core muse.ai cookies (hatch_sess / hatch_gw / hatch_vml /
 * hatch_native_auth_device) are all httpOnly, invisible to page JS;
 * only the extension cookies API can read them.
 */

const $ = (id) => document.getElementById(id);
const STORE = 'muse2api_ext_cfg';
const LANG_KEY = 'muse2api_ext_lang';

/* UI strings: add a new key here (en + zh) whenever the popup gains new text. */
const STR = {
  en: {
    sub: 'Sync this browser\u2019s muse.ai login session to your muse2api service in one click.',
    base: 'Service URL (BASE URL)',
    key: 'API Key',
    label: 'Account label (optional)',
    go: 'Read and import',
    stepsTitle: 'Before you start, confirm two things:',
    step1a: 'You are logged in to ',
    step1b: ' in <b>this browser</b> (chat UI visible).',
    step2: 'The service URL and API Key above are filled in (copy them from the top of the \u201cAccount Pool\u201d page in the muse2api admin panel).',
    foot: 'This extension does one thing only: it reads muse.ai cookies via the browser <code>chrome.cookies</code> API (including httpOnly ones) and POSTs them to the service URL you entered. Nothing is collected or uploaded to any third-party server.',
    needBase: 'Please enter the service URL first',
    needKey: 'Please enter the API Key first',
    reading: 'Reading muse.ai cookies\u2026',
    noCookies: 'No muse.ai cookies found.\nPlease open and log in to https://muse.ai/ in this browser, then try again.',
    missingCore: (n, m) => `Found ${n} cookies but core ones are missing: ${m}\nThis browser is not logged in yet. Log in until the chat UI is visible, then retry.`,
    uploading: (n, b) => `Found ${n} cookies, uploading to ${b} \u2026`,
    wrongKey: 'Wrong API Key (service returned 401).\nCopy the correct API Key from the top of the \u201cAccount Pool\u201d admin page.',
    httpFail: (s, t) => `Import failed: HTTP ${s}\n${t}`,
    ok: (label, id, n, exp, warn) => `\u2713 Import succeeded\nAccount label: ${label}\nAccount ID: ${id}\nCookie count: ${n}\nValid until: ${exp}\n${warn}`,
    auto: '(auto)',
    unknown: 'unknown',
    errHead: 'Error: ',
    errCauses: '\n\nCommon causes:\n\u00b7 Wrong service URL or service not running\n\u00b7 URL is not https (or its certificate is untrusted)\n\u00b7 Browser blocked the cross-origin request',
  },
  zh: {
    sub: '\u4e00\u952e\u5c06\u672c\u6d4f\u89c8\u5668\u7684 muse.ai \u767b\u5f55\u6001\u540c\u6b65\u5230\u4f60\u7684 muse2api \u670d\u52a1\u3002',
    base: '\u670d\u52a1\u5730\u5740\uff08BASE URL\uff09',
    key: 'API Key',
    label: '\u8d26\u53f7\u5907\u6ce8\uff08\u53ef\u9009\uff09',
    go: '\u8bfb\u53d6\u5e76\u5bfc\u5165',
    stepsTitle: '\u5f00\u59cb\u524d\u8bf7\u786e\u8ba4\u4e24\u4ef6\u4e8b\uff1a',
    step1a: '\u5df2\u5728<b>\u672c\u6d4f\u89c8\u5668</b>\u767b\u5f55 ',
    step1b: '\uff08\u80fd\u770b\u5230\u804a\u5929\u754c\u9762\uff09\u3002',
    step2: '\u4e0a\u65b9\u5df2\u586b\u5199\u670d\u52a1\u5730\u5740\u548c API Key\uff08\u53ef\u4ece muse2api \u7ba1\u7406\u540e\u53f0\u201c\u8d26\u53f7\u6c60\u201d\u9875\u9762\u9876\u90e8\u590d\u5236\uff09\u3002',
    foot: '\u672c\u6269\u5c55\u53ea\u505a\u4e00\u4ef6\u4e8b\uff1a\u901a\u8fc7\u6d4f\u89c8\u5668 <code>chrome.cookies</code> API \u8bfb\u53d6 muse.ai Cookie\uff08\u542b httpOnly\uff09\uff0c\u5e76 POST \u5230\u4f60\u586b\u5199\u7684\u670d\u52a1\u5730\u5740\u3002\u4e0d\u6536\u96c6\u3001\u4e0d\u4e0a\u4f20\u5230\u4efb\u4f55\u7b2c\u4e09\u65b9\u670d\u52a1\u5668\u3002',
    needBase: '\u8bf7\u5148\u586b\u5199\u670d\u52a1\u5730\u5740',
    needKey: '\u8bf7\u5148\u586b\u5199 API Key',
    reading: '\u6b63\u5728\u8bfb\u53d6 muse.ai Cookie\u2026',
    noCookies: '\u672a\u627e\u5230 muse.ai Cookie\u3002\n\u8bf7\u5148\u5728\u672c\u6d4f\u89c8\u5668\u6253\u5f00 https://muse.ai/ \u5e76\u767b\u5f55\uff0c\u518d\u91cd\u8bd5\u3002',
    missingCore: (n, m) => `\u627e\u5230 ${n} \u4e2a Cookie\uff0c\u4f46\u7f3a\u5c11\u6838\u5fc3\u9879\uff1a${m}\n\u6d4f\u89c8\u5668\u8fd8\u672a\u767b\u5f55\uff0c\u767b\u5f55\u5230\u804a\u5929\u754c\u9762\u53ef\u89c1\u540e\u91cd\u8bd5\u3002`,
    uploading: (n, b) => `\u627e\u5230 ${n} \u4e2a Cookie\uff0c\u6b63\u5728\u4e0a\u4f20\u5230 ${b} \u2026`,
    wrongKey: 'API Key \u9519\u8bef\uff08\u670d\u52a1\u8fd4\u56de 401\uff09\u3002\n\u8bf7\u4ece\u201c\u8d26\u53f7\u6c60\u201d\u7ba1\u7406\u9875\u9876\u90e8\u590d\u5236\u6b63\u786e\u7684 Key\u3002',
    httpFail: (s, t) => `\u5bfc\u5165\u5931\u8d25\uff1aHTTP ${s}\n${t}`,
    ok: (label, id, n, exp, warn) => `\u2713 \u5bfc\u5165\u6210\u529f\n\u8d26\u53f7\u5907\u6ce8\uff1a${label}\n\u8d26\u53f7 ID\uff1a${id}\nCookie \u6570\u91cf\uff1a${n}\n\u6709\u6548\u671f\u81f3\uff1a${exp}\n${warn}`,
    auto: '\uff08\u81ea\u52a8\uff09',
    unknown: '\u672a\u77e5',
    errHead: '\u51fa\u9519\uff1a',
    errCauses: '\n\n\u5e38\u89c1\u539f\u56e0\uff1a\n\u00b7 \u670d\u52a1\u5730\u5740\u9519\u8bef\u6216\u670d\u52a1\u672a\u8fd0\u884c\n\u00b7 URL \u4e0d\u662f https\uff08\u6216\u8bc1\u4e66\u4e0d\u53ef\u4fe1\uff09\n\u00b7 \u6d4f\u89c8\u5668\u62e6\u622a\u4e86\u8de8\u57df\u8bf7\u6c42',
  },
};
let LANG = 'en';
const S = () => STR[LANG] || STR.en;
async function initLang() {
  try {
    const o = await chrome.storage.local.get(LANG_KEY);
    LANG = o[LANG_KEY] || (((navigator.language || 'en').toLowerCase().startsWith('zh')) ? 'zh' : 'en');
  } catch (e) { LANG = (((navigator.language || 'en').toLowerCase().startsWith('zh')) ? 'zh' : 'en'); }
  applyLang();
}
function applyLang() {
  const s = S();
  document.documentElement.lang = LANG === 'zh' ? 'zh-CN' : 'en';
  document.querySelector('.sub').textContent = s.sub;
  const labels = document.querySelectorAll('label');
  if (labels[0]) labels[0].textContent = s.base;
  if (labels[1]) labels[1].textContent = s.key;
  if (labels[2]) labels[2].textContent = s.label;
  $('go').textContent = s.go;
  $('stepsTitle').innerHTML = '<b>' + s.stepsTitle + '</b>';
  $('step1').innerHTML = s.step1a + '<a href="https://muse.ai/" target="_blank" style="color:#4f8cff">muse.ai</a>' + s.step1b;
  $('step2').textContent = s.step2;
  document.querySelector('.foot').innerHTML = s.foot;
  $('langToggle').textContent = LANG === 'zh' ? 'EN' : '\u4e2d\u6587';
}
async function toggleLang() {
  LANG = LANG === 'zh' ? 'en' : 'zh';
  try { await chrome.storage.local.set({ [LANG_KEY]: LANG }); } catch (e) { /* ignore */ }
  applyLang();
}

function log(html, cls) {
  const el = $('log');
  el.className = 'show';
  el.innerHTML = cls ? `<span class="${cls}">${html}</span>` : html;
}

/* Normalize the service URL: strip trailing slashes and a /v1 suffix */
function normBase(v) {
  let s = (v || '').trim();
  if (!s) return '';
  if (!/^https?:\/\//i.test(s)) s = 'https://' + s;
  s = s.replace(/\/+$/, '');
  s = s.replace(/\/v1$/i, '');
  return s;
}

async function loadCfg() {
  const o = await chrome.storage.local.get(STORE);
  const c = o[STORE] || {};
  if (c.base) $('base').value = c.base;
  if (c.key) $('key').value = c.key;
  if (c.label) $('label').value = c.label;
  // If never configured, guess from the active tab (when user is on the admin page)
  if (!c.base) {
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      const u = tab && tab.url ? new URL(tab.url) : null;
      if (u && /\/admin/.test(u.pathname)) {
        $('base').value = u.origin;
        const k = new URLSearchParams(u.search).get('key');
        if (k) $('key').value = k;
      }
    } catch (e) { /* ignore */ }
  }
}

async function saveCfg() {
  await chrome.storage.local.set({
    [STORE]: {
      base: normBase($('base').value),
      key: $('key').value.trim(),
      label: $('label').value.trim(),
    },
  });
}

async function grabCookies() {
  const all = await chrome.cookies.getAll({ domain: 'muse.ai' });
  const out = {}, exp = {};
  for (const c of all) {
    const dom = (c.domain || '').replace(/^\./, '');
    if (!dom.endsWith('muse.ai')) continue;
    out[c.name] = c.value;
    if (c.expirationDate) exp[c.name] = Math.floor(c.expirationDate);
  }
  return { cookies: out, expires: exp };
}

async function run() {
  const s = S();
  const base = normBase($('base').value);
  const key = $('key').value.trim();
  const label = $('label').value.trim();

  if (!base) return log(s.needBase, 'bad');
  if (!key) return log(s.needKey, 'bad');

  $('go').disabled = true;
  log(s.reading);

  try {
    const { cookies, expires } = await grabCookies();
    const names = Object.keys(cookies);
    if (!names.length) {
      return log(s.noCookies, 'bad');
    }
    const missing = ESSENTIAL.filter((n) => !(n in cookies));
    if (missing.length) {
      log(s.missingCore(names.length, missing.join(', ')), 'warn');
      return;
    }

    log(s.uploading(names.length, base));

    const r = await fetch(base + '/admin/accounts', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + key,
      },
      body: JSON.stringify({ label, cookies, expires }),
    });

    const text = await r.text();
    let data;
    try { data = JSON.parse(text); } catch (e) { data = { raw: text }; }

    if (r.status === 401) {
      return log(s.wrongKey, 'bad');
    }
    if (!r.ok) {
      return log(s.httpFail(r.status, text.slice(0, 300)), 'bad');
    }

    const a = (data.added && data.added[0]) || {};
    await saveCfg();
    log(s.ok(a.label || label || s.auto, a.id || '?', a.cookie_count || names.length,
             a.expires_at ? new Date(a.expires_at * 1000).toLocaleString() : s.unknown,
             data.warning ? `\nNote: ${data.warning}` : ''), 'ok');
  } catch (e) {
    log(s.errHead + (e && e.message ? e.message : String(e)) + s.errCauses, 'bad');
  } finally {
    $('go').disabled = false;
  }
}

$('go').addEventListener('click', run);
$('langToggle').addEventListener('click', toggleLang);
loadCfg();
initLang();

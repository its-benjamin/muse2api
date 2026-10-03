# Contributing to muse2api

Thanks for your interest in contributing! This document explains how to get a development environment running and how to submit changes.

---

## Ways to contribute

- Bug reports: open a [GitHub Issue](https://github.com/its-benjamin/muse2api/issues) with steps to reproduce, your OS, Python version, and the relevant log lines
- Feature requests: open an issue describing the use case
- Bug fixes and improvements: open a Pull Request (PR)
- Documentation: corrections, translations, and clarifications are always welcome

---

## Development setup

```bash
git clone https://github.com/its-benjamin/muse2api.git
cd muse2api
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Run the service locally:
```bash
python run.py
```

---

## Running tests

The test suite uses no real muse.ai accounts and consumes no generation quota:

```bash
python tests/test_session_health.py   # account-health logic
python tests/test_media_selection.py  # media-selection regression
python tests/test_async_images.py     # async image task logic
python tests/test_vm_wait.py engine.py --assert  # VM wait behaviour
```

If Chromium is not on PATH, set:
```bash
MUSE2API_CHROMIUM=/path/to/chromium python tests/test_media_selection.py
```

---

## Submitting a PR

1. Fork the repo and create a branch: `git checkout -b fix/your-fix-name`
2. Make your changes; keep them focused, one logical change per PR
3. Run the tests above and make sure they pass
4. Commit with a clear message: `fix: describe what changed and why`
5. Push to your fork and open a PR against `its-benjamin/muse2api:main`

### Commit message convention

```
type: short description

Optional longer explanation.
```

Types: `fix`, `feat`, `docs`, `refactor`, `test`, `chore`

---

## Code style

- Python: follow the existing style (no formatter enforced; just keep it readable)
- Avoid adding new dependencies unless necessary
- Keep Chinese comments/strings only where they serve as DOM-matching regex alternatives (e.g. `/发送|send/i`): these are intentional and must not be removed

---

## Security issues

If you find a security vulnerability, please **do not** open a public issue. Email the maintainer directly or use GitHub's private vulnerability reporting.

---

## Credits

All core reverse-engineering and architecture credit belongs to [@czg86389-hub](https://github.com/czg86389-hub) and the [LINUX DO](https://linux.do/) community. Please credit them in any derivative work.

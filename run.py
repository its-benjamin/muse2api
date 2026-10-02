"""muse2api entrypoint: `python run.py` (honors MUSE2API_HTTP2).

Equivalent manual form without HTTP/2:
    python -m uvicorn app:app --host 127.0.0.1 --port 18610
With experimental HTTP/2 (needs `pip install zttp`):
    python -m uvicorn app:app --host 127.0.0.1 --port 18610 --http zttp --http2
"""
from __future__ import annotations

import uvicorn

from app import app
from config import CFG


def main() -> None:
    kwargs: dict = {"host": CFG.host, "port": CFG.port}
    if CFG.http2:
        try:
            import zttp  # noqa: F401
        except ImportError:
            raise SystemExit("MUSE2API_HTTP2=1 needs the zttp package: pip install zttp")
        kwargs.update(http="zttp", http2=True)
    uvicorn.run(app, **kwargs)


if __name__ == "__main__":
    main()

"""Download dataset files on demand, pinned to exact commits, and cache them locally.

Datasets are never bundled inside this package: they are fetched from their
original repositories (pinned to a commit so results are reproducible) and
stored under the cache directory.
"""

from __future__ import annotations

import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

USER_AGENT = "indicrt/0.1 (+https://github.com/)"


def cache_dir() -> Path:
    base = os.environ.get("INDICRT_CACHE")
    if base:
        p = Path(base)
    else:
        xdg = os.environ.get("XDG_CACHE_HOME")
        p = (Path(xdg) if xdg else Path.home() / ".cache") / "indicrt"
    p.mkdir(parents=True, exist_ok=True)
    return p


def github_raw(repo: str, sha: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{sha}/{path}"


def fetch(url: str, dest: Path, *, retries: int = 3, quiet: bool = False, headers: dict | None = None) -> Path:
    """Download url to dest unless it is already cached."""
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    last: Exception | None = None
    for attempt in range(retries):
        try:
            if not quiet:
                print(f"  downloading {url}", file=sys.stderr)
            with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    f.write(chunk)
            tmp.replace(dest)
            return dest
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (401, 403, 404):
                break
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
        time.sleep(1.5 * (attempt + 1))
    if tmp.exists():
        tmp.unlink()
    raise RuntimeError(f"Could not download {url}: {last}")

# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
"""Minimal Google Slides API client shared by the thumbnail scripts.

Auth: gcloud user credentials with Drive scope
(`gcloud auth login --enable-gdrive-access`). The Slides API needs a
quota project with slides.googleapis.com enabled: mithro-drive-backup
by default, GOOGLE_QUOTA_PROJECT overrides.
"""
import os
import subprocess
import sys
import time

import requests

SLIDES = "https://slides.googleapis.com/v1/presentations"
RETRY = (429, 500, 502, 503, 504)
_TOKEN: str | None = None


def token() -> str:
    global _TOKEN
    if _TOKEN is None:
        _TOKEN = subprocess.run(["gcloud", "auth", "print-access-token"],
                                capture_output=True, text=True,
                                check=True).stdout.strip()
    return _TOKEN


def headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {token()}",
            "X-Goog-User-Project": os.environ.get("GOOGLE_QUOTA_PROJECT",
                                                  "mithro-drive-backup")}


def get(url: str, params: dict | None = None,
        tries: int = 5) -> requests.Response:
    """GET with exponential backoff on quota/server errors."""
    for attempt in range(tries):
        r = requests.get(url, params=params, headers=headers(), timeout=30)
        if r.status_code in RETRY and attempt < tries - 1:
            time.sleep(1.5 * 2 ** attempt)
            continue
        return r
    return r


def slide_ids(pid: str) -> list[str] | None:
    """Page objectIds in deck order, or None (with a message) on failure."""
    r = get(f"{SLIDES}/{pid}", params={"fields": "slides.objectId"})
    if not r.ok:
        print(f"slides {pid}: metadata HTTP {r.status_code}", file=sys.stderr)
        return None
    return [s["objectId"] for s in r.json().get("slides", [])]


def thumbnail_png(pid: str, page: str, size: str = "MEDIUM") -> bytes | None:
    """Render one page (MEDIUM = 800 px wide). Paced: the render quota is
    tight per minute, so callers should keep thread pools small."""
    time.sleep(1.5)
    r = get(f"{SLIDES}/{pid}/pages/{page}/thumbnail",
            params={"thumbnailProperties.thumbnailSize": size})
    if not r.ok:
        print(f"slides {pid}/{page}: thumbnail HTTP {r.status_code}",
              file=sys.stderr)
        return None
    img = requests.get(r.json()["contentUrl"], timeout=30)
    if not img.ok:
        print(f"slides {pid}/{page}: contentUrl HTTP {img.status_code}",
              file=sys.stderr)
        return None
    return img.content

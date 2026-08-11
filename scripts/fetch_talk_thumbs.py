#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "pillow", "pyyaml"]
# ///
"""Fetch and optimize preview thumbnails for the talks page.

For every YouTube recording and Google Slides deck in _data/talks.yaml
and _data/interviews.yaml, download the source thumbnail once and emit
two locally-hosted WebP renditions:

    assets/thumbs/video/<id>-320.webp   (~180px tall, slow networks)
    assets/thumbs/video/<id>-640.webp   (desktop / high-DPI)
    assets/thumbs/slides/<id>-320.webp / -640.webp

plus _data/thumbs.yaml recording each thumbnail's real large-rendition
pixel size (srcset descriptors must state true widths). Templates only
reference thumbnails present in the manifest, so unfetchable ones
(access-restricted decks) degrade to a plain tile at build time.

Re-run after adding talks; existing files are refetched only if their
outputs are missing.
"""

import io
import pathlib
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import requests
import yaml
from PIL import Image

VIDEO_DIR = pathlib.Path("assets/thumbs/video")
SLIDES_DIR = pathlib.Path("assets/thumbs/slides")
MANIFEST = pathlib.Path("_data/thumbs.yaml")
QUALITY = 70

YT_RE = re.compile(r"(?:youtu\.be/|watch\?v=)([\w-]+)")
PRES_RE = re.compile(r"presentation/d/(?!e/)([\w-]+)")
RKEY_RE = re.compile(r"resourcekey=([\w-]+)")


ALIAS_RE = re.compile(r"https?://(?:bit\.ly|j\.mp|wafer\.space)/([\w-]+)")


def collect() -> tuple[set[str], dict[str, tuple[str | None, str]]]:
    """Videos and slides. Slide thumbnails are named by the talk's short
    link alias when it has one (readable file names), else the deck id.
    slides_short (wafer.space) wins over a bit.ly/j.mp slides link."""
    videos: set[str] = set()
    slides: dict[str, tuple[str | None, str]] = {}
    talks = yaml.safe_load(pathlib.Path("_data/talks.yaml").read_text())
    interviews = yaml.safe_load(pathlib.Path("_data/interviews.yaml").read_text())
    for entry in talks + interviews:
        m = YT_RE.search(entry.get("video") or "")
        if m:
            videos.add(m.group(1))
        embed = entry.get("slides_embed") or ""
        m = PRES_RE.search(embed)
        if m:
            rk = RKEY_RE.search(embed)
            am = (ALIAS_RE.match(entry.get("slides_short") or "")
                  or ALIAS_RE.match(entry.get("slides") or ""))
            name = am.group(1) if am else m.group(1)
            slides.setdefault(m.group(1),
                              (rk.group(1) if rk else None, name))
    return videos, slides


def existing(base: pathlib.Path) -> dict | None:
    """Reuse committed renditions instead of refetching (delete to force)."""
    large = pathlib.Path(f"{base}-640.webp")
    if large.exists() and pathlib.Path(f"{base}-320.webp").exists():
        with Image.open(large) as img:
            return {"w": img.width, "h": img.height}
    return None


def emit(img: Image.Image, base: pathlib.Path) -> dict:
    img = img.convert("RGB")
    large = img if img.width <= 640 else img.resize(
        (640, round(img.height * 640 / img.width)), Image.LANCZOS)
    small = img.resize((320, round(img.height * 320 / img.width)),
                       Image.LANCZOS) if img.width > 320 else img
    large.save(f"{base}-640.webp", "WEBP", quality=QUALITY)
    small.save(f"{base}-320.webp", "WEBP", quality=QUALITY)
    return {"w": large.width, "h": large.height}


def fetch_video(vid: str) -> tuple[str, dict] | None:
    base = VIDEO_DIR / vid
    if (have := existing(base)):
        return vid, have
    for name in ("hq720.jpg", "hqdefault.jpg"):
        r = requests.get(f"https://i.ytimg.com/vi/{vid}/{name}", timeout=20)
        if r.ok and r.content[:3] == b"\xff\xd8\xff":
            img = Image.open(io.BytesIO(r.content))
            if name == "hqdefault.jpg":  # 480x360 letterboxed: crop to 16:9
                img = img.crop((0, 45, 480, 315))
            return vid, emit(img, base)
    print(f"video {vid}: no thumbnail", file=sys.stderr)
    return None


_TOKEN: str | None = None


def token() -> str:
    """gcloud user token with Drive scope (gcloud auth login --enable-gdrive-access)."""
    global _TOKEN
    if _TOKEN is None:
        import subprocess
        _TOKEN = subprocess.run(["gcloud", "auth", "print-access-token"],
                                capture_output=True, text=True,
                                check=True).stdout.strip()
    return _TOKEN


def fetch_slides(item: tuple[str, str | None]) -> tuple[str, dict] | None:
    """First-slide PNG via the Slides API — the anonymous
    drive.google.com/thumbnail endpoint bounces many PUBLIC decks to a
    sign-in page, so authenticated rendering is the reliable path.
    The Slides API demands a quota project (enable slides.googleapis.com
    on it once): defaults to mithro-drive-backup, override with
    GOOGLE_QUOTA_PROJECT."""
    import os
    import time
    pid, (_rkey, name) = item
    base = SLIDES_DIR / name
    if (have := existing(base)):
        return pid, {**have, "name": name}
    if name != pid and existing(SLIDES_DIR / pid):
        for sz in ("320", "640"):  # rename id-named renditions in place
            (SLIDES_DIR / f"{pid}-{sz}.webp").rename(
                SLIDES_DIR / f"{name}-{sz}.webp")
        return pid, {**existing(base), "name": name}
    time.sleep(1.5)  # getThumbnail has a tight per-minute render quota
    hdr = {"Authorization": f"Bearer {token()}",
           "X-Goog-User-Project": os.environ.get("GOOGLE_QUOTA_PROJECT",
                                                 "mithro-drive-backup")}
    r = requests.get(f"https://slides.googleapis.com/v1/presentations/{pid}",
                     params={"fields": "slides.objectId"}, headers=hdr,
                     timeout=30)
    if not r.ok or not r.json().get("slides"):
        print(f"slides {pid}: metadata HTTP {r.status_code}", file=sys.stderr)
        return None
    page = r.json()["slides"][0]["objectId"]
    r = requests.get(
        f"https://slides.googleapis.com/v1/presentations/{pid}"
        f"/pages/{page}/thumbnail",
        params={"thumbnailProperties.thumbnailSize": "MEDIUM"},
        headers=hdr, timeout=30)
    if not r.ok:
        print(f"slides {pid}: thumbnail HTTP {r.status_code}", file=sys.stderr)
        return None
    img_r = requests.get(r.json()["contentUrl"], timeout=30)
    if not img_r.ok:
        print(f"slides {pid}: contentUrl HTTP {img_r.status_code}",
              file=sys.stderr)
        return None
    try:
        img = Image.open(io.BytesIO(img_r.content))
    except Exception as exc:
        print(f"slides {pid}: undecodable ({exc})", file=sys.stderr)
        return None
    return pid, {**emit(img, base), "name": name}


def main() -> None:
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    SLIDES_DIR.mkdir(parents=True, exist_ok=True)
    videos, slides = collect()
    token()  # resolve once before threading
    with ThreadPoolExecutor(8) as pool:
        vids = [r for r in pool.map(fetch_video, sorted(videos)) if r]
    with ThreadPoolExecutor(4) as pool:  # Slides API: stay under read quota
        decks = [r for r in pool.map(fetch_slides, sorted(slides.items())) if r]
    manifest = {
        "video": {k: v for k, v in sorted(vids)},
        "slides": {k: v for k, v in sorted(decks)},
    }
    MANIFEST.write_text(
        "# Generated by scripts/fetch_talk_thumbs.py — do not hand-edit.\n"
        "# w/h are the -640 rendition's true pixel size (for srcset/width);\n"
        "# slides entries carry the thumbnail file basename in 'name'.\n"
        + yaml.safe_dump(manifest, sort_keys=True, allow_unicode=True))
    print(f"videos: {len(vids)}/{len(videos)}  "
          f"slides: {len(decks)}/{len(slides)}", file=sys.stderr)
    # Coverage check: every talk with an embed should end up with a
    # thumbnail — published-form (/d/e/) embeds silently escape the
    # collector, which is exactly how tiles go black. Shout about it.
    talks = yaml.safe_load(pathlib.Path("_data/talks.yaml").read_text())
    have = set(manifest["slides"])
    for t in talks:
        embed = t.get("slides_embed") or ""
        if "/presentation/d/e/" in embed:
            print(f"WARNING: published-form embed (no thumbnail possible): "
                  f"{t['title'][:60]} — set slides_edit to the file id",
                  file=sys.stderr)
        else:
            m = PRES_RE.search(embed)
            if m and m.group(1) not in have:
                print(f"WARNING: no thumbnail for {t['title'][:60]}",
                      file=sys.stderr)


if __name__ == "__main__":
    main()

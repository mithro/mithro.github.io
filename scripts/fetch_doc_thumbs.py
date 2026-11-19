#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "pillow", "pyyaml", "pymupdf"]
# ///
"""Fetch first-page preview thumbnails for the design documents page.

For every document in _data/design_docs.yaml, export the Google Doc as
PDF *anonymously* (no credentials — exactly what a site visitor can do),
render page 1 and emit two locally-hosted WebP renditions:

    assets/thumbs/docs/<alias>-240.webp   (card size)
    assets/thumbs/docs/<alias>-480.webp   (high-DPI)

plus _data/doc_thumbs.yaml recording each large rendition's pixel size.

The anonymous export doubles as the "publicly shared" check, and it runs
for every document on every run: a document that bounces to a Google
sign-in page is reported, its old renditions are deleted (so the first
page of a document that has since been un-shared is not left on the
site), and the script exits non-zero so the gap can't go unnoticed.
Existing renditions of public documents are reused rather than
re-rendered; delete them to force a refresh.
"""

import io
import pathlib
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import pymupdf
import requests
import yaml
from PIL import Image

DATA = pathlib.Path("_data/design_docs.yaml")
MANIFEST = pathlib.Path("_data/doc_thumbs.yaml")
OUT = pathlib.Path("assets/thumbs/docs")
QUALITY = 72
LARGE, SMALL = 480, 240

DOC_RE = re.compile(r"/document/d/([\w-]+)")
RKEY_RE = re.compile(r"resourcekey=([\w-]+)")
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) mith.ro-thumbs"}


def existing(base: pathlib.Path) -> dict | None:
    large = pathlib.Path(f"{base}-{LARGE}.webp")
    if large.exists() and pathlib.Path(f"{base}-{SMALL}.webp").exists():
        with Image.open(large) as img:
            return {"w": img.width, "h": img.height}
    return None


def emit(img: Image.Image, base: pathlib.Path) -> dict:
    img = img.convert("RGB")
    large = img if img.width <= LARGE else img.resize(
        (LARGE, round(img.height * LARGE / img.width)), Image.LANCZOS)
    small = large.resize((SMALL, round(large.height * SMALL / large.width)),
                         Image.LANCZOS)
    large.save(f"{base}-{LARGE}.webp", "WEBP", quality=QUALITY)
    small.save(f"{base}-{SMALL}.webp", "WEBP", quality=QUALITY)
    return {"w": large.width, "h": large.height}


def fetch(doc: dict) -> tuple[str, dict | None, dict | None]:
    """(alias, fresh preview size or None, kept-but-unchecked size or None)."""
    alias, url = doc["alias"], doc["url"]
    base = OUT / alias
    m = DOC_RE.search(url)
    if not m:
        print(f"{alias}: not a Google Docs URL: {url}", file=sys.stderr)
        return alias, None, None
    params = {"format": "pdf"}
    if (rk := RKEY_RE.search(url)):
        params["resourcekey"] = rk.group(1)
    try:
        r = requests.get(f"https://docs.google.com/document/d/{m.group(1)}/export",
                         params=params, headers=UA, timeout=120)
    except requests.RequestException as e:
        r = None
        why = str(e)
    if r is None or r.status_code == 429 or r.status_code >= 500:
        # Could not tell either way (rate limit, Google hiccup, network):
        # keep whatever previews exist, but still fail the run.
        why = why if r is None else f"HTTP {r.status_code}"
        print(f"{alias}: could not check ({why}); keeping existing previews",
              file=sys.stderr)
        return alias, None, existing(base)
    if not r.ok or "accounts.google.com" in r.url or r.content[:5] != b"%PDF-":
        print(f"{alias}: NOT publicly readable (HTTP {r.status_code}, "
              f"final URL {r.url[:60]})", file=sys.stderr)
        for size in (LARGE, SMALL):
            stale = pathlib.Path(f"{base}-{size}.webp")
            if stale.exists():
                stale.unlink()
                print(f"{alias}: deleted {stale}", file=sys.stderr)
        return alias, None, None
    if (have := existing(base)):
        return alias, have, None
    with pymupdf.open(stream=r.content, filetype="pdf") as pdf:
        page = pdf[0]
        zoom = LARGE / page.rect.width  # render straight to the large width
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
    return alias, emit(img, base), None


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    groups = yaml.safe_load(DATA.read_text())
    docs = [d for g in groups for d in g["docs"]]
    aliases = [d["alias"] for d in docs]
    if len(set(aliases)) != len(aliases):
        dupes = sorted({a for a in aliases if aliases.count(a) > 1})
        print(f"duplicate aliases in {DATA}: {dupes}", file=sys.stderr)
        return 1
    with ThreadPoolExecutor(4) as ex:
        results = list(ex.map(fetch, docs))
    unchecked = [a for a, _, kept in results if kept]
    # Previews of documents that could not be checked this time are kept
    # (a rate limit must not wipe the page); only a confirmed non-public
    # document loses its preview.
    manifest = {a: r or kept for a, r, kept in results if r or kept}
    # Previews of documents no longer listed would stay published.
    for f in sorted(OUT.glob("*.webp")):
        if f.stem.rsplit("-", 1)[0] not in aliases:
            f.unlink()
            print(f"deleted {f} (not in {DATA})", file=sys.stderr)
    MANIFEST.write_text(
        "# Generated by scripts/fetch_doc_thumbs.py — do not hand-edit.\n"
        "# w/h are the -480 rendition's true pixel size (for srcset/width).\n"
        + yaml.safe_dump(manifest, sort_keys=True, allow_unicode=True))
    missing = [a for a in aliases if a not in manifest]
    print(f"{len(manifest)}/{len(aliases)} documents have thumbnails")
    if missing:
        print("MISSING thumbnails (page will show plain cards): "
              + ", ".join(missing), file=sys.stderr)
    if unchecked:
        print("NOT CHECKED this run (re-run later): " + ", ".join(unchecked),
              file=sys.stderr)
    return 1 if missing or unchecked else 0


if __name__ == "__main__":
    sys.exit(main())

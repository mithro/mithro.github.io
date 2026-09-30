#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "pillow", "pyyaml"]
# ///
"""Export per-slide film-strip thumbnails for talks marked strips: true.

    uv run scripts/fetch_slide_strips.py            # everything missing/stale
    uv run scripts/fetch_slide_strips.py --only hw26 --force

For each deck: assets/strips/<slug>/NNN-240.webp and NNN-480.webp
(NNN = 1-based slide number, zero-padded) plus a manifest entry in
_data/strips.yaml. A deck is skipped when its manifest entry already
lists the same slide ids and the files are present. Decks whose talk
no longer has strips: true are removed on a full run (the sheet's
Strips column is the authority — see talks_sheet.py import).
Where a clicked frame goes is not recorded here: see deck_links.py.
"""
import argparse
import io
import pathlib
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor

import yaml
from PIL import Image

import slides_api

STRIPS_DIR = pathlib.Path("assets/strips")
MANIFEST = pathlib.Path("_data/strips.yaml")
TALKS = pathlib.Path("_data/talks.yaml")
PRES_RE = re.compile(r"presentation/d/(?!e/)([\w-]+)")
WIDTHS = (240, 480)
QUALITY = 70


def collect() -> list[tuple[str, str]]:
    """(slug, presentation id) for every strips: true talk."""
    out = []
    for t in yaml.safe_load(TALKS.read_text()):
        if not t.get("strips"):
            continue
        pid = next((m.group(1) for f in ("slides_edit", "slides", "slides_embed")
                    if (m := PRES_RE.search(t.get(f) or ""))), None)
        if not pid:
            print(f"{t['slug']}: strips: true but no usable deck id",
                  file=sys.stderr)
            continue
        out.append((t["slug"], pid))
    return out


def have_files(slug: str, n: int) -> bool:
    d = STRIPS_DIR / slug
    return all((d / f"{i:03d}-{w}.webp").exists()
               for i in range(1, n + 1) for w in WIDTHS)


def size_of(slug: str) -> tuple[int, int]:
    with Image.open(STRIPS_DIR / slug / "001-480.webp") as img:
        return img.width, img.height


def export(item: tuple[str, str], old: dict | None,
           force: bool) -> tuple[str, dict] | None:
    """One deck; never raises (a failure must not sink the whole run)."""
    slug = item[0]
    try:
        return _export(item, old, force)
    except Exception as exc:  # noqa: BLE001 — report and move on
        shutil.rmtree(STRIPS_DIR / f".{slug}.partial", ignore_errors=True)
        print(f"{slug}: failed ({exc!r})", file=sys.stderr)
        return None


def _export(item: tuple[str, str], old: dict | None,
            force: bool) -> tuple[str, dict] | None:
    slug, pid = item
    ids = slides_api.slide_ids(pid)
    if not ids:
        return None
    if not force and have_files(slug, len(ids)):
        if old and old.get("slides") == ids:
            return slug, old
        if not old:
            # Complete directory from an earlier run whose manifest write
            # never happened: adopt it rather than re-rendering.
            w, h = size_of(slug)
            print(f"{slug}: adopted {len(ids)} existing slides", file=sys.stderr)
            return slug, {"deck": pid, "count": len(ids),
                          "w": w, "h": h, "slides": ids}
    tmp = STRIPS_DIR / f".{slug}.partial"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    size = None
    for n, oid in enumerate(ids, start=1):
        png = slides_api.thumbnail_png(pid, oid)
        if png is None:
            shutil.rmtree(tmp)
            print(f"{slug}: gave up at slide {n}/{len(ids)}", file=sys.stderr)
            return None
        img = Image.open(io.BytesIO(png)).convert("RGB")
        for w in WIDTHS:
            small = img.resize((w, round(img.height * w / img.width)),
                               Image.LANCZOS)
            small.save(tmp / f"{n:03d}-{w}.webp", "WEBP", quality=QUALITY)
            if w == 480:
                size = (small.width, small.height)
    final = STRIPS_DIR / slug
    shutil.rmtree(final, ignore_errors=True)
    tmp.rename(final)
    print(f"{slug}: {len(ids)} slides", file=sys.stderr)
    return slug, {"deck": pid, "count": len(ids),
                  "w": size[0], "h": size[1], "slides": ids}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append", default=[],
                    help="slug (repeatable)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    STRIPS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = (yaml.safe_load(MANIFEST.read_text()) or {}) if MANIFEST.exists() else {}
    wanted = collect()
    if args.only:
        wanted = [w for w in wanted if w[0] in args.only]
    slides_api.token()
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(
            lambda w: export(w, manifest.get(w[0]), args.force), wanted))
    done = dict(r for r in results if r)
    # Prune decks that lost strips: true (only meaningful on a full run).
    if not args.only:
        keep = {w[0] for w in wanted}
        for slug in sorted(set(manifest) - keep):
            shutil.rmtree(STRIPS_DIR / slug, ignore_errors=True)
            print(f"{slug}: removed (strips no longer requested)", file=sys.stderr)
        manifest = {k: v for k, v in manifest.items() if k in keep}
    manifest.update(done)
    MANIFEST.write_text(
        "# Generated by scripts/fetch_slide_strips.py — do not hand-edit.\n"
        "# One entry per talk slug with strips: true; slides lists page\n"
        "# objectIds in deck order, w/h are the -480 rendition's size.\n"
        + yaml.safe_dump(manifest, sort_keys=True, allow_unicode=True))
    failed = [w[0] for w, r in zip(wanted, results) if r is None]
    print(f"strips: {len(done)}/{len(wanted)} decks ok"
          + (f"; FAILED: {', '.join(failed)}" if failed else ""),
          file=sys.stderr)


if __name__ == "__main__":
    main()

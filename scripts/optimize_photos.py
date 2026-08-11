#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow"]
# ///
"""Generate responsive WebP renditions of the display photos.

For each photo used on the home page, emit
assets/photos/opt/<stem>-480.webp and <stem>-960.webp (no upscaling —
the large rendition is capped at the source width). The originals stay
as the <img src> fallback. Re-run after adding or replacing photos and
update the srcset markup if a new width appears (the script prints the
true emitted widths).
"""

import pathlib
import sys

from PIL import Image

PHOTOS = ["tim-ansell", "wafer-grid", "die-scan", "chip-on-board",
          "die-on-finger", "numato-opsis", "fomu"]
SRC = pathlib.Path("assets/photos")
OUT = SRC / "opt"
QUALITY = 78


def rendition(img: Image.Image, width: int, dest: pathlib.Path) -> int:
    if img.width > width:
        img = img.resize((width, round(img.height * width / img.width)),
                         Image.LANCZOS)
    img.convert("RGB").save(dest, "WEBP", quality=QUALITY)
    return img.width

OUT.mkdir(exist_ok=True)
for stem in PHOTOS:
    src = SRC / f"{stem}.jpg"
    img = Image.open(src)
    w480 = rendition(img, 480, OUT / f"{stem}-480.webp")
    w960 = rendition(img, 960, OUT / f"{stem}-960.webp")
    kb = lambda p: (OUT / p).stat().st_size // 1024
    print(f"{stem}: {w480}w ({kb(f'{stem}-480.webp')}KB), "
          f"{w960}w ({kb(f'{stem}-960.webp')}KB)  [src {img.width}w]",
          file=sys.stderr)

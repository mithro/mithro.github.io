# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow"]
# ///
"""Generate assets/photos/og-image.jpg: a 1200x630 landscape crop of the
die scan, sized for link-unfurl previews (Open Graph / Twitter cards).

The source die-scan.jpg is a 1600x2082 portrait photo of the full die,
dominated by rows of standard cells with a blue/teal pad ring running
around all four edges. A straight resize to a 1200x630 landscape box
would either letterbox heavily or squash the die out of proportion, so
instead we crop a full-width horizontal band (1600x840, already very
close to the 1200x630 aspect ratio) from a region that shows the
standard-cell texture plus a strip of the pad ring on the left/right
edges, then downscale that band to exactly 1200x630.

Usage: uv run scripts/make_og_image.py
"""
import pathlib

from PIL import Image

SRC = pathlib.Path("assets/photos/die-scan.jpg")
DEST = pathlib.Path("assets/photos/og-image.jpg")
TARGET_W, TARGET_H = 1200, 630
MAX_BYTES = 300_000

im = Image.open(SRC)
im = im.convert("RGB")
w, h = im.size
print(f"source: {SRC} {w}x{h}")

# Full-width band, vertically centered on the standard-cell area (avoids
# the corner logos/QR patterns right at the top and bottom edges) while
# still catching a run of the pad-ring squares down the left and right
# sides. Band height chosen to match the target aspect ratio (1200:630)
# so the downscale below doesn't need to further crop.
band_h = round(w * TARGET_H / TARGET_W)  # ~840 for a 1600-wide source
center_y = round(h * 0.53)  # slightly below the geometric middle, into
                             # the denser/darker macro block visible there
top = max(0, min(h - band_h, center_y - band_h // 2))
box = (0, top, w, top + band_h)
print(f"crop box: {box} ({box[2]-box[0]}x{box[3]-box[1]})")

crop = im.crop(box)
resized = crop.resize((TARGET_W, TARGET_H), Image.LANCZOS)

quality = 90
while quality >= 40:
    resized.save(DEST, "JPEG", quality=quality, optimize=True)
    size = DEST.stat().st_size
    print(f"quality={quality} -> {size} bytes")
    if size <= MAX_BYTES:
        break
    quality -= 5

print(f"wrote {DEST} {resized.size[0]}x{resized.size[1]} ({DEST.stat().st_size} bytes)")
if DEST.stat().st_size > MAX_BYTES:
    raise SystemExit(f"still over {MAX_BYTES} bytes at quality={quality}")

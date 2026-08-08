# /// script
# requires-python = ">=3.11"
# ///
"""Download the selected wafer.space photos for mith.ro at web resolution.

Source albums (Google Photos shared links, resolved 2026-08-08):
  WS-RUN1:   https://photos.app.goo.gl/zLqQ9kHEEbKYhzww5
  Customer:  https://photos.app.goo.gl/2vo4baXmki3fGFdb7
"""
import pathlib
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

# base URLs are recorded in assets/photos/manifest.yaml alongside their
# source albums; =w1600 requests a 1600px-wide rendition.
PHOTOS = {
    "wafer-grid.jpg": "https://lh3.googleusercontent.com/pw/AP1GczM3MseGDmcDF7egcGuUbrGhADx8ywKMx62n8fm3a9VsVnJ18rSdlopoaGP1XKMalPq2qO0zXD6rt8EMnyJZtht434iaDUqCiCxFg4imHTRqmw6RXHU",
    "die-scan.jpg": "https://lh3.googleusercontent.com/pw/AP1GczMh6LOLVO5gNiSWKeaxcmp7dZs9wQochSNMexsj9Fk728Lhq6mmvlRsDqpWeWJ4r0-8UaR7byzq5MRZr2ytqNwcyBeew571ZvIqF1ann8BpdAQ2S8U4",
    "chip-on-board.jpg": "https://lh3.googleusercontent.com/pw/AP1GczOdfsd1IvdpzJOy64GnPRcG0HYyhUy2ZHSxYsgj6NrjW9znncORvjwMmxJ69G_fLq8e6ZyU6I47j3KSqpkzQKoTvtZrYfHk8x87EU3KQNHAGoJk0dWn",
    "die-on-finger.jpg": "https://lh3.googleusercontent.com/pw/AP1GczPUQfpMW1m8tASXoPAjuSZQzsh0TK_r-EMZftDczSxkLXGjg1gDu8ihfhWtdS5734OaExmqQZMRjLBpDke7ggWLUD2sjIjirIKU67PyM4Bqv4Bk6ZgC",
}

outdir = pathlib.Path("assets/photos")
outdir.mkdir(parents=True, exist_ok=True)
for name, base in PHOTOS.items():
    dest = outdir / name
    req = urllib.request.Request(base + "=w1600", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        dest.write_bytes(resp.read())
    print(f"OK {dest} ({dest.stat().st_size} bytes)")

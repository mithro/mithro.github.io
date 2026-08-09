# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Generate jekyll-redirect-from stub pages from _data/shortlinks.yaml.

Stubs live in redirects/ but publish at /<keyword>/ via permalink.
Re-running is idempotent: the redirects/ dir is rebuilt from scratch.

Source of truth for public/private is the "mith.ro short links" Google
Sheet (Visibility column); _data/shortlinks.yaml mirrors it (include:
true == public). Ask Claude to re-sync the YAML from the sheet after
flipping rows, then re-run this script.
"""
import pathlib
import shutil

import yaml

RESERVED = {"talks", "papers", "resume", "about", "assets", "docs", "scripts", "404"}

links = yaml.safe_load(open("_data/shortlinks.yaml"))
outdir = pathlib.Path("redirects")
if outdir.exists():
    shutil.rmtree(outdir)
outdir.mkdir()

count = 0
for e in links:
    if not e["include"]:
        continue
    kw = e["keyword"]
    if kw.lower() in RESERVED:
        print(f"SKIP reserved: {kw}")
        continue
    stub = outdir / f"{kw}.md"
    stub.write_text(
        "---\n"
        f"permalink: /{kw}/\n"
        f"redirect_to: \"{e['long_url']}\"\n"
        "sitemap: false\n"
        "---\n"
    )
    count += 1
print(f"Wrote {count} redirect stubs")

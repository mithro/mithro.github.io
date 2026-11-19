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

Keywords imported from bit.ly as "mithro-<name>" publish under the
shorter "<name>" as their primary mith.ro path (mith.ro/hepic24); the
original "mithro-<name>" keeps working as an alias to the same target.
If "<name>" is reserved (e.g. mithro-talks, mithro-resume) only the
original keyword is published.
"""
import pathlib
import shutil

import yaml

RESERVED = {"talks", "interviews", "papers", "projects", "resume", "about",
            "assets", "docs", "scripts", "404"}
PREFIX = "mithro-"

links = yaml.safe_load(open("_data/shortlinks.yaml"))
outdir = pathlib.Path("redirects")
if outdir.exists():
    shutil.rmtree(outdir)
outdir.mkdir()

count = 0
seen: set[str] = set()
for e in links:
    if not e["include"]:
        continue
    customs = [u.rsplit("/", 1)[-1] for u in e.get("custom_bitlinks") or []]
    names = [e["keyword"], *customs]
    if e["keyword"].startswith(PREFIX):
        # Primary name drops the redundant "mithro-" prefix.
        names.insert(0, e["keyword"][len(PREFIX):])
    # A stub for every name; each redirects straight to the long URL
    # (no hop via the primary) so aliases are as fast as the primary.
    for name in names:
        if name.lower() in RESERVED:
            print(f"SKIP reserved: {name}")
            continue
        if name in seen:
            continue
        seen.add(name)
        stub = outdir / f"{name}.md"
        stub.write_text(
            "---\n"
            f"permalink: /{name}/\n"
            f"redirect_to: \"{e['long_url']}\"\n"
            "sitemap: false\n"
            "---\n"
        )
        count += 1
print(f"Wrote {count} redirect stubs")

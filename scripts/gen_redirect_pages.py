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
import os
import pathlib
import re
import shutil

import yaml

# Names that must never become short links because the site already
# serves something there. Top-level files and directories and any
# front-matter permalink are added automatically below; this list covers
# what that scan cannot see (paths added on other branches, and words
# kept free for future sections).
RESERVED = {"talks", "interviews", "papers", "projects", "resume", "about",
            "assets", "docs", "scripts", "404", "contributions",
            "design-docs", ".well-known"}
PREFIX = "mithro-"


def site_paths() -> set[str]:
    """First path segment of everything the site already publishes."""
    found = {p.name.split(".")[0] if p.is_file() else p.name
             for p in pathlib.Path(".").iterdir()
             if p.name not in {"redirects"} and not p.name.startswith("_")}
    skip = {"redirects", "_site", "docs", "vendor", "assets", "node_modules"}
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in skip and not d.startswith(".")]
        for fn in files:
            if not fn.endswith((".md", ".html")):
                continue
            head = pathlib.Path(root, fn).read_text(errors="ignore")[:2000]
            if not head.startswith("---"):
                continue
            m = re.search(r"^permalink:\s*[\"']?/([^/\"'\s]+)", head, re.M)
            if m:
                found.add(m.group(1).split(".")[0])
    return {n.lower() for n in found if n}


reserved = RESERVED | site_paths()

links = yaml.safe_load(open("_data/shortlinks.yaml"))
outdir = pathlib.Path("redirects")
if outdir.exists():
    shutil.rmtree(outdir)
outdir.mkdir()

# Two passes so that a real keyword (or custom alias) always wins over a
# name made by stripping "mithro-": if bit.ly ever has both "hepic24"
# and "mithro-hepic24" pointing at different places, /hepic24/ follows
# the "hepic24" keyword and the stripped name is dropped with a warning.
claims: dict[str, str] = {}   # lowercased name -> long URL
order: list[tuple[str, str]] = []


def claim(name: str, url: str, derived_from: str | None = None) -> None:
    key = name.lower()
    if key in reserved:
        print(f"SKIP reserved: {name}")
        return
    if key in claims:
        if derived_from and claims[key] != url:
            print(f"WARN: /{name}/ already belongs to another link; "
                  f"{derived_from} is published only under its full name")
        return
    claims[key] = url
    order.append((name, url))


public = [e for e in links if e["include"]]
for e in public:
    for name in [e["keyword"], *(u.rsplit("/", 1)[-1] for u in e.get("custom_bitlinks") or [])]:
        claim(name, e["long_url"])
for e in public:
    kw = e["keyword"]
    if kw.lower().startswith(PREFIX) and len(kw) > len(PREFIX):
        # Primary name drops the redundant "mithro-" prefix.
        claim(kw[len(PREFIX):], e["long_url"], derived_from=kw)

# A stub for every name; each redirects straight to the long URL (no hop
# via the primary) so aliases are as fast as the primary.
for name, url in order:
    (outdir / f"{name}.md").write_text(
        "---\n"
        f"permalink: /{name}/\n"
        f"redirect_to: \"{url}\"\n"
        "sitemap: false\n"
        "---\n"
    )
print(f"Wrote {len(order)} redirect stubs")

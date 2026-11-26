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
import json
import pathlib
import re
import shutil
import subprocess

import yaml

# Names that must never become short links because the site already
# serves something there. Top-level files and directories and any
# front-matter permalink are added automatically below; this list covers
# what that scan cannot see (paths added on other branches, and words
# kept free for future sections).
RESERVED = {"talks", "interviews", "papers", "projects", "resume", "about",
            "assets", "docs", "scripts", "404", "contributions",
            "design-docs", "pcbs", ".well-known"}
PREFIX = "mithro-"
FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---", re.S)


def site_paths() -> set[str]:
    """First path segment of everything the site already publishes.

    Uses the files git tracks (so stray local files and build output
    don't count), minus what _config.yml excludes from the build, plus
    every front-matter permalink.
    """
    tracked = subprocess.run(["git", "ls-files"], capture_output=True,
                             text=True, check=True).stdout.splitlines()
    exclude = {str(x).rstrip("/") for x in
               (yaml.safe_load(open("_config.yml")) or {}).get("exclude") or []}
    found = set()
    for path in tracked:
        top = path.split("/", 1)[0]
        if (top.startswith(("_", ".")) or top == "redirects"
                or top in exclude or path in exclude):
            continue
        found.add(top.split(".")[0] if "/" not in path else top)
        if path.endswith((".md", ".html")):
            fm = FRONT_MATTER.match(pathlib.Path(path).read_text(errors="ignore"))
            m = fm and re.search(r"^permalink:\s*[\"']?/([^/\"'\s]+)", fm.group(1), re.M)
            if m:
                found.add(m.group(1).split(".")[0])
    return {n.lower() for n in found if n}


reserved = RESERVED | site_paths()

links = yaml.safe_load(open("_data/shortlinks.yaml"))
outdir = pathlib.Path("redirects")
if outdir.exists():
    shutil.rmtree(outdir)
outdir.mkdir()

# Real keywords and custom aliases always win over a name made by
# stripping "mithro-", and that includes PRIVATE ones: if bit.ly has a
# "hepic24" keyword (public or not) as well as "mithro-hepic24", then
# mith.ro/hepic24 must never point somewhere bit.ly/hepic24 doesn't, so
# the stripped name is dropped with a warning. Private keywords only
# claim their name; they never get a stub.
claims: dict[str, str] = {}   # lowercased name -> long URL
order: list[tuple[str, str]] = []


def claim(name: str, url: str, public: bool, derived_from: str | None = None) -> None:
    key = name.lower()
    if key in reserved:
        if public:
            print(f"SKIP reserved: {name}")
        return
    if key in claims:
        if claims[key] != url and public:
            what = derived_from or name
            print(f"WARN: /{name}/ already belongs to another link; "
                  f"{what} is not published under that name")
        return
    claims[key] = url
    if public:
        order.append((name, url))


def names(e: dict) -> list[str]:
    return [e["keyword"], *(u.rsplit("/", 1)[-1] for u in e.get("custom_bitlinks") or [])]


for e in links:  # public first, so a public link wins a clash with a private one
    if e["include"]:
        for name in names(e):
            claim(name, e["long_url"], public=True)
for e in links:
    if not e["include"]:
        for name in names(e):
            claim(name, e["long_url"], public=False)
for e in links:
    kw = e["keyword"]
    if e["include"] and kw.lower().startswith(PREFIX) and len(kw) > len(PREFIX):
        # Primary name drops the redundant "mithro-" prefix.
        claim(kw[len(PREFIX):], e["long_url"], public=True, derived_from=kw)

# A stub for every name; each redirects straight to the long URL (no hop
# via the primary) so aliases are as fast as the primary.
for name, url in order:
    (outdir / f"{name}.md").write_text(
        "---\n"
        f"permalink: /{name}/\n"
        # json.dumps gives a valid YAML double-quoted scalar for any URL
        # (quotes/backslashes escaped) and is byte-identical to plain
        # "..." quoting for ordinary ASCII URLs.
        f"redirect_to: {json.dumps(url)}\n"
        "sitemap: false\n"
        "---\n"
    )
print(f"Wrote {len(order)} redirect stubs")

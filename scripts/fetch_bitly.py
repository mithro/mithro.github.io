# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Fetch all bitlinks for the mithro bit.ly group into _data/shortlinks.yaml.

Usage: BITLY_TOKEN=... uv run scripts/fetch_bitly.py
The token is never written anywhere; keep it out of the repo and shell history
(e.g. `read -s BITLY_TOKEN && export BITLY_TOKEN`).
"""
import json
import os
import sys
import urllib.request

import yaml

TOKEN = os.environ.get("BITLY_TOKEN")
if not TOKEN:
    sys.exit("Set BITLY_TOKEN in the environment")

GROUP = "Bb5ml3vJt6Z"
# Keep in sync with RESERVED in gen_redirect_pages.py (which also adds
# every top-level path and permalink it finds at generation time).
RESERVED = {"talks", "interviews", "papers", "projects", "resume", "about",
            "assets", "docs", "scripts", "404", "contributions",
            "design-docs", "pcbs", ".well-known"}

def api(url):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)

links = []
url = f"https://api-ssl.bitly.com/v4/groups/{GROUP}/bitlinks?size=100"
while url:
    page = api(url)
    links.extend(page["links"])
    url = page.get("pagination", {}).get("next") or None
print(f"Fetched {len(links)} bitlinks", file=sys.stderr)

# Visibility belongs to the "mith.ro short links" sheet (format_sheets.py
# sync writes it into this mirror as include:), never to this script: a
# link keeps the include: it already has, and a link bit.ly reports for the
# first time is PRIVATE until marked public in the sheet. (This used to
# guess public from talks/resume references, which could republish a link
# the sheet had made private if gen_redirect_pages.py ran before a sync.)
try:
    previous = yaml.safe_load(open("_data/shortlinks.yaml")) or []
except FileNotFoundError:
    previous = []
known = {e["keyword"]: bool(e.get("include")) for e in previous}

out = []
for l in sorted(links, key=lambda x: x["id"]):
    keyword = l["id"].split("/", 1)[1]
    kl = keyword.lower()
    reserved = kl in RESERVED
    include = known.get(keyword, False) and not reserved
    reason = ("reserved path" if reserved
              else "visibility from the sheet" if keyword in known
              else "new on bit.ly — private until marked public in the sheet")
    entry = {
        "keyword": keyword,
        "long_url": l["long_url"],
        "title": l.get("title", ""),
        "created": l["created_at"][:10],
        "include": include,
        "reason": reason,
    }
    if l.get("custom_bitlinks"):
        entry["custom_bitlinks"] = l["custom_bitlinks"]
    out.append(entry)

# Sheet-native entries (mith.ro/<alias> rows imported by format_sheets.py
# sync, no bitlink behind them) survive regeneration unless bit.ly now has
# the same keyword.
bitly_keywords = {e["keyword"] for e in out}
kept = [e for e in previous
        if e.get("source") == "sheet" and e["keyword"] not in bitly_keywords]
out.extend(kept)

with open("_data/shortlinks.yaml", "w") as f:
    yaml.safe_dump(out, f, sort_keys=False, allow_unicode=True)
new = [e["keyword"] for e in out if e["keyword"] not in known]
print(f"Wrote _data/shortlinks.yaml ({sum(e['include'] for e in out)} included / "
      f"{len(out)} total, {len(kept)} sheet-native kept)", file=sys.stderr)
if new:
    print(f"{len(new)} new link(s), private until reviewed in the sheet: "
          + ", ".join(new), file=sys.stderr)

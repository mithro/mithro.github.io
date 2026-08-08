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
import re
import sys
import urllib.request

import yaml

TOKEN = os.environ.get("BITLY_TOKEN")
if not TOKEN:
    sys.exit("Set BITLY_TOKEN in the environment")

GROUP = "Bb5ml3vJt6Z"
RESERVED = {"talks", "papers", "resume", "about", "assets", "docs", "scripts", "404"}

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

# Public-findability seed: keywords referenced in already-public sources.
# The talks sheet and resume reference these short links.
def load_public_keywords():
    kws = set()
    talks = yaml.safe_load(open("_data/talks.yaml"))
    for t in talks:
        for field in ("slides", "video"):
            v = t.get(field) or ""
            m = re.match(r"https?://(?:bit\.ly|j\.mp)/([\w\-]+)", v)
            if m:
                kws.add(m.group(1).lower())
    # short links mentioned in the resume doc
    kws |= {"mithro-resume", "goog-nist", "goog-analog", "iccad20-goog-miss",
            "iccad20-goog-miss-video"}
    return kws

public = load_public_keywords()

out = []
for l in sorted(links, key=lambda x: x["id"]):
    keyword = l["id"].split("/", 1)[1]
    kl = keyword.lower()
    reserved = kl in RESERVED
    include = (kl in public) and not reserved
    reason = ("reserved path" if reserved
              else "referenced in talks sheet or resume" if include
              else "not found in held public sources — review")
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

with open("_data/shortlinks.yaml", "w") as f:
    yaml.safe_dump(out, f, sort_keys=False, allow_unicode=True)
print(f"Wrote _data/shortlinks.yaml ({sum(e['include'] for e in out)} included / {len(out)} total)", file=sys.stderr)

#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Snapshot Tim's public GitHub profile into _data/github.yaml.

Uses the authenticated `gh` CLI (read-only public data): profile
counts, org memberships, and the top-starred personal repositories.
Re-run whenever the numbers feel stale.
"""

import json
import pathlib
import subprocess
import sys
from datetime import date

import yaml


def gh(path: str) -> dict | list:
    out = subprocess.run(["gh", "api", path], capture_output=True,
                         text=True, check=True).stdout
    return json.loads(out)


user = gh("users/mithro")
orgs = [o["login"] for o in gh("users/mithro/orgs")]
top = gh("search/repositories?q=user:mithro&sort=stars&order=desc&per_page=6")

data = {
    "snapshot_date": date.today().isoformat(),
    "profile": {
        "login": "mithro",
        "url": "https://github.com/mithro",
        "followers": user["followers"],
        "public_repos": user["public_repos"],
        "member_since": user["created_at"][:4],
    },
    "orgs": orgs,
    "top_repos": [
        {"name": r["name"], "url": r["html_url"],
         "stars": r["stargazers_count"], "description": r["description"]}
        for r in top["items"]
    ],
}

out = pathlib.Path("_data/github.yaml")
out.write_text("# Snapshot of github.com/mithro — regenerate with "
               "scripts/fetch_github.py\n"
               + yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
print(f"wrote {out}: {user['followers']} followers, "
      f"{user['public_repos']} repos, {len(orgs)} orgs", file=sys.stderr)

#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "ruamel.yaml"]
# ///
"""Record each design document's last-modified date from Google Drive.

Each document gets a `modified:` date read from Google Drive, each topic
group gets an `activity:` date (the *median* of its documents' dates),
which /design-docs/ uses to lead with the most recently edited
documents, and with the topics that are active rather than the ones
holding a single freshly touched old file. The entries are left where
they are in the file; the page does the ordering.

    uv run scripts/fetch_doc_dates.py

Reading `modifiedTime` needs a Drive-scoped token, so authenticate once
with:

    gcloud auth login --enable-gdrive-access

The dates can also be supplied from a JSON file of {alias: "YYYY-MM-DD"}
when no token is available, which is how the field was first populated:

    uv run scripts/fetch_doc_dates.py --dates dates.json

Comments and formatting in the YAML are preserved (ruamel round-trip),
so this is safe to re-run over the hand-written descriptions.
"""

import argparse
import json
import pathlib
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import requests
from ruamel.yaml import YAML

DATA = pathlib.Path("_data/design_docs.yaml")
DOC_RE = re.compile(r"/document/d/([\w-]+)")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def token() -> str:
    """User token with Drive scope (gcloud auth login --enable-gdrive-access)."""
    try:
        done = subprocess.run(["gcloud", "auth", "print-access-token"],
                              capture_output=True, text=True, check=True)
    except FileNotFoundError:
        sys.exit("gcloud not found: install it, or pass --dates <file.json>")
    except subprocess.CalledProcessError as e:
        sys.exit("could not get a Drive token "
                 f"({e.stderr.strip().splitlines()[-1] if e.stderr else e}).\n"
                 "Run: gcloud auth login --enable-gdrive-access\n"
                 "or pass pre-fetched dates with --dates <file.json>")
    return done.stdout.strip()


def drive_dates(docs: list, hdr: dict) -> dict[str, str]:
    def one(doc):
        m = DOC_RE.search(doc["url"])
        if not m:
            return doc["alias"], None
        r = requests.get(
            f"https://www.googleapis.com/drive/v3/files/{m.group(1)}",
            params={"fields": "modifiedTime"}, headers=hdr, timeout=60)
        if not r.ok:
            print(f"{doc['alias']}: HTTP {r.status_code} {r.text[:120]}",
                  file=sys.stderr)
            return doc["alias"], None
        return doc["alias"], r.json().get("modifiedTime", "")[:10] or None

    with ThreadPoolExecutor(5) as ex:
        return {a: d for a, d in ex.map(one, docs) if d}


def median_date(dates: list[str]) -> str:
    """Middle date; the lower of the two middles for an even count."""
    if not dates:
        raise ValueError("cannot take the median of no dates")
    ordered = sorted(dates)
    return ordered[(len(ordered) - 1) // 2]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dates", type=pathlib.Path,
                    help="JSON {alias: YYYY-MM-DD} to use instead of Drive")
    args = ap.parse_args()

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096  # never re-wrap the hand-written descriptions
    groups = yaml.load(DATA)
    docs = [d for g in groups for d in g["docs"]]

    if args.dates:
        dates = json.loads(args.dates.read_text())
        known = {d["alias"] for d in docs}
        if bad := sorted(a for a, v in dates.items()
                         if not isinstance(v, str)
                         or not DATE_RE.fullmatch(v)):
            print(f"not YYYY-MM-DD dates: {', '.join(bad)}", file=sys.stderr)
            return 1
        if extra := sorted(set(dates) - known):
            print(f"ignoring aliases not in {DATA}: {', '.join(extra)}",
                  file=sys.stderr)
    else:
        dates = drive_dates(docs, {"Authorization": f"Bearer {token()}"})

    missing = [d["alias"] for d in docs if d["alias"] not in dates]
    if missing:
        print(f"no date for: {', '.join(missing)}", file=sys.stderr)
        return 1

    for doc in docs:
        doc["modified"] = dates[doc["alias"]]
    for group in groups:
        if not group["docs"]:
            print(f"topic {group['id']!r} has no documents", file=sys.stderr)
            return 1
        group["activity"] = median_date([d["modified"] for d in group["docs"]])

    # Entries are left in place rather than re-sorted here: ruamel attaches
    # comments to sequence positions, so reordering would silently move any
    # comment written beside a topic or document. /design-docs/ sorts on
    # `modified` and `activity` itself, so file order does not affect it.
    yaml.dump(groups, DATA)
    ranked = sorted(groups, key=lambda g: g["activity"], reverse=True)
    print(f"{len(docs)} documents dated; topics rank "
          + " > ".join(f"{g['id']} ({g['activity']})" for g in ranked))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Compare two crawls of the same preview (result.json from
link-report.py --result-out).

The first crawl ran as soon as the preview served the PR's commit; the
second ran after the CDN's maximum cache time, when no cached copy of an
earlier deployment can still be served. If the first crawl saw the real
deployment, both must have crawled the same pages and found the same
internal failures.

External failures are compared for information only: other sites
rate-limit and recover between two crawls.

Writes a Markdown summary to --out. Exits 0 when the crawls agree, 1
when they do not.
"""

import argparse
import json
import sys


def load(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return (set(data["pages"]),
            {tuple(e) for e in data["internal"]},
            {(page, url) for page, url, _ in data["external"]})


def listing(title, items, limit=20):
    if not items:
        return []
    rows = ["\t".join(i) if isinstance(i, tuple) else i for i in sorted(items)]
    more = [f"... and {len(rows) - limit} more"] if len(rows) > limit else []
    return [f"**{title}** ({len(rows)})", "", "```", *rows[:limit], *more,
            "```", ""]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", help="result.json of the first crawl")
    parser.add_argument("second", help="result.json of the later crawl")
    parser.add_argument("--out", required=True, help="Markdown summary path")
    args = parser.parse_args()

    pages1, internal1, external1 = load(args.first)
    pages2, internal2, external2 = load(args.second)

    differences = [
        *listing("Pages only the first crawl saw", pages1 - pages2),
        *listing("Pages only the later crawl saw", pages2 - pages1),
        *listing("Internal failures only the first crawl saw",
                 internal1 - internal2),
        *listing("Internal failures only the later crawl saw",
                 internal2 - internal1),
    ]
    agree = not differences
    lines = []
    if agree:
        lines += ["## ✅ The later crawl agrees with the first", "",
                  f"Both crawled the same {len(pages2)} page(s) and found "
                  f"the same {len(internal2)} internal failure(s)."]
    else:
        lines += ["## ❌ The later crawl disagrees with the first", "",
                  "The first crawl may have read cached pages from an "
                  "earlier deployment, so its result should not be relied "
                  "on. Push again or re-run the check.", "", *differences]
    external_changed = external1 ^ external2
    if external_changed:
        lines += ["", f"{len(external_changed)} external failure(s) differ "
                      "between the crawls, which is expected of sites that "
                      "rate-limit and does not count."]

    text = "\n".join(lines) + "\n"
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(text)
    sys.stdout.write(text)
    return 0 if agree else 1


if __name__ == "__main__":
    sys.exit(main())

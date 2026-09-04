#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Invariants for the talks data files. Exit 1 with a list of problems.

    uv run scripts/validate_talks.py
"""
import pathlib
import re
import sys

import yaml

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
RESERVED = {"timeline", "topics", "highlights", "feed", "index"}


def main() -> None:
    talks = yaml.safe_load(pathlib.Path("_data/talks.yaml").read_text())
    cats_path = pathlib.Path("_data/talk_categories.yaml")
    cats = yaml.safe_load(cats_path.read_text()) if cats_path.exists() else []
    strips_path = pathlib.Path("_data/strips.yaml")
    strips = (yaml.safe_load(strips_path.read_text()) or {}) if strips_path.exists() else {}
    keys = {c["key"] for c in cats}
    problems: list[str] = []
    slugs: dict[str, int] = {}
    ranks: dict[int, str] = {}
    for i, t in enumerate(talks):
        who = f"talk {i} ({t['title'][:40]})"
        slug = t.get("slug")
        if not slug or not SLUG_RE.match(slug) or slug in RESERVED:
            problems.append(f"{who}: bad slug {slug!r}")
        elif slug in slugs:
            problems.append(f"{who}: slug {slug} duplicates talk {slugs[slug]}")
        slugs[slug] = i
        if keys:
            if not t.get("categories"):
                problems.append(f"{who}: no categories")
            for c in t.get("categories") or []:
                if c not in keys:
                    problems.append(f"{who}: unknown category {c!r}")
            if not t.get("talk_title"):
                problems.append(f"{who}: no talk_title")
        if "strips" in t and t["strips"] is not True:
            problems.append(f"{who}: strips must be true or absent")
        if t.get("strips") and strips and slug not in strips:
            problems.append(f"{who}: strips: true but no manifest entry (run fetch_slide_strips.py)")
        if (h := t.get("highlight")) is not None:
            if not isinstance(h, int) or not 1 <= h <= 10:
                problems.append(f"{who}: highlight must be 1..10")
            elif h in ranks:
                problems.append(f"{who}: highlight rank {h} also used by {ranks[h]}")
            ranks[h] = slug
            if not t.get("blurb"):
                problems.append(f"{who}: highlighted talks need a blurb")
    for slug, entry in strips.items():
        d = pathlib.Path("assets/strips") / slug
        n = entry["count"]
        if slug not in slugs:
            problems.append(f"strips manifest: {slug} is not a talk")
        elif not talks[slugs[slug]].get("strips"):
            problems.append(f"strips manifest: {slug} has strips: true unset")
        if len(list(d.glob("*-240.webp"))) != n or len(list(d.glob("*-480.webp"))) != n:
            problems.append(f"strips manifest: {slug} expects {n} slides, files differ")
    for p in problems:
        print(p, file=sys.stderr)
    print(f"{len(talks)} talks, {len(keys)} categories, {len(strips)} strips, "
          f"{len(ranks)} highlights: {'OK' if not problems else f'{len(problems)} problems'}",
          file=sys.stderr)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()

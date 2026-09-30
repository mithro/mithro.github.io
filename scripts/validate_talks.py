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
    # Every topic needs a page, and every page a topic: /talks/topics/<key>/
    # comes from a real file in _topics/ (scripts/gen_topic_pages.py), so a
    # category added without regenerating would 404 from the topics table.
    stubs = {p.stem for p in pathlib.Path("_topics").glob("*.md")}
    for key in sorted(keys - stubs):
        problems.append(f"topic {key}: no _topics/{key}.md (run gen_topic_pages.py)")
    for key in sorted(stubs - keys):
        problems.append(f"_topics/{key}.md: no such category (run gen_topic_pages.py)")
    for c in cats:
        if not SLUG_RE.match(c["key"]):
            problems.append(f"category {c['key']!r}: bad key")
        if not c.get("name") or not c.get("blurb"):
            problems.append(f"category {c['key']}: needs name and blurb")
    used: set[str] = set()
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
                used.add(c)
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
    venues_path = pathlib.Path("_data/talk_venues.yaml")
    venue_urls = yaml.safe_load(venues_path.read_text()) if venues_path.exists() else {}
    for v in sorted({t["venue"] for t in talks if t.get("venue")}):
        if not str(venue_urls.get(v, "")).startswith("https://"):
            problems.append(f"venue {v!r}: no https link in _data/talk_venues.yaml")
    for key in sorted(keys - used):
        problems.append(f"topic {key}: no talks, its page would be empty")
    for slug, entry in strips.items():
        d = pathlib.Path("assets/strips") / slug
        n = entry["count"]
        if slug not in slugs:
            problems.append(f"strips manifest: {slug} is not a talk")
        elif not talks[slugs[slug]].get("strips"):
            problems.append(f"strips manifest: {slug} has strips: true unset")
        link = entry.get("link")
        if link is not None and "/embed?start=false" not in link:
            # /edit etc. send visitors of published-only decks to a sign-in page.
            problems.append(f"strips manifest: {slug} link is not an /embed slideshow "
                            "(run fetch_slide_strips.py --relink)")
        if len(list(d.glob("*-240.webp"))) != n or len(list(d.glob("*-480.webp"))) != n:
            problems.append(f"strips manifest: {slug} expects {n} slides, files differ")
    for p in problems:
        print(p, file=sys.stderr)
    print(f"{len(talks)} talks, {len(keys)} categories ({len(stubs)} pages), "
          f"{len(strips)} strips, "
          f"{len(ranks)} highlights: {'OK' if not problems else f'{len(problems)} problems'}",
          file=sys.stderr)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()

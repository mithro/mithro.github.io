#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Rebuild the _topics/ collection: one front-matter-only stub per topic.

Jekyll cannot make pages out of a data file, so /talks/topics/<key>/ needs
a real file per category. Content is rendered by _layouts/topic.html from
site.data.talk_categories + site.data.talks, so the stubs only carry what
Jekyll needs for the URL and <head> — nothing that goes stale when a talk
changes category. Idempotent: _topics/ is rebuilt from scratch. Re-run
after editing _data/talk_categories.yaml.
"""
import pathlib
import re
import shutil

import yaml

PRES_RE = re.compile(r"presentation/d/(?!e/)([\w-]+)")
cats = yaml.safe_load(pathlib.Path("_data/talk_categories.yaml").read_text())
talks = yaml.safe_load(pathlib.Path("_data/talks.yaml").read_text())
thumbs = yaml.safe_load(pathlib.Path("_data/thumbs.yaml").read_text())["slides"]


def thumb(talk: dict) -> str | None:
    """The talk's own deck thumbnail, for og:image."""
    m = PRES_RE.search(talk.get("slides_embed") or "")
    if m and m.group(1) in thumbs:
        return f"/assets/thumbs/slides/{thumbs[m.group(1)]['name']}-640.webp"
    return None


out = pathlib.Path("_topics")
shutil.rmtree(out, ignore_errors=True)
out.mkdir()
for c in cats:
    members = [t for t in talks if c["key"] in (t.get("categories") or [])]
    # Social card: the topic's flagship talk (best highlight rank), ties
    # broken by the most recent — whichever first has a deck thumbnail.
    # sort() is stable, so the date pass below survives the rank pass.
    members.sort(key=lambda t: t.get("sort_date") or "", reverse=True)
    members.sort(key=lambda t: t.get("highlight") or 99)
    fm = {"slug": c["key"], "title": c["name"],
          "description": f"Talks by Tim 'mithro' Ansell on {c['name']} — "
                         f"{c['blurb']}"}
    for t in members:
        if img := thumb(t):
            fm["image"] = img
            break
    (out / f"{c['key']}.md").write_text(
        "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True,
                                 width=4096) + "---\n")
print(f"Wrote {len(cats)} topic stubs")

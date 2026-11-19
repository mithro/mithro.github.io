#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Rebuild the _talks/ collection: one front-matter-only stub per talk.

Content is rendered by _layouts/talk.html from site.data.talks, so the
stubs only carry what Jekyll needs for the URL and <head>. Idempotent:
_talks/ is rebuilt from scratch. Re-run after editing _data/talks.yaml.
"""
import pathlib
import re
import shutil

import yaml

PRES_RE = re.compile(r"presentation/d/(?!e/)([\w-]+)")
talks = yaml.safe_load(pathlib.Path("_data/talks.yaml").read_text())
thumbs = yaml.safe_load(pathlib.Path("_data/thumbs.yaml").read_text())["slides"]
out = pathlib.Path("_talks")
shutil.rmtree(out, ignore_errors=True)
out.mkdir()
for t in talks:
    fm = {"slug": t["slug"], "title": t.get("talk_title") or t["title"]}
    where = " · ".join(p for p in (t.get("event"), t.get("date")) if p)
    fm["description"] = ("Talk by Tim 'mithro' Ansell"
                         + (f" — {where}" if where else "") + ".")
    m = PRES_RE.search(t.get("slides_embed") or "")
    if m and m.group(1) in thumbs:
        fm["image"] = f"/assets/thumbs/slides/{thumbs[m.group(1)]['name']}-640.webp"
    (out / f"{t['slug']}.md").write_text(
        "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True,
                                 width=4096) + "---\n")
print(f"Wrote {len(talks)} talk stubs")

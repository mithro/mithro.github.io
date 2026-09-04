# Talks Section Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single `/talks/` page with a hub (stats + charts), timeline, topics, highlights and per-talk detail pages, each talk carrying a scrollable film strip of its slides.

**Architecture:** Jekyll (classic GitHub Pages builder, safe mode) renders everything from `_data/talks.yaml` plus two generated manifests (`_data/strips.yaml`, `_data/thumbs.yaml`) and a script-generated `_talks/` collection. Google Sheets stay Tim's review surface; `scripts/talks_sheet.py` moves Slug/Strips columns between sheet and YAML on request. `scripts/fetch_slide_strips.py` exports per-slide WebPs through the Slides API.

**Tech Stack:** Jekyll/Liquid, inlined CSS (`_includes/main.css`), Python 3.11 via `uv run` (PEP 723 scripts: requests, pyyaml, pillow), Google Sheets + Slides REST APIs with gcloud user credentials, Playwright MCP for visual checks, muffet for link checks.

Spec: `docs/superpowers/specs/2026-09-05-talks-overhaul-design.md`.

---

## Conventions for every task

- Build: `export PATH="$(ruby -e 'print Gem.user_dir')/bin:$PATH" && bundle exec jekyll build` — never bare `jekyll`. A local server on :8931 serves `_site` (`cd _site && python3 -m http.server 8931` if not running).
- Python: always `uv run scripts/<name>.py`; scripts carry PEP 723 headers. No shell loops — write a Python script instead.
- Scratch files go in the gitignored project `tmp/` (never `/tmp`), and are deleted when the task ends. Never `2>/dev/null`.
- Commit messages end with the session attribution trailer used by the earlier commits on this branch (`git log -3` shows it).
- `_data/shortlinks.yaml` is gitignored and must never be staged.
- Playwright screenshots must be saved under `<repo>/.playwright-mcp/`; bust the browser cache with `?v=N` query strings when re-checking a page.

## File structure

| Path | Responsibility |
|---|---|
| `scripts/slides_api.py` | Thin Slides API client (token, quota header, backoff, paced thumbnail render) shared by both thumbnail scripts |
| `scripts/fetch_talk_thumbs.py` | Existing first-slide/video thumbnails; now imports `slides_api` |
| `scripts/fetch_slide_strips.py` | Per-slide film-strip export → `assets/strips/<slug>/NNN-{240,480}.webp` + `_data/strips.yaml` |
| `scripts/talks_sheet.py` | Sheet↔YAML: `dump`, `slugs`, `strips`, `import`, `shortlinks` |
| `scripts/talks_yaml.py` | Textual, comment-preserving field updates for `_data/talks.yaml` (used by `talks_sheet.py import` and the one-off data scripts) |
| `scripts/validate_talks.py` | Data invariants for talks/categories/strips/highlights; run before every commit that touches `_data/` |
| `scripts/gen_talk_pages.py` | Rebuilds `_talks/<slug>.md` stubs (front matter only) |
| `_data/talk_categories.yaml` | Ordered taxonomy `{key, name, blurb}` |
| `_includes/talk_embeds.html` | The slides/video click-to-load tiles for one talk |
| `_includes/embed_script.html` | The tile→iframe swap script (once per page) |
| `_includes/talk_row.html` | One timeline/topics table row pair (title row + embeds row with strip) |
| `_includes/strip.html` | The film strip component |
| `_includes/talks_nav.html` | Sub-navigation shared by all talks pages |
| `_layouts/talk.html` | Detail page layout |
| `talks/index.html` | Hub |
| `talks/timeline/index.html`, `talks/topics/index.html`, `talks/highlights/index.html` | Listing pages |
| `talks/feed.xml` | Items now link to detail pages |
| `_layouts/default.html` | `og:image` honours `page.image` |
| `_config.yml` | `collections.talks`, layout default for the collection |

---

### Task 1: Bring the CI workflows onto this branch

**Files:** none edited by hand.

- [ ] **Step 1: Check whether PR #1 has merged**

Run: `gh pr view 1 --repo mithro/mithro.github.io --json state,mergedAt --jq '{state,mergedAt}'`

- [ ] **Step 2a (merged): rebase onto master**

```bash
git fetch origin master
git rebase origin/master
```
Expected: clean rebase (this branch only adds files and `slug:` lines).

- [ ] **Step 2b (not merged): merge the CI branch in**

```bash
git merge --no-edit ci-previews-linkcheck
```
Expected: `.github/workflows/{pr-preview,preview-verification,cleanup-previews}.yml` now exist on `talks-overhaul`. (When PR #1 later merges, the eventual PR for this branch simply shows fewer commits.)

- [ ] **Step 3: Confirm the workflows are present**

Run: `ls .github/workflows/`
Expected: the three workflow files.

---

### Task 2: Factor the talk row and embed tiles into includes (no visual change)

**Files:**
- Create: `_includes/talk_embeds.html`, `_includes/embed_script.html`, `_includes/talk_row.html`
- Modify: `talks/index.html`

- [ ] **Step 1: Snapshot the current rendered page**

```bash
export PATH="$(ruby -e 'print Gem.user_dir')/bin:$PATH" && bundle exec jekyll build
mkdir -p tmp && cp _site/talks/index.html tmp/talks-before.html
```

- [ ] **Step 2: Create `_includes/embed_script.html`**

Move the `<script>…</script>` block verbatim from the bottom of `talks/index.html` (the `document.querySelectorAll('.embed-lite')…` block) into this file, unchanged.

- [ ] **Step 3: Create `_includes/talk_embeds.html`**

This renders the two tiles for `include.talk`. It must reproduce the existing markup exactly; `include.eager` (boolean) replaces the old `tile_n <= 2` test.

```liquid
{%- comment -%}
Slides + video click-to-load tiles for one talk.
  include.talk   the talk entry
  include.eager  true for above-the-fold tiles (fetchpriority=high)
  include.no_slides_tile  true when a film strip replaces the slides tile
{%- endcomment -%}
{%- assign talk = include.talk -%}
{%- assign vid_id = "" -%}
{%- assign vid_start = "" -%}
{%- if talk.video != "" and talk.video -%}
  {%- if talk.video contains "youtu.be/" -%}
    {%- assign vid_id = talk.video | split: "youtu.be/" | last | split: "?" | first -%}
  {%- elsif talk.video contains "watch?v=" -%}
    {%- assign vid_id = talk.video | split: "v=" | last | split: "&" | first -%}
  {%- endif -%}
  {%- if vid_id != "" and talk.video contains "t=" -%}
    {%- assign vid_start = talk.video | split: "t=" | last | split: "&" | first | split: "s" | first -%}
  {%- endif -%}
{%- endif -%}
{%- assign short_disp = "" -%}
{%- assign slides_href = talk.slides -%}
{%- if talk.slides_short -%}
  {%- assign short_disp = talk.slides_short | replace: "https://", "" | replace: "http://", "" -%}
  {%- assign slides_href = talk.slides_short -%}
{%- elsif talk.slides contains "bit.ly/" or talk.slides contains "j.mp/" -%}
  {%- assign short_disp = talk.slides | replace: "https://", "" | replace: "http://", "" -%}
  {%- assign mith_alias = short_disp | split: "/" | last -%}
  {%- assign stub_path = "/" | append: mith_alias | append: "/" -%}
  {%- assign stub = site.pages | where: "permalink", stub_path | first -%}
  {%- if stub -%}
    {%- assign slides_href = stub_path | relative_url -%}
    {%- assign short_disp = "mith.ro/" | append: mith_alias -%}
  {%- endif -%}
{%- endif -%}
{%- assign pres_id = "" -%}
{%- if talk.slides_embed and talk.slides_embed contains "/presentation/d/" -%}
  {%- unless talk.slides_embed contains "/d/e/" -%}
    {%- assign pres_id = talk.slides_embed | split: "/d/" | last | split: "/embed" | first -%}
  {%- endunless -%}
{%- endif -%}
{%- if talk.slides_embed and include.no_slides_tile != true %}
{%- assign st = site.data.thumbs.slides[pres_id] %}
<div class="embed-col">
  <a class="emb-cap" href="{{ slides_href | escape }}"><span class="ci-icon" aria-hidden="true">{% include icons/googleslides.svg %}</span> {% if short_disp != "" %}{{ short_disp | escape }}{% else %}Slides{% endif %}</a>
  <button type="button" class="embed-lite lite-slides" data-src="{{ talk.slides_embed | escape }}" aria-label="Load slides: {{ talk.title | escape }}">
    {% if st %}<img src="{{ '/assets/thumbs/slides/' | relative_url }}{{ st.name }}-320.webp" srcset="{{ '/assets/thumbs/slides/' | relative_url }}{{ st.name }}-320.webp 320w, {{ '/assets/thumbs/slides/' | relative_url }}{{ st.name }}-640.webp {{ st.w }}w" sizes="(max-width: 640px) 92vw, 420px" width="{{ st.w }}" height="{{ st.h }}" alt="" {% if include.eager %}fetchpriority="high"{% else %}loading="lazy"{% endif %} decoding="async">{% endif %}
    <span class="lite-play" aria-hidden="true">{% include icons/slides-play.svg %}</span>
  </button>
</div>
{%- endif %}
{%- if vid_id != "" %}
{%- assign vt = site.data.thumbs.video[vid_id] %}
<div class="embed-col">
  <a class="emb-cap" href="{{ talk.video | escape }}"><span class="ci-icon" aria-hidden="true">{% include icons/youtube.svg %}</span> youtu.be/{{ vid_id }}</a>
  <button type="button" class="embed-lite lite-video" data-src="https://www.youtube-nocookie.com/embed/{{ vid_id }}?autoplay=1{% if vid_start != '' %}&amp;start={{ vid_start }}{% endif %}" aria-label="Play video: {{ talk.title | escape }}">
    {% if vt %}<img src="{{ '/assets/thumbs/video/' | relative_url }}{{ vid_id }}-320.webp" srcset="{{ '/assets/thumbs/video/' | relative_url }}{{ vid_id }}-320.webp 320w, {{ '/assets/thumbs/video/' | relative_url }}{{ vid_id }}-640.webp {{ vt.w }}w" sizes="(max-width: 640px) 92vw, 420px" width="{{ vt.w }}" height="{{ vt.h }}" alt="" {% if include.eager %}fetchpriority="high"{% else %}loading="lazy"{% endif %} decoding="async">{% endif %}
    <span class="lite-play" aria-hidden="true">{% include icons/youtube-play.svg %}</span>
  </button>
</div>
{%- endif %}
```

Note the old page computed `tile_n` per tile (slides tile and video tile counted separately, first two tiles eager). With `include.eager` per talk, the first talk's two tiles are eager and a second talk's slides tile is not — accept this one-pixel-irrelevant difference; the diff in Step 6 will show it and nothing else.

- [ ] **Step 4: Create `_includes/talk_row.html`**

The title row + embeds row, taking `include.talk` and `include.eager`. Reproduce the `<tr>…</tr>` and `<tr class="embrow">` markup from `talks/index.html` lines 55–104, but: the title cell keeps linking to the slides for now (Task 9 repoints it), and the embeds row becomes

```liquid
{%- assign has_video = false -%}
{%- if talk.video != "" and talk.video -%}{%- if talk.video contains "youtu.be/" or talk.video contains "watch?v=" -%}{%- assign has_video = true -%}{%- endif -%}{%- endif -%}
{%- if talk.slides_embed or has_video %}
<tr class="embrow">
  <td colspan="2">
    <div class="embeds">
      {% include talk_embeds.html talk=talk eager=include.eager %}
    </div>
  </td>
</tr>
{%- endif %}
```

The slides-href/short-display logic for the title link is duplicated between `talk_row.html` and `talk_embeds.html` for now; Task 9 removes it from the row when the title starts pointing at the detail page.

- [ ] **Step 5: Rewrite the loop in `talks/index.html`**

Replace lines 21–105 (the per-talk block) with:

```liquid
    {% for talk in talks_sorted %}{% if talk.year == y %}
    {%- assign eager = false -%}
    {%- if tile_n < 1 -%}{%- if talk.slides_embed or talk.video -%}{%- assign eager = true -%}{%- assign tile_n = tile_n | plus: 1 -%}{%- endif -%}{%- endif %}
    {% include talk_row.html talk=talk eager=eager %}
    {% endif %}{% endfor %}
```

and replace the trailing `<script>…</script>` with `{% include embed_script.html %}`.

- [ ] **Step 6: Build and diff**

```bash
bundle exec jekyll build
diff <(sed 's/[[:space:]]\+/ /g' tmp/talks-before.html) <(sed 's/[[:space:]]\+/ /g' _site/talks/index.html) | head -40
```
Expected: only the `fetchpriority="high"` ↔ `loading="lazy"` swap on the second talk's slides tile; no other lines differ. Fix anything else before continuing.

- [ ] **Step 7: Commit**

```bash
rm tmp/talks-before.html
git add _includes/talk_embeds.html _includes/embed_script.html _includes/talk_row.html talks/index.html
git commit -m "Factor the talk row and embed tiles into includes"
```

---

### Task 3: Data validator and talks.yaml field editor

**Files:**
- Create: `scripts/talks_yaml.py`, `scripts/validate_talks.py`

- [ ] **Step 1: Write `scripts/talks_yaml.py`**

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Comment-preserving field edits for _data/talks.yaml.

The file is hand-maintained with a commented header, so it is edited
textually per entry (the same chunking enrich_talk_embeds.py uses)
rather than round-tripped through a YAML dumper.
"""
import pathlib
import re

import yaml

TALKS = pathlib.Path("_data/talks.yaml")
# Field order for lines inserted by set_fields (after the title line).
ORDER = ["slug", "talk_title", "categories", "series", "venue", "strips",
         "highlight", "blurb"]


def load() -> list[dict]:
    return yaml.safe_load(TALKS.read_text())


def chunks() -> tuple[str, list[str]]:
    text = TALKS.read_text()
    head, sep, body = text.partition("- title:")
    return head, ["- title:" + c for c in (sep + body).split("- title:")[1:]]


def render(value) -> str:
    """One-line YAML scalar/flow-list, matching the file's hand style."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(render(v) for v in value) + "]"
    s = str(value)
    if re.search(r"[:#\[\]{}&*!|>'\"%@`,]|^\s|\s$", s) or s in ("", "yes", "no", "true", "false", "null"):
        return yaml.safe_dump(s, default_style='"', width=4096).strip()
    return s


def set_fields(updates: dict[int, dict[str, object]]) -> None:
    """updates: {talk index: {field: value or None to remove}}.

    New fields go directly after the '- title:' line in ORDER; existing
    fields are replaced in place.
    """
    head, parts = chunks()
    for i, fields in updates.items():
        lines = parts[i].splitlines(keepends=True)
        for field, value in fields.items():
            pat = f"  {field}:"
            existing = next((n for n, l in enumerate(lines) if l.startswith(pat)), None)
            if value is None:
                if existing is not None:
                    del lines[existing]
                continue
            new = f"  {field}: {render(value)}\n"
            if existing is not None:
                lines[existing] = new
            else:
                # Insert after the last already-present ORDER field that
                # precedes this one, else right after the title line.
                pos = 1
                for prior in ORDER[:ORDER.index(field)] if field in ORDER else []:
                    hit = next((n for n, l in enumerate(lines) if l.startswith(f"  {prior}:")), None)
                    if hit is not None:
                        pos = hit + 1
                lines.insert(pos, new)
        parts[i] = "".join(lines)
    TALKS.write_text(head + "".join(parts))
```

- [ ] **Step 2: Write `scripts/validate_talks.py`**

```python
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
    cats = yaml.safe_load(pathlib.Path("_data/talk_categories.yaml").read_text()) \
        if pathlib.Path("_data/talk_categories.yaml").exists() else []
    strips_path = pathlib.Path("_data/strips.yaml")
    strips = yaml.safe_load(strips_path.read_text()) if strips_path.exists() else {}
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
    for slug, entry in (strips or {}).items():
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
    print(f"{len(talks)} talks, {len(keys)} categories, {len(strips or {})} strips, "
          f"{len(ranks)} highlights: {'OK' if not problems else f'{len(problems)} problems'}",
          file=sys.stderr)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the validator on current data**

Run: `uv run scripts/validate_talks.py`
Expected: `121 talks, 0 categories, 0 strips, 0 highlights: OK` (no taxonomy yet, so category checks are skipped).

- [ ] **Step 4: Smoke-test the editor**

Write `tmp/edit_test.py`:
```python
import sys
sys.path.insert(0, "scripts")
import talks_yaml
before = talks_yaml.TALKS.read_text()
talks_yaml.set_fields({0: {"talk_title": "Build custom silicon with Google!", "categories": ["open-silicon"]}})
after = talks_yaml.TALKS.read_text()
assert '  slug: ispd23-goog\n  talk_title: Build custom silicon with Google!\n  categories: [open-silicon]\n' in after, after[:600]
talks_yaml.set_fields({0: {"talk_title": None, "categories": None}})
assert talks_yaml.TALKS.read_text() == before
print("ok")
```
Run: `uv run --with pyyaml tmp/edit_test.py` → `ok`; then `rm tmp/edit_test.py`. `git diff --stat` must be empty.

- [ ] **Step 5: Commit**

```bash
git add scripts/talks_yaml.py scripts/validate_talks.py
git commit -m "Add a talks.yaml field editor and data validator"
```

---

### Task 4: Taxonomy and per-talk metadata (categories, series, venue, talk_title)

**Files:**
- Create: `_data/talk_categories.yaml`
- Modify: `_data/talks.yaml` (via a one-off `tmp/assign_meta.py` using `scripts/talks_yaml.py`)

- [ ] **Step 1: Write `_data/talk_categories.yaml`**

```yaml
# Talk taxonomy for /talks/topics/ (order = display order).
# A talk may carry several keys (talks.yaml `categories:`).
- key: open-silicon
  name: Open source silicon
  blurb: SkyWater/GF open PDKs, the Open MPW shuttles, OpenROAD and Google's open silicon programme, and now wafer.space.
- key: fpga-tools
  name: Open FPGA toolchains
  blurb: SymbiFlow/F4PGA, Yosys, VPR, LiteX and the road to a "GCC of FPGAs".
- key: conference-video
  name: Conference capture & TimVideos
  blurb: HDMI2USB and the open hardware built to record and stream free-software conferences.
- key: tiny-boards
  name: Tomu & Fomu
  blurb: Microcontrollers and FPGAs that fit inside a USB port.
- key: python
  name: Python
  blurb: PyCon talks — Python for hardware, MicroPython on FPGAs, GStreamer pipelines and libraries.
- key: community
  name: Community & projects
  blurb: Mentoring, open source practice, and the long-running "Tim has too many projects" series.
- key: education
  name: Education & workforce
  blurb: Teaching chip design and growing the open silicon workforce.
- key: games
  name: Games & early talks
  blurb: The 2007–2009 game-development and Google-era talks.
```

- [ ] **Step 2: Write the assignment script `tmp/assign_meta.py`**

A dict keyed by **slug** with `talk_title`, `categories`, and optional `series`/`venue`, covering all 121 talks, applied through `talks_yaml.set_fields`. Rules:
- `talk_title`: the talk's own title, without event names, years, "Version", "(33C3 Version)", "[2022]", "-- Original?", "- Tim Ansell, Google" decorations. Repeat performances share the same `talk_title`.
- `series` (display name, only for talks given more than once): `Tim has too many projects`, `I'm Tomu`, `SymbiFlow – finally the GCC of FPGAs`, `Open down to the transistor`, `The missing pieces of open design enablement`, `Why is Google investing in fully open source IC design?`, `Using Python to build conference-recording hardware`, `Designing hardware with Python`, `Other things!`, `Fun with GStreamer pipelines`, `Fomu`, `Build custom silicon with Google`.
- `venue` (display name, only for recurring venues): `linux.conf.au`, `PyCon AU`, `Chaos Communication Congress/Camp`, `ORConf`, `RISC-V Summit`, `CHIPS Alliance`, `DARPA ERI`, `Latch-Up`, `Hackaday`, `Teardown`, `COSCUP`, `NSF`, `OpenPOWER`, `ESSCIRC/ESSDERC`, `RIOS`, `Hackware`.
- Every talk gets ≥1 category; the mapping is the executor's judgement from the titles/events — print the full table (slug, talk_title, categories, series, venue) to stdout for the PR description.

Sketch:
```python
import sys
sys.path.insert(0, "scripts")
import talks_yaml
META = {
    "ispd23-goog": dict(talk_title="Build custom silicon with Google!", categories=["open-silicon"], series="Build custom silicon with Google"),
    "35c3-symbiflow": dict(talk_title="SymbiFlow – finally the GCC of FPGAs!", categories=["fpga-tools"], series="SymbiFlow – finally the GCC of FPGAs", venue="Chaos Communication Congress/Camp"),
    # … all 121 slugs …
}
talks = talks_yaml.load()
missing = [t["slug"] for t in talks if t["slug"] not in META]
assert not missing, missing
talks_yaml.set_fields({i: META[t["slug"]] for i, t in enumerate(talks)})
for t in talks_yaml.load():
    print(t["slug"], "|", t["talk_title"], "|", ",".join(t["categories"]), "|", t.get("series", ""), "|", t.get("venue", ""))
```

- [ ] **Step 3: Apply and validate**

```bash
uv run --with pyyaml tmp/assign_meta.py > tmp/meta-table.txt
uv run scripts/validate_talks.py
```
Expected: `121 talks, 8 categories, 0 strips, 0 highlights: OK`. Fix unknown keys/missing entries until clean.

- [ ] **Step 4: Build still passes**

`bundle exec jekyll build` → no errors (new fields are unused so far).

- [ ] **Step 5: Commit** (keep `tmp/meta-table.txt` until the PR description is written, then delete)

```bash
rm tmp/assign_meta.py
git add _data/talk_categories.yaml _data/talks.yaml
git commit -m "Categorise every talk and add clean titles, series and venues"
```

---

### Task 5: Sheet workflow — `strips` and `import` subcommands

**Files:**
- Modify: `scripts/talks_sheet.py`

- [ ] **Step 1: Reserve the sub-page names in `validate_slugs`**

Add `RESERVED = {"timeline", "topics", "highlights", "feed", "index"}` and in `validate_slugs` reject `slug in RESERVED` with a clear message.

- [ ] **Step 2: Add a column helper**

```python
def ensure_column(s, tab, name: str, after: str, width: int = 90) -> tuple[int, list[dict]]:
    """Return (column index, batchUpdate requests) for header `name`,
    creating it immediately after column `after` if absent."""
    header = tab["header"]
    if name in header:
        return header.index(name), []
    col = header.index(after) + 1
    reqs = [{"insertDimension": {"range": {"sheetId": tab["sheet_id"], "dimension": "COLUMNS",
                                            "startIndex": col, "endIndex": col + 1},
                                  "inheritFromBefore": True}},
            {"updateDimensionProperties": {"range": {"sheetId": tab["sheet_id"], "dimension": "COLUMNS",
                                                      "startIndex": col, "endIndex": col + 1},
                                            "properties": {"pixelSize": width}, "fields": "pixelSize"}}]
    header.insert(col, name)
    for r in tab["rows"]:
        if len(r["cells"]) >= col:
            r["cells"].insert(col, "")
    return col, reqs
```
(`inheritFromBefore` copies the Slug column's formatting to the new header cell; values are written separately.)

- [ ] **Step 3: Add `do_strips`**

For each non-pivot tab: `col, reqs = ensure_column(s, tab, "Strips", "Slug")`; batchUpdate `reqs` (plus writing the header text `Strips` in that column via `values.update`). Then for every matched row whose Strips cell is empty and whose talk has a deck id present in `_data/thumbs.yaml` (`site` public thumbnail exists), write `yes` in bold red (same `repeatCell` pattern as `do_slugs`). Never touch a non-empty cell. Print per-tab counts.

- [ ] **Step 4: Add `do_import`**

```python
def do_import(s):
    talks = yaml.safe_load(TALKS_YAML.read_text())
    tabs = load_tabs(s, TALKS_SHEET) + load_tabs(s, ADDITIONS_SHEET)
    match_rows(talks, tabs)
    wanted: dict[int, dict] = {}       # talk index -> {slug, strips}
    origin: dict[int, str] = {}
    accepted: list[tuple[dict, int, int]] = []   # (tab, row, col) cells to turn black
    for tab in tabs:
        if "Slug" not in tab["header"]:
            continue
        c_slug = tab["header"].index("Slug")
        c_strips = tab["header"].index("Strips") if "Strips" in tab["header"] else None
        for r in tab["rows"]:
            if not r["talk"]:
                continue
            i = r["talk"][0]
            cells = r["cells"]
            slug = (cells[c_slug] if len(cells) > c_slug else "").strip()
            strips = (cells[c_strips] if c_strips is not None and len(cells) > c_strips else "").strip().lower() == "yes"
            if not slug:
                continue
            val = {"slug": slug, "strips": strips}
            if i in wanted and wanted[i] != val:
                sys.exit(f"conflict for {talks[i]['title'][:50]}: {origin[i]} vs {tab['title']} row {r['row']}")
            wanted[i], origin[i] = val, f"{tab['title']} row {r['row']}"
            accepted.append((tab, r["row"], c_slug))
            if c_strips is not None:
                accepted.append((tab, r["row"], c_strips))
    updates, changes = {}, []
    for i, val in wanted.items():
        t = talks[i]
        fields = {}
        if val["slug"] != t.get("slug"):
            fields["slug"] = val["slug"]
            changes.append(f"{t['slug']} -> {val['slug']}")
        if val["strips"] != bool(t.get("strips")):
            fields["strips"] = True if val["strips"] else None
            changes.append(f"{t['slug']}: strips {'on' if val['strips'] else 'off'}")
        if fields:
            updates[i] = fields
    # Validate the post-import state before writing anything.
    future = [dict(t, **{k: v for k, v in updates.get(i, {}).items() if v is not None}) for i, t in enumerate(talks)]
    for i in updates:
        if updates[i].get("strips", 1) is None:
            future[i].pop("strips", None)
    validate_slugs(future)
    if updates:
        import talks_yaml
        talks_yaml.set_fields(updates)
    # Accepted cells: black, not bold.
    by_sheet: dict[str, list[dict]] = {}
    for tab, row, col in accepted:
        by_sheet.setdefault(tab["spreadsheet"], []).append({"repeatCell": {
            "range": {"sheetId": tab["sheet_id"], "startRowIndex": row - 1, "endRowIndex": row,
                      "startColumnIndex": col, "endColumnIndex": col + 1},
            "cell": {"userEnteredFormat": {"textFormat": {"foregroundColor": BLACK, "bold": False}}},
            "fields": "userEnteredFormat.textFormat(foregroundColor,bold)"}})
    for spreadsheet, reqs in by_sheet.items():
        check(s.post(f"{SHEETS}/{spreadsheet}:batchUpdate", json={"requests": reqs}))
    print("\n".join(changes) or "no changes", file=sys.stderr)
    print(f"import: {len(changes)} changes, {len(accepted)} cells accepted", file=sys.stderr)
```
`validate_slugs` must be relaxed to accept the `future` list (it reads `slug` and `existing_alias` only — fine). Register both subcommands in `main()` and extend the module docstring.

- [ ] **Step 5: Run `strips`, inspect, run `import`, re-run both**

```bash
uv run scripts/talks_sheet.py strips     # creates the column, pre-fills red "yes"
uv run scripts/talks_sheet.py import     # expect: every deck talk gains strips: true; cells turn black
uv run scripts/validate_talks.py
uv run scripts/talks_sheet.py strips     # expect: 0 cells written
uv run scripts/talks_sheet.py import     # expect: no changes
git diff --stat                          # only _data/talks.yaml (strips: true lines)
```
Read back a handful of cells (a small `tmp/check_sheet.py` modelled on the earlier one) to confirm the column sits right after Slug and the colours are black after import. Delete the scratch script.

Note the semantics agreed with Tim: after this step the strips flags in YAML reflect the sheet; Tim edits the sheet later and `import` is re-run on request.

- [ ] **Step 6: Commit**

```bash
git add scripts/talks_sheet.py _data/talks.yaml
git commit -m "Add Strips column round-trip to talks_sheet.py"
```

---

### Task 6: Shared Slides API client

**Files:**
- Create: `scripts/slides_api.py`
- Modify: `scripts/fetch_talk_thumbs.py:107-168`

- [ ] **Step 1: Write `scripts/slides_api.py`**

```python
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
"""Minimal Google Slides API client shared by the thumbnail scripts.

Auth: gcloud user credentials with Drive scope
(`gcloud auth login --enable-gdrive-access`). The Slides API needs a
quota project with slides.googleapis.com enabled: mithro-drive-backup
by default, GOOGLE_QUOTA_PROJECT overrides.
"""
import os
import subprocess
import sys
import time

import requests

SLIDES = "https://slides.googleapis.com/v1/presentations"
RETRY = (429, 500, 502, 503, 504)
_TOKEN: str | None = None


def token() -> str:
    global _TOKEN
    if _TOKEN is None:
        _TOKEN = subprocess.run(["gcloud", "auth", "print-access-token"],
                                capture_output=True, text=True, check=True).stdout.strip()
    return _TOKEN


def headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {token()}",
            "X-Goog-User-Project": os.environ.get("GOOGLE_QUOTA_PROJECT", "mithro-drive-backup")}


def get(url: str, params: dict | None = None, tries: int = 5) -> requests.Response:
    """GET with exponential backoff on quota/server errors."""
    for attempt in range(tries):
        r = requests.get(url, params=params, headers=headers(), timeout=30)
        if r.status_code in RETRY and attempt < tries - 1:
            time.sleep(1.5 * 2 ** attempt)
            continue
        return r
    return r


def slide_ids(pid: str) -> list[str] | None:
    """Page objectIds in deck order, or None (with a message) on failure."""
    r = get(f"{SLIDES}/{pid}", params={"fields": "slides.objectId"})
    if not r.ok:
        print(f"slides {pid}: metadata HTTP {r.status_code}", file=sys.stderr)
        return None
    return [s["objectId"] for s in r.json().get("slides", [])]


def thumbnail_png(pid: str, page: str, size: str = "MEDIUM") -> bytes | None:
    """Render one page (MEDIUM = 800 px wide). Paced: the render quota is
    tight per minute, so callers should keep thread pools small."""
    time.sleep(1.5)
    r = get(f"{SLIDES}/{pid}/pages/{page}/thumbnail",
            params={"thumbnailProperties.thumbnailSize": size})
    if not r.ok:
        print(f"slides {pid}/{page}: thumbnail HTTP {r.status_code}", file=sys.stderr)
        return None
    img = requests.get(r.json()["contentUrl"], timeout=30)
    if not img.ok:
        print(f"slides {pid}/{page}: contentUrl HTTP {img.status_code}", file=sys.stderr)
        return None
    return img.content
```

- [ ] **Step 2: Make `fetch_talk_thumbs.py` use it**

Delete its `_TOKEN`/`token()` and the inline request code in `fetch_slides` (lines 107–168); replace the body after the `existing()` checks with:

```python
    from slides_api import slide_ids, thumbnail_png
    ids = slide_ids(pid)
    if not ids:
        return None
    png = thumbnail_png(pid, ids[0])
    if png is None:
        return None
    try:
        img = Image.open(io.BytesIO(png))
    except Exception as exc:
        print(f"slides {pid}: undecodable ({exc})", file=sys.stderr)
        return None
    return pid, {**emit(img, base), "name": name}
```
and in `main()` replace `token()  # resolve once before threading` with `import slides_api; slides_api.token()`.

- [ ] **Step 3: Prove the refactor is behaviour-preserving**

```bash
uv run scripts/fetch_talk_thumbs.py
git status --short   # expected: only scripts/ changed; no thumbnail or manifest churn
```
(Every rendition already exists, so the script only exercises the `existing()` path plus the import; to exercise the API path, temporarily `mv assets/thumbs/slides/ispd23-goog-320.webp tmp/` and `-640`, re-run, confirm they are regenerated at the same pixel size, then `git checkout assets/thumbs/slides/` to restore the committed bytes.)

- [ ] **Step 4: Commit**

```bash
git add scripts/slides_api.py scripts/fetch_talk_thumbs.py
git commit -m "Share the Slides API client between thumbnail scripts"
```

---

### Task 7: Film strip exporter

**Files:**
- Create: `scripts/fetch_slide_strips.py`
- Create (generated): `_data/strips.yaml`, `assets/strips/<slug>/NNN-{240,480}.webp`
- Modify: `.gitignore` (add `assets/strips/.*.partial/`)

- [ ] **Step 1: Write `scripts/fetch_slide_strips.py`**

```python
#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "pillow", "pyyaml"]
# ///
"""Export per-slide film-strip thumbnails for talks marked strips: true.

    uv run scripts/fetch_slide_strips.py            # everything that is missing/stale
    uv run scripts/fetch_slide_strips.py --only hw26 --force

For each deck: assets/strips/<slug>/NNN-240.webp and NNN-480.webp
(NNN = 1-based slide number, zero-padded) plus a manifest entry in
_data/strips.yaml. A deck is skipped when its manifest entry already
lists the same slide ids and the files are present. Decks whose talk
no longer has strips: true are removed (the sheet's Strips column is
the authority — see talks_sheet.py import).
"""
import argparse
import io
import pathlib
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor

import yaml
from PIL import Image

import slides_api

STRIPS_DIR = pathlib.Path("assets/strips")
MANIFEST = pathlib.Path("_data/strips.yaml")
TALKS = pathlib.Path("_data/talks.yaml")
PRES_RE = re.compile(r"presentation/d/(?!e/)([\w-]+)")
WIDTHS = (240, 480)
QUALITY = 70


def collect() -> list[tuple[str, str, str]]:
    """(slug, presentation id, deck link) for every strips: true talk."""
    out = []
    for t in yaml.safe_load(TALKS.read_text()):
        if not t.get("strips"):
            continue
        pid = next((m.group(1) for f in ("slides_edit", "slides", "slides_embed")
                    if (m := PRES_RE.search(t.get(f) or ""))), None)
        if not pid:
            print(f"{t['slug']}: strips: true but no usable deck id", file=sys.stderr)
            continue
        link = (t.get("slides_edit") or f"https://docs.google.com/presentation/d/{pid}/edit").split("#")[0]
        out.append((t["slug"], pid, link))
    return out


def have_files(slug: str, n: int) -> bool:
    d = STRIPS_DIR / slug
    return all((d / f"{i:03d}-{w}.webp").exists() for i in range(1, n + 1) for w in WIDTHS)


def export(item: tuple[str, str, str], old: dict | None, force: bool) -> tuple[str, dict] | None:
    slug, pid, link = item
    ids = slides_api.slide_ids(pid)
    if not ids:
        return None
    if old and not force and old.get("slides") == ids and have_files(slug, len(ids)):
        return slug, {**old, "link": link}
    tmp = STRIPS_DIR / f".{slug}.partial"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    size = None
    for n, oid in enumerate(ids, start=1):
        png = slides_api.thumbnail_png(pid, oid)
        if png is None:
            shutil.rmtree(tmp)
            print(f"{slug}: gave up at slide {n}/{len(ids)}", file=sys.stderr)
            return None
        img = Image.open(io.BytesIO(png)).convert("RGB")
        for w in WIDTHS:
            small = img.resize((w, round(img.height * w / img.width)), Image.LANCZOS)
            small.save(tmp / f"{n:03d}-{w}.webp", "WEBP", quality=QUALITY)
            if w == 480:
                size = (small.width, small.height)
    final = STRIPS_DIR / slug
    shutil.rmtree(final, ignore_errors=True)
    tmp.rename(final)
    print(f"{slug}: {len(ids)} slides", file=sys.stderr)
    return slug, {"deck": pid, "link": link, "count": len(ids),
                  "w": size[0], "h": size[1], "slides": ids}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append", default=[], help="slug (repeatable)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    STRIPS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = yaml.safe_load(MANIFEST.read_text()) if MANIFEST.exists() else {}
    manifest = manifest or {}
    wanted = collect()
    if args.only:
        wanted = [w for w in wanted if w[0] in args.only]
    slides_api.token()
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda w: export(w, manifest.get(w[0]), args.force), wanted))
    done = {slug: entry for slug, entry in (r for r in results if r)}
    # Prune decks that lost strips: true (only on a full run).
    if not args.only:
        keep = {w[0] for w in wanted}
        for slug in sorted(set(manifest) - keep):
            shutil.rmtree(STRIPS_DIR / slug, ignore_errors=True)
            print(f"{slug}: removed (strips no longer requested)", file=sys.stderr)
        manifest = {k: v for k, v in manifest.items() if k in keep}
    manifest.update(done)
    MANIFEST.write_text(
        "# Generated by scripts/fetch_slide_strips.py — do not hand-edit.\n"
        "# One entry per talk slug with strips: true; slides lists page\n"
        "# objectIds in deck order, w/h are the -480 rendition's size.\n"
        + yaml.safe_dump(manifest, sort_keys=True, allow_unicode=True))
    failed = [w[0] for w, r in zip(wanted, results) if r is None]
    print(f"strips: {len(done)}/{len(wanted)} decks ok"
          + (f"; FAILED: {', '.join(failed)}" if failed else ""), file=sys.stderr)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Export one deck and inspect**

```bash
echo 'assets/strips/.*.partial/' >> .gitignore
uv run scripts/fetch_slide_strips.py --only ispd23-goog
ls assets/strips/ispd23-goog | head; cat _data/strips.yaml
```
Expected: `NNN-240.webp`/`NNN-480.webp` pairs, count matching the deck, `w: 480, h: 270`. Open one `-480.webp` with the Read tool to eyeball it.

- [ ] **Step 3: Full export (long — run in the background and monitor)**

`uv run scripts/fetch_slide_strips.py` — roughly 2,600 renders at 1.5 s each over 4 threads ≈ 20 minutes. Expected summary: `strips: N/N decks ok`. Re-run once: every deck is skipped (idempotent) and the manifest is byte-identical.

- [ ] **Step 4: Validate and size-check**

```bash
uv run scripts/validate_talks.py      # strips manifest vs files vs flags
du -sh assets/strips
```
Record the size in the eventual PR description.

- [ ] **Step 5: Commit**

```bash
git add .gitignore scripts/fetch_slide_strips.py _data/strips.yaml assets/strips
git commit -m "Export per-slide film strips for every cleared deck"
```

---

### Task 8: Film strip component in the listings

**Files:**
- Create: `_includes/strip.html`
- Modify: `_includes/talk_row.html`, `_includes/main.css`

- [ ] **Step 1: Write `_includes/strip.html`**

```liquid
{%- comment -%}
Scrollable film strip of a deck's slides.
  include.slug   talk slug (manifest key)
  include.title  accessible label text
  include.size   "lg" on detail pages (taller frames)
{%- endcomment -%}
{%- assign st = site.data.strips[include.slug] -%}
{%- if st -%}
{%- assign base = '/assets/strips/' | append: include.slug | append: '/' | relative_url -%}
<div class="strip-wrap{% if include.size == 'lg' %} strip-lg{% endif %}">
  <div class="strip" role="group" aria-label="Slides: {{ include.title | escape }}" tabindex="0">
  {%- for oid in st.slides -%}
    {%- assign n = forloop.index -%}
    {%- assign nn = n | prepend: '000' | slice: -3, 3 -%}
    <a class="frame" href="{{ st.link | escape }}#slide=id.{{ oid }}" title="Slide {{ n }} of {{ st.count }}"><img src="{{ base }}{{ nn }}-240.webp" srcset="{{ base }}{{ nn }}-240.webp 240w, {{ base }}{{ nn }}-480.webp 480w" sizes="{% if include.size == 'lg' %}356px{% else %}240px{% endif %}" width="{{ st.w }}" height="{{ st.h }}" alt="Slide {{ n }} of {{ st.count }}" loading="lazy" decoding="async"></a>
  {%- endfor -%}
  </div>
</div>
{%- endif -%}
```

- [ ] **Step 2: Add the CSS to `_includes/main.css`** (after the `.embed-lite` rules)

```css
/* ---- Film strips ---------------------------------------------------- */
.strip-wrap { flex: 1 1 320px; min-width: 0; content-visibility: auto; contain-intrinsic-size: auto 150px; }
.strip { display: flex; gap: .35rem; overflow-x: auto; scroll-snap-type: x proximity; padding: .2rem 0 .5rem; scrollbar-width: thin; scrollbar-color: var(--gold-dim) transparent; }
.strip:focus-visible { outline: 2px solid var(--gold); outline-offset: 2px; }
.strip .frame { flex: 0 0 auto; scroll-snap-align: start; border: 1px solid var(--line); border-radius: 3px; overflow: hidden; background: var(--panel); line-height: 0; }
.strip .frame:hover, .strip .frame:focus-visible { border-color: var(--gold); }
.strip img { display: block; height: 135px; width: auto; }
.strip-lg .strip img { height: 200px; }
.strip-lg { contain-intrinsic-size: auto 220px; }
@media (prefers-reduced-motion: no-preference) {
  .strip .frame { transition: transform .12s ease, border-color .12s ease; }
  .strip .frame:hover { transform: translateY(-2px); }
}
@media (max-width: 640px) {
  .strip img { height: 110px; }
  .strip-lg .strip img { height: 150px; }
}
```

- [ ] **Step 3: Use the strip in `talk_row.html`**

Inside `<div class="embeds">`, before the embeds include:

```liquid
{%- assign has_strip = false -%}
{%- if site.data.strips[talk.slug] -%}{%- assign has_strip = true -%}{%- endif -%}
{% if has_strip %}{% include strip.html slug=talk.slug title=talk.talk_title %}{% endif %}
{% include talk_embeds.html talk=talk eager=include.eager no_slides_tile=has_strip %}
```
and change the row condition to `{%- if talk.slides_embed or has_video or has_strip %}` (compute `has_strip` above it).

- [ ] **Step 4: Build and check visually**

```bash
bundle exec jekyll build
```
Playwright: open `http://localhost:8931/talks/?v=1` at 1280 px and 390 px; screenshot to `.playwright-mcp/strip-desktop.png` / `strip-mobile.png`. Check: strips scroll horizontally (evaluate `document.querySelector('.strip').scrollWidth > document.querySelector('.strip').clientWidth`), video tile sits beside the strip on desktop and below on mobile, `document.documentElement.scrollWidth === window.innerWidth` (no page-level horizontal scroll), and a strip frame's href ends in `#slide=id.<objectId>`.

- [ ] **Step 5: Commit**

```bash
git add _includes/strip.html _includes/talk_row.html _includes/main.css
git commit -m "Show a scrollable film strip for every talk with exported slides"
```

---

### Task 9: Detail pages (collection, layout, generator, feed, OG image)

**Files:**
- Create: `scripts/gen_talk_pages.py`, `_layouts/talk.html`, `_includes/talks_nav.html`, `_talks/*.md` (generated)
- Modify: `_config.yml`, `_layouts/default.html:15`, `talks/feed.xml:17-20`, `_includes/talk_row.html`, `_includes/main.css`

- [ ] **Step 1: Configure the collection in `_config.yml`**

```yaml
collections:
  talks:
    output: true
    permalink: /talks/:slug/

defaults:
  - scope: { path: "", type: talks }
    values: { layout: talk }
```

- [ ] **Step 2: Write `scripts/gen_talk_pages.py`**

```python
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
    fm["description"] = f"Talk by Tim 'mithro' Ansell" + (f" — {where}" if where else "") + "."
    m = PRES_RE.search(t.get("slides_embed") or "")
    if m and m.group(1) in thumbs:
        fm["image"] = f"/assets/thumbs/slides/{thumbs[m.group(1)]['name']}-640.webp"
    (out / f"{t['slug']}.md").write_text(
        "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, width=4096) + "---\n")
print(f"Wrote {len(talks)} talk stubs")
```

- [ ] **Step 3: `og:image` honours `page.image`** in `_layouts/default.html:15`

```liquid
<meta property="og:image" content="{{ page.image | default: '/assets/photos/og-image.jpg' | absolute_url }}">
```

- [ ] **Step 4: Write `_includes/talks_nav.html`**

```liquid
<nav class="subnav" aria-label="Talks pages">
  <a href="{{ '/talks/' | relative_url }}"{% if page.url == '/talks/' %} class="on" aria-current="page"{% endif %}>Overview</a>
  <a href="{{ '/talks/highlights/' | relative_url }}"{% if page.url == '/talks/highlights/' %} class="on" aria-current="page"{% endif %}>Highlights</a>
  <a href="{{ '/talks/timeline/' | relative_url }}"{% if page.url == '/talks/timeline/' %} class="on" aria-current="page"{% endif %}>Timeline</a>
  <a href="{{ '/talks/topics/' | relative_url }}"{% if page.url == '/talks/topics/' %} class="on" aria-current="page"{% endif %}>Topics</a>
  <a href="{{ '/talks/feed.xml' | relative_url }}">RSS</a>
</nav>
```
CSS: `.subnav { display: flex; flex-wrap: wrap; gap: .3rem 1.3rem; font-size: .8rem; margin: -.4rem 0 1.2rem; } .subnav a { color: var(--muted); text-decoration: none; padding: .2rem 0; } .subnav a.on { color: var(--silk); border-bottom: 2px solid var(--gold); } .subnav a:hover, .subnav a:focus-visible { color: var(--gold); }`

- [ ] **Step 5: Write `_layouts/talk.html`**

```liquid
---
layout: default
---
{%- assign talk = site.data.talks | where: "slug", page.slug | first -%}
{%- assign sorted = site.data.talks | sort: "sort_date" -%}
{%- for t in sorted %}{% if t.slug == page.slug %}{% assign idx = forloop.index0 %}{% endif %}{% endfor -%}
{%- assign prev_i = idx | minus: 1 -%}{%- assign next_i = idx | plus: 1 -%}
{%- if idx > 0 %}{% assign prev = sorted[prev_i] %}{% endif -%}
{%- assign next = sorted[next_i] -%}
<section class="sect talk-page">
  {% include talks_nav.html %}
  <h2>{{ talk.talk_title | default: talk.title | escape }}</h2>
  <p class="talk-meta">
    {%- if talk.event and talk.event != "" -%}{%- if talk.event_url %}<a href="{{ talk.event_url | escape }}">{{ talk.event | escape }}</a>{% else %}{{ talk.event | escape }}{% endif -%}{%- endif -%}
    {%- if talk.date and talk.date != "" %} · <span class="nowrap">{{ talk.date | escape }}</span>{% endif -%}
    {%- if talk.series %} · part of <em>{{ talk.series | escape }}</em>{% endif %}
  </p>
  <p class="chips">{% for c in talk.categories %}{% assign cat = site.data.talk_categories | where: "key", c | first %}<a class="chip" href="{{ '/talks/topics/' | relative_url }}#{{ c }}">{{ cat.name | escape }}</a>{% endfor %}</p>
  {% if talk.blurb %}<p class="prose">{{ talk.blurb | escape }}</p>{% endif %}
  {% include strip.html slug=talk.slug title=talk.talk_title size="lg" %}
  <div class="embeds">
    {% include talk_embeds.html talk=talk eager=true %}
  </div>
  {%- assign alias = talk.slides_short | default: "" -%}
  {%- assign stub_path = "/" | append: talk.slug | append: "/" -%}
  {%- assign stub = site.pages | where: "permalink", stub_path | first -%}
  {%- if stub %}<p class="talk-meta">Short link: <a href="{{ stub_path | relative_url }}">mith.ro/{{ talk.slug }}</a></p>{% endif %}
  <p class="talk-meta prevnext">
    {% if prev %}<a href="{{ '/talks/' | append: prev.slug | append: '/' | relative_url }}">← {{ prev.talk_title | default: prev.title | escape }}</a>{% endif %}
    {% if next %}<a href="{{ '/talks/' | append: next.slug | append: '/' | relative_url }}">{{ next.talk_title | default: next.title | escape }} →</a>{% endif %}
  </p>
</section>
{% include embed_script.html %}
```
CSS: `.talk-page h2 { margin-bottom: .3rem; } .talk-meta { color: var(--muted); font-size: .82rem; margin: .2rem 0 .8rem; } .talk-meta a { color: var(--silk); } .chips { display: flex; flex-wrap: wrap; gap: .4rem; margin: 0 0 1rem; } .chip { font-size: .72rem; letter-spacing: .06em; text-transform: uppercase; color: var(--gold); border: 1px solid var(--gold-dim); border-radius: 999px; padding: .15rem .6rem; text-decoration: none; } .chip:hover, .chip:focus-visible { border-color: var(--gold); } .prevnext { display: flex; justify-content: space-between; gap: 1rem; margin-top: 1.5rem; }`

- [ ] **Step 6: Point titles and feed items at the detail page**

In `_includes/talk_row.html` the title cell becomes
`<a href="{{ '/talks/' | append: talk.slug | append: '/' | relative_url }}">{{ talk.talk_title | default: talk.title | escape }}</a>` (drop the slides-href/short-display block there; the `▶ video` fallback link for non-YouTube videos stays). In `talks/feed.xml` replace the `talk_link` logic with `<link>{{ '/talks/' | append: talk.slug | append: '/' | absolute_url }}</link>` and keep the recording URL in the description.

- [ ] **Step 7: Generate, build, verify**

```bash
uv run scripts/gen_talk_pages.py            # Wrote 121 talk stubs
bundle exec jekyll build
ls -d _site/talks/*/ | wc -l                # 121 + timeline/topics/highlights dirs once they exist (Task 10)
grep -c 'og:image" content="https://mith.ro/assets/thumbs/slides/' _site/talks/ispd23-goog/index.html   # 1
grep -o '<link>[^<]*</link>' _site/talks/feed.xml | head -3          # https://mith.ro/talks/<slug>/
```
Playwright: `/talks/35c3-symbiflow/?v=1` (strip + video) and `/talks/goog08-gaming-freedom/?v=1` (video only, no deck) at 1280/390; prev/next links resolve (click one).

- [ ] **Step 8: Commit**

```bash
git add _config.yml scripts/gen_talk_pages.py _layouts/talk.html _layouts/default.html _includes/talks_nav.html _includes/talk_row.html _includes/main.css talks/feed.xml _talks
git commit -m "Give every talk a detail page at /talks/<slug>/"
```

---

### Task 10: Timeline, topics and highlights pages

**Files:**
- Create: `talks/timeline/index.html`, `talks/topics/index.html`, `talks/highlights/index.html`
- Modify: `_data/talks.yaml` (highlight ranks + blurbs), `_includes/main.css`

- [ ] **Step 1: Move the timeline**

`git mv talks/index.html talks/timeline/index.html`; set front matter `title: Talks timeline`, `description: "Every talk by Tim 'mithro' Ansell in date order, 2007–present."`; insert `{% include talks_nav.html %}` right after the `<h2>`. (The hub is written in Task 11; until then `/talks/` 404s locally — fine.)

- [ ] **Step 2: Write `talks/topics/index.html`**

```liquid
---
layout: default
title: Talks by topic
description: "Tim 'mithro' Ansell's talks grouped by topic: open silicon, FPGA toolchains, conference video, Tomu/Fomu, Python and more."
---
<section class="sect">
  <h2><span aria-hidden="true">🗂️</span> Talks by topic</h2>
  {% include talks_nav.html %}
  {% assign talks_sorted = site.data.talks | sort: "sort_date" | reverse %}
  {% assign tile_n = 0 %}
  {% for cat in site.data.talk_categories %}
  {% assign in_cat = talks_sorted | where_exp: "t", "t.categories contains cat.key" %}
  {% if in_cat.size > 0 %}
  <h3 class="year-head" id="{{ cat.key }}">{{ cat.name }} <span class="count">{{ in_cat.size }}</span></h3>
  <p class="prose cat-blurb">{{ cat.blurb }}</p>
  <div class="table-scroll" tabindex="0" role="region" aria-label="{{ cat.name }} talks">
  <table class="talks-table">
    <caption class="visually-hidden">{{ cat.name }} talks</caption>
    <thead><tr><th scope="col">Talk</th><th scope="col">Event · Date</th></tr></thead>
    <tbody>
    {% for talk in in_cat %}
    {%- assign eager = false -%}
    {%- if tile_n < 1 -%}{%- if talk.slides_embed or talk.video -%}{%- assign eager = true -%}{%- assign tile_n = tile_n | plus: 1 -%}{%- endif -%}{%- endif %}
    {% include talk_row.html talk=talk eager=eager %}
    {% endfor %}
    </tbody>
  </table>
  </div>
  {% endif %}
  {% endfor %}
</section>
{% include embed_script.html %}
```
CSS: `.year-head .count { color: var(--muted); font-weight: 400; font-size: .8rem; margin-left: .4rem; } .cat-blurb { margin: 0 0 .6rem; }`

- [ ] **Step 3: Propose the highlights**

Add `highlight:` (rank) and `blurb:` to these talks via a `tmp/set_highlights.py` using `talks_yaml.set_fields` — the proposal, with the reasoning to paste into the PR description:

| rank | slug | why |
|---|---|---|
| 1 | `35c3-symbiflow` | CCC main-stage talk that put "the GCC of FPGAs" on the map; the most-watched recording |
| 2 | `du20-sky130` | The FOSSi Dial-Up where the SkyWater open PDK was introduced to the community |
| 3 | `oto21-sky130` | OpenTapeOut keynote: open silicon down to the transistor |
| 4 | `35c3-snakes-rabbits` | With bunnie — how CCC shaped an open hardware success |
| 5 | `33c3-hdmi` | Dissecting HDMI: the definitive TimVideos/HDMI2USB talk |
| 6 | `fomu-camp19` | Fomu at CCCamp with xobs — an FPGA inside your USB port |
| 7 | `supercon18-tomu` | Hackaday Supercon: Tomu |
| 8 | `rvs20-sky130` | RISC-V Summit: manufacturable open 130 nm PDK |
| 9 | `ispd23-goog` | "Build custom silicon with Google" — the mature programme |
| 10 | `hw26` | wafer.space: silicon now $4 — the current chapter |

Each blurb is one sentence in Tim's voice, factual, no superlatives that can't be backed. `uv run scripts/validate_talks.py` must report `10 highlights: OK`.

- [ ] **Step 4: Write `talks/highlights/index.html`**

```liquid
---
layout: default
title: Highlighted talks
description: "A short list of Tim 'mithro' Ansell's most significant talks — start here."
---
<section class="sect">
  <h2><span aria-hidden="true">⭐</span> Highlighted talks</h2>
  {% include talks_nav.html %}
  {% assign picks = site.data.talks | where_exp: "t", "t.highlight" | sort: "highlight" | slice: 0, 10 %}
  {% for talk in picks %}
  <article class="hl">
    <h3><a href="{{ '/talks/' | append: talk.slug | append: '/' | relative_url }}">{{ talk.talk_title | default: talk.title | escape }}</a></h3>
    <p class="talk-meta">{% if talk.event_url %}<a href="{{ talk.event_url | escape }}">{{ talk.event | escape }}</a>{% else %}{{ talk.event | escape }}{% endif %}{% if talk.date and talk.date != "" %} · <span class="nowrap">{{ talk.date | escape }}</span>{% endif %}</p>
    <p class="prose">{{ talk.blurb | escape }}</p>
    {% include strip.html slug=talk.slug title=talk.talk_title %}
    <div class="embeds">{% include talk_embeds.html talk=talk eager=forloop.first no_slides_tile=true %}</div>
  </article>
  {% endfor %}
</section>
{% include embed_script.html %}
```
CSS: `.hl { border-top: 1px solid var(--line); padding: 1.2rem 0; } .hl h3 { margin: 0 0 .2rem; font-family: var(--mono); font-size: 1rem; } .hl h3 a { color: var(--silk); text-decoration: none; border-bottom: 1px solid var(--gold-dim); } .hl h3 a:hover { color: var(--gold); }`

Note `no_slides_tile=true` here: highlighted decks all have strips, so the strip carries the slides and only the video tile is rendered. If a highlighted talk ever lacks a strip, pass `no_slides_tile=false`.

- [ ] **Step 5: Build and verify**

```bash
uv run scripts/validate_talks.py && bundle exec jekyll build
ls _site/talks/timeline/index.html _site/talks/topics/index.html _site/talks/highlights/index.html
grep -c '<article class="hl">' _site/talks/highlights/index.html     # 10
grep -o 'id="[a-z-]*"' _site/talks/topics/index.html                  # the 8 category ids
```
Playwright at 1280/390 for all three pages (`?v=2`): sub-nav highlights the current page; category anchors from a detail page's chips land on the right heading.

- [ ] **Step 6: Commit** (two commits: pages, then highlight data)

```bash
git add talks/timeline/index.html talks/topics/index.html _includes/main.css
git commit -m "Split the talks listing into timeline and topics pages"
git add talks/highlights/index.html _data/talks.yaml
git commit -m "Add the highlighted talks page with a proposed top ten"
rm tmp/set_highlights.py
```

---

### Task 11: The hub with statistics

**Files:**
- Create: `talks/index.html`
- Modify: `_includes/main.css`, `index.html` (home "Recent talks" titles → detail pages)

- [ ] **Step 1: Write `talks/index.html`**

```liquid
---
layout: default
title: Talks
description: "Tim 'mithro' Ansell has given {{ site.data.talks | size }} talks since 2007 — highlights, timeline, topics and the numbers."
---
{%- assign talks = site.data.talks -%}
{%- assign dated = talks | where_exp: "t", "t.year != 0" -%}
{%- assign by_year = dated | group_by: "year" | sort: "name" -%}
{%- assign busiest = by_year | sort: "size" | last -%}
{%- assign first_year = by_year | first -%}
{%- assign last_year = by_year | last -%}
{%- assign recorded = talks | where_exp: "t", "t.video and t.video != ''" -%}
{%- assign decks = talks | where_exp: "t", "t.slides_embed" -%}
{%- assign events = talks | where_exp: "t", "t.event and t.event != ''" | map: "event" | uniq -%}
{%- assign total_slides = 0 -%}
{%- for s in site.data.strips %}{% assign total_slides = total_slides | plus: s[1].count %}{% endfor -%}
{%- assign venues = talks | where_exp: "t", "t.venue" | group_by: "venue" | sort: "size" | reverse -%}
{%- assign series = talks | where_exp: "t", "t.series" | group_by: "series" | sort: "size" | reverse -%}
{%- assign picks = talks | where_exp: "t", "t.highlight" | sort: "highlight" | slice: 0, 3 -%}
<section class="sect">
  <h2><span aria-hidden="true">🎤</span> Talks &amp; presentations</h2>
  {% include talks_nav.html %}
  <div class="cards">
    <a class="card" href="{{ '/talks/highlights/' | relative_url }}"><strong>Highlights</strong><span>Start with the ten that matter most.</span></a>
    <a class="card" href="{{ '/talks/timeline/' | relative_url }}"><strong>Timeline</strong><span>All {{ talks | size }} talks, newest first.</span></a>
    <a class="card" href="{{ '/talks/topics/' | relative_url }}"><strong>Topics</strong><span>Grouped by subject across {{ site.data.talk_categories | size }} themes.</span></a>
  </div>
</section>

<dl class="spec">
  <div><dt>Talks</dt><dd>{{ talks | size }}</dd></div>
  <div><dt>Years speaking</dt><dd>{{ last_year.name | minus: first_year.name | plus: 1 }}</dd></div>
  <div><dt>Recordings</dt><dd>{{ recorded | size }}</dd></div>
  <div><dt>Slide decks</dt><dd>{{ decks | size }}</dd></div>
  <div><dt>Slides shown</dt><dd>{{ total_slides }}</dd></div>
  <div><dt>Events</dt><dd>{{ events | size }}</dd></div>
</dl>

<section class="sect">
  <h3 class="year-head">Talks per year <span class="count">{{ first_year.name }}–{{ last_year.name }} · busiest {{ busiest.name }} with {{ busiest.size }}</span></h3>
  <div class="bars" aria-hidden="true">
  {%- for year in (first_year.name..last_year.name) -%}
    {%- assign g = by_year | where: "name", year | first -%}
    {%- assign n = 0 -%}{%- if g %}{% assign n = g.size %}{% endif -%}
    {%- assign pct = n | times: 100 | divided_by: busiest.size -%}
    <div class="bar-col" style="--h: {{ pct }}"><span class="n">{% if n > 0 %}{{ n }}{% endif %}</span><span class="b"></span><span class="y">{{ year }}</span></div>
  {%- endfor -%}
  </div>
  <table class="visually-hidden"><caption>Talks per year</caption><thead><tr><th scope="col">Year</th><th scope="col">Talks</th></tr></thead><tbody>
  {%- for g in by_year %}<tr><td>{{ g.name }}</td><td>{{ g.size }}</td></tr>{% endfor -%}
  </tbody></table>
</section>

<section class="sect stats-grid">
  <div>
    <h3 class="year-head">By topic</h3>
    <ul class="stat-list">
    {%- for cat in site.data.talk_categories -%}
      {%- assign n = talks | where_exp: "t", "t.categories contains cat.key" | size -%}
      <li><a href="{{ '/talks/topics/' | relative_url }}#{{ cat.key }}">{{ cat.name }}</a><span class="num">{{ n }}</span></li>
    {%- endfor -%}
    </ul>
  </div>
  <div>
    <h3 class="year-head">Favourite venues</h3>
    <ul class="stat-list">
    {%- for v in venues limit: 6 -%}<li>{{ v.name }}<span class="num">{{ v.size }}</span></li>{%- endfor -%}
    </ul>
  </div>
  <div>
    <h3 class="year-head">Most-repeated talks</h3>
    <ul class="stat-list">
    {%- for sr in series limit: 5 -%}
      {%- assign yrs = sr.items | where_exp: "t", "t.year != 0" | map: "year" | sort -%}
      <li>{{ sr.name }}<span class="num">{{ sr.size }}× · {{ yrs | first }}–{{ yrs | last }}</span></li>
    {%- endfor -%}
    </ul>
  </div>
</section>

<section class="sect">
  <h3 class="year-head">Start here</h3>
  {% for talk in picks %}
  <article class="hl">
    <h3><a href="{{ '/talks/' | append: talk.slug | append: '/' | relative_url }}">{{ talk.talk_title | default: talk.title | escape }}</a></h3>
    <p class="talk-meta">{{ talk.event | escape }}{% if talk.date and talk.date != "" %} · {{ talk.date | escape }}{% endif %}</p>
    {% include strip.html slug=talk.slug title=talk.talk_title %}
  </article>
  {% endfor %}
  <p class="more"><a href="{{ '/talks/highlights/' | relative_url }}">All highlights →</a></p>
</section>
```

- [ ] **Step 2: CSS**

```css
/* ---- Talks hub ------------------------------------------------------ */
.cards { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; margin: .2rem 0 1.6rem; }
.card { display: block; border: 1px solid var(--line); border-radius: 6px; padding: 1rem 1.1rem; background: var(--panel); color: var(--silk); text-decoration: none; }
.card strong { display: block; color: var(--gold); margin-bottom: .25rem; }
.card span { font-family: var(--sans); font-size: .9rem; color: var(--muted); }
.card:hover, .card:focus-visible { border-color: var(--gold); }
.bars { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr); gap: 4px; align-items: end; margin: .6rem 0 1.6rem; }
.bar-col { display: flex; flex-direction: column; align-items: center; min-width: 0; }
.bar-col .n { font-size: .65rem; color: var(--muted); line-height: 1; height: .8rem; }
.bar-col .b { width: 100%; height: calc(130px * var(--h) / 100); min-height: 2px; background: var(--gold); border-radius: 2px 2px 0 0; }
.bar-col .y { font-size: .58rem; color: var(--muted); margin-top: .35rem; writing-mode: vertical-rl; transform: rotate(180deg); }
.stats-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0 2rem; }
.stat-list { list-style: none; margin: 0; padding: 0; font-size: .85rem; }
.stat-list li { display: flex; justify-content: space-between; gap: 1rem; border-top: 1px solid var(--line); padding: .35rem 0; }
.stat-list .num { color: var(--gold); font-variant-numeric: tabular-nums; white-space: nowrap; }
.stat-list a { color: var(--silk); text-decoration: none; border-bottom: 1px solid var(--gold-dim); }
@media (max-width: 760px) {
  .cards, .stats-grid { grid-template-columns: 1fr; }
  .bar-col .b { height: calc(90px * var(--h) / 100); }
}
```

- [ ] **Step 3: Home page "Recent talks" titles** link to the detail page (`index.html`, the recent-talks table): same `href` expression as in `talk_row.html`.

- [ ] **Step 4: Build and check the numbers by hand**

```bash
bundle exec jekyll build
grep -o '<dd>[0-9]*</dd>' _site/talks/index.html
```
Cross-check with a scratch Python script over the YAML (talk count, recorded count where `video` non-empty, decks with `slides_embed`, sum of strip counts, distinct non-empty events, min/max year). All six must match. Playwright at 1280/390 (`?v=3`): bars render with year labels, no horizontal page scroll, cards stack on mobile.

- [ ] **Step 5: Commit**

```bash
git add talks/index.html _includes/main.css index.html
git commit -m "Turn /talks/ into a hub with statistics and a talks-per-year chart"
```

---

### Task 12: Verification sweep

- [ ] **Step 1: Strict build and page inventory**

```bash
bundle exec jekyll build --strict_front_matter
python3 - <<'EOF'
import pathlib, yaml
slugs = {t["slug"] for t in yaml.safe_load(open("_data/talks.yaml"))}
missing = [s for s in slugs if not pathlib.Path(f"_site/talks/{s}/index.html").exists()]
print("missing detail pages:", missing)
EOF
```
Expected: `missing detail pages: []`. (Put the snippet in `tmp/check_pages.py` and run with `uv run --with pyyaml` if the heredoc is blocked.)

- [ ] **Step 2: Local link check**

Serve `_site` on :8931 and run muffet with the same flags and excludes as `.github/workflows/preview-verification.yml` against `http://localhost:8931/`. Expected: exit 0. Any broken internal link is a bug in this work — fix it.

- [ ] **Step 3: Lighthouse**

Run mobile Lighthouse (`npx lighthouse http://localhost:8931/talks/ --preset=... --only-categories=performance,accessibility,best-practices,seo --form-factor=mobile --quiet --output=json --output-path=tmp/lh-hub.json`, likewise for `/talks/timeline/`) and read the four scores. Target 100/100/100/100; if performance dips, the usual culprits are eager images above the fold (only the first talk's tiles may be eager) and missing `width`/`height`.

- [ ] **Step 4: Screenshots for the PR**

Playwright screenshots (desktop + mobile) of hub, highlights, timeline, topics, one detail page → `.playwright-mcp/`; attach the useful ones to the PR description via SendUserFile or by referencing them in the summary.

- [ ] **Step 5: Push and open the PR**

```bash
git push -u git@github.com:mithro/mithro.github.io.git talks-overhaul
gh pr create --head talks-overhaul --title "Talks section: hub, timeline, topics, highlights, detail pages and film strips" --body-file tmp/pr-body.md
```
`tmp/pr-body.md` includes: the category/series/venue table (Task 4), the highlights proposal table (Task 10), the strips footprint (Task 7), Lighthouse scores, and the standing note that red slugs in the sheet are still awaiting Tim's review. Watch the preview + verification checks with the Monitor tool; the preview link goes to Tim.

---

### Task 13: Short links for talks that have none (independent, last)

**Files:**
- Modify: `scripts/talks_sheet.py` (add `shortlinks`), `scripts/format_sheets.py` (`do_sync`), `scripts/fetch_bitly.py`

- [ ] **Step 1: `talks_sheet.py shortlinks`**

For every talk where `existing_alias(t)` is None: target = `slides_edit` or `slides` (Google URL) else `video`; skip (and report) talks with neither. Read the shortlinks sheet (`SHORTLINKS_SHEET`, header row A1:G1 gives column order — read it rather than assuming) and skip aliases already present. Append rows with: alias `mith.ro/<slug>`, Visibility `private`, target URL, title `talk_title`, created = today (ISO 8601), Source `talk`. Print the count and the slugs appended.

- [ ] **Step 2: `format_sheets.py do_sync` imports sheet-native rows**

After computing `public_aliases`, for every sheet row whose alias (column A, minus the `bit.ly/`/`mith.ro/` prefix) matches no YAML `keyword`/custom alias, append `{keyword, long_url (target column), title, created, include: visibility == "public", reason: "sheet-native <date>", source: "sheet"}`. Keep the existing ordering logic; add `source` to the ordered keys.

- [ ] **Step 3: `fetch_bitly.py` preserves `source: sheet` entries**

Before writing `_data/shortlinks.yaml`, load the existing file (if any) and carry over every entry with `source == "sheet"`, unless bit.ly now has the same keyword.

- [ ] **Step 4: Run end to end**

```bash
uv run scripts/talks_sheet.py shortlinks     # appends N rows (private)
uv run scripts/format_sheets.py sync         # N new sheet-native entries, include: false
uv run scripts/gen_redirect_pages.py         # count unchanged (all private)
git status --short                           # _data/shortlinks.yaml must NOT appear (gitignored)
```
Once Tim flips rows to public, `sync` + `gen_redirect_pages.py` publish them and the detail page's "Short link" line appears automatically.

- [ ] **Step 5: Commit**

```bash
git add scripts/talks_sheet.py scripts/format_sheets.py scripts/fetch_bitly.py
git commit -m "Mint mith.ro short links for talks that have none"
```

---

### Task 14: Docs and memory

- [ ] **Step 1:** If `README.md` lists the scripts, add `slides_api.py`, `fetch_slide_strips.py`, `talks_sheet.py`, `talks_yaml.py`, `validate_talks.py`, `gen_talk_pages.py` with one line each, and the regeneration order after editing talks: `validate_talks.py` → `gen_talk_pages.py` → (`fetch_talk_thumbs.py`, `fetch_slide_strips.py` when decks change).
- [ ] **Step 2:** Update the `talks.yaml` header comment with the new fields (one line each).
- [ ] **Step 3:** Commit: `git commit -m "Document the talks section tooling"`.
- [ ] **Step 4:** Update the project memory file (`mith-ro-site-project.md`): talks overhaul state, the sheet round-trip commands, that `gen_talk_pages.py` must be re-run after any `talks.yaml` change.

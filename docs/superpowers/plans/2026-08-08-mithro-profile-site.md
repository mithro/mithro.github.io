# mith.ro Profile Site Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Tim 'mithro' Ansell's profile site (resume, talks, papers, contact, short-link redirects) as a Jekyll site in `mithro/mithro.github.io`, served at mith.ro.

**Architecture:** Jekyll built natively by GitHub Pages; all content driven from `_data/*.yaml` snapshot files produced by `uv run` Python scripts in `scripts/`; short links become committed redirect stub pages rendered by `jekyll-redirect-from`. Single dark "Silkscreen" theme in one hand-written CSS file — no webfonts, no JS frameworks, no analytics.

**Tech Stack:** Jekyll (`github-pages` gem), jekyll-redirect-from, Liquid templates, plain CSS, Python 3.13 via `uv run` for data fetching.

**Spec:** `docs/superpowers/specs/2026-08-08-mithro-profile-site-design.md` — read it before starting.

**Environment notes (verified 2026-08-08):**
- Ruby 3.3.8 present; bundler installed to user gems. Every `bundle` command needs:
  `export PATH="$(ruby -e 'print Gem.user_dir')/bin:$PATH"`
- `uv` 0.9.7 present. Use `uv run`, never bare python (user convention).
- Never create files in `/tmp/` — use the repo-local `tmp/` dir (gitignored in Task 1); it already holds brainstorming leftovers (`tmp/photo_urls.json` is reused by Task 7; the mockup files are cleaned up in Task 15).
- Work on `master` (the Pages deploy branch; mith.ro DNS is NOT yet pointed here, so partial deploys are harmless). Commit after every task; do not push until Tim says so.

**Data-holding tasks:** Tasks 3, 5, and 6 (talks/papers/resume YAML) must be executed by the orchestrator inline — their content comes from Google Drive MCP reads and WebFetch results that live in the orchestrating session's context, not in files. Do not dispatch these to subagents. Tasks 4 and 13 need WebSearch/WebFetch and interaction with Tim.

---

### Task 1: Jekyll scaffolding

**Files:**
- Create: `Gemfile`
- Create: `_config.yml`
- Create: `.gitignore`

- [ ] **Step 1: Write `Gemfile`**

```ruby
source "https://rubygems.org"

gem "github-pages", group: :jekyll_plugins
```

- [ ] **Step 2: Write `_config.yml`**

```yaml
title: "Tim 'mithro' Ansell"
description: "Building open source silicon ecosystems — SKY130 & GF180MCU PDKs, Open MPW, wafer.space."
url: "https://mith.ro"
lang: en

plugins:
  - jekyll-redirect-from

# Redirect stubs are generated files; everything else is hand-written.
exclude:
  - Gemfile
  - Gemfile.lock
  - README.md
  - LICENSE
  - docs/
  - scripts/
  - tmp/
  - vendor/
```

- [ ] **Step 3: Write `.gitignore`**

```
_site/
.jekyll-cache/
.jekyll-metadata
vendor/
tmp/
Gemfile.lock
```

(`Gemfile.lock` is ignored because GitHub Pages resolves its own pinned
versions; a local lock from bundler 4 would just drift.)

- [ ] **Step 4: Install and build — verify empty site builds**

Run:
```bash
export PATH="$(ruby -e 'print Gem.user_dir')/bin:$PATH"
bundle config set --local path vendor/bundle
bundle install
bundle exec jekyll build
```
Expected: `bundle install` completes; `jekyll build` finishes with `done in X seconds` and `_site/` exists. (If `github-pages` fails to resolve on Ruby 3.3, fall back to `gem "jekyll", "~> 3.10"` plus `gem "jekyll-redirect-from"` and note the deviation in the commit message.)

- [ ] **Step 5: Commit**

```bash
git add Gemfile _config.yml .gitignore
git commit -m "Add Jekyll scaffolding for mith.ro site"
```

---

### Task 2: Layout, contact include, and Silkscreen stylesheet

**Files:**
- Create: `_layouts/default.html`
- Create: `_includes/contact.html`
- Create: `_data/contact.yaml`
- Create: `assets/css/main.css`

- [ ] **Step 1: Write `_data/contact.yaml`**

```yaml
email: me@mith.ro
phones:
  - label: US
    number: "+1 774 264 8476"
    href: "tel:+17742648476"
  - label: AU
    number: "+61 421 968 221"
    href: "tel:+61421968221"
links:
  - label: GitHub
    url: https://github.com/mithro
    handle: mithro
  - label: LinkedIn
    url: https://www.linkedin.com/in/mithro/
    handle: in/mithro
  - label: Twitter
    url: https://twitter.com/mithro
    handle: "@mithro"
  - label: Mastodon
    url: https://fosstodon.org/@mithro
    handle: "@mithro@fosstodon.org"
  - label: Bluesky
    url: https://bsky.app/profile/mith.ro
    handle: "@mith.ro"
  - label: Blog
    url: https://blog.mithis.net/
    handle: blog.mithis.net
```

- [ ] **Step 2: Write `_includes/contact.html`**

```html
{% raw %}<ul class="contact{% if include.class %} {{ include.class }}{% endif %}">
  <li><a href="mailto:{{ site.data.contact.email }}">{{ site.data.contact.email }}</a></li>
  {% for phone in site.data.contact.phones %}
  <li><a href="{{ phone.href }}">{{ phone.number }}</a></li>
  {% endfor %}
  {% for link in site.data.contact.links %}
  <li><a href="{{ link.url }}" rel="me">{{ link.label }}: {{ link.handle }}</a></li>
  {% endfor %}
</ul>{% endraw %}
```

- [ ] **Step 3: Write `_layouts/default.html`**

```html
{% raw %}<!DOCTYPE html>
<html lang="{{ site.lang }}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% if page.title %}{{ page.title }} · {{ site.title }}{% else %}{{ site.title }}{% endif %}</title>
  <meta name="description" content="{{ page.description | default: site.description }}">
  <link rel="stylesheet" href="{{ '/assets/css/main.css' | relative_url }}">
  <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 16 16%22><circle cx=%228%22 cy=%228%22 r=%226%22 fill=%22none%22 stroke=%22%23d4a72c%22 stroke-width=%221.5%22/><path d=%22M8 0v5M8 11v5M0 8h5M11 8h5%22 stroke=%22%23d4a72c%22 stroke-width=%221.5%22/></svg>">
  <meta property="og:title" content="{{ page.title | default: site.title }}">
  <meta property="og:description" content="{{ page.description | default: site.description }}">
  <meta property="og:url" content="{{ page.url | absolute_url }}">
  <meta property="og:image" content="{{ '/assets/photos/die-scan.jpg' | absolute_url }}">
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "Person",
    "name": "Tim Ansell",
    "alternateName": "mithro",
    "email": "mailto:me@mith.ro",
    "url": "https://mith.ro/",
    "sameAs": [
      "https://github.com/mithro",
      "https://www.linkedin.com/in/mithro/",
      "https://twitter.com/mithro",
      "https://fosstodon.org/@mithro",
      "https://bsky.app/profile/mith.ro",
      "https://scholar.google.com/citations?user=pDTwJe4AAAAJ"
    ]
  }
  </script>
</head>
<body>
  <header class="topline">
    <a class="brand" href="{{ '/' | relative_url }}">mith.ro</a>
    <nav>
      <a href="{{ '/' | relative_url }}"{% if page.url == '/' %} class="on" aria-current="page"{% endif %}>About</a>
      <a href="{{ '/talks/' | relative_url }}"{% if page.url contains '/talks/' %} class="on" aria-current="page"{% endif %}>Talks</a>
      <a href="{{ '/papers/' | relative_url }}"{% if page.url contains '/papers/' %} class="on" aria-current="page"{% endif %}>Papers</a>
      <a href="{{ '/resume/' | relative_url }}"{% if page.url contains '/resume/' %} class="on" aria-current="page"{% endif %}>Resume</a>
    </nav>
  </header>
  <main>
    {{ content }}
  </main>
  <footer class="footer">
    {% include contact.html class="contact-inline" %}
  </footer>
</body>
</html>{% endraw %}
```

- [ ] **Step 4: Write `assets/css/main.css`**

Complete stylesheet (tokens from the approved mockup; no skeuomorphic
decorations; `.hero-contact` styles because contact sits in the hero):

```css
:root {
  --bg: #0e0f11;
  --panel: #16171a;
  --panel2: #1c1d21;
  --line: #2c2d31;
  --gold: #d4a72c;
  --gold-dim: #8a6d1f;
  --silk: #e8e6df;
  --muted: #9a948a;
  --blue: #5a74e8;
  --mono: ui-monospace, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
  --sans: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--bg);
  color: var(--silk);
  font-family: var(--mono);
  line-height: 1.55;
}

main { display: block; }

a { color: var(--gold); }

.topline {
  display: flex; justify-content: space-between; align-items: center;
  flex-wrap: wrap; gap: .5rem;
  max-width: 1080px; margin: 0 auto;
  padding: .9rem 1.25rem;
  border-bottom: 1px solid var(--gold-dim);
  font-size: .8rem; letter-spacing: .1em; text-transform: uppercase;
}
.topline .brand {
  color: var(--gold); font-weight: 700; text-decoration: none;
}
.topline .brand::before { content: "⌖ "; color: var(--silk); }
.topline nav { display: flex; gap: 1.5rem; }
.topline nav a { color: var(--muted); text-decoration: none; }
.topline nav a.on { color: var(--silk); border-bottom: 2px solid var(--gold); padding-bottom: .1rem; }
.topline nav a:hover, .topline nav a:focus-visible { color: var(--gold); }

.hero {
  display: grid; grid-template-columns: 1.15fr 1fr;
  max-width: 1080px; margin: 0 auto;
  border-bottom: 1px solid var(--line);
}
.hero-text { padding: 2.4rem 1.25rem; align-self: center; }
.hero-text h1 {
  font-size: 2.5rem; line-height: 1.08; margin: 0 0 .9rem;
  letter-spacing: -.01em; font-weight: 700; text-wrap: balance;
}
.hero-text h1 .nick { color: var(--gold); }
.hero-text .bio {
  margin: 0 0 1.4rem; color: #c4beb2; font-size: .95rem;
  max-width: 52ch; font-family: var(--sans);
}
.hero-photo { position: relative; min-height: 340px; border-left: 1px solid var(--gold-dim); }
.hero-photo img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.hero-photo .cap {
  position: absolute; left: 0; right: 0; bottom: 0;
  background: rgba(14,15,17,.82);
  border-top: 1px solid var(--gold-dim);
  font-size: .7rem; letter-spacing: .1em; text-transform: uppercase;
  padding: .45rem .9rem; margin: 0;
}

.contact { list-style: none; margin: 0; padding: 0; font-size: .82rem; }
.hero-contact { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .3rem 1.2rem; }
.hero-contact a { color: var(--silk); text-decoration: none; border-bottom: 1px solid var(--gold-dim); }
.hero-contact a:hover, .hero-contact a:focus-visible { color: var(--gold); }
.contact-inline { display: flex; flex-wrap: wrap; gap: .3rem 1.4rem; }
.contact-inline a { color: var(--muted); text-decoration: none; }
.contact-inline a:hover, .contact-inline a:focus-visible { color: var(--gold); }

.spec {
  display: grid; grid-template-columns: repeat(3, 1fr);
  max-width: 1080px; margin: 0 auto;
  border-bottom: 1px solid var(--line);
}
.spec > div { padding: 1rem 1.25rem; border-right: 1px solid var(--line); }
.spec > div:last-child { border-right: 0; }
.spec dt { font-size: .68rem; letter-spacing: .14em; text-transform: uppercase; color: var(--muted); margin: 0 0 .2rem; }
.spec dd { margin: 0; font-size: 1.5rem; font-weight: 700; color: var(--gold); font-variant-numeric: tabular-nums; }

.sect { max-width: 1080px; margin: 0 auto; padding: 1.8rem 1.25rem 0; }
.sect h2 {
  font-size: .8rem; letter-spacing: .16em; text-transform: uppercase;
  color: var(--gold); margin: 0 0 .9rem;
}
.sect .more { font-size: .8rem; }

.talks-table { border-collapse: collapse; width: 100%; font-size: .85rem; }
.talks-table td { border-top: 1px solid var(--line); padding: .55rem .8rem .55rem 0; vertical-align: top; }
.talks-table td.yr { color: var(--muted); white-space: nowrap; width: 4.5rem; font-variant-numeric: tabular-nums; }
.talks-table td.ti a { color: var(--silk); text-decoration: none; border-bottom: 1px solid var(--gold-dim); }
.talks-table td.ti a:hover, .talks-table td.ti a:focus-visible { color: var(--gold); }
.talks-table td.ev { color: var(--muted); text-align: right; white-space: nowrap; }
.talks-table td.ev > span { display: block; max-width: 18rem; overflow: hidden; text-overflow: ellipsis; }
.talks-table .vid { color: var(--blue); font-size: .78rem; text-decoration: none; }
.talks-table th { font-size: .65rem; letter-spacing: .12em; text-transform: uppercase; color: var(--muted); text-align: left; font-weight: 600; padding: 0 .8rem .3rem 0; border-bottom: 1px solid var(--gold-dim); }
.talks-table th:last-child { text-align: right; padding-right: 0; }
.table-scroll { overflow-x: auto; }

.visually-hidden { position: absolute !important; width: 1px; height: 1px; margin: -1px; padding: 0; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0; }

.gallery {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: .9rem;
  max-width: 1080px; margin: 0 auto; padding: 1.8rem 1.25rem 2.2rem;
}
.shot { position: relative; border: 1px solid var(--line); border-radius: 6px; overflow: hidden; aspect-ratio: 4 / 3; }
.shot img { width: 100%; height: 100%; object-fit: cover; display: block; }
.shot figcaption {
  position: absolute; left: 0; right: 0; bottom: 0;
  background: rgba(14,15,17,.82);
  font-size: .65rem; letter-spacing: .1em; text-transform: uppercase;
  padding: .3rem .6rem;
}

.footer {
  border-top: 1px solid var(--gold-dim);
  margin-top: 2.5rem;
}
.footer .contact-inline {
  max-width: 1080px; margin: 0 auto; padding: 1rem 1.25rem 1.4rem;
  font-size: .72rem; letter-spacing: .04em;
}

.prose { max-width: 72ch; font-family: var(--sans); font-size: .95rem; color: #c4beb2; }
.prose h2 { font-family: var(--mono); color: var(--gold); font-size: .95rem; letter-spacing: .1em; text-transform: uppercase; margin: 2rem 0 .6rem; }
.prose h3 { font-family: var(--mono); color: var(--silk); font-size: .9rem; margin: 1.4rem 0 .4rem; }
.prose .meta { color: var(--muted); font-family: var(--mono); font-size: .78rem; }

.papers-list { list-style: none; margin: 0; padding: 0; }
.papers-list li { border-top: 1px solid var(--line); padding: .8rem 0; }
.papers-list .ti a { color: var(--silk); text-decoration: none; border-bottom: 1px solid var(--gold-dim); }
.papers-list .ti a:hover, .papers-list .ti a:focus-visible { color: var(--gold); }
.papers-list .au { display: block; color: var(--muted); font-size: .8rem; font-family: var(--sans); }
.papers-list .ve { display: block; color: var(--muted); font-size: .78rem; }
.papers-list .ci { color: var(--gold); font-size: .78rem; }

.err { max-width: 1080px; margin: 0 auto; padding: 4rem 1.25rem; text-align: center; }
.err h1 { color: var(--gold); font-size: 2rem; }

@media (max-width: 760px) {
  .hero { grid-template-columns: 1fr; }
  .hero-photo { border-left: 0; border-top: 1px solid var(--gold-dim); min-height: 240px; }
  .spec { grid-template-columns: 1fr; }
  .spec > div { border-right: 0; border-bottom: 1px solid var(--line); }
  .spec > div:last-child { border-bottom: 0; }
  .gallery { grid-template-columns: 1fr; }
  .hero-contact { grid-template-columns: 1fr; }
}

@media (prefers-reduced-motion: no-preference) {
  a { transition: color .12s ease; }
}
```

- [ ] **Step 5: Build and verify assets are emitted**

Run:
```bash
export PATH="$(ruby -e 'print Gem.user_dir')/bin:$PATH"
bundle exec jekyll build && ls _site/assets/css/main.css
```
Expected: build succeeds; `_site/assets/css/main.css` listed. (No page uses the layout yet — that's fine.)

- [ ] **Step 6: Commit**

```bash
git add _layouts _includes _data/contact.yaml assets/css
git commit -m "Add Silkscreen layout, contact data, and stylesheet"
```

---

### Task 3: Talks data snapshot — ORCHESTRATOR INLINE

**Files:**
- Create: `_data/talks.yaml`

The full spreadsheet content ("Tim 'mithro' Ansell - Talks & Presentations",
Sheet ID `10TQ8mG1LRhiOalG_pqrUbOVp3gcnPFxttuyLUHfe4eA`) was read via the
Google Drive MCP during brainstorming and lives in the orchestrator's
context. The orchestrator writes the YAML directly.

- [ ] **Step 1: Write `_data/talks.yaml`** with one entry per spreadsheet row
that has a slides title. Schema (dates stay day-first strings as in the
sheet; `year` is an integer for grouping; omit empty keys):

```yaml
- title: "ISPD 2023 - Build custom silicon with Google!"
  event: "International Symposium on Physical Design 2023 (ISPD)"
  year: 2023
  date: "29 Mar 2023"
  slides: "https://bit.ly/ispd23-goog"
  slides_edit: "https://docs.google.com/presentation/d/1F9i-x-7Hl1ZUGAByBf5bHPwoskI6MQmHJBoja78a8uU/edit"
  video: ""
  source: sheet
```

Rules: `slides` prefers the short link column; falls back to the Slides
edit URL when no short link exists. Rows with no year get `year: 0` —
never null, because Liquid's `sort: "year"` fails on nil values; the
talks page renders year 0 as "Undated". The extra YouTube-only tab
entries (e.g. The Amp Hour interview, LCA 2020 "3 Talks for the Price
of 1!") are included with `video` set and no `slides`. Every entry also
carries a derived `sort_date` (YYYY-MM-DD) for stable chronological
sorting: the parsed `date` when its year matches the `year` field,
`YYYY-07-01` otherwise, `0000-01-01` for undated — year-only sorting is
unstable and cannot order within a year.

- [ ] **Step 2: Validate the YAML parses and count entries**

Run: `uv run python -c "import yaml,collections;d=yaml.safe_load(open('_data/talks.yaml'));print(len(d));print(collections.Counter(t['year'] for t in d))"`
(If PyYAML is unavailable to `uv run python`, use `uv run --with pyyaml python ...`.)
Expected: ~112 entries; year distribution matching the sheet's pivot
(2012:2 … 2022:16, 2023:2, plus the undated rows counted under 0).

- [ ] **Step 3: Commit**

```bash
git add _data/talks.yaml
git commit -m "Add talks data snapshot from Talks & Presentations sheet"
```

---

### Task 4: Talks refresh 2023–2026 — ORCHESTRATOR (needs WebSearch)

**Files:**
- Modify: `_data/talks.yaml` (append compiled entries)
- Create: `docs/talks-2023-2026-additions.csv`

The sheet stops in early 2023; it is now 2026. Compile newer talks.

- [ ] **Step 1: Gather candidates.** Sources, in order:
  1. `_data/shortlinks.yaml` if Task 13 already ran; otherwise query the
     bit.ly API directly for links created 2023-01-01 → today whose
     `long_url` points at docs.google.com/presentation or a conference
     site (e.g. `bit.ly/tim-silicon-2024` → the published
     "silicon interchange formats" deck). Token handling as in Task 13:
     env var only, keep it out of the repo and shell history.
  2. WebSearch: `"Tim Ansell" OR mithro talk OR presentation 2024`,
     same for 2025/2026, plus site-specific searches (YouTube, ORConf,
     Latch-Up, FOSSi Foundation, wafer.space, Tiny Tapeout).
  3. YouTube channel/search for recorded 2023–2026 appearances.
- [ ] **Step 2: Append entries** to `_data/talks.yaml` with
  `source: compiled` and the same schema.
- [ ] **Step 3: Write `docs/talks-2023-2026-additions.csv`** with the
  sheet's column order: Slides View, Slides Edit, Slides Title, Full Event,
  Event Year, Date, YouTube, Video Title — one row per compiled entry, so
  Tim can paste them into the spreadsheet.
- [ ] **Step 4: Show Tim the compiled list** in the conversation (title,
  event, date, evidence URL each) and note these ship immediately;
  corrections come later per spec.
- [ ] **Step 5: Validate the modified YAML** (same check as Task 3):

Run: `uv run --with pyyaml python -c "import yaml,collections;d=yaml.safe_load(open('_data/talks.yaml'));print(len(d));print(collections.Counter(t['year'] for t in d))"`
Expected: parses cleanly; count grew by the number of compiled entries.

- [ ] **Step 6: Commit**

```bash
git add _data/talks.yaml docs/talks-2023-2026-additions.csv
git commit -m "Compile 2023-2026 talks from public sources"
```

---

### Task 5: Papers data snapshot — ORCHESTRATOR INLINE

**Files:**
- Create: `_data/papers.yaml`

- [ ] **Step 1: Fetch the complete publication list** from Google Scholar
profile `pDTwJe4AAAAJ` via WebFetch (the profile shows ~16 papers; page
through "Show more" URLs `&cstart=0&pagesize=100` variant if needed).
Scholar often blocks non-browser fetches — if the re-fetch fails, write
the YAML from the profile data already held in the orchestrator's context
from brainstorming (metrics plus top papers are known; fill the tail from
whatever partial fetches succeed and note any gaps to Tim).
- [ ] **Step 2: Write `_data/papers.yaml`**:

```yaml
metrics:
  citations: 246
  h_index: 6
  i10_index: 5
  snapshot_date: 2026-08-08
  profile: "https://scholar.google.com/citations?user=pDTwJe4AAAAJ"
papers:
  - title: "CFU Playground: Full-stack open-source framework for tiny machine learning"
    authors: "S Prakash, T Callahan, J Bushagour, C Banbury, AV Green, P Warden, T Ansell, VJ Reddi"
    venue: "2023 IEEE International Symposium on Performance Analysis of Systems and Software (ISPASS)"
    year: 2023
    citations: 69
    url: "https://ieeexplore.ieee.org/abstract/document/10158162"
```

(url: use the Scholar citation view link or the publisher link surfaced on
the profile; leave `url` out if none is available. Uncited papers get
`citations: 0` — never omit the key, `/papers/` sorts on it.)

- [ ] **Step 3: Validate**

Run: `uv run --with pyyaml python -c "import yaml;d=yaml.safe_load(open('_data/papers.yaml'));print(d['metrics']['citations'], len(d['papers']))"`
Expected: `246` and the paper count (~16).

- [ ] **Step 4: Commit**

```bash
git add _data/papers.yaml
git commit -m "Add papers data snapshot from Google Scholar profile"
```

---

### Task 6: Resume data — ORCHESTRATOR INLINE

**Files:**
- Create: `_data/resume.yaml`

Content comes from the resume Google Doc
(`1126EBDPSCOEaunBqJtJVgW2PQKZETRea7FS31C7Ck6E`, already read via Drive
MCP). Structure it:

- [ ] **Step 1: Write `_data/resume.yaml`**:

```yaml
doc_url: "https://bit.ly/mithro-resume"
skills:
  - "Expert in building open ecosystems."
  - "Strong organization & project management capabilities."
  - "Strong presentation ability."
  - "Cross role collaborator including with finance, legal, sales & public policy."
technical_skills:
  - ">10 years experience with C++ & Python"
  - "Embedded C (Zephyr, Linux & Bare Metal)"
  - "Verilog, VHDL, Migen, Amaranth, & other HDLs"
  - "Strong experience with Javascript & CSS and web browser development"
achievements:
  - title: "SKY130 & GF180MCU PDKs"
    role: "Creator, Manager & Project Lead"
    years: "2018 - 2024"
    detail: "Worked with SkyWater Technology Foundry and GlobalFoundries to release open source PDKs for their 130nm and 180nm process technologies with support for open source EDA tooling such as OpenROAD, KLayout, Magic, OpenRAM, Xschem and many others."
    links:
      - { label: "SKY130", url: "https://skywater-pdk.rtfd.io" }
      - { label: "GF180MCU", url: "https://gf180mcu-pdk.rtfd.io" }
  # ... one entry per achievement in the doc: Open MPW program, NIST
  # Nanotechnology Development Platform, academic grants, >100 technical
  # presentations, 7 crowdfunding campaigns, PyCon AU.
employment:
  - org: "Arc PBC / Arc Labs"
    role: "SVP of Hardware / Chief Technology Officer"
    years: "2024 - Present"
    location: "New Jersey, USA"
  # ... Google roles back to 2008, ASTC 2006-2007, note about pre-1995 truncation.
projects:
  - { name: "TimVideos.us", years: "2015 - Present" }
  - { name: "Tomu device series (Tomu, Fomu, Somu, Qomu)", years: "2015 - 2021" }
  - { name: "F4PGA (previously SymbiFlow)", years: "2015 - 2022", url: "https://f4pga.org" }
  - { name: "OpenZaurus, OpenEmbedded & BitBake", years: "2002 - 2008" }
education:
  - org: "University of Adelaide"
    years: "2001 - 2006"
    degrees:
      - "Bachelor of Engineering (Information Technology & Telecommunications) with Honors"
      - "Bachelor of Arts (Philosophy & Cognitive Science) with Honors"
references_note: "Reference contact details provided on request."
```

Include every achievement/employment entry from the doc — no truncation
beyond what the doc itself truncates. Skip the named references grid
(names/roles stay in the Google Doc; the site shows `references_note`
only — they are third parties who did not consent to a new public page).

- [ ] **Step 2: Validate**

Run: `uv run --with pyyaml python -c "import yaml;d=yaml.safe_load(open('_data/resume.yaml'));print(len(d['achievements']), len(d['employment']))"`
Expected: 6+ achievements, 6 employment entries.

- [ ] **Step 3: Commit**

```bash
git add _data/resume.yaml
git commit -m "Add resume data from resume Google Doc"
```

---

### Task 7: Photos

**Files:**
- Create: `scripts/fetch_photos.py`
- Create: `assets/photos/` (4 photos + `manifest.yaml`)

- [ ] **Step 1: Write `scripts/fetch_photos.py`**

```python
# /// script
# requires-python = ">=3.11"
# ///
"""Download the selected wafer.space photos for mith.ro at web resolution.

Source albums (Google Photos shared links, resolved 2026-08-08):
  WS-RUN1:   https://photos.app.goo.gl/zLqQ9kHEEbKYhzww5
  Customer:  https://photos.app.goo.gl/2vo4baXmki3fGFdb7
"""
import pathlib
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

# base URLs come from tmp/photo_urls.json captured during brainstorming;
# =w1600 requests a 1600px-wide rendition.
PHOTOS = {
    "wafer-grid.jpg": "https://lh3.googleusercontent.com/pw/AP1GczM3MseGDmcDF7egcGuUbrGhADx8ywKMx62n8fm3a9VsVnJ18rSdlopoaGP1XKMalPq2qO0zXD6rt8EMnyJZtht434iaDUqCiCxFg4imHTRqmw6RXHU",
    "die-scan.jpg": "https://lh3.googleusercontent.com/pw/AP1GczMFuVOjJIqcx0HHKDSv-iz-awjtN8ES4ePYyHTogmQJl_l-wcQWyYIJ8EHMc4wvp_qU_2dJ5NpbMisSzbfAidfJBt1w7A0Rswt2E826hRapuI0KDiI",
    "chip-on-board.jpg": "https://lh3.googleusercontent.com/pw/AP1GczMxFeq15A7U4m4QjthFvEhRgSxbnFzqGY_et1P-yKfCmRAeBKNBtMcOPD2gl8x1EGMfD7CZl0mZ-BvoXgG26lRdkbC3hPEEdy4EC-2ToLwD3noMQvR_",
    "die-on-finger.jpg": "https://lh3.googleusercontent.com/pw/AP1GczPUQfpMW1m8tASXoPAjuSZQzsh0TK_r-EMZftDczSxkLXGjg1gDu8ihfhWtdS5734OaExmqQZMRjLBpDke7ggWLUD2sjIjirIKU67PyM4Bqv4Bk6ZgC",
}

outdir = pathlib.Path("assets/photos")
outdir.mkdir(parents=True, exist_ok=True)
for name, base in PHOTOS.items():
    dest = outdir / name
    req = urllib.request.Request(base + "=w1600", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        dest.write_bytes(resp.read())
    print(f"OK {dest} ({dest.stat().st_size} bytes)")
```

**Note:** `die-scan.jpg` and `die-on-finger.jpg` URL indices must be
double-checked against `tmp/photo_urls.json` (customer album entries 1 and
0 respectively) — after downloading, view each image and confirm it matches
its filename (wafer grid macro / full die scan with blue pad ring /
wire-bonded chip rows on black PCB / die on fingertip). Swap URLs from the
manifest if any mismatch.

- [ ] **Step 2: Run it and view every downloaded photo**

Run: `uv run scripts/fetch_photos.py`
Expected: four `OK` lines, each file > 100KB. Then Read each image and
verify content matches the filename.

- [ ] **Step 3: Write `assets/photos/manifest.yaml`** mapping each file to
its album name, album share URL, and base lh3 URL.

- [ ] **Step 4: Commit**

```bash
git add scripts/fetch_photos.py assets/photos
git commit -m "Add wafer.space photos and fetch script"
```

---

### Task 8: Homepage

**Files:**
- Create: `index.html`

- [ ] **Step 1: Write `index.html`**

```html
{% raw %}---
layout: default
description: "Tim 'mithro' Ansell — building open source silicon ecosystems: SKY130 & GF180MCU PDKs, Open MPW, wafer.space."
---
<section class="hero">
  <div class="hero-text">
    <h1>Tim <span class="nick">'mithro'</span> Ansell</h1>
    <p class="bio">I build open source silicon ecosystems — creator of the
    SkyWater SKY130 &amp; GF180MCU open PDKs and Google's Open MPW shuttle
    program (&gt;1,000 tapeouts, &gt;40% by first-time designers). Now SVP
    of Hardware at Arc PBC and founder of wafer.space.</p>
    {% include contact.html class="hero-contact" %}
  </div>
  <div class="hero-photo">
    <img src="{{ '/assets/photos/wafer-grid.jpg' | relative_url }}"
         alt="Macro photo of a GF180MCU multi-project wafer: a gold grid of dies">
    <p class="cap">wafer.space Run 1 — GF180MCU multi-project wafer</p>
  </div>
</section>

<dl class="spec">
  <div><dt>Talks</dt><dd>{{ site.data.talks | size }}</dd></div>
  <div><dt>Papers</dt><dd>{{ site.data.papers.papers | size }}</dd></div>
  <div><dt>Citations</dt><dd>{{ site.data.papers.metrics.citations }}</dd></div>
</dl>

<section class="sect">
  <h2>Recent talks</h2>
  {% assign recent = site.data.talks | sort: "sort_date" | reverse | slice: 0, 5 %}
  <div class="table-scroll" tabindex="0" role="region" aria-label="Recent talks">
  <table class="talks-table">
    <caption class="visually-hidden">Five most recent talks</caption>
    <thead>
      <tr><th scope="col">Year</th><th scope="col">Talk</th><th scope="col">Event</th></tr>
    </thead>
    <tbody>
    {% for talk in recent %}
    <tr>
      <td class="yr">{{ talk.year }}</td>
      <td class="ti">
        {% if talk.slides != "" and talk.slides %}<a href="{{ talk.slides | escape }}">{{ talk.title | escape }}</a>{% else %}{{ talk.title | escape }}{% endif %}
        {% if talk.video != "" and talk.video %} <a class="vid" href="{{ talk.video | escape }}"><span aria-hidden="true">▶</span> video</a>{% endif %}
      </td>
      <td class="ev"><span>{{ talk.event | escape }}</span></td>
    </tr>
    {% endfor %}
    </tbody>
  </table>
  </div>
  <p class="more"><a href="{{ '/talks/' | relative_url }}">All {{ site.data.talks | size }} talks →</a></p>
</section>

<div class="gallery">
  <figure class="shot">
    <img src="{{ '/assets/photos/die-scan.jpg' | relative_url }}" alt="Full die scan in gold and copper with a blue pad ring" loading="lazy">
    <figcaption>Die scan — GF180MCU</figcaption>
  </figure>
  <figure class="shot">
    <img src="{{ '/assets/photos/chip-on-board.jpg' | relative_url }}" alt="Wire-bonded chips on black circuit boards" loading="lazy">
    <figcaption>Chip on board — wafer.space Run 1</figcaption>
  </figure>
  <figure class="shot">
    <img src="{{ '/assets/photos/die-on-finger.jpg' | relative_url }}" alt="A single silicon die resting on a fingertip" loading="lazy">
    <figcaption>One die, actual size</figcaption>
  </figure>
</div>{% endraw %}
```

(Undated talks carry `year: 0` per Task 3, so the sort here is safe and
they can never appear in the recent-five slice.)

- [ ] **Step 2: Build and verify**

Run:
```bash
export PATH="$(ruby -e 'print Gem.user_dir')/bin:$PATH"
bundle exec jekyll build && grep -c "talks-table" _site/index.html && grep -o "me@mith.ro" _site/index.html | head -1
```
Expected: build passes; grep finds the table and the email in the hero.

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "Add homepage with hero contact, stats, recent talks, gallery"
```

---

### Task 9: Talks page

**Files:**
- Create: `talks/index.html`

- [ ] **Step 1: Write `talks/index.html`**

```html
{% raw %}---
layout: default
title: Talks
description: "All of Tim 'mithro' Ansell's talks and presentations, 2012–present."
---
<section class="sect">
  <h2>Talks &amp; presentations</h2>
  <p class="prose">Slides links go to the deck for each talk; ▶ links go to
  recordings. Entries marked ✱ were compiled from public sources in
  August 2026 and may still be corrected.</p>

  {% assign talks_sorted = site.data.talks | sort: "sort_date" | reverse %}
  {% assign years = talks_sorted | map: "year" | uniq %}
  {% for y in years %}
  <h3 class="year-head">{% if y == 0 %}Undated{% else %}{{ y }}{% endif %}</h3>
  <div class="table-scroll" tabindex="0" role="region" aria-label="{% if y == 0 %}Undated talks{% else %}Talks from {{ y }}{% endif %}">
  <table class="talks-table">
    <caption class="visually-hidden">{% if y == 0 %}Undated talks{% else %}Talks from {{ y }}{% endif %}</caption>
    <thead>
      <tr><th scope="col">Talk</th><th scope="col">Event · Date</th></tr>
    </thead>
    <tbody>
    {% for talk in talks_sorted %}{% if talk.year == y %}
    <tr>
      <td class="ti">
        {% if talk.slides != "" and talk.slides %}<a href="{{ talk.slides | escape }}">{{ talk.title | escape }}</a>{% else %}{{ talk.title | escape }}{% endif %}
        {% if talk.video != "" and talk.video %} <a class="vid" href="{{ talk.video | escape }}"><span aria-hidden="true">▶</span> video</a>{% endif %}
        {% if talk.source == "compiled" %} <span class="compiled" title="Compiled from public sources">✱</span>{% endif %}
      </td>
      <td class="ev"><span>{% if talk.event != "" and talk.event %}{{ talk.event | escape }}{% if talk.date != "" and talk.date %} · {{ talk.date | escape }}{% endif %}{% else %}{{ talk.date | escape }}{% endif %}</span></td>
    </tr>
    {% endif %}{% endfor %}
    </tbody>
  </table>
  </div>
  {% endfor %}

Note: `map: "year"` over the sort_date-sorted list yields years in
correct newest-first order because sort_date always starts with the
year; `uniq` then keeps first occurrences. Undated (year 0) groups last.
</section>{% endraw %}
```

Add to `assets/css/main.css`:

```css
.year-head { font-family: var(--mono); color: var(--silk); font-size: 1rem; margin: 1.6rem 0 .4rem; }
.compiled { color: var(--muted); }
```

- [ ] **Step 2: Build and verify**

Run:
```bash
export PATH="$(ruby -e 'print Gem.user_dir')/bin:$PATH"
bundle exec jekyll build && grep -c "<tr>" _site/talks/index.html
```
Expected: row count ≈ talks entry count (112+).

- [ ] **Step 3: Commit**

```bash
git add talks/index.html assets/css/main.css
git commit -m "Add talks archive page grouped by year"
```

---

### Task 10: Papers page

**Files:**
- Create: `papers/index.html`

- [ ] **Step 1: Write `papers/index.html`**

```html
{% raw %}---
layout: default
title: Papers
description: "Scientific papers by Tim 'mithro' Ansell."
---
<section class="sect">
  <h2>Papers</h2>
  <p class="prose meta">
    {{ site.data.papers.metrics.citations }} citations ·
    h-index {{ site.data.papers.metrics.h_index }} ·
    i10-index {{ site.data.papers.metrics.i10_index }} ·
    snapshot {{ site.data.papers.metrics.snapshot_date }} ·
    <a href="{{ site.data.papers.metrics.profile }}">Google Scholar profile</a>
  </p>
  <ul class="papers-list">
    {% assign papers_sorted = site.data.papers.papers | sort: "citations" | reverse %}
    {% for paper in papers_sorted %}
    <li>
      <span class="ti">{% if paper.url %}<a href="{{ paper.url }}">{{ paper.title | escape }}</a>{% else %}{{ paper.title | escape }}{% endif %}</span>
      <span class="au">{{ paper.authors | escape }}</span>
      <span class="ve">{{ paper.venue | escape }} · {{ paper.year }}{% if paper.citations and paper.citations > 0 %} · <span class="ci">{{ paper.citations }} citations</span>{% endif %}</span>
    </li>
    {% endfor %}
  </ul>
</section>{% endraw %}
```

- [ ] **Step 2: Build and verify**

Run:
```bash
export PATH="$(ruby -e 'print Gem.user_dir')/bin:$PATH"
bundle exec jekyll build && grep -c "<li>" _site/papers/index.html
```
Expected: count equals number of papers in the YAML.

- [ ] **Step 3: Commit**

```bash
git add papers/index.html
git commit -m "Add papers page from Scholar snapshot"
```

---

### Task 11: Resume page

**Files:**
- Create: `resume/index.html`

- [ ] **Step 1: Write `resume/index.html`** rendering every block of
`_data/resume.yaml`: skills + technical skills side by side, achievements
(title/role/years/detail/links), employment (org/role/years/location),
projects, education, and the references note. End with a link to the
canonical Google Doc (`{% raw %}{{ site.data.resume.doc_url }}{% endraw %}`).
Use `.sect` + `.prose` classes; achievements/employment as definition-style
blocks with mono headers, sans detail text. Full markup is at the
implementer's discretion within the existing CSS classes — no new CSS
unless a class is genuinely missing.

- [ ] **Step 2: Build and verify**

Run:
```bash
export PATH="$(ruby -e 'print Gem.user_dir')/bin:$PATH"
bundle exec jekyll build && grep -c "Arc PBC" _site/resume/index.html
```
Expected: ≥ 1.

- [ ] **Step 3: Commit**

```bash
git add resume/index.html
git commit -m "Add resume page rendered from resume data"
```

---

### Task 12: 404 page

**Files:**
- Create: `404.html`

- [ ] **Step 1: Write `404.html`**

```html
{% raw %}---
layout: default
title: Not found
permalink: /404.html
---
<div class="err">
  <h1>404 — no connection</h1>
  <p class="prose" style="margin: 0 auto;">Nothing is routed to this address.
  Try <a href="{{ '/' | relative_url }}">the homepage</a>, or
  <a href="{{ '/talks/' | relative_url }}">the talks archive</a>.</p>
</div>{% endraw %}
```

- [ ] **Step 2: Build, verify, commit**

Run:
```bash
export PATH="$(ruby -e 'print Gem.user_dir')/bin:$PATH"
bundle exec jekyll build && ls _site/404.html
```
```bash
git add 404.html
git commit -m "Add 404 page"
```

---

### Task 13: Short links — fetch, classify, Tim review gate

**Files:**
- Create: `scripts/fetch_bitly.py`
- Create: `_data/shortlinks.yaml`

- [ ] **Step 1: Write `scripts/fetch_bitly.py`**

```python
# /// script
# requires-python = ">=3.11"
# requires = ["pyyaml"]
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
import urllib.parse
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
```

- [ ] **Step 2: Run it** (Tim's token from the session; NOT in the repo)

Run: `BITLY_TOKEN=<token> uv run scripts/fetch_bitly.py`
Expected: stderr reports fetched count and include/total split.

- [ ] **Step 3: Sanity-check against known keywords**

Run: `uv run --with pyyaml python -c "import yaml;d=yaml.safe_load(open('_data/shortlinks.yaml'));ks={e['keyword'] for e in d};print('tim-silicon-2024' in ks, 'mithro-resume' in ks, len(d))"`
Expected: `True True <count>`.

- [ ] **Step 4: Present the YAML to Tim for review.** Show included list
in full and the excluded list summarized; ask him to flip `include` flags
as desired. **Do not proceed to Task 14 until Tim approves.** Also remind
Tim to rotate the bit.ly token now that fetching is done.

- [ ] **Step 5: Commit**

```bash
git add scripts/fetch_bitly.py _data/shortlinks.yaml
git commit -m "Fetch bit.ly shortlinks with public-findability defaults"
```

---

### Task 14: Redirect stub pages (after Tim's approval)

**Files:**
- Create: `scripts/gen_redirect_pages.py`
- Create: `redirects/<keyword>.md` stubs (one per included link)

- [ ] **Step 1: Write `scripts/gen_redirect_pages.py`**

```python
# /// script
# requires-python = ">=3.11"
# requires = ["pyyaml"]
# ///
"""Generate jekyll-redirect-from stub pages from _data/shortlinks.yaml.

Stubs live in redirects/ but publish at /<keyword>/ via permalink.
Re-running is idempotent: the redirects/ dir is rebuilt from scratch.
"""
import pathlib
import shutil

import yaml

RESERVED = {"talks", "papers", "resume", "about", "assets", "docs", "scripts", "404"}

links = yaml.safe_load(open("_data/shortlinks.yaml"))
outdir = pathlib.Path("redirects")
if outdir.exists():
    shutil.rmtree(outdir)
outdir.mkdir()

count = 0
for e in links:
    if not e["include"]:
        continue
    kw = e["keyword"]
    if kw.lower() in RESERVED:
        print(f"SKIP reserved: {kw}")
        continue
    stub = outdir / f"{kw}.md"
    stub.write_text(
        "---\n"
        f"permalink: /{kw}/\n"
        f"redirect_to: \"{e['long_url']}\"\n"
        "sitemap: false\n"
        "---\n"
    )
    count += 1
print(f"Wrote {count} redirect stubs")
```

- [ ] **Step 2: Run and build**

Run:
```bash
uv run scripts/gen_redirect_pages.py
export PATH="$(ruby -e 'print Gem.user_dir')/bin:$PATH"
bundle exec jekyll build
```
Expected: stub count reported; build passes.

- [ ] **Step 3: Verify a known redirect renders**

Run: `grep -l "tim-silicon-2024" _site/tim-silicon-2024/index.html && grep -o 'http-equiv="refresh"' _site/tim-silicon-2024/index.html`
Expected: the built page exists and contains a meta refresh to the long URL.
(If `tim-silicon-2024` ended up excluded, use any included keyword.)

- [ ] **Step 4: Commit**

```bash
git add scripts/gen_redirect_pages.py redirects/
git commit -m "Generate short-link redirect pages from approved list"
```

---

### Task 15: CNAME, deployment docs, cleanup, final verification

**Files:**
- Create: `CNAME`
- Modify: `README.md`
- Delete: brainstorming leftovers in `tmp/`

- [ ] **Step 0: OG image** (added by Task 7 code review): generate
`assets/photos/og-image.jpg`, a ~1200x630 landscape crop of the die scan
under 300KB (e.g. via Pillow in a `uv run` script), and point
`_layouts/default.html`'s `og:image` at it — the full 1600x2082 / 1.7MB
portrait die-scan.jpg previews poorly on link-unfurl platforms.
- [ ] **Step 1: Write `CNAME`** containing exactly `mith.ro`.
- [ ] **Step 2: Rewrite `README.md`**: what the site is, how data files are
refreshed (`scripts/*.py` usage incl. `BITLY_TOKEN`), how to build locally
(bundler PATH note), a pointer to `docs/talks-2023-2026-additions.csv`
(rows awaiting paste-back into the talks spreadsheet), and the DNS/deploy
steps for Tim:
  - GitHub repo → Settings → Pages: custom domain `mith.ro`, enforce HTTPS.
  - Cloudflare: point apex A records at GitHub Pages
    (185.199.108.153/109/110/111 + AAAA 2606:50c0:8000..8003::153) or
    CNAME-flatten to `mithro.github.io`; grey-cloud or SSL "Full".
- [ ] **Step 3: Clean up `tmp/`** (user convention: tmp files removed when
done): delete `tmp/photo_samples/`, `tmp/*.py`, `tmp/*.html` — keep
`tmp/photo_urls.json` only if photos may still be re-picked, otherwise
delete it too (it is gitignored either way).
- [ ] **Step 4: Full verification**

```bash
export PATH="$(ruby -e 'print Gem.user_dir')/bin:$PATH"
bundle exec jekyll build
uv run --with pyyaml python - <<'EOF'
import pathlib, re
site = pathlib.Path("_site")
# every internal href must resolve to a built file
missing = []
for html in site.rglob("*.html"):
    for m in re.finditer(r'href="(/[^"]*)"', html.read_text()):
        target = m.group(1).split("#")[0]
        if target.startswith("//"):
            continue
        p = site / target.lstrip("/")
        if not (p.exists() or p.with_suffix(".html").exists() or (p / "index.html").exists()):
            missing.append((str(html), target))
print("MISSING:", missing if missing else "none")
EOF
```
Expected: `MISSING: none`.

- [ ] **Step 5: Commit**

```bash
git add CNAME README.md
git commit -m "Add CNAME and deployment documentation"
```

- [ ] **Step 6: Report to Tim**: site ready to push; pushing master deploys
to mithro.github.io immediately; mith.ro goes live once he makes the DNS
change; remind about token rotation and the talks/shortlinks review items.
Do not push without Tim's go-ahead. Include the post-push checklist (also
recorded in the README): after push + DNS, spot-check a sample of
redirects, e.g.

```bash
curl -sL -o /dev/null -w "%{url_effective}\n" https://mith.ro/tim-silicon-2024/
```

expecting each to land on its long URL.

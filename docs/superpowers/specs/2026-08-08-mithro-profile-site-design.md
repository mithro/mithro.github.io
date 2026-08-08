# mith.ro profile site — design

Date: 2026-08-08
Status: approved by Tim (with changes, incorporated below)

## Purpose

Turn the empty `mithro/mithro.github.io` repo into Tim 'mithro' Ansell's
personal profile site, served at https://mith.ro. The site presents who Tim
is and what he has done: resume, ~112+ technical talks, scientific papers,
and contact details — plus working short-link redirects that free him from
depending on bit.ly.

## Decisions already made

| Decision | Choice |
| --- | --- |
| Stack | Jekyll, built natively by GitHub Pages (no CI to maintain) |
| Hosting | GitHub Pages, custom domain mith.ro |
| Structure | Multi-page: home, /talks/, /papers/, /resume/ |
| Data updates | One-time snapshot now; fetch scripts kept for manual re-runs |
| Short links | Top-level redirects (mith.ro/tim-silicon-2024), no public index, only publicly-findable links included |
| Visual design | "Silkscreen": black soldermask + ENIG gold + datasheet mono type, built on Tim's wafer.space photos (mockup approved) |
| Contact info | Email, phones, GitHub, LinkedIn, Twitter, Mastodon, Bluesky, blog — front and center on the homepage |

## Visual design

Palette sampled from Tim's own hardware photos (wafer.space Run 1):

- Ground: matte black soldermask `#0e0f11`, panels `#16171a`
- Accent: ENIG gold `#d4a72c` (dim `#8a6d1f` for rules/borders)
- Text: silkscreen off-white `#e8e6df`, muted `#9a948a`
- Video/link secondary accent: pad-ring blue `#5a74e8`

Type: `ui-monospace` system stack for headings, labels, nav, and data;
`system-ui` for prose paragraphs. No webfonts — zero external requests.
The ⌖ fiducial mark is the site glyph and favicon.

Copy rules (per Tim's feedback):

- No skeuomorphic document text: no "FIG. 1", no "DOC. NO. / REV" lines,
  no invented spec labels like "Tapeouts Enabled".
- Photo captions are plain descriptions ("wafer.space Run 1 — GF180MCU
  multi-project wafer").
- Stats strip uses plain labels: Talks, Papers, Citations.

Single committed dark theme (it is the identity, not a missing feature);
every color painted explicitly.

## Pages

### / (home)

- Header nav: About · Talks · Papers · Resume (+ ⌖ mith.ro brand).
  "About" is the homepage itself (`/`), not a separate page; `about` still
  joins the reserved shortlink paths in case that ever changes.
- Hero: name, 2–3 sentence bio (open silicon ecosystems: SKY130 & GF180MCU
  PDKs, Open MPW, wafer.space, Arc PBC), wafer photo.
- Contact block directly in the hero, not buried: me@mith.ro,
  +1 774 264 8476, +61 421 968 221, github.com/mithro, linkedin.com/in/mithro,
  twitter.com/mithro, fosstodon.org/@mithro, bsky.app/profile/mith.ro,
  blog.mithis.net.
- Stats strip: talks / papers / citations. Talk and paper counts are
  computed from their data files; the citations figure reads the
  profile-metrics block in `_data/papers.yaml` (not a sum of per-paper
  counts), so home and /papers/ can never disagree.
- Recent talks: latest ~5 from `_data/talks.yaml`.
- Photo gallery row (3 shots: die scan, chip-on-board, die on fingertip).
- Footer: repeat of contact links (footer appears on every page).

### /talks/

All talks grouped by year, newest first. Each row: title, event, date
(day-first format), slides link, ▶ video link when available. Source:
`_data/talks.yaml`.

### /papers/

Citation metrics line (246 citations, h-index 6, i10-index 5 — snapshot
values) plus one entry per paper: title, authors, venue, year, citations,
link. Source: `_data/papers.yaml`.

### /resume/

HTML rendering of the resume Google Doc content: skills, technical skills,
career achievements, employment history, open source projects, academic,
references. Phone numbers included (Tim's explicit choice). Source:
`_data/resume.yaml`. Links back to the canonical Google Doc.

### 404

Styled error page in the same identity.

### SEO / metadata

OpenGraph tags with a die-shot image, schema.org Person JSON-LD,
per-page titles and descriptions. No analytics.

## Short-link redirects

- One page per included link at `/<keyword>/` using `jekyll-redirect-from`
  (GitHub Pages whitelisted plugin) with `redirect_to:` the long URL.
  Old bit.ly/j.mp links keep working; mith.ro copies are additive.
- Source: complete bitlink list from the bit.ly API (bit.ly and j.mp are
  the same account), fetched by `scripts/fetch_bitly.py`. Token comes from
  the `BITLY_TOKEN` env var and is never committed. The token pasted into
  this design conversation should be rotated once fetching is done.
- Stored in `_data/shortlinks.yaml`: keyword, long URL, title, created
  date, `include` flag, and a `reason` note for the flag's default.
- Public-findability filter: `include: true` by default only when the
  keyword or target already appears in a public source we hold — the talks
  spreadsheet, the resume doc, or public web references. Everything else
  defaults to `include: false`. Tim reviews the generated YAML before the
  redirect pages go live.
- No public index page of redirects.
- Reserved paths (`talks`, `papers`, `resume`, `assets`, and any future
  page slugs) always win; a colliding keyword is flagged in the YAML and
  skipped.

## Data pipeline

All scripts run with `uv run`, live in `scripts/`, and write YAML into
`_data/`. Snapshot data is committed; scripts remain for future re-runs.

- `scripts/fetch_bitly.py` → `_data/shortlinks.yaml` (paginates the group
  bitlinks endpoint; applies the findability defaults).
- `_data/talks.yaml` — snapshot of the "Tim 'mithro' Ansell - Talks &
  Presentations" Google Sheet (fetched via Drive access), normalised:
  title, event, year, date, slides URL, video URL, short link.
- **Talks refresh (2023 → 2026)**: the sheet stops at early 2023. Compile
  newer talks from (a) recent bit.ly links pointing at presentation decks,
  (b) web/YouTube searches for Tim's 2023–2026 appearances. New entries are
  marked `source: compiled` in the YAML for Tim's review, and delivered as
  CSV rows matching the sheet's columns so Tim can paste them back into
  the spreadsheet. Unlike shortlinks, compiled talks ship on the site
  immediately (they are the point of the refresh); Tim's review corrects
  or removes entries afterwards.
- `_data/papers.yaml` — snapshot of the Google Scholar profile
  (user pDTwJe4AAAAJ): all papers with title, authors, venue, year,
  citations, plus the profile metrics.
- `_data/resume.yaml` — structured from the resume Google Doc content
  (already retrieved via Drive access).
- `assets/photos/` — selected shots from the three Google Photos albums
  (WS-RUN1, TTPG Test output, wafer.space Run 1 Customer Photos),
  downloaded at ~1600px web resolution. `assets/photos/manifest.yaml`
  records each file's source album and URL.

## Deployment

- `CNAME` file containing `mith.ro` committed to the repo; GitHub Pages
  custom domain configured with HTTPS enforced.
- DNS (Tim's side, Cloudflare currently returns error 526): point the apex
  at GitHub Pages (A/AAAA records or CNAME-flatten to `mithro.github.io`)
  and either grey-cloud the record or set Cloudflare SSL to "Full".

## Verification

- `bundle exec jekyll build` passes locally before each commit.
- After deploy: curl spot-checks that a sample of `/<keyword>/` redirects
  return the right targets, and an HTML link check over the built site.

## Out of scope

- Automated/scheduled data refresh (snapshot only, by choice).
- Public directory of short links.
- Analytics.
- Blog/writing section (blog.mithis.net stays where it is).

## Open items

1. Tim reviews `_data/shortlinks.yaml` include flags before redirects ship.
2. Tim reviews compiled 2023–2026 talks and pastes the CSV back into the
   Google Sheet.
3. Tim makes the DNS change when the site is ready.
4. Tim rotates the bit.ly token after the snapshot is fetched.

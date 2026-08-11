# Drive Link Migration — Design

Migrate short-link references inside Tim's Google Drive assets
(Slides, Docs, Sheets; Drawings via a manual queue) from
`bit.ly/*` / `j.mp/*` to `mith.ro/*`, and resolve dead `goo.gl/*`
links, without mangling or losing any historical content.

## Decisions (from brainstorming, 2026-08-12)

| Topic | Decision |
| --- | --- |
| Which links | Phase 1: only the 233 public aliases with live mith.ro redirects. Private-alias references are inventoried into a phase-2 backlog and left untouched. |
| Rewrite form | Domain swap of whatever alias the document already uses (`bit.ly/X` → `mith.ro/X`). Prerequisite: mith.ro must serve BOTH friendly aliases and hash twins (see Prerequisite below). |
| File ownership | Files Tim owns are eligible by default. Files owned by others require an explicit per-file opt-in checkbox in the review sheet. |
| Rewrite scope in-file | Body/display text, underlying hyperlink URLs, file titles, speaker notes, slide masters & layouts. |
| goo.gl | Fully in scope: resolve each via Wayback's archived redirect data to a proposed real destination (or mith.ro alias when the target matches a public link); unresolvable ones become "research needed" rows. |
| Backups | None. Before a file's first edit, its current `headRevisionId` is fetched, pinned (`revisions.update keepForever=true`) and logged — version history is the restore mechanism. |
| Process | Approach A: read-only scan → review spreadsheet with per-occurrence Approve checkboxes → small applied batches → verify pass with before/after slide thumbnails → 5-file pilot first. |

## Corpus (probed 2026-08-11, Drive full-text search)

| domain | Slides | Docs | Sheets | Drawings |
| --- | --- | --- | --- | --- |
| bit.ly | 90 | 134 | 38 | 1 |
| j.mp | 162 | 59 | 8 | 3 |
| goo.gl | 15 | 20 | 14 | 1 |

Roughly 400–500 unique files (overlap between rows); ~45 of the
bit.ly files are owned by others. Full-text search only sees display
text — files where a short link exists only inside a hyperlink URL are
invisible to it, hence the deep scan below.

## Prerequisite: hash-twin redirects on mith.ro

`scripts/format_sheets.py sync` + `scripts/gen_redirect_pages.py` are
extended so every PUBLIC link's hash keyword (e.g. `2Axn2Iw`, today
folded into its custom alias and skipped) also gets a mith.ro redirect
stub. After this, a pure domain swap of ANY public alias resolves.

## Components

All tooling lives in the mith.ro repo (`scripts/`), PEP 723 uv
scripts, authenticated via gcloud user credentials with Drive scope
(`gcloud auth login --enable-gdrive-access`) and quota project
`mithro-drive-backup` (Docs/Slides/Sheets APIs are enabled on it).

### 1. `scan` (read-only)

- **Discovery:** Drive `files.list` full-text queries per domain and
  mime type, PLUS a full inventory of Tim-owned Slides/Docs/Sheets
  whose content is then fetched regardless of search hits, so
  hyperlink-URL-only references are found. (The deep pass is
  incremental: it records per-file scan timestamps and skips files
  unmodified since the last scan.)
- **Extraction:** per file, walk the document JSON:
  - Docs: `documents.get` — body, headers/footers, footnotes; text
    runs (content) and `textStyle.link.url`.
  - Slides: `presentations.get` — slides, layouts, masters, notes
    pages; shape/table text runs and their link attributes.
  - Sheets: `spreadsheets.get` with grid data — cell values, formulas
    (`HYPERLINK(...)`), rich-text link runs.
  - Titles: Drive metadata.
- **Classification** of every occurrence against
  `_data/shortlinks.yaml` (+ the public-alias set):
  `public` (proposed rewrite), `private` (phase-2 backlog, no action),
  `googl` (Wayback-resolved proposal or research-needed), `unknown`
  (alias not in the mirror — flagged).
- **Output:** `tmp/migration/occurrences.jsonl`, one record per
  occurrence: file id/name/type/owner, location descriptor
  (e.g. `body`, `notes[slide 12]`, `master`, `title`, `Sheet1!C7`,
  `link-url` vs `display-text`), exact old string, proposed new
  string, classification, risk flags.

### 2. `sheet`

Builds/updates a "mith.ro link migration" Google Sheet from the
occurrences file. One row per occurrence, grouped by file:

    File (linked) | Type | Owner | Location | Old | Proposed |
    Risk notes | Approve (checkbox) | Status | Batch

- Formatted like the short-links sheet (frozen header, filter,
  conditional colours; Status: blank / applied / verified / error /
  FAILED-verify).
- Risk notes include: `shared owner — opt-in`, `length change`,
  `goo.gl unverified`, `unknown alias`.
- Re-running refreshes rows by stable occurrence key
  (file id + location + old string) WITHOUT clobbering Approve ticks
  or Status of already-processed rows.

### 3. `apply`

Processes rows that are Approved and Status-blank, batched ≤20 files
per run (batch id written back):

1. Per file, first edit only: fetch `headRevisionId`, pin it via
   `revisions.update(keepForever=true)`, log it (sheet + applied-log).
2. Edits, chosen per occurrence group:
   - `replaceAllText` (Docs/Slides/Sheets `batchUpdate`) ONLY when
     every occurrence of that exact old string in the file is
     approved — it is a whole-file operation.
   - Otherwise targeted edits: Docs `updateTextStyle`/`replaceText` on
     computed ranges; Slides per-shape text edits; Sheets
     `updateCells` for the specific cell/formula.
   - Hyperlink URLs: range-targeted `updateTextStyle` with
     `link.url` (Docs/Slides); Sheets rich-link cell rewrite.
   - Titles: Drive `files.update(name=...)`.
3. Write back Status=applied + revision id; append full before/after
   to `tmp/migration/applied-log.jsonl`.

Index invalidation note: within one file, ranges are recomputed from a
fresh `get` immediately before that file's batchUpdate, and all edits
for a file go in ONE batchUpdate ordered from the end of the document
backwards so earlier ranges stay valid.

### 4. `verify`

For every file in the batch:

- Re-extract and assert: zero remaining approved-old strings; the
  proposed new strings present; no occurrences of OTHER classes
  changed count (nothing beyond the approved edits happened).
- Slides visual diff: `pages.getThumbnail` of every touched slide was
  captured during `apply` (pre-edit) and is captured again post-edit;
  `verify` writes a side-by-side HTML gallery
  (`tmp/migration/verify-batch-N.html`) for eyeballing reflow.
- Status=verified on pass, FAILED-verify (with detail) on mismatch.

A batch is complete only when verify is green AND Tim has glanced at
the gallery. The next batch does not start before that.

### 5. Drawings manual queue

The ~5 Google Drawings (no editing API) get a worklist section in the
review sheet: file link + exact old→new strings, Status hand-ticked by
Tim after manual editing; `verify` can still re-export the drawing
text (Drive export) to confirm.

## Pilot

Batch 0 = five low-stakes files (old decks with a single j.mp
footer each, one Doc, one Sheet) exercising every component
end-to-end, reviewed by Tim before any further batch is approved.

## Error handling

- Any per-file API failure → Status=error with the message; the file
  is skipped; the batch continues.
- Rate limits: paced requests + exponential backoff; scan and apply
  both resumable (idempotent by occurrence key / Status).
- Rollback recipe (documented in the sheet header): open the file's
  version history → restore the pinned revision id recorded in its
  row. Nothing in the pipeline ever deletes content.

## Non-goals

- No edits to files whose rows aren't approved. No private-alias
  rewrites (phase 2). No bulk sharing changes. No history rewriting of
  decks' visual design — text/link replacement only.

## Testing

- `scan`/`sheet` are pure read/report — safe to run any time.
- Unit checks in the scripts: classification table against a fixture
  of URL forms; range-computation round-trip on a scratch Doc/Deck
  created by the test itself (then trashed).
- The pilot batch is the integration test; verify is the regression
  gate for every subsequent batch.

#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "pyyaml"]
# ///
"""Keep the talks Google Sheets and _data/talks.yaml in step.

The original "Tim 'mithro' Ansell - Talks & Presentations" sheet plus
the "talks additions" paste-back sheet together cover every talk in
_data/talks.yaml. Rows are matched to YAML entries by the Google Slides
document id (falling back to the YouTube video id for deck-less talks).

    uv run scripts/talks_sheet.py dump    # print both sheets as JSON (row-matched)
    uv run scripts/talks_sheet.py slugs   # YAML -> sheet: write/refresh the Slug column
    uv run scripts/talks_sheet.py strips  # YAML -> sheet: add a Strips column, pre-fill proposals
    uv run scripts/talks_sheet.py import  # sheet -> YAML: pull Slug/Strips values (colours untouched)
    uv run scripts/talks_sheet.py import --accept   # ...and mark the cells black (Tim has reviewed)
    uv run scripts/talks_sheet.py shortlinks        # propose mith.ro/<slug> rows in the short-links sheet

Cell colour is the review state: black = accepted/current, bold red =
a proposal awaiting Tim. Only `import --accept` turns cells black.

Auth: gcloud user credentials with Drive scope
(`gcloud auth login --enable-gdrive-access`), as for format_sheets.py.
"""

import json
import pathlib
import re
import sys

import requests
import yaml

from format_sheets import SHEETS, check, session

TALKS_SHEET = "10TQ8mG1LRhiOalG_pqrUbOVp3gcnPFxttuyLUHfe4eA"
ADDITIONS_SHEET = "1oaJnQU_g0scQPYJpSbo6PqmkBmN6Hft-4-gbvQwdno4"
TALKS_YAML = pathlib.Path("_data/talks.yaml")

DOC_RE = re.compile(r"/presentation/d/(?:e/)?([\w-]+)")
YT_RE = re.compile(r"(?:youtu\.be/|watch\?v=)([\w-]+)")


def doc_id(url: str | None) -> str | None:
    m = DOC_RE.search(url or "")
    return m.group(1) if m else None


def yt_id(url: str | None) -> str | None:
    m = YT_RE.search(url or "")
    return m.group(1) if m else None


SHORT_RE = re.compile(r"(?:bit\.ly|j\.mp|wafer\.space|mith\.ro)/([\w-]+)")


def ids_from(*urls: str | None) -> set[str]:
    """Every identity a talk/row exposes: deck ids, video ids, short aliases."""
    keys = set()
    for u in urls:
        if not u:
            continue
        if k := doc_id(u):
            keys.add("doc:" + k)
        if k := yt_id(u):
            keys.add("yt:" + k)
        if k := SHORT_RE.search(u):
            keys.add("short:" + k.group(1).lower())
    return keys


def title_key(title: str | None) -> str:
    return "title:" + re.sub(r"\W+", " ", title or "").strip().lower()


def talk_keys(talk: dict) -> set[str]:
    keys = ids_from(talk.get("slides_edit"), talk.get("slides_embed"),
                    talk.get("slides"), talk.get("slides_short"),
                    talk.get("video"))
    if talk.get("slug"):
        keys.add("slug:" + talk["slug"])
    keys.add(title_key(talk.get("title")))
    return keys


def load_tabs(s: requests.Session, spreadsheet: str) -> list[dict]:
    """Every tab: sheetId, title, header row and data rows (as lists)."""
    meta = check(s.get(f"{SHEETS}/{spreadsheet}",
                       params={"fields": "sheets.properties"}))
    tabs = []
    for sh in meta["sheets"]:
        props = sh["properties"]
        title = props["title"]
        grid = check(s.get(f"{SHEETS}/{spreadsheet}/values/{title!r}")
                     ).get("values", [])
        if not grid:
            continue
        tabs.append({"spreadsheet": spreadsheet, "sheet_id": props["sheetId"],
                     "title": title,
                     "n_cols": props["gridProperties"]["columnCount"],
                     "header": grid[0], "rows": grid[1:]})
    return tabs


def row_keys(header: list[str], row: list[str]) -> set[str]:
    cells = dict(zip(header, row))
    keys = ids_from(cells.get("Slides Edit"), cells.get("Slides View"),
                    cells.get("Slides"), cells.get("YouTube"),
                    cells.get("YouTube URL"), cells.get("Video"))
    # Talks without any deck/video URL (early blog-recovered ones) are only
    # identifiable by the slug we wrote earlier, or failing that the title.
    if cells.get("Slug"):
        keys.add("slug:" + cells["Slug"].strip())
    if cells.get("Slides Title"):
        keys.add(title_key(cells["Slides Title"]))
    return keys


def match_rows(talks: list[dict], tabs: list[dict]) -> None:
    """Annotate each tab row with the index of the YAML talk it belongs to."""
    by_key: dict[str, int] = {}
    for i, t in enumerate(talks):
        for k in talk_keys(t):
            by_key.setdefault(k, i)
    # Strongest identifier wins: two talks can share a title (the same
    # deck given twice) but never a deck id or alias.
    tiers = ("doc:", "yt:", "short:", "slug:", "title:")
    for tab in tabs:
        annotated = []
        for n, row in enumerate(tab["rows"], start=2):
            keys = row_keys(tab["header"], row)
            hits: set[int] = set()
            for tier in tiers:
                hits = {by_key[k] for k in keys
                        if k.startswith(tier) and k in by_key}
                if hits:
                    break
            annotated.append({"row": n, "keys": sorted(keys), "cells": row,
                              "talk": sorted(hits)})
        tab["rows"] = annotated


def do_dump(s: requests.Session) -> None:
    talks = yaml.safe_load(TALKS_YAML.read_text())
    tabs = load_tabs(s, TALKS_SHEET) + load_tabs(s, ADDITIONS_SHEET)
    match_rows(talks, tabs)
    seen = {i for tab in tabs for r in tab["rows"] for i in r["talk"]}
    out = {"tabs": tabs,
           "yaml_only": [{"index": i, "title": t["title"]}
                         for i, t in enumerate(talks) if i not in seen]}
    print(json.dumps(out, indent=1, ensure_ascii=False))


SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# Names that are pages under /talks/ and so can never be a talk slug.
RESERVED = {"timeline", "topics", "highlights", "feed", "index"}
RED = {"red": 0.8, "green": 0.0, "blue": 0.0}
BLACK = {"red": 0.0, "green": 0.0, "blue": 0.0}
SHORTLINKS_YAML = pathlib.Path("_data/shortlinks.yaml")
ADDITIONS_HEADER = ["Slides View", "Slides Edit", "Slides Title", "Full Event",
                    "Event Year", "Date", "YouTube", "Video Title"]


def existing_alias(talk: dict) -> str | None:
    for field in ("slides_short", "slides"):
        if m := SHORT_RE.search(talk.get(field) or ""):
            return m.group(1).lower()
    return None


def shortlink_names() -> set[str]:
    """Every alias that already resolves at mith.ro/<alias>."""
    if not SHORTLINKS_YAML.exists():
        return set()
    names = set()
    for e in yaml.safe_load(SHORTLINKS_YAML.read_text()):
        names.add(e["keyword"].lower())
        names.update(u.rsplit("/", 1)[-1].lower()
                     for u in e.get("custom_bitlinks") or [])
    return names


def validate_slugs(talks: list[dict]) -> None:
    seen: dict[str, int] = {}
    taken = shortlink_names()
    for i, t in enumerate(talks):
        slug = t.get("slug")
        if not slug or not SLUG_RE.match(slug) or slug in RESERVED:
            sys.exit(f"talk {i} ({t['title'][:50]}): bad, reserved or missing slug {slug!r}")
        if slug in seen:
            sys.exit(f"duplicate slug {slug}: talks {seen[slug]} and {i}")
        seen[slug] = i
        # A proposed slug that collides with an unrelated short link would
        # later clash at mith.ro/<slug>.
        if slug != existing_alias(t) and slug in taken:
            print(f"WARNING: proposed slug {slug} (talk {i}) is already a "
                  f"mith.ro short link", file=sys.stderr)


def col_letter(idx: int) -> str:
    return chr(ord("A") + idx)


def do_slugs(s: requests.Session) -> None:
    """Write the Slug column: existing aliases in black, proposals in red."""
    talks = yaml.safe_load(TALKS_YAML.read_text())
    validate_slugs(talks)
    tabs = load_tabs(s, TALKS_SHEET) + load_tabs(s, ADDITIONS_SHEET)
    match_rows(talks, tabs)
    seen = {i for tab in tabs for r in tab["rows"] for i in r["talk"]}

    # Talks that exist in no sheet get a row in the additions sheet first,
    # so the review surface is complete.
    additions = next(t for t in tabs if t["spreadsheet"] == ADDITIONS_SHEET)
    new_rows = []
    for i, t in enumerate(talks):
        if i in seen:
            continue
        new_rows.append([t.get("slides") or "", t.get("slides_edit") or "",
                         t["title"], t.get("event") or "",
                         str(t["year"]) if t["year"] else "",
                         t.get("date") or "", t.get("video") or "",
                         t.get("video_title") or ""])
        start = len(additions["rows"]) + 2
        additions["rows"].append({"row": start, "keys": [], "cells": new_rows[-1],
                                  "talk": [i]})
    if new_rows:
        check(s.post(f"{SHEETS}/{ADDITIONS_SHEET}/values/{additions['title']!r}"
                     f"!A1:append",
                     params={"valueInputOption": "RAW",
                             "insertDataOption": "INSERT_ROWS"},
                     json={"values": new_rows}))
        print(f"appended {len(new_rows)} talks to the additions sheet",
              file=sys.stderr)

    for tab in tabs:
        if tab["title"] == "Pivot Table 1":
            continue
        header = tab["header"]
        col = header.index("Slug") if "Slug" in header else len(header)
        reqs = []
        if col >= tab["n_cols"]:
            reqs.append({"appendDimension": {"sheetId": tab["sheet_id"],
                                             "dimension": "COLUMNS",
                                             "length": col + 1 - tab["n_cols"]}})
        if "Slug" not in header:
            # Header cell takes its look from the neighbouring header.
            reqs.append({"copyPaste": {
                "source": {"sheetId": tab["sheet_id"], "startRowIndex": 0,
                           "endRowIndex": 1, "startColumnIndex": col - 1,
                           "endColumnIndex": col},
                "destination": {"sheetId": tab["sheet_id"], "startRowIndex": 0,
                                "endRowIndex": 1, "startColumnIndex": col,
                                "endColumnIndex": col + 1},
                "pasteType": "PASTE_FORMAT"}})
            reqs.append({"updateDimensionProperties": {
                "range": {"sheetId": tab["sheet_id"], "dimension": "COLUMNS",
                          "startIndex": col, "endIndex": col + 1},
                "properties": {"pixelSize": 200}, "fields": "pixelSize"}})
        values = [["Slug"]]
        written = 0
        for r in tab["rows"]:
            if not r["talk"]:
                values.append([""] if "Slug" not in header else [None])
                continue
            t = talks[r["talk"][0]]
            values.append([t["slug"]])
            proposed = t["slug"] != existing_alias(t)
            reqs.append({"repeatCell": {
                "range": {"sheetId": tab["sheet_id"],
                          "startRowIndex": r["row"] - 1, "endRowIndex": r["row"],
                          "startColumnIndex": col, "endColumnIndex": col + 1},
                "cell": {"userEnteredFormat": {"textFormat": {
                    "foregroundColor": RED if proposed else BLACK,
                    "bold": proposed}}},
                "fields": "userEnteredFormat.textFormat(foregroundColor,bold)"}})
            written += 1
        # (None cells are skipped by the API, so existing Slug values on
        # rows that match no talk are left untouched.)
        check(s.post(f"{SHEETS}/{tab['spreadsheet']}:batchUpdate",
                     json={"requests": reqs}))
        rng = f"{tab['title']!r}!{col_letter(col)}1:{col_letter(col)}{len(values)}"
        check(s.put(f"{SHEETS}/{tab['spreadsheet']}/values/{rng}",
                    params={"valueInputOption": "RAW"},
                    json={"range": rng, "majorDimension": "ROWS",
                          "values": values}))
        print(f"{tab['title']}: {written} slugs in column {col_letter(col)}",
              file=sys.stderr)


THUMBS_YAML = pathlib.Path("_data/thumbs.yaml")
PRES_RE = re.compile(r"presentation/d/(?!e/)([\w-]+)")


def deck_id(talk: dict) -> str | None:
    for field in ("slides_edit", "slides", "slides_embed"):
        if m := PRES_RE.search(talk.get(field) or ""):
            return m.group(1)
    return None


def ensure_column(tab: dict, name: str, after: str,
                  width: int = 90) -> tuple[int, list[dict]]:
    """Return (column index, batchUpdate requests) for header `name`,
    inserting it right after column `after` when absent. The tab's
    in-memory header/rows are shifted to match."""
    header = tab["header"]
    if name in header:
        return header.index(name), []
    col = header.index(after) + 1
    sid = tab["sheet_id"]
    if col >= tab["n_cols"]:
        # Past the grid's edge: append (inheritFromBefore would copy the
        # red/bold proposal formatting from the Slug cells).
        grow = {"appendDimension": {"sheetId": sid, "dimension": "COLUMNS",
                                    "length": col + 1 - tab["n_cols"]}}
        tab["n_cols"] = col + 1
    else:
        grow = {"insertDimension": {"range": {"sheetId": sid, "dimension": "COLUMNS",
                                              "startIndex": col, "endIndex": col + 1},
                                    "inheritFromBefore": False}}
        tab["n_cols"] += 1
    reqs = [
        grow,
        # Header cell takes its look from the neighbouring header.
        {"copyPaste": {"source": {"sheetId": sid, "startRowIndex": 0,
                                  "endRowIndex": 1, "startColumnIndex": col - 1,
                                  "endColumnIndex": col},
                       "destination": {"sheetId": sid, "startRowIndex": 0,
                                       "endRowIndex": 1, "startColumnIndex": col,
                                       "endColumnIndex": col + 1},
                       "pasteType": "PASTE_FORMAT"}},
        {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS",
                      "startIndex": col, "endIndex": col + 1},
            "properties": {"pixelSize": width}, "fields": "pixelSize"}},
    ]
    header.insert(col, name)
    for r in tab["rows"]:
        if len(r["cells"]) >= col:
            r["cells"].insert(col, "")
    return col, reqs


def cell_format(tab: dict, row: int, col: int, proposed: bool) -> dict:
    return {"repeatCell": {
        "range": {"sheetId": tab["sheet_id"], "startRowIndex": row - 1,
                  "endRowIndex": row, "startColumnIndex": col,
                  "endColumnIndex": col + 1},
        "cell": {"userEnteredFormat": {"textFormat": {
            "foregroundColor": RED if proposed else BLACK,
            "bold": proposed}}},
        "fields": "userEnteredFormat.textFormat(foregroundColor,bold)"}}


def write_column(s: requests.Session, tab: dict, col: int,
                 values: list[list[str | None]], reqs: list[dict]) -> None:
    """Apply format/structure requests, then the column values (None
    cells are skipped by the API, i.e. left untouched)."""
    if reqs:
        check(s.post(f"{SHEETS}/{tab['spreadsheet']}:batchUpdate",
                     json={"requests": reqs}))
    rng = f"{tab['title']!r}!{col_letter(col)}1:{col_letter(col)}{len(values)}"
    check(s.put(f"{SHEETS}/{tab['spreadsheet']}/values/{rng}",
                params={"valueInputOption": "RAW"},
                json={"range": rng, "majorDimension": "ROWS",
                      "values": values}))


def do_strips(s: requests.Session) -> None:
    """Add a Strips column after Slug; propose 'yes' (red) for every
    talk whose deck has a public thumbnail. Filled cells are never
    overwritten — the column is Tim's to edit."""
    talks = yaml.safe_load(TALKS_YAML.read_text())
    validate_slugs(talks)
    thumbs = set(yaml.safe_load(THUMBS_YAML.read_text())["slides"])
    tabs = load_tabs(s, TALKS_SHEET) + load_tabs(s, ADDITIONS_SHEET)
    match_rows(talks, tabs)
    for tab in tabs:
        if "Slug" not in tab["header"]:
            continue
        fresh = "Strips" not in tab["header"]
        col, reqs = ensure_column(tab, "Strips", "Slug")
        values: list[list[str | None]] = [["Strips"] if fresh else [None]]
        proposed = 0
        for r in tab["rows"]:
            cells = r["cells"]
            current = cells[col].strip() if len(cells) > col else ""
            t = talks[r["talk"][0]] if r["talk"] else None
            if t and not current and deck_id(t) in thumbs:
                values.append(["yes"])
                reqs.append(cell_format(tab, r["row"], col, proposed=True))
                proposed += 1
            else:
                values.append([None])
        write_column(s, tab, col, values, reqs)
        print(f"{tab['title']}: {proposed} strips proposals in column "
              f"{col_letter(col)}", file=sys.stderr)


def do_import(s: requests.Session, accept: bool = False) -> None:
    """Pull the Slug and Strips columns back into talks.yaml. With
    accept=True (Tim has finished reviewing) the imported cells are also
    turned black; otherwise colours are left exactly as they are."""
    import copy

    import talks_yaml

    talks = yaml.safe_load(TALKS_YAML.read_text())
    tabs = load_tabs(s, TALKS_SHEET) + load_tabs(s, ADDITIONS_SHEET)
    match_rows(talks, tabs)
    wanted: dict[int, dict] = {}
    origin: dict[int, str] = {}
    accepted: list[tuple[dict, int, int]] = []
    for tab in tabs:
        if "Slug" not in tab["header"]:
            continue
        c_slug = tab["header"].index("Slug")
        c_strips = (tab["header"].index("Strips")
                    if "Strips" in tab["header"] else None)
        for r in tab["rows"]:
            if not r["talk"]:
                continue
            i, cells = r["talk"][0], r["cells"]
            slug = (cells[c_slug] if len(cells) > c_slug else "").strip()
            if not slug:
                continue
            strips = (c_strips is not None and len(cells) > c_strips
                      and cells[c_strips].strip().lower() == "yes")
            val = {"slug": slug, "strips": strips}
            where = f"{tab['title']} row {r['row']}"
            if i in wanted and wanted[i] != val:
                sys.exit(f"conflict for {talks[i]['title'][:50]}: "
                         f"{origin[i]} vs {where}")
            wanted[i], origin[i] = val, where
            accepted.append((tab, r["row"], c_slug))
            if c_strips is not None:
                accepted.append((tab, r["row"], c_strips))

    updates: dict[int, dict] = {}
    changes: list[str] = []
    for i, val in wanted.items():
        t, fields = talks[i], {}
        if val["slug"] != t.get("slug"):
            fields["slug"] = val["slug"]
            changes.append(f"{t['slug']} -> {val['slug']}")
        if val["strips"] != bool(t.get("strips")):
            fields["strips"] = True if val["strips"] else None
            changes.append(f"{t['slug']}: strips {'on' if val['strips'] else 'off'}")
        if fields:
            updates[i] = fields
    # Validate the post-import state before touching the file.
    future = copy.deepcopy(talks)
    for i, fields in updates.items():
        for k, v in fields.items():
            if v is None:
                future[i].pop(k, None)
            else:
                future[i][k] = v
    validate_slugs(future)
    if updates:
        talks_yaml.set_fields(updates)

    if accept:
        by_sheet: dict[str, list[dict]] = {}
        for tab, row, col in accepted:
            by_sheet.setdefault(tab["spreadsheet"], []).append(
                cell_format(tab, row, col, proposed=False))
        for spreadsheet, reqs in by_sheet.items():
            check(s.post(f"{SHEETS}/{spreadsheet}:batchUpdate",
                         json={"requests": reqs}))
    print("\n".join(changes) or "no changes", file=sys.stderr)
    print(f"import: {len(changes)} changes; {len(accepted)} cells "
          f"{'marked accepted' if accept else 'read (colours untouched)'}",
          file=sys.stderr)


def do_shortlinks(s: requests.Session) -> None:
    """Append a private mith.ro/<slug> row to the short-links sheet for
    every talk that has no short link at all, pointing at the deck (else
    the recording). Tim flips Visibility; format_sheets.py sync then
    imports the rows as sheet-native entries."""
    from datetime import date

    from format_sheets import SHORTLINKS_SHEET

    talks = yaml.safe_load(TALKS_YAML.read_text())
    validate_slugs(talks)
    grid = check(s.get(f"{SHEETS}/{SHORTLINKS_SHEET}/values/A2:A100000")
                 ).get("values", [])
    in_sheet = {re.sub(r"^(bit\.ly|j\.mp|mith\.ro)/", "", r[0]).lower()
                for r in grid if r}
    taken = in_sheet | shortlink_names()
    today = date.today().isoformat()
    rows, skipped = [], []
    for t in talks:
        if existing_alias(t):
            continue
        deck = next((t.get(f) for f in ("slides_edit", "slides")
                     if "docs.google.com" in (t.get(f) or "")), None)
        target = deck or t.get("video")
        if not target:
            skipped.append(t["slug"])
            continue
        if t["slug"] in taken:
            continue
        rows.append([f"mith.ro/{t['slug']}", "private",
                     t.get("talk_title") or t["title"], today, target, "",
                     "", "talk short link — proposed, review visibility"])
    if rows:
        check(s.post(f"{SHEETS}/{SHORTLINKS_SHEET}/values/'short links'!A1:append",
                     params={"valueInputOption": "RAW",
                             "insertDataOption": "INSERT_ROWS"},
                     json={"values": rows}))
    print(f"shortlinks: appended {len(rows)} private rows"
          + (f"; no deck or video for: {', '.join(skipped)}" if skipped else ""),
          file=sys.stderr)
    for r in rows:
        print(f"  {r[0]} -> {r[4]}", file=sys.stderr)


def main() -> None:
    actions = {"dump": do_dump, "slugs": do_slugs, "strips": do_strips,
               "import": do_import, "shortlinks": do_shortlinks}
    args = sys.argv[1:]
    accept = "--accept" in args
    args = [a for a in args if a != "--accept"]
    if len(args) != 1 or args[0] not in actions or (accept and args[0] != "import"):
        sys.exit(f"usage: {sys.argv[0]} {{{'|'.join(actions)}}} [import --accept]")
    if args[0] == "import":
        do_import(session(), accept=accept)
    else:
        actions[args[0]](session())


if __name__ == "__main__":
    main()

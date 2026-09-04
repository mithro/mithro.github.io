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
    uv run scripts/talks_sheet.py slugs   # write/refresh the Slug column

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
        if not slug or not SLUG_RE.match(slug):
            sys.exit(f"talk {i} ({t['title'][:50]}): bad or missing slug {slug!r}")
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


def main() -> None:
    actions = {"dump": do_dump, "slugs": do_slugs}
    if len(sys.argv) != 2 or sys.argv[1] not in actions:
        sys.exit(f"usage: {sys.argv[0]} {{{'|'.join(actions)}}}")
    actions[sys.argv[1]](session())


if __name__ == "__main__":
    main()

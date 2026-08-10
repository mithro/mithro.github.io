#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "pyyaml"]
# ///
"""Format the mith.ro Google Sheets in place via the Sheets API.

Auth comes from gcloud user credentials with Drive scope:

    gcloud auth login --enable-gdrive-access

Then:

    uv run scripts/format_sheets.py shortlinks   # rewrite + format the short-links sheet
    uv run scripts/format_sheets.py talks        # format the talks-additions sheet
    uv run scripts/format_sheets.py trash-junk   # trash leftover xlsx/test files

If the API complains about an unregistered caller / quota project, set
GOOGLE_QUOTA_PROJECT to one of your GCP projects that has the Sheets
and Drive APIs enabled.

"shortlinks" replaces the sheet's data from _data/shortlinks.yaml
(gitignored local mirror — regenerate with scripts/fetch_bitly.py) and
so also upgrades any truncated target URLs to the full ones; "talks"
touches formatting only. Both are idempotent: existing conditional
format rules are cleared before new ones are added.
"""

import pathlib
import subprocess
import sys

import requests
import yaml

SHORTLINKS_SHEET = "1asrDy1-BwPuOSLjAM79Voz48lmDTeRBF3gWuOmRT2a8"
TALKS_SHEET = "1oaJnQU_g0scQPYJpSbo6PqmkBmN6Hft-4-gbvQwdno4"
JUNK_FILES = {
    # Leftovers from the failed Drive-MCP xlsx-conversion attempts.
    "1WVHpPzAhE2UtjMMyHM-9FWWtjXTJ0KKY": "mith.ro short links.xlsx",
    "1gum4-5tyY3W7DLPAEBeEfrmHE8R2Wd24": "zz mith.ro shortlinks raw check (trash me)",
    "1ZGb8Lv1gik3ZJKfjCEYbEO4PIWMAV_MYzh1-grGsROc": "empty failed conversion sheet",
    "1PEYfoU0odEm66THuT28PD9VicmlTtVhWI2mT6H6JyM0": "tiny conversion test sheet",
    "1JjfN4r4v5P01Z_Dl4X05DifjH2D9nIO0pgt31OTRHCg": "formatted talks copy (superseded by in-place format)",
}

SHEETS = "https://sheets.googleapis.com/v4/spreadsheets"
DRIVE = "https://www.googleapis.com/drive/v3/files"

DARK = {"red": 0x26 / 255, "green": 0x32 / 255, "blue": 0x38 / 255}
WHITE = {"red": 1, "green": 1, "blue": 1}
GREEN = {"red": 0xD9 / 255, "green": 0xEA / 255, "blue": 0xD3 / 255}
GREY = {"red": 0xEF / 255, "green": 0xEF / 255, "blue": 0xEF / 255}


def session() -> requests.Session:
    token = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {token}"
    import os
    if os.environ.get("GOOGLE_QUOTA_PROJECT"):
        s.headers["X-Goog-User-Project"] = os.environ["GOOGLE_QUOTA_PROJECT"]
    return s


def check(resp: requests.Response) -> dict:
    if not resp.ok:
        sys.exit(f"API error {resp.status_code}: {resp.text[:800]}")
    return resp.json()


def first_sheet_id(s: requests.Session, spreadsheet: str) -> tuple[int, int]:
    """Return (sheetId, existing conditional-format rule count)."""
    meta = check(s.get(
        f"{SHEETS}/{spreadsheet}",
        params={"fields": "sheets(properties.sheetId,conditionalFormats)"},
    ))
    props = meta["sheets"][0]
    return (props["properties"]["sheetId"],
            len(props.get("conditionalFormats", [])))


def header_and_dims(sheet_id: int, n_cols: int, n_rows: int,
                    widths: list[int], tab_title: str) -> list[dict]:
    """batchUpdate requests shared by both sheets."""
    reqs = [
        {"updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "title": tab_title,
                           "gridProperties": {"rowCount": n_rows,
                                              "columnCount": n_cols,
                                              "frozenRowCount": 1}},
            "fields": "title,gridProperties(rowCount,columnCount,frozenRowCount)"}},
        {"repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {"userEnteredFormat": {
                "backgroundColor": DARK,
                "textFormat": {"bold": True, "foregroundColor": WHITE},
                "wrapStrategy": "CLIP"}},
            "fields": ("userEnteredFormat(backgroundColor,textFormat,"
                       "wrapStrategy)")}},
        {"repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1},
            "cell": {"userEnteredFormat": {"verticalAlignment": "TOP"}},
            "fields": "userEnteredFormat.verticalAlignment"}},
        {"setBasicFilter": {"filter": {"range": {
            "sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": n_rows,
            "startColumnIndex": 0, "endColumnIndex": n_cols}}}},
    ]
    for i, width in enumerate(widths):
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                      "startIndex": i, "endIndex": i + 1},
            "properties": {"pixelSize": width},
            "fields": "pixelSize"}})
    return reqs


def drop_conditional_rules(sheet_id: int, count: int) -> list[dict]:
    return [{"deleteConditionalFormatRule": {"sheetId": sheet_id, "index": 0}}
            for _ in range(count)]


def do_shortlinks(s: requests.Session) -> None:
    links = yaml.safe_load(
        pathlib.Path("_data/shortlinks.yaml").read_text())
    rows = [["Keyword", "Visibility", "Title", "Created", "Target URL",
             "Custom bit.ly aliases", "Notes"]]
    for e in links:
        aliases = ", ".join(
            u.rsplit("/", 1)[-1] for u in e.get("custom_bitlinks") or [])
        rows.append([e["keyword"],
                     "public" if e["include"] else "private",
                     e.get("title") or "", str(e.get("created") or ""),
                     e["long_url"], aliases, e.get("reason") or ""])
    n_rows, n_cols = len(rows), 7

    sheet_id, old_rules = first_sheet_id(s, SHORTLINKS_SHEET)
    check(s.post(f"{SHEETS}/{SHORTLINKS_SHEET}/values/A1:ZZ100000:clear"))
    check(s.put(
        f"{SHEETS}/{SHORTLINKS_SHEET}/values/A1",
        params={"valueInputOption": "RAW"},
        json={"values": rows}))

    reqs = drop_conditional_rules(sheet_id, old_rules)
    reqs += header_and_dims(sheet_id, n_cols, n_rows,
                            [180, 90, 380, 100, 480, 200, 320], "short links")
    vis_range = {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": n_rows,
                 "startColumnIndex": 1, "endColumnIndex": 2}
    reqs.append({"setDataValidation": {
        "range": vis_range,
        "rule": {"condition": {"type": "ONE_OF_LIST",
                               "values": [{"userEnteredValue": "public"},
                                          {"userEnteredValue": "private"}]},
                 "strict": True, "showCustomUi": True}}})
    reqs.append({"repeatCell": {
        "range": vis_range,
        "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
        "fields": "userEnteredFormat.horizontalAlignment"}})
    for value, color in (("public", GREEN), ("private", GREY)):
        reqs.append({"addConditionalFormatRule": {"rule": {
            "ranges": [vis_range],
            "booleanRule": {
                "condition": {"type": "TEXT_EQ",
                              "values": [{"userEnteredValue": value}]},
                "format": {"backgroundColor": color}}}}})
    check(s.post(f"{SHEETS}/{SHORTLINKS_SHEET}:batchUpdate",
                 json={"requests": reqs}))
    print(f"shortlinks: wrote {n_rows - 1} rows and formatted in place",
          file=sys.stderr)


def do_talks(s: requests.Session) -> None:
    sheet_id, old_rules = first_sheet_id(s, TALKS_SHEET)
    n_rows, n_cols = 18, 8  # header + 17 talks
    reqs = drop_conditional_rules(sheet_id, old_rules)
    reqs += header_and_dims(
        sheet_id, n_cols, n_rows,
        [320, 120, 380, 350, 80, 110, 320, 350], "talks additions")
    reqs.append({"repeatCell": {
        "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": n_rows,
                  "startColumnIndex": 4, "endColumnIndex": 5},
        "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
        "fields": "userEnteredFormat.horizontalAlignment"}})
    check(s.post(f"{SHEETS}/{TALKS_SHEET}:batchUpdate",
                 json={"requests": reqs}))
    print("talks: formatted in place (values untouched)", file=sys.stderr)


def do_trash(s: requests.Session) -> None:
    for file_id, label in JUNK_FILES.items():
        resp = s.patch(f"{DRIVE}/{file_id}", json={"trashed": True})
        state = "trashed" if resp.ok else f"FAILED {resp.status_code}"
        print(f"{state}: {label} ({file_id})", file=sys.stderr)


def main() -> None:
    actions = {"shortlinks": do_shortlinks, "talks": do_talks,
               "trash-junk": do_trash}
    if len(sys.argv) != 2 or sys.argv[1] not in actions:
        sys.exit(f"usage: {sys.argv[0]} {{{'|'.join(actions)}}}")
    actions[sys.argv[1]](session())


if __name__ == "__main__":
    main()

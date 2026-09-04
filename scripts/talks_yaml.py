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
    # Quote only when YAML would misread a plain scalar ("!" is an
    # indicator only at the start, so a trailing "!" stays bare).
    if (re.search(r"[:#\[\]{}&*|>'\"%@`,]|^[!?\-\s]|\s$", s)
            or s in ("", "yes", "no", "true", "false", "null")):
        return yaml.safe_dump(s, default_style='"', width=4096,
                              allow_unicode=True).strip()
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

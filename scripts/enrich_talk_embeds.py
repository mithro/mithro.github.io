#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Derive slides_embed URLs for entries in _data/talks.yaml.

For each talk, find a Google Slides presentation URL — preferring the
slides_edit field, then a direct slides URL, then resolving a bit.ly /
j.mp slides alias through the local _data/shortlinks.yaml mirror (which
is gitignored; regenerate it with scripts/fetch_bitly.py first) — and
record it as a slides_embed field:

    https://docs.google.com/presentation/d/<id>/embed[?resourcekey=..]

The talks page renders that URL in an <iframe>. The file is edited
textually (comments and formatting preserved); existing slides_embed
lines are regenerated, so the script is idempotent.
"""

import pathlib
import re
import sys

import yaml

TALKS = pathlib.Path("_data/talks.yaml")
SHORTLINKS = pathlib.Path("_data/shortlinks.yaml")

PRES_RE = re.compile(r"docs\.google\.com/presentation/d/(e/)?([A-Za-z0-9_-]+)")
RKEY_RE = re.compile(r"resourcekey=([A-Za-z0-9_-]+)")
ALIAS_RE = re.compile(r"https?://(?:bit\.ly|j\.mp)/([^/?#\s]+)")


def alias_map() -> dict[str, str]:
    """Map every bit.ly/j.mp alias (keyword + custom aliases) to its long URL."""
    if not SHORTLINKS.exists():
        print(f"warning: {SHORTLINKS} missing — bit.ly slides links "
              "cannot be resolved (run scripts/fetch_bitly.py)", file=sys.stderr)
        return {}
    amap: dict[str, str] = {}
    for entry in yaml.safe_load(SHORTLINKS.read_text()):
        amap[entry["keyword"]] = entry["long_url"]
        for custom in entry.get("custom_bitlinks") or []:
            m = ALIAS_RE.match(custom)
            if m:
                amap[m.group(1)] = entry["long_url"]
    return amap


def embed_url(url: str) -> str | None:
    """Turn a Google Slides URL into its /embed form, keeping resourcekey."""
    m = PRES_RE.search(url)
    if not m:
        return None
    prefix = "e/" if m.group(1) else ""
    embed = f"https://docs.google.com/presentation/d/{prefix}{m.group(2)}/embed"
    rk = RKEY_RE.search(url)
    return f"{embed}?resourcekey={rk.group(1)}" if rk else embed


def main() -> None:
    aliases = alias_map()
    text = TALKS.read_text()
    head, sep, body = text.partition("- title:")
    chunks = ("- title:" + c for c in (sep + body).split("- title:")[1:])

    out, stats = [], {"direct": 0, "alias": 0, "none": 0}
    unresolved: list[str] = []
    for chunk in chunks:
        old_embed = next((l for l in chunk.splitlines(keepends=True)
                          if l.startswith("  slides_embed:")), None)
        lines = [l for l in chunk.splitlines(keepends=True)
                 if not l.startswith("  slides_embed:")]
        fields = dict(re.findall(r"^  (\w+): (.+)$", "".join(lines), re.M))
        embed, how = None, "none"
        for candidate in (fields.get("slides_edit"), fields.get("slides")):
            if not candidate:
                continue
            embed = embed_url(candidate)
            if embed:
                how = "direct"
                break
            am = ALIAS_RE.match(candidate)
            if am and am.group(1) in aliases:
                embed = embed_url(aliases[am.group(1)])
                if embed:
                    how = "alias"
                    break
        stats[how] += 1
        if not embed and fields.get("slides"):
            unresolved.append(f"{fields.get('title', '?')[:60]} — {fields['slides']}")
        embed_line = (f"  slides_embed: {embed}\n" if embed
                      else old_embed)  # keep hand-added embeds we can't derive
        if embed_line:
            anchor = next(i for i, l in enumerate(lines)
                          if l.startswith(("  slides_edit:", "  slides:")))
            lines.insert(anchor + 1, embed_line)
        out.append("".join(lines))

    TALKS.write_text(head + "".join(out))
    print(f"embeds: {stats['direct']} direct, {stats['alias']} via bit.ly, "
          f"{stats['none']} without", file=sys.stderr)
    if unresolved:
        print("no embed derivable for:", file=sys.stderr)
        for u in unresolved:
            print(f"  {u}", file=sys.stderr)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Split a muffet JSON report into internal and external link failures.

muffet crawls the locally served build at --origin. A failure whose link
is on that origin is an internal problem (a missing page or asset in this
build) and fails the check. Any other failure is an external site that
did not answer the GitHub runner; those often block or rate-limit
datacenter IPs, so they are reported but never fail the check.

Writes a Markdown report to --out and prints GitHub Actions outputs
(internal_failures=N, external_failures=N) to --github-output.
"""

import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", help="muffet --format=json output")
    parser.add_argument("--origin", required=True,
                        help="origin muffet crawled, e.g. http://localhost:4000")
    parser.add_argument("--display-origin", default="",
                        help="origin to show pages under, e.g. the preview URL")
    parser.add_argument("--out", required=True, help="Markdown report path")
    parser.add_argument("--github-output", help="append outputs to this file")
    args = parser.parse_args()

    origin = args.origin.rstrip("/")
    display = args.display_origin.rstrip("/") or origin

    with open(args.report, encoding="utf-8") as f:
        text = f.read().strip()
    pages = json.loads(text) if text else []

    def shown(url):
        return display + url[len(origin):] if url.startswith(origin) else url

    internal = {}  # page -> [(error, link)]
    external = {}
    for page in pages:
        for link in page.get("links") or []:
            url = link.get("url", "")
            error = link.get("error", "")
            if not error:
                continue
            is_internal = url == origin or url.startswith(origin + "/")
            bucket = internal if is_internal else external
            bucket.setdefault(shown(page["url"]), []).append(
                (error, shown(url)))

    def count(bucket):
        return sum(len(v) for v in bucket.values())

    def unique_links(bucket):
        links = {}
        for entries in bucket.values():
            for error, url in entries:
                links.setdefault(url, error)
        return links

    lines = []
    n_int = count(internal)
    if n_int:
        lines.append(f"## ❌ {n_int} broken internal link(s) or asset(s)")
        lines.append("")
        lines.append("These are pages or files missing from this build. "
                     "They fail the check.")
        lines.append("")
        lines.append("```")
        for page in sorted(internal):
            lines.append(page)
            for error, url in sorted(internal[page], key=lambda e: e[1]):
                lines.append(f"\t{error}\t{url}")
        lines.append("```")
    else:
        lines.append("## ✅ All internal links and assets are valid")
    lines.append("")

    ext_links = unique_links(external)
    if ext_links:
        lines.append(f"### ⚠️ {len(ext_links)} external link(s) did not "
                     "answer (not blocking)")
        lines.append("")
        lines.append("Often a site blocking or rate-limiting GitHub's "
                     "runners rather than a dead link. Check by hand; add "
                     "persistent false alarms to the exclude list in "
                     "`preview-verification.yml`.")
        lines.append("")
        lines.append("<details><summary>External links and the pages "
                     "that use them</summary>")
        lines.append("")
        lines.append("```")
        for url in sorted(ext_links):
            pages_using = sorted(p for p, entries in external.items()
                                 if any(u == url for _, u in entries))
            lines.append(f"{ext_links[url]}\t{url}")
            for p in pages_using[:5]:
                lines.append(f"\t\t{p}")
            if len(pages_using) > 5:
                lines.append(f"\t\t... and {len(pages_using) - 5} more")
        lines.append("```")
        lines.append("")
        lines.append("</details>")
    else:
        lines.append("All external links answered.")

    with open(args.out, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    outputs = f"internal_failures={n_int}\nexternal_failures={len(ext_links)}\n"
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as f:
            f.write(outputs)
    sys.stdout.write(outputs)


if __name__ == "__main__":
    main()

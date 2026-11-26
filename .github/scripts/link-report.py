#!/usr/bin/env python3
"""Split a muffet JSON report into internal and external link failures.

muffet crawls the deployed PR preview. A failure whose link is on the
host of --origin (the preview host) or of an --internal-origin is an
internal problem (a missing page or asset of this site) and fails the
check. So does a link muffet could not resolve to a URL at all. Any other
failure is
an external site that did not answer the GitHub runner; those often
block or rate-limit datacenter IPs, so they are reported but never fail
the check.

With --page-prefix (this PR's own https://preview.mith.ro/pr-<N>/), a
link from one of this PR's pages to anywhere else on the preview host is
itself an internal failure, whether or not it loads: such a link leaves
the preview (for the host's front page or another PR's preview) and
would be wrong on production too. Seeing those needs muffet --verbose,
which also lists the links that loaded. muffet follows links to any page
on the crawled host, so an escaping link can drag other PRs' previews
into the crawl; failures found on those pages are not this PR's and are
dropped.

Internal failures that look temporary (5xx, 408, 429, network errors)
are also counted separately as internal_transient: GitHub Pages answers
503 while it redeploys the preview host for another PR, so the workflow
crawls again when it sees any.

Writes a Markdown report to --out and prints GitHub Actions outputs
(internal_failures=N, internal_transient=N, external_failures=N,
pages_crawled=N) to
stdout and, if given, --github-output. --result-out writes the pages
crawled and every failure as JSON, for comparing two crawls.
"""

import argparse
import json
import re
import sys
from urllib.parse import urlsplit


def clean(text):
    """One line of plain text: muffet decodes %0A and friends in its
    error messages, and the report is passed on line by line."""
    return re.sub(r"[\x00-\x1f\x7f]+", " ", str(text)).strip()


def host_of(url):
    """Lower-case hostname of an absolute http(s) URL, else None."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https"):
        return None
    # "mith.ro." (with the root dot) is the same host as "mith.ro".
    return parts.hostname.rstrip(".") if parts.hostname else None


ESCAPE = "leaves this preview"


def is_transient(error, url):
    """True for errors that a later crawl could plausibly not see."""
    if error.startswith(ESCAPE):
        return False  # the link is in the page, whatever its target did
    if host_of(url) is None or error.startswith("parse "):
        # muffet could not parse the link; that is how it was written.
        return False
    if re.fullmatch(r"\d{3}", error):
        return error.startswith("5") or error in ("408", "429")
    # muffet reports a missing fragment target as "id #... not found";
    # that is a property of the page, not of the network.
    return not error.startswith("id #")


def size(text):
    """GitHub limits comments in characters but environment variables
    (which carry the report between steps) in bytes; count the larger."""
    return len(text.encode("utf-8"))


def existing_size(path):
    try:
        with open(path, encoding="utf-8") as f:
            return size(f.read())
    except FileNotFoundError:
        return 0


def truncate(lines, budget):
    """Cut at a whole line, then close any open code block and <details>."""
    note = "... report truncated to fit in a PR comment"
    out, used = [], 0
    for line in lines:
        if used + size(line) + 1 > budget - 200:  # room for the closers
            # Whole-line matches only: a URL in the data may contain
            # either marker.
            fence_open = sum(l == "```" for l in out) % 2 == 1
            details_open = (sum(l.startswith("<details>") for l in out)
                            > sum(l == "</details>" for l in out))
            if fence_open:
                out.append(note)
                out.append("```")
            else:
                out.append(f"_{note}_")
            if details_open:
                out += ["", "</details>"]
            return out
        out.append(line)
        used += size(line) + 1
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", help="muffet --format=json output")
    parser.add_argument("--origin", required=True,
                        help="origin muffet crawled, e.g. https://preview.mith.ro")
    parser.add_argument("--internal-origin", action="append", default=[],
                        help="another origin whose links count as internal, "
                             "e.g. https://mith.ro (repeatable)")
    parser.add_argument("--page-prefix", default="",
                        help="this PR's preview, e.g. https://preview.mith.ro/pr-9/: "
                             "only its pages are reported, and their links "
                             "to elsewhere on the --origin host are failures")
    parser.add_argument("--result-out",
                        help="write pages crawled and failures here as JSON")
    parser.add_argument("--max-chars", type=int, default=0,
                        help="truncate the appended report at a line boundary "
                             "to keep the whole file under this many bytes")
    parser.add_argument("--out", required=True, help="Markdown report path")
    parser.add_argument("--github-output", help="append outputs to this file")
    args = parser.parse_args()

    # The site's own absolute links (https://mith.ro/...) are just as
    # much "ours" as relative ones, whatever scheme they are written with.
    internal_hosts = set()
    for origin in [args.origin, *args.internal_origin]:
        host = host_of(origin)
        if host is None:
            parser.error(f"not an http(s) origin: {origin!r}")
        internal_hosts.add(host)

    with open(args.report, encoding="utf-8") as f:
        pages = json.load(f)  # muffet prints "[]" when nothing failed

    origin_host = host_of(args.origin)
    prefix = args.page_prefix
    if prefix and not prefix.endswith("/"):
        parser.error("--page-prefix must end with /")

    def escapes(url):
        """True for a link to the preview host outside this PR's preview."""
        if not prefix or host_of(url) != origin_host:
            return False
        return not (url.startswith(prefix) or url == prefix[:-1])

    internal = {}  # page -> [(error, link)]
    external = {}
    crawled = []   # this PR's pages
    foreign_pages = 0
    n_escapes = 0
    for page in pages:
        page_url = clean(page["url"])
        if prefix and not page_url.startswith(prefix):
            foreign_pages += 1
            continue
        crawled.append(page_url)
        for link in page.get("links") or []:
            url = clean(link.get("url", ""))
            error = clean(link.get("error", ""))
            if escapes(url):
                # Wrong even when it loads (muffet --verbose reports
                # those with a status instead of an error).
                outcome = error or f"answered {link.get('status', '?')}"
                internal.setdefault(page_url, []).append(
                    (f"{ESCAPE} ({outcome})", url))
                n_escapes += 1
                continue
            if not error:
                continue
            host = host_of(url)
            # No host means muffet could not parse the href, so it is a
            # malformed link in our own page.
            is_internal = host is None or host in internal_hosts
            bucket = internal if is_internal else external
            bucket.setdefault(page_url, []).append((error, url))

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
    n_transient = sum(is_transient(error, url)
                      for entries in internal.values() for error, url in entries)
    if n_int:
        lines.append(f"## ❌ {n_int} broken internal link(s) or asset(s)")
        lines.append("")
        lines.append("These are pages or files of this site that did not "
                     "load. They fail the check.")
        if n_escapes:
            lines.append("")
            lines.append(f"{n_escapes} of them are links that leave this "
                         f"preview (`{prefix}`) for another part of the "
                         "preview host. A page of this site must never link "
                         "there; the link is probably written without "
                         "`relative_url`.")
        if n_transient:
            lines.append("")
            lines.append(f"{n_transient} of them look temporary (server "
                         "error or network failure) and may be GitHub Pages "
                         "redeploying the preview host; re-run the check if "
                         "the links work in a browser.")
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

    if args.max_chars:
        lines = truncate(lines, args.max_chars - existing_size(args.out))
    with open(args.out, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    if args.result_out:
        def flat(bucket):
            return sorted([page, url, error] for page, entries in bucket.items()
                          for error, url in entries)
        with open(args.result_out, "w", encoding="utf-8") as f:
            json.dump({"pages": sorted(crawled),
                       "foreign_pages": foreign_pages,
                       "internal": flat(internal),
                       "external": flat(external)}, f, indent=1)

    outputs = (f"internal_failures={n_int}\n"
               f"internal_transient={n_transient}\n"
               f"external_failures={len(ext_links)}\n"
               f"pages_crawled={len(crawled)}\n")
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as f:
            f.write(outputs)
    sys.stdout.write(outputs)


if __name__ == "__main__":
    main()

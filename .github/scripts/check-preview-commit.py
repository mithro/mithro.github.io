#!/usr/bin/env python3
"""Check that the deployed preview serves the PR's commit on every page.

Every page built from _layouts/default.html carries
<meta name="git-commit" content="<sha>">. GitHub Pages and its CDN cache
each URL separately (Cache-Control: max-age=600), so the front page
showing the new commit does not prove the other pages do.

Pages checked: the front page, every page in the preview's sitemap.xml
and, with --pages-from, every page of this preview that muffet crawled.
A page showing a different commit is stale. A page with no git-commit
tag (a redirect stub, for instance) cannot be verified and is only
counted. The front page must show the commit.

With --wait SECONDS the check is repeated until it passes or the time is
up. Exits 0 when no page is stale, 1 otherwise.
"""

import argparse
import concurrent.futures
import json
import re
import sys
import time
import urllib.error
import urllib.request

META = re.compile(r'<meta name="git-commit" content="([a-f0-9]{40})"')
USER_AGENT = "mith.ro-preview-check"


def fetch(url):
    """(body, headers) of url, or (None, reason) when it does not load."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8", "replace"), response.headers
    except urllib.error.HTTPError as e:
        return None, str(e.code)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return None, str(getattr(e, "reason", e))


def commit_of(url):
    """The commit a page shows, None if it shows none, or "error: ..."."""
    body, info = fetch(url)
    if body is None:
        return f"error: {info}"
    match = META.search(body)
    return match.group(1) if match else None


def sitemap_pages(preview_url):
    body, _ = fetch(preview_url + "sitemap.xml")
    if body is None:
        return []
    return [u for u in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body)
            if u.startswith(preview_url) and not u.lower().endswith(".pdf")]


def crawled_pages(path, preview_url):
    with open(path, encoding="utf-8") as f:
        return [p["url"] for p in json.load(f)
                if isinstance(p.get("url"), str)
                and p["url"].startswith(preview_url)]


def check(preview_url, commit, pages_from):
    """One pass. Returns (stale, summary): stale maps page -> what it shows."""
    front_body, front_info = fetch(preview_url)
    max_age = None
    if front_body is None:
        return {preview_url: f"error: {front_info}"}, {"max_age": None}
    cache_control = front_info.get("Cache-Control", "")
    match = re.search(r"max-age=(\d+)", cache_control)
    if match:
        max_age = int(match.group(1))
    match = META.search(front_body)
    front_commit = match.group(1) if match else None
    if front_commit != commit:
        return ({preview_url: front_commit or "no git-commit tag"},
                {"max_age": max_age})

    pages = set(sitemap_pages(preview_url))
    if pages_from:
        pages.update(crawled_pages(pages_from, preview_url))
    pages.discard(preview_url)

    stale, verified, unverifiable = {}, 1, 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for url, shown in zip(sorted(pages), pool.map(commit_of, sorted(pages))):
            if shown == commit:
                verified += 1
            elif shown is None:
                unverifiable += 1
            else:
                stale[url] = shown
    return stale, {"max_age": max_age, "verified": verified,
                   "unverifiable": unverifiable}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview-url", required=True,
                        help="this PR's preview, e.g. https://preview.mith.ro/pr-9/")
    parser.add_argument("--commit", required=True, help="expected 40-hex commit")
    parser.add_argument("--pages-from",
                        help="muffet --format=json --verbose output; also "
                             "check every page of this preview in it")
    parser.add_argument("--wait", type=int, default=0,
                        help="keep re-checking for up to this many seconds")
    parser.add_argument("--github-output", help="append outputs to this file")
    args = parser.parse_args()
    if not args.preview_url.endswith("/"):
        parser.error("--preview-url must end with /")
    if not re.fullmatch(r"[a-f0-9]{40}", args.commit):
        parser.error("--commit must be a 40-character hex commit")

    deadline = time.monotonic() + args.wait
    while True:
        stale, summary = check(args.preview_url, args.commit, args.pages_from)
        if not stale:
            break
        shown = sorted(stale.items())
        print(f"{len(stale)} page(s) not serving {args.commit}:")
        for url, what in shown[:10]:
            print(f"  {what}\t{url}")
        if len(shown) > 10:
            print(f"  ... and {len(shown) - 10} more")
        if time.monotonic() + 5 >= deadline:
            print("Preview is not serving the expected commit on every page",
                  file=sys.stderr)
            return 1
        sys.stdout.flush()
        time.sleep(5)

    print(f"Preview serves {args.commit}: {summary['verified']} page(s) "
          f"verified, {summary['unverifiable']} without a git-commit tag")
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as f:
            # When the whole preview was first seen serving the commit, and
            # how long the CDN may keep serving a copy of any URL.
            f.write(f"ready_at={int(time.time())}\n")
            f.write(f"max_age={summary['max_age'] if summary['max_age'] is not None else 600}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

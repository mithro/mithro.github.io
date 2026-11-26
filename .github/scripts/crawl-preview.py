#!/usr/bin/env python3
"""Link-check one PR's deployed preview with muffet and report on it.

Runs muffet over https://preview.mith.ro/pr-<N>/, has link-report.py
split the result into internal failures and dead external links (which
fail the check) and other external failures (which are only reported),
then has check-preview-commit.py confirm that every page muffet crawled
serves the PR's commit.

An external link only counts as dead if it answered 404 or 410, or its
domain did not resolve, and it still does not load when requested again
here: some sites answer a crawler 404 now and then.

The crawl is repeated, up to --max-attempts times a minute apart, when
its result cannot be trusted yet:
- internal failures that look temporary. GitHub Pages answers 503 while
  it redeploys the preview host for another PR, and muffet does not
  retry a 5xx or 429 answer;
- muffet could not crawl at all (the same 503 on the front page);
- a crawled page serves a different commit, i.e. a stale cached copy.

Writes into --out-dir: verification-report.md (the PR comment body),
result.json (pages crawled and failures, for comparing two crawls) and
muffet's raw output. Appends verification_status, the counts,
have_result and report_content to --github-output. Always exits 0 unless
it is misused; the workflow fails the job from verification_status.
"""

import argparse
import json
import pathlib
import re
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request

SCRIPTS = pathlib.Path(__file__).resolve().parent

# External domains that answer GitHub's runners with an error whatever
# the link, so checking them only adds noise to every report. Each
# pattern is anchored to the URL's host so it cannot match a path of
# this site. The reasons, with the evidence, are in .github/PREVIEWS.md.
EXCLUDED_HOSTS = [
    # Block automated clients (403, or 999 for LinkedIn).
    r"([a-z0-9-]+\.)*linkedin\.com",
    r"([a-z0-9-]+\.)*docs\.google\.com",
    r"([a-z0-9-]+\.)*drive\.google\.com",
    r"([a-z0-9-]+\.)*scholar\.google\.com",
    r"([a-z0-9-]+\.)*doi\.org",
    r"([a-z0-9-]+\.)*dl\.acm\.org",
    r"([a-z0-9-]+\.)*ieeexplore\.ieee\.org",
    r"([a-z0-9-]+\.)*electronics-lab\.com",
    r"([a-z0-9-]+\.)?twitter\.com",
    r"(www\.)?x\.com",
    r"fosstodon\.org",
    r"(www\.)?crowdsupply\.com",
    # Rate-limit the runners (429).
    r"web\.archive\.org",
    r"opensource\.googleblog\.com",
    # Refuses connections from the runners.
    r"(www\.)?tsri\.org\.tw",
    # Redirects into the domains above.
    r"([a-z0-9-]+\.)*bit\.ly",
]

MUFFET_ARGS = [
    "--format=json",
    # Also list the links that loaded: a link that leaves /pr-<N>/ for
    # another part of the preview host is wrong even when it answers 200.
    "--verbose",
    "--timeout=30",
    "--max-connections=10",
    "--max-connections-per-host=5",
    "--rate-limit=20",
    "--max-retries=3",
    "--buffer-size=16384",
    "--max-response-body-size=33554432",
    *(f"--exclude=^https?://{host}([/?#].*)?$" for host in EXCLUDED_HOSTS),
    "--header=User-Agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "--header=Accept:text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,*/*;q=0.8",
    "--header=Accept-Language:en-US,en;q=0.9",
]


def printable(text, limit=2000):
    """Text safe to show inside a Markdown code block."""
    text = text[:limit].replace("`", "'")
    return "".join(c if c.isprintable() or c == "\n" else " " for c in text)


BROWSER = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")


def loads(url):
    """True if url answers with a success or redirect status."""
    request = urllib.request.Request(url, headers={
        "User-Agent": BROWSER, "Accept": "text/html,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status < 400
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False


def recovered(urls, tries, delay):
    """The urls that load on any of several spaced requests."""
    pending, alive = set(urls), set()
    for attempt in range(tries):
        if attempt:
            time.sleep(delay)
        alive |= {url for url in sorted(pending) if loads(url)}
        pending -= alive
        if not pending:
            break
    return alive


def split_report(args, raw, report, header, result, alive=None):
    """Run link-report.py over muffet's output; returns its process."""
    report.write_text("\n".join(header) + "\n\n", encoding="utf-8")
    command = [sys.executable, str(SCRIPTS / "link-report.py"), str(raw),
               "--origin", args.preview_origin,
               "--internal-origin", "https://mith.ro",
               "--internal-origin", "https://www.mith.ro",
               "--page-prefix", args.preview_url,
               "--max-chars", "60000",
               "--out", str(report),
               "--result-out", str(result)]
    if alive is not None:
        command += ["--alive", str(alive)]
    return subprocess.run(command, stdout=subprocess.PIPE, text=True)


def crawl_once(args, attempt, out):
    """One crawl. Returns (problem, counts): problem is None when the
    result can be trusted, else a (heading, detail) pair."""
    report = out / "verification-report.md"
    raw = out / "muffet-report.json"
    with open(raw, "wb") as stdout:
        muffet = subprocess.run(
            ["muffet", *MUFFET_ARGS, args.preview_url],
            stdout=stdout, stderr=subprocess.PIPE)
    stderr = muffet.stderr.decode("utf-8", "replace")
    if stderr.strip():
        print("muffet stderr:\n" + stderr)

    # muffet prints an error on stderr, and no JSON, when the crawl could
    # not run (for example the front page answered 503). No output at all
    # is never a pass, whatever the exit status.
    if raw.stat().st_size == 0:
        return ("The link checker could not crawl the preview",
                f"muffet exited with status {muffet.returncode} and "
                f"reported nothing.\n\n```\n{printable(stderr)}\n```"), {}

    header = [f"**PR:** #{args.pr_number}",
              f"**Preview:** {args.preview_url}",
              f"**Commit:** `{args.commit}`"]
    if args.label:
        header.append(f"**Crawl:** {args.label}")
    if attempt > 1:
        header.append(f"**Crawl attempts:** {attempt} (earlier ones could "
                      "not be trusted; see the workflow log)")
    result = out / "result.json"
    split = split_report(args, raw, report, header, result)
    if split.returncode == 0:
        # Ask again before calling an external link dead.
        candidates = {url for _, url, _ in
                      json.loads(result.read_text(encoding="utf-8"))["dead"]}
        if candidates:
            alive = recovered(candidates, 3, args.retry_delay // 2)
            print(f"{len(candidates)} external link(s) looked dead; "
                  f"{len(alive)} loaded when requested again")
            if alive:
                alive_file = out / "alive.txt"
                alive_file.write_text("\n".join(sorted(alive)) + "\n",
                                      encoding="utf-8")
                split = split_report(args, raw, report, header, result,
                                     alive_file)
    print(split.stdout, end="")
    if split.returncode != 0:
        # For example JSON cut short because muffet was killed.
        return ("The link checker could not crawl the preview",
                f"muffet exited with status {muffet.returncode} and its "
                "report could not be read."), {}
    counts = dict(line.split("=", 1) for line in split.stdout.splitlines())

    if counts.get("pages_crawled") == "0":
        return ("The link checker could not crawl the preview",
                "muffet reported no pages of this preview."), counts

    # The crawl read the pages a moment ago; make sure none of them was
    # a cached copy of an earlier deployment.
    stale = subprocess.run(
        [sys.executable, str(SCRIPTS / "check-preview-commit.py"),
         "--preview-url", args.preview_url, "--commit", args.commit,
         "--pages-from", str(raw)],
        stdout=subprocess.PIPE, text=True)
    print(stale.stdout, end="")
    if stale.returncode != 0:
        return ("The preview is serving pages from another commit",
                "Some pages did not show this commit right after the crawl, "
                "so its result cannot be trusted.\n\n"
                f"```\n{printable(stale.stdout)}\n```"), counts

    if counts.get("internal_transient") != "0":
        return ("temporary", ""), counts
    return None, counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview-origin", required=True,
                        help="e.g. https://preview.mith.ro")
    parser.add_argument("--preview-url", required=True,
                        help="e.g. https://preview.mith.ro/pr-9/")
    parser.add_argument("--pr-number", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--label", default="",
                        help="extra line for the report header")
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--retry-delay", type=int, default=60)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--github-output", required=True)
    args = parser.parse_args()
    if not args.preview_url.endswith("/"):
        parser.error("--preview-url must end with /")
    if not re.fullmatch(r"[0-9]+", args.pr_number):
        parser.error("--pr-number must be a number")

    out = pathlib.Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    report = out / "verification-report.md"
    result = out / "result.json"

    for attempt in range(1, args.max_attempts + 1):
        print(f"::group::Crawl attempt {attempt} of {args.max_attempts}",
              flush=True)
        result.unlink(missing_ok=True)
        problem, counts = crawl_once(args, attempt, out)
        print("::endgroup::", flush=True)
        if problem is None:
            break
        print(f"Crawl attempt {attempt} cannot be trusted: {problem[0]}",
              flush=True)
        if attempt < args.max_attempts:
            time.sleep(args.retry_delay)

    outputs = []
    if problem is not None and problem[0] != "temporary":
        # Still report on the PR, so that an older "passed" comment is
        # not left standing as the latest result.
        heading, detail = problem
        report.write_text(
            f"**PR:** #{args.pr_number}\n**Preview:** {args.preview_url}\n"
            f"**Commit:** `{args.commit}`\n\n## ❌ {heading}\n\n"
            f"This was still the case after {args.max_attempts} "
            f"attempts.\n\n{detail}\n", encoding="utf-8")
        result.unlink(missing_ok=True)
        status = "failed"
    else:
        # A trusted result, or failures that stayed "temporary" through
        # every attempt, which then count as real.
        outputs += [f"{k}={v}" for k, v in counts.items()]
        passed = (counts.get("internal_failures") == "0"
                  and counts.get("external_dead") == "0")
        status = "success" if passed else "failed"
    outputs.append(f"verification_status={status}")
    outputs.append(f"have_result={'true' if result.exists() else 'false'}")

    # The delimiter is random so that no line of the report can end the
    # value early.
    text = report.read_text(encoding="utf-8")
    delimiter = f"REPORT_{secrets.token_hex(16)}"
    outputs += [f"report_content<<{delimiter}", text.rstrip("\n"), delimiter]
    with open(args.github_output, "a", encoding="utf-8") as f:
        f.write("\n".join(outputs) + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

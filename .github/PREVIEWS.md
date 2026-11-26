# PR previews and link checking

Modelled on wafer.space's CI
([wafer-space/wafer-space.github.io](https://github.com/wafer-space/wafer-space.github.io)).

## How it works

- **`workflows/pr-preview.yml`** — on every PR against `master`: builds the
  site with `--baseurl /pr-<N>`, pushes the result into the
  [mithro/preview.mith.ro](https://github.com/mithro/preview.mith.ro)
  repository, then polls the deployed URL until the page's
  `<meta name="git-commit">` matches the PR's HEAD commit and comments the
  preview link on the PR. Each PR also gets a slugified alias directory
  (`pr-12-fix-title-wrapping/`) that redirects to `pr-12/`.
- **`workflows/preview-verification.yml`** — link-checks the deployed
  preview with [muffet](https://github.com/raviqqe/muffet), so it checks
  exactly what a reviewer sees. See "Link checking" below.
- **`workflows/cleanup-previews.yml`** — every 15 minutes, removes preview
  directories whose PR has closed and marks their GitHub deployments
  inactive.

Previews are served at `https://preview.mith.ro/pr-<N>/` — the
`preview.mith.ro` repository has that custom domain configured, backed by a
Cloudflare DNS-only CNAME (`preview` → `mithro.github.io`, matching the
apex record). An index of active previews lives at
`https://preview.mith.ro/`.

The commit-hash meta tag comes from `site.github.build_revision`
(jekyll-github-metadata, part of the github-pages gem), which works on the
classic Pages builder, in Actions, and locally — no custom plugin needed.

## Link checking

`preview-verification.yml` has two jobs.

**`verify-preview`** publishes a result as soon as it can:

1. It waits (up to 15 minutes) until the preview serves the PR's head
   commit: the `git-commit` hash on the front page and on every page in
   the preview's `sitemap.xml` must match
   (`scripts/check-preview-commit.py`).
2. It crawls `https://preview.mith.ro/pr-<N>/` with the latest muffet
   release (`scripts/crawl-preview.py`).
3. `scripts/link-report.py` splits the result:
   - **Internal failures fail the check.** Internal is any link to
     `preview.mith.ro` or `mith.ro`.
   - **A link that leaves `/pr-<N>/` for anywhere else on the preview
     host fails the check even if it loads**, whether it points at the
     host's front page, a path missing its baseurl or another PR's
     preview. A page of this site must never contain one; it usually
     means a link written without `relative_url`. muffet runs with
     `--verbose` so that links which loaded are listed too.
   - **A dead external link fails the check.** Dead means it answered
     404 or 410, or its domain no longer resolves, and it still did not
     load when requested three more times over a minute. The second look
     matters: hackaday.io answered the runners 404 in three old reports
     for a page that loads.
   - **Other external failures are only reported** (403, 429, 5xx,
     timeouts). That is what a site blocking or rate-limiting GitHub's
     runners looks like, so it does not show the link is dead.
4. It re-reads every page muffet crawled and checks the `git-commit`
   hash again, so a crawl that read a stale cached page is not trusted.
5. The report lands as a PR comment (previous reports are archived into
   `<details>` blocks). Manual (`workflow_dispatch`) runs do not comment.

The crawl is repeated, up to three times a minute apart, while its result
cannot be trusted: internal failures that look temporary (5xx, 408, 429
or a network error), muffet unable to start, or a page showing another
commit. GitHub Pages answers 503 while it redeploys the preview host for
another PR, and muffet's `--max-retries` only retries requests that time
out, never a 5xx or 429 answer. Whatever still fails on the last crawl
fails the check. If the job fails before it has a result, the PR gets a
"did not run to completion" comment so an older pass is not left as the
latest word.

**`sanity-check`** runs after `verify-preview` and does not hold up its
comment or its check status. GitHub Pages serves every URL with
`Cache-Control: max-age=600`, so for ten minutes after a deployment the
CDN may hand out a copy of a page from the deployment before. The job
waits until `max-age` plus a minute after the preview was first seen
serving the commit, crawls again in the same way, and compares the two
crawls (`scripts/compare-link-results.py`): the same pages must have
been crawled and the same internal failures found. External failures may
differ. If the crawls agree the job simply passes; if not, it fails and
comments on the PR that the first result should not be relied on. A
newer push cancels the whole run, including a waiting `sanity-check`.

muffet follows links to any page on the host it crawls, so a link that
leaves `/pr-<N>/` can drag other PRs' previews into the crawl. The link
itself is reported; failures on those other pages are not this PR's and
are left out.

## Link-checker exclusions

Domains that answer GitHub's runners with an error whatever the link
are excluded (in `scripts/crawl-preview.py`) so that the report stays
readable. An excluded link is not fetched at all. If a site answers the
runners 404 for pages that exist, excluding it is also the way to stop
it failing the check. Each pattern is anchored to the
URL's host, so it cannot match a path of this site.

Added in November 2026, from the 40 failed reports posted on PRs #2 to
#8 (each report shows only muffet's first 60 lines, so the counts are
lower bounds):

| Domain | Seen | Why |
| --- | --- | --- |
| `twitter.com` (any subdomain) | 403, 18 reports | Refuses clients that are not logged-in browsers. |
| `x.com` | none yet | Same service as twitter.com; excluded so a link updated to the new name does not bring the 403s back. |
| `fosstodon.org` | 403, 25 reports | Blocks the runners' datacenter addresses. |
| `crowdsupply.com` | 403, 20 reports | Bot protection in front of the site. |
| `web.archive.org` | 429, 25 reports | Rate-limits; the site has 31 distinct Wayback links, which a crawl requests in a burst. |
| `opensource.googleblog.com` | 429, 17 reports | Rate-limits the runners. |
| `tsri.org.tw` | connection never opens, 25 reports | Does not accept connections from the runners' network. |

Older exclusions: LinkedIn, ACM (`dl.acm.org`) and `doi.org`, IEEE
Xplore, Google Docs/Drive/Scholar and electronics-lab.com block
automated clients; `bit.ly` redirects into those.

Everything else, including YouTube and every internal page, PDF and
thumbnail, is checked. The cost of an exclusion is that a link to that
domain which really is dead goes unnoticed, so check those by hand when
editing them.

## One-time setup (already done)

1. Repository `mithro/preview.mith.ro` with Pages enabled (branch `main`,
   root) and custom domain `preview.mith.ro`. Contains `.nojekyll` (so built
   sites are served verbatim), `CNAME` (binds the custom domain — for
   branch-based Pages the file in the branch is authoritative) and a
   deny-all `robots.txt` (previews must not be crawled or indexed); the
   deploy workflow re-creates all three every run.
2. Cloudflare DNS: CNAME `preview` → `mithro.github.io`, DNS-only, in the
   mith.ro zone.
3. An ed25519 deploy key with write access on `preview.mith.ro`; its private
   half stored as the `PREVIEW_KEY` Actions secret on this repository.

`PREVIEW_ORIGIN` (set in all three workflow files) is the single knob if the
preview host ever moves again.

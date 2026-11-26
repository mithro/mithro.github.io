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
- **`workflows/preview-verification.yml`** — waits for the same
  commit-verified deployment, then runs
  [muffet](https://github.com/raviqqe/muffet) over the deployed preview,
  so it checks exactly what a reviewer sees. A broken internal page or
  asset fails the check. "Internal" is anything on `preview.mith.ro` or
  `mith.ro`, so a link written without `relative_url` (which lands outside
  `/pr-<N>/`) fails too. External links are checked but only reported,
  because many sites block or rate-limit GitHub's runners. The report
  lands as a PR comment (previous reports are archived into `<details>`
  blocks), with internal failures first and external ones in a collapsed
  list. `.github/scripts/link-report.py` does the split. Pages can answer
  503 while it redeploys the preview host for another PR, so when internal
  failures look temporary (5xx, 408, 429 or a network error) the whole
  crawl is repeated, up to three times a minute apart; whatever still
  fails on the last crawl fails the check.
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

## Link-checker exclusions

External links never fail the check, but domains that always error on
GitHub's runners are excluded in `preview-verification.yml` so the report
stays readable:

- Block automated clients: LinkedIn, ACM/doi.org, IEEE Xplore, Google
  Docs/Drive/Scholar, electronics-lab.com, Twitter/X, fosstodon.org and
  crowdsupply.com (403s).
- Rate-limit: web.archive.org and opensource.googleblog.com (429s).
- Refuse connections from the runners: tsri.org.tw (connect timeout).
- Redirect into blocked domains: bit.ly.

Each pattern is anchored to the URL's host, so it cannot match a path of
this site. The preview host's front page (`https://preview.mith.ro/`) is
excluded as well: it lists every open PR's preview and muffet follows
links to any page on the host it crawls, so one stray link would pull
the other previews into the crawl. Failures on pages outside this PR's
`/pr-<N>/` are dropped from the report for the same reason.

Everything else, including YouTube and every internal page, PDF and
thumbnail, is checked. `--max-retries=3` only retries requests that time
out; muffet does not retry a 5xx or 429 answer, which is why the workflow
repeats the crawl itself. muffet is pinned by `MUFFET_VERSION` in the
workflow.

Known gap: a link written as `/` without `relative_url` lands on that
front page, which answers 200, so the link check cannot see it.

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

# PR previews and link checking

Modelled on wafer.space's CI
([wafer-space/wafer-space.github.io](https://github.com/wafer-space/wafer-space.github.io)).

## How it works

- **`workflows/pr-preview.yml`** — on every PR against `master`: builds the
  site with `--baseurl /preview.mith.ro/pr-<N>`, pushes the result into the
  [mithro/preview.mith.ro](https://github.com/mithro/preview.mith.ro)
  repository, then polls the deployed URL until the page's
  `<meta name="git-commit">` matches the PR's HEAD commit and comments the
  preview link on the PR. Each PR also gets a slugified alias directory
  (`pr-12-fix-title-wrapping/`) that redirects to `pr-12/`.
- **`workflows/preview-verification.yml`** — builds the PR's site itself,
  serves `_site` on `http://localhost:4000` and runs
  [muffet](https://github.com/raviqqe/muffet) over it. A broken internal
  page or asset fails the check. External links are checked too but only
  reported, because many sites block or rate-limit GitHub's runners. The
  report lands as a PR comment (previous reports are archived into
  `<details>` blocks), with internal failures first and external ones in a
  collapsed list. `.github/scripts/link-report.py` does the split. Checking
  a local build rather than preview.mith.ro means a Pages redeploy for
  another PR cannot cause 503s in this check.
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

Everything else, including YouTube and every internal page, PDF and
thumbnail, is checked. `--max-retries=3` absorbs transient DNS/network
failures. muffet is pinned by `MUFFET_VERSION` in the workflow.

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

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
- **`workflows/preview-verification.yml`** — waits for the same
  commit-verified deployment, then runs
  [muffet](https://github.com/raviqqe/muffet) over the deployed preview,
  checking every internal page, asset and external link. The report lands as
  a PR comment (previous reports are archived into `<details>` blocks) and
  broken links fail the check.
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

Domains excluded in `preview-verification.yml` either block automated
clients outright (LinkedIn, ACM/doi.org, Google Docs/Drive/Scholar,
electronics-lab.com, IEEE Xplore and Twitter/X — the last two only
from datacenter IPs) or redirect into blocked domains (bit.ly). Everything
else — including YouTube, archive.org and all internal pages, PDFs and
thumbnails — is checked. `--max-retries=3` absorbs transient DNS/network
failures.

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

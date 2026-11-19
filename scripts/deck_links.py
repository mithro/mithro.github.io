#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "requests"]
# ///
"""Pick the link visitors get for each talk's slide deck.

    uv run scripts/deck_links.py

Writes _data/deck_links.yaml ({slug: {via, url}}) and prints a report of
every deck that could not use its published-to-the-web link. Each
candidate is fetched WITHOUT credentials — the question is what an
anonymous visitor sees — in this order:

  pub    the deck published to the web: talks.yaml `slides_pub` (the
         /d/e/2PACX-…/pub link from Slides' "Publish to the web"
         dialog); a /d/e/ published id already in the talk's URLs; any
         /d/e/ link a PUBLIC short-link redirect (redirects/*.md) points
         at whose page shows exactly the talk's deck: the full, ordered
         list of slide object ids must equal the strip manifest's AND the
         page title must equal the deck's own title. Alias names don't
         line up with slugs, and a copied deck keeps its slide ids even
         after its text is edited — per-event copies (CHIPS Alliance vs
         SSCD 2021) differ only in title; else
         /d/<id>/pub, which Google serves for link-shared decks
  embed  /d/<id>/embed, the slideshow. Two kinds of deck land here: ones
         link-shared but never published to the web (no /pub exists), and
         ones published to the web but not link-shared, whose /pub only
         exists under their /d/e/ id — add it as slides_pub
  edit   /d/<id>/edit, the view-only editor of a link-shared deck
  none   nothing opens anonymously; url is null and the site shows the
         slides without linking to the deck

Every url already has a query string, so a single slide is
url + "&slide=id.<objectId>" for pub/embed and url + "#slide=id.<id>" for
edit (strip frames). Short links (bit.ly, j.mp, mith.ro, wafer.space)
are not rewritten — their targets live outside this repo — but ones
that end at a sign-in page are reported.
"""
import html
import pathlib
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import requests
import yaml

TALKS = pathlib.Path("_data/talks.yaml")
STRIPS = pathlib.Path("_data/strips.yaml")
REDIRECTS = pathlib.Path("redirects")
OUT = pathlib.Path("_data/deck_links.yaml")
DOC_RE = re.compile(r"docs\.google\.com/presentation/d/(?!e/)([\w-]+)")
PUB_RE = re.compile(r"docs\.google\.com/presentation/d/e/([\w-]+)")
KEY_RE = re.compile(r"resourcekey=([\w-]+)")
SHORT_RE = re.compile(r"^https?://(bit\.ly|j\.mp|mith\.ro|wafer\.space)/")
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"}
FIELDS = ("slides_pub", "slides_edit", "slides", "slides_embed")


def opens(url: str) -> bool:
    """True if an anonymous visitor gets the deck (not a sign-in page).

    Streams and stops early: published decks are 5-15 MB pages, and the
    status plus final host are what distinguish them from a sign-in wall.
    """
    try:
        with requests.get(url, headers=UA, timeout=60, stream=True) as r:
            return (r.status_code == 200
                    and r.url.startswith("https://docs.google.com/")
                    and "accounts.google.com" not in r.url)
    except requests.RequestException as e:
        print(f"  {url}: {e}", file=sys.stderr)
        return False


def public_pub_links() -> dict[str, str]:
    """alias -> /d/e/…/pub URL, from the committed (public) redirect stubs.

    Only the public stubs: the gitignored short-link data holds private
    targets and must never feed anything that gets committed.
    """
    out = {}
    for f in REDIRECTS.glob("*.md"):
        fm = yaml.safe_load(f.read_text().split("---")[1]) or {}
        url = fm.get("redirect_to") or ""
        if PUB_RE.search(url) and "/pub" in url:
            out[fm["permalink"].strip("/")] = url
    return out


# A Slides viewer page lists every slide in its JS as
#   ["<objectId>",<0-based position>,"<slide title, maybe empty>",[],[<videos>…
# (big decks render only the first slides as SVG, so the SVG is no guide;
# the videos field is [] unless the slide embeds one).
SLIDE_RE = re.compile(r'\["([\w-]+)",(\d+),"(?:[^"\\]|\\.)*",\[\],\[')


TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)


def clean_title(raw: str) -> str:
    return html.unescape(raw).removesuffix(" - Google Slides").strip()


def slides_shown(url: str) -> tuple[tuple[str, ...], str] | None:
    """(ordered slide object ids, deck title) an anonymous visitor sees."""
    try:
        r = requests.get(url, headers=UA, timeout=180)
    except requests.RequestException as e:
        print(f"  {url}: {e}", file=sys.stderr)
        return None
    if r.status_code != 200:
        return None
    pos: dict[int, str] = {}
    for oid, n in SLIDE_RE.findall(r.text):
        pos.setdefault(int(n), oid)
    t = TITLE_RE.search(r.text)
    ids = tuple(pos[n] for n in sorted(pos))
    return (ids, clean_title(t.group(1)) if t else "") if ids else None


def deck_title(urls: list[str]) -> str | None:
    """The deck's own title, from the first of urls that opens anonymously.

    Streams only until </title>: the pages themselves run to 15 MB.
    """
    for url in urls:
        try:
            with requests.get(url, headers=UA, timeout=60, stream=True) as r:
                if r.status_code != 200:
                    continue
                head = ""
                for chunk in r.iter_content(1 << 14, decode_unicode=True):
                    head += chunk
                    if (m := TITLE_RE.search(head)) or len(head) > 1 << 20:
                        break
                if m:
                    return clean_title(m.group(1))
        except requests.RequestException:
            continue
    return None


def published_by_slides() -> dict[tuple[tuple[str, ...], str], str]:
    """(slide-id list, title) -> public /d/e/ link, for every public redirect."""
    links = sorted(set(public_pub_links().values()))
    with ThreadPoolExecutor(8) as pool:
        shown = list(pool.map(slides_shown, links))
    out = {}
    for url, got in zip(links, shown):
        if got:
            out.setdefault(got, url)
            PAGE_SLIDES[url] = got[0]
    return out


STRIP_IDS = ({k: tuple(v["slides"]) for k, v in (yaml.safe_load(STRIPS.read_text()) or {}).items()}
             if STRIPS.exists() else {})
PUB_BY_SLIDES: dict = {}  # filled in main(): fetching ~80 decks is slow
PAGE_SLIDES: dict = {}    # public /d/e/ link -> the slide ids it shows


def talk_aliases(t: dict) -> list[str]:
    """The talk's own short-link names: its slug and any short link's."""
    names = [t["slug"]]
    for f in ("slides_short", "slides"):
        if SHORT_RE.match(t.get(f) or ""):
            names.append(t[f].rstrip("/").rsplit("/", 1)[-1])
    return list(dict.fromkeys(names))


def near_misses(t: dict) -> list[str]:
    """The talk's OWN public published link, when it shows other slides.

    Only links under the talk's own names count: other talks reuse many
    slides, so overlap alone would flag sibling decks. A mismatch usually
    means a stale publication or a link pointing at a later revision.
    """
    ours = STRIP_IDS.get(t["slug"]) or ()
    links = public_pub_links()
    out = []
    for alias in talk_aliases(t):
        url = links.get(alias)
        ids = PAGE_SLIDES.get(url)
        if url and ids != ours:
            if ids is None:
                out.append(f"mith.ro/{alias} is a published link that shows no slides anonymously")
            else:
                shared = len(set(ours) & set(ids))
                out.append(f"mith.ro/{alias} is a published link showing {shared}/{len(ours)} "
                           f"of this deck's slides (+{len(set(ids) - set(ours))} others) — "
                           "a different revision or deck")
    return out


def candidates(t: dict) -> list[tuple[str, str]]:
    urls = [t.get(f) or "" for f in FIELDS]
    key = next((m.group(1) for u in urls if (m := KEY_RE.search(u))), None)
    q = f"&resourcekey={key}" if key else ""
    doc = next((m.group(1) for u in urls if (m := DOC_RE.search(u))), None)
    out = []
    if t.get("slides_pub"):
        u = t["slides_pub"].split("#")[0]
        out.append(("pub", u if "?" in u else u + "?start=false"))
    for u in urls:
        if m := PUB_RE.search(u):
            out.append(("pub", f"https://docs.google.com/presentation/d/e/{m.group(1)}/pub?start=false"))
            break
    ids = STRIP_IDS.get(t["slug"])
    if doc and ids and any(k[0] == ids for k in PUB_BY_SLIDES):
        base = f"https://docs.google.com/presentation/d/{doc}"
        title = deck_title([f"{base}/embed?start=false{q}", f"{base}/pub?start=false{q}",
                            f"{base}/edit?usp=sharing{q}"])
        if (u := PUB_BY_SLIDES.get((ids, title))):
            out.append(("pub", u))
    if doc:
        base = f"https://docs.google.com/presentation/d/{doc}"
        out += [("pub", f"{base}/pub?start=false{q}"),
                ("embed", f"{base}/embed?start=false{q}"),
                ("edit", f"{base}/edit?usp=sharing{q}")]
    return out


def pick(t: dict) -> tuple[dict, str] | None:
    """(deck_links entry, reason for the report) or None if no deck."""
    cands = candidates(t)
    if not cands:
        return None  # no Google Slides deck (e.g. a PDF or no slides)
    for via, url in cands:
        if opens(url):
            reason = via
            if via == "pub" and "/d/e/" not in url:
                reason = "pub-doc"
            if via == "embed":
                edit = dict(cands).get("edit")
                reason = "embed-shared" if edit and opens(edit) else "embed-published"
            return {"via": via, "url": url}, reason
    return {"via": "none", "url": None}, "none"


def short_link_ends(url: str) -> str:
    try:
        r = requests.get(url, headers=UA, timeout=60, stream=True)
        r.close()
    except requests.RequestException as e:
        return f"error ({type(e).__name__})"
    if "accounts.google.com" in r.url or r.status_code in (401, 403):
        return f"SIGN-IN ({r.status_code}) at {r.url[:90]}"
    return "ok" if r.status_code == 200 else f"HTTP {r.status_code} at {r.url[:90]}"


def main() -> None:
    talks = yaml.safe_load(TALKS.read_text())
    PUB_BY_SLIDES.update(published_by_slides())
    print(f"{len(PUB_BY_SLIDES)} public published-to-the-web links identified by their slides")
    with ThreadPoolExecutor(8) as pool:
        picks = list(pool.map(pick, talks))
    links = {t["slug"]: p[0] for t, p in zip(talks, picks) if p}
    reasons = {t["slug"]: p[1] for t, p in zip(talks, picks) if p}
    OUT.write_text(
        "# Generated by scripts/deck_links.py — do not hand-edit.\n"
        "# Where each talk's deck links for an anonymous visitor: via is\n"
        "# pub (published to the web), embed, edit, or none (url: null).\n"
        + yaml.safe_dump(links, sort_keys=True, allow_unicode=True, width=4096))

    by_slug = {t["slug"]: t for t in talks}
    by = {}
    for slug, r in reasons.items():
        by.setdefault(r, []).append(slug)
    print(f"{len(links)} decks: " + ", ".join(f"{len(v)} {k}" for k, v in sorted(by.items())))
    for via, why in (("pub-doc", "link-shared, no published-to-the-web (/d/e/) link found — "
                                 "linked to its /d/<id>/pub view, which Google serves for "
                                 "link-shared decks (add slides_pub to use a real one)"),
                     ("embed-published", "published to the web but not link-shared: /pub only "
                                         "exists under its /d/e/ link (add it as slides_pub) — "
                                         "linked to the /embed slideshow meanwhile"),
                     ("embed-shared", "link-shared but NOT published to the web — linked to "
                                      "the /embed slideshow"),
                     ("edit", "link-shared, not published, no slideshow — linked to the "
                              "view-only editor"),
                     ("none", "NOT OPENABLE ANONYMOUSLY in any form — not linked")):
        if by.get(via):
            print(f"\n{via}: {why} ({len(by[via])})")
            for slug in sorted(by[via]):
                print(f"  {slug}")
                for note in near_misses(by_slug[slug]):
                    print(f"      {note}")

    shorts = sorted({(t["slug"], t.get(f)) for t in talks for f in ("slides", "slides_short")
                     if SHORT_RE.match(t.get(f) or "")})
    with ThreadPoolExecutor(8) as pool:
        ends = list(pool.map(lambda s: short_link_ends(s[1]), shorts))
    bad = [(s, u, e) for (s, u), e in zip(shorts, ends) if e != "ok"]
    print(f"\nshort links: {len(shorts) - len(bad)}/{len(shorts)} open anonymously")
    for slug, u, e in bad:
        print(f"  {slug}: {u} -> {e}")


if __name__ == "__main__":
    main()

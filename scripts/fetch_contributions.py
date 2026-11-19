#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Snapshot Tim's GitHub contribution calendar into _data/contributions.yaml.

Fetches the public per-year calendar fragment that github.com itself
loads on a profile page (no token needed, public contributions only)
and records one entry per day so /contributions/ can draw every year
stacked on one page.

Years: GitHub dates commits by their author date, so there can be
contributions from before the account existed. The script walks back
from the current year and stops after EMPTY_YEARS_TO_STOP consecutive
years with no contributions older than the account.

Shading: GitHub shades each year on its own scale, which makes years
impossible to compare. Each day's level is therefore recomputed here on
one fixed all-time scale, so the same colour means the same amount of
activity in any year. The scale doubles at each step (1, 2-3, 4-7, ...
128+): daily counts range from 1 to several hundred, and an even split
would paint every day of a busy year in the top colour.

Organisations: under each year's calendar GitHub shows buttons for
three organisations, but they are not the ones with the most
contributions (in 2021 it leads with one that has 2). The fragment
does list every organisation contributed to that year, and the same
fragment with &org=<login> gives that organisation's count, so the
real top TOP_ORGS are ranked here. That is one request per
organisation per year (hundreds in total, and github.com rate-limits
them), so results for finished years are reused from the existing
data file. Pass --refresh-orgs to fetch them all again.

Re-run whenever the page feels stale.
"""

import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from html.parser import HTMLParser

import yaml

LOGIN = "mithro"
URL = "https://github.com/users/{login}/contributions?from={year}-01-01&to={year}-12-31"
OUT = pathlib.Path("_data/contributions.yaml")
EMPTY_YEARS_TO_STOP = 5
TOP_ORGS = 3
# Upper bounds of levels 1-7; anything above the last is level 8.
LEVEL_BOUNDS = [1, 3, 7, 15, 31, 63, 127]
PAUSE = 2  # seconds between requests; github.com rate-limits bursts
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class Calendar(HTMLParser):
    """Collects day cells, tooltips, the heading and the organisation filter links."""

    def __init__(self) -> None:
        super().__init__()
        self.cells: dict[str, str] = {}              # td id -> iso date
        self.tips: dict[str, str] = {}               # td id -> tooltip text
        self.orgs: list[dict] = []                   # {login, avatar}
        self.heading = ""
        self._tip_for: str | None = None
        self._in_h2 = False
        self._in_org = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "td" and "data-date" in a:
            self.cells[a.get("id", "")] = a["data-date"]
        elif tag == "tool-tip" and "for" in a:
            self._tip_for = a["for"]
            self.tips[self._tip_for] = ""
        elif tag == "h2" and not self.heading:
            self._in_h2 = True
        elif tag == "a" and "js-org-filter-link" in (a.get("class") or "").split():
            # Both the three buttons and the entries of the "More" menu.
            query = urllib.parse.urlparse(a.get("href") or "").query
            for org in urllib.parse.parse_qs(query).get("org", []):
                if all(o["login"] != org for o in self.orgs):
                    self.orgs.append({"login": org, "avatar": ""})
                    self._in_org = True
        elif tag == "img" and self._in_org and not self.orgs[-1]["avatar"]:
            self.orgs[-1]["avatar"] = a.get("src") or ""

    def handle_endtag(self, tag):
        if tag == "tool-tip":
            self._tip_for = None
        elif tag == "h2":
            self._in_h2 = False
        elif tag == "a":
            self._in_org = False

    def handle_data(self, data):
        if self._tip_for is not None:
            self.tips[self._tip_for] += data
        elif self._in_h2:
            self.heading += data


def fetch(year: int, org: str | None = None) -> Calendar:
    url = URL.format(login=LOGIN, year=year)
    if org:
        url += "&org=" + urllib.parse.quote(org)
    req = urllib.request.Request(url, headers={"User-Agent": "contribution-calendar-snapshot"})
    for attempt in range(8):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                html = resp.read().decode("utf-8")
            break
        except urllib.error.HTTPError as err:
            # Retry rate limiting and transient server errors; anything
            # else (404, 403, ...) is a real problem and fails the run.
            if not (err.code == 429 or err.code >= 500) or attempt == 7:
                raise
            wait = int(err.headers.get("Retry-After") or 0) or 30 * (attempt + 1)
            print(f"{year}: HTTP {err.code}, retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
            # Network blips (DNS, reset, timeout) on a CI runner.
            if attempt == 7:
                raise
            wait = 15 * (attempt + 1)
            print(f"{year}: {err}, retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
    time.sleep(PAUSE)
    cal = Calendar()
    cal.feed(html)
    return cal


def heading_total(cal: Calendar) -> int | None:
    m = re.search(r"([\d,]+)\s+contributions?", cal.heading)
    return int(m.group(1).replace(",", "")) if m else None


def fetch_year(year: int) -> tuple[int, dict[str, int], list[dict]]:
    """Returns (total, {iso date: count}, organisations) for one year."""
    cal = fetch(year)
    days: dict[str, int] = {}
    for cell_id, day in cal.cells.items():
        tip = cal.tips.get(cell_id, "").strip()
        m = re.match(r"([\d,]+) contributions?\b", tip)
        if m:
            count = int(m.group(1).replace(",", ""))
        elif tip.startswith("No contributions"):
            count = 0
        else:
            sys.exit(f"{year}: cannot read the tooltip for {day}: {tip!r} "
                     "(GitHub's markup may have changed)")
        days[day] = count
    if len(days) < 365:
        sys.exit(f"{year}: only {len(days)} day cells found "
                 "(GitHub's markup may have changed)")
    summed = sum(days.values())
    total = heading_total(cal)
    if total is None:
        total = summed
    elif total != summed:
        print(f"{year}: heading says {total} but the days sum to {summed}; "
              "using the heading", file=sys.stderr)
    return total, days, cal.orgs


def fetch_top_orgs(year: int, orgs: list[dict]) -> list[dict]:
    """Returns the TOP_ORGS organisations of a year by contribution count."""
    counted = []
    for n, org in enumerate(orgs, start=1):
        total = heading_total(fetch(year, org["login"]))
        if total is None:
            sys.exit(f"{year}: cannot read the total for organisation "
                     f"{org['login']} (GitHub's markup may have changed)")
        print(f"{year}: org {n}/{len(orgs)} {org['login']}: {total}", file=sys.stderr)
        if total:
            counted.append({"login": org["login"], "avatar": org["avatar"],
                            "count": total, "count_text": f"{total:,}"})
    counted.sort(key=lambda o: (-o["count"], o["login"].lower()))
    return counted[:TOP_ORGS]


def level_for(count: int) -> int:
    if count == 0:
        return 0
    for level, limit in enumerate(LEVEL_BOUNDS, start=1):
        if count <= limit:
            return level
    return len(LEVEL_BOUNDS) + 1


refresh_orgs = "--refresh-orgs" in sys.argv[1:]
today = date.today()
github = yaml.safe_load(pathlib.Path("_data/github.yaml").read_text())
member_since = int(github["profile"]["member_since"])

# Finished years' organisation rankings no longer change, so keep them.
known_orgs: dict[int, list[dict]] = {}
if OUT.exists() and not refresh_orgs:
    for y in (yaml.safe_load(OUT.read_text()) or {}).get("years", []):
        if y["year"] < today.year - 1 and all("count" in o for o in y.get("orgs", [{}])):
            known_orgs[y["year"]] = y["orgs"]

raw = {}
year, empty_run = today.year, 0
while True:
    raw[year] = fetch_year(year)
    print(f"{year}: {raw[year][0]} contributions, {len(raw[year][2])} organisations",
          file=sys.stderr)
    empty_run = empty_run + 1 if raw[year][0] == 0 else 0
    if year < member_since and empty_run >= EMPTY_YEARS_TO_STOP:
        break
    year -= 1
# Drop the empty years before the first contribution.
while raw and raw[min(raw)][0] == 0:
    del raw[min(raw)]
if not raw:
    sys.exit("no contributions found in any year")

busiest_day = max(c for _, days, _ in raw.values() for c in days.values())
max_total = max(total for total, _, _ in raw.values())

years = []
for year, (total, days, orgs) in raw.items():
    jan1 = date(year, 1, 1)
    pad = (jan1.weekday() + 1) % 7  # blank cells before 1 Jan; weeks start on Sunday
    months, cells = [], []
    d = jan1
    while d.year == year:
        if d.day == 1:
            months.append({"name": MONTHS[d.month - 1],
                           "col": ((d - jan1).days + pad) // 7 + 1})
        label = f"{WEEKDAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]} {year}"
        if d > today or d.isoformat() not in days:
            cells.append([-1, 0, label])  # not happened yet
        else:
            count = days[d.isoformat()]
            cells.append([count, level_for(count), label])
        d += timedelta(days=1)
    years.append({
        "year": year,
        "total": total,
        "total_text": f"{total:,}",  # Liquid has no thousands separator
        "bar": max(2, round(total / max_total * 100)) if total else 0,
        "orgs": known_orgs[year] if year in known_orgs else fetch_top_orgs(year, orgs),
        "pad": pad,
        "months": months,
        "days": cells,  # [count, level, label]
    })

data = {
    "snapshot_date": today.isoformat(),
    "login": LOGIN,
    "total": sum(y["total"] for y in years),
    "total_text": f"{sum(y['total'] for y in years):,}",
    "first_year": years[-1]["year"],
    "last_year": years[0]["year"],
    "busiest_day": busiest_day,
    # Upper bounds of levels 1-7; anything above the last is level 8.
    "thresholds": LEVEL_BOUNDS,
    "years": years,
}


class Dumper(yaml.SafeDumper):
    """Keeps each day / month / organisation on one line so the file stays diffable."""


def _str(dumper, value):
    # Ruby's YAML parser (used by Jekyll) reads a bare 1,374 as the
    # integer 1374, so strings made of digits and commas must be quoted.
    style = "'" if re.fullmatch(r"[\d,]+", value) else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


def _list(dumper, value):
    flat = all(not isinstance(v, (list, dict)) for v in value)
    return dumper.represent_sequence("tag:yaml.org,2002:seq", value, flow_style=flat)


def _dict(dumper, value):
    flat = set(value) in ({"name", "col"}, {"login", "avatar", "count", "count_text"})
    return dumper.represent_mapping("tag:yaml.org,2002:map", value, flow_style=flat)


Dumper.add_representer(str, _str)
Dumper.add_representer(list, _list)
Dumper.add_representer(dict, _dict)

OUT.write_text("# Snapshot of github.com/mithro's contribution calendar — "
               "regenerate with scripts/fetch_contributions.py\n"
               + yaml.dump(data, Dumper=Dumper, sort_keys=False,
                           allow_unicode=True, width=200))
print(f"wrote {OUT}: {data['total']} contributions, "
      f"{data['first_year']}-{data['last_year']}, busiest day {busiest_day}",
      file=sys.stderr)

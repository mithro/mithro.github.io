#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "pillow"]
# ///
"""Snapshot the 2026 PCB repositories into _data/pcbs.yaml + assets/pcbs/.

Feeds the unlisted /pcbs/ page. For each repository in REPOS below it
records repository state from the GitHub API (via the authenticated `gh`
CLI), board statistics parsed straight from each `.kicad_pcb` file (size
from the Edge.Cuts outline, copper layer count, footprint count, KiCad
version), and converts the repository's own committed 3D renders to
small WebP files under assets/pcbs/.

The repository list is hand-curated: PCB repositories with commits in
the current year. Re-run whenever the page feels stale.
"""

import json
import math
import pathlib
import subprocess
import sys
import urllib.request
from datetime import date

import yaml
from PIL import Image, ImageChops

OWNER = "mithro"
ASSETS = pathlib.Path("assets/pcbs")
CLONES = pathlib.Path("tmp/pcb-repos")  # gitignored scratch clones
MAX_WIDTH = 960

# image: (path in repo, optional crop box as fractions (left, top, right, bottom))
# Only the repositories listed here are published. Deliberately left out:
# the YT9215S switch mirror (someone else's design, not relevant here).
REPOS = [
    {
        "repo": "minidc-temp-monitor",
        "title": "minidc-temp-monitor",
        "blurb": "Daisy-chained 42 x 13 mm temperature sensor strips for a "
                 "miniature datacenter's hot and cold aisles: a CH32V003 or "
                 "CH32V005 RISC-V MCU plus an NTC thermistor, with a JST SH "
                 "(Qwiic-style) connector at each end. A board's I2C address "
                 "is its position in the chain.",
        "boards": [
            {"name": "sensor-ch32v003",
             "pcb": "hardware/sensor-ch32v003/sensor-ch32v003.kicad_pcb",
             "images": [("hardware/sensor-ch32v003/out/board-3d.png", (0, .05, 1, .37))]},
            {"name": "sensor-ch32v005",
             "pcb": "hardware/sensor-ch32v005/sensor-ch32v005.kicad_pcb",
             "images": [("hardware/sensor-ch32v005/out/board-3d.png", (0, .05, 1, .37))]},
        ],
    },
    {
        "repo": "esp32-to-433mhz",
        "title": "esp32-to-433mhz",
        "blurb": "Carrier boards that join an ESP32-C3 SuperMini and a cheap "
                 "433 MHz radio module (Ebyte E07 / D-Sun CC1101, or an "
                 "SX1278 LoRa Ra-02) into one small unit, with a 3D-printed "
                 "case.",
        "boards": [
            {"name": "esp32c3-radio-adapter",
             "pcb": "hardware/esp32c3-radio-adapter/esp32c3-radio-adapter.kicad_pcb",
             "images": [("docs/images/esp32c3-radio-adapter-assembly-e07-iso.png", None),
                        ("docs/images/esp32c3-radio-adapter-3d-top.png", None)]},
            {"name": "esp32c3-sx1278-adapter",
             "pcb": "hardware/esp32c3-sx1278-adapter/esp32c3-sx1278-adapter.kicad_pcb",
             "images": [("docs/images/esp32c3-sx1278-adapter-assembly-module-iso.png", None),
                        ("docs/images/esp32c3-sx1278-adapter-3d-top.png", None)]},
        ],
    },
    {
        "repo": "rpi-camera-led",
        "title": "rpi-camera-led",
        "blurb": None,  # GitHub description is good
        "boards": [
            {"name": "rpi-camera-led",
             "pcb": "hardware/rpi-camera-led.kicad_pcb",
             "images": [("docs/img/board-3d-iso.png", None),
                        ("docs/img/board-3d-top.png", None)]},
        ],
    },
    {
        "repo": "budget-poe-adapter",
        "title": "budget-poe-adapter",
        "blurb": "Research and design notes for a very cheap, non-isolated "
                 "PoE to USB-C adapter that passes Ethernet through at "
                 "gigabit speed. Research stage: no schematic or PCB yet, so "
                 "the picture is the block diagram.",
        "boards": [
            {"name": "block diagram", "pcb": None,
             "images": [("design/block-diagram.png", (0, 0, 1, .46))]},
        ],
    },
]


# ---------------------------------------------------------------- GitHub

def gh(path: str):
    """GET a GitHub REST endpoint: authenticated `gh` first, anonymous HTTPS
    as a fallback (all these repositories are public; ~5 calls per repo
    fits the 60/hour anonymous limit)."""
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if r.returncode == 0:
        return json.loads(r.stdout)
    print(f"  gh api {path} failed ({r.stderr.strip()[:120]}); trying anonymously",
          file=sys.stderr)
    req = urllib.request.Request(f"https://api.github.com/{path}",
                                 headers={"Accept": "application/vnd.github+json",
                                          "User-Agent": "fetch_pcbs.py"})
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def git(repo_dir: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo_dir), *args], capture_output=True,
                          text=True, check=True).stdout


def checkout(name: str) -> pathlib.Path:
    """Blobless clone (or fetch) over SSH into tmp/pcb-repos/<name>."""
    d = CLONES / name
    if d.exists():
        git(d, "fetch", "--quiet", "origin")
        git(d, "reset", "--quiet", "--hard", "origin/HEAD")
    else:
        CLONES.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--quiet", "--filter=blob:none",
                        f"git@github.com:{OWNER}/{name}.git", str(d)], check=True)
    return d


def repo_state(name: str, d: pathlib.Path) -> dict:
    info = gh(f"repos/{OWNER}/{name}")
    branch = info["default_branch"]
    # Latest non-merge commit: merge subjects ("Merge pull request #N from
    # ...") say nothing about the work itself.
    sha, cdate, subject = git(d, "log", "-1", "--no-merges",
                              "--format=%H%x00%cs%x00%s").strip().split("\0")
    year = date.today().year
    commits_year = int(git(d, "rev-list", "--count", f"--since={year}-01-01", "HEAD"))
    open_prs = len(gh(f"repos/{OWNER}/{name}/pulls?state=open&per_page=100"))
    releases = gh(f"repos/{OWNER}/{name}/releases?per_page=1")
    runs = gh(f"repos/{OWNER}/{name}/actions/runs?branch={branch}&per_page=1")["workflow_runs"]
    return {
        "url": info["html_url"],
        "description": info["description"],
        "license": (info.get("license") or {}).get("spdx_id"),
        "stars": info["stargazers_count"],
        "created": info["created_at"][:10],
        "default_branch": branch,
        "last_commit": {
            "date": cdate,
            "sha": sha[:7],
            "message": subject,
            "url": f"{info['html_url']}/commit/{sha}",
        },
        "commits_this_year": commits_year,
        # GitHub's open_issues_count includes open PRs.
        "open_issues": info["open_issues_count"] - open_prs,
        "open_prs": open_prs,
        "release": ({"tag": releases[0]["tag_name"],
                     "date": releases[0]["published_at"][:10],
                     "url": releases[0]["html_url"]} if releases else None),
        "ci": ({"workflow": runs[0]["name"],
                "conclusion": runs[0]["conclusion"] or runs[0]["status"],
                "url": runs[0]["html_url"]} if runs else None),
    }


# ------------------------------------------------------- .kicad_pcb parsing

def parse_sexpr(text: str):
    """Minimal S-expression parser: lists, quoted strings, bare atoms."""
    stack, cur, i, n = [], [], 0, len(text)
    while i < n:
        c = text[i]
        if c == "(":
            stack.append(cur)
            cur = []
            i += 1
        elif c == ")":
            done, cur = cur, stack.pop()
            cur.append(done)
            i += 1
        elif c == '"':
            j, buf = i + 1, []
            while text[j] != '"':
                if text[j] == "\\":
                    j += 1
                buf.append(text[j])
                j += 1
            cur.append("".join(buf))
            i = j + 1
        elif c.isspace():
            i += 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in '()"':
                j += 1
            cur.append(text[i:j])
            i = j
    return cur[0]


def child(node, key):
    for x in node[1:]:
        if isinstance(x, list) and x and x[0] == key:
            return x
    return None


def children(node, key):
    return [x for x in node[1:] if isinstance(x, list) and x and x[0] == key]


def xy(node):
    return float(node[1]), float(node[2])


def arc_points(s, m, e):
    """Start, end and any axis extremes of the circular arc through s, m, e."""
    (ax, ay), (bx, by), (cx, cy) = s, m, e
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return [s, m, e]
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay)
          + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx)
          + (cx * cx + cy * cy) * (bx - ax)) / d
    r = math.hypot(ax - ux, ay - uy)
    ang = lambda p: math.atan2(p[1] - uy, p[0] - ux) % (2 * math.pi)  # noqa: E731
    a0, am, a1 = ang(s), ang(m), ang(e)
    span = (a1 - a0) % (2 * math.pi)
    ccw = (am - a0) % (2 * math.pi) < span  # does the arc go a0 -> a1 increasing?
    pts = [s, e]
    for k in range(4):
        t = k * math.pi / 2
        inside = ((t - a0) % (2 * math.pi) < span) if ccw else \
                 ((a0 - t) % (2 * math.pi) < (2 * math.pi - span))
        if inside:
            pts.append((ux + r * math.cos(t), uy + r * math.sin(t)))
    return pts


def shape_points(g):
    """Outline points of a gr_*/fp_* graphic item (local coordinates)."""
    kind = g[0][3:]
    if kind in ("line", "rect"):
        (x0, y0), (x1, y1) = xy(child(g, "start")), xy(child(g, "end"))
        return [(x0, y0), (x1, y1), (x0, y1), (x1, y0)]
    if kind == "arc":
        return arc_points(xy(child(g, "start")), xy(child(g, "mid")), xy(child(g, "end")))
    if kind == "circle":
        (cx, cy), (ex, ey) = xy(child(g, "center")), xy(child(g, "end"))
        r = math.hypot(ex - cx, ey - cy)
        return [(cx - r, cy - r), (cx + r, cy + r)]
    if kind in ("poly", "curve"):
        return [xy(p) for p in children(child(g, "pts"), "xy")]
    return []


def on_edge_cuts(g):
    layer = child(g, "layer")
    return layer is not None and layer[1] == "Edge.Cuts"


def board_stats(text: str) -> dict:
    root = parse_sexpr(text)
    pts = []
    for g in root[1:]:
        if isinstance(g, list) and g and str(g[0]).startswith("gr_") and on_edge_cuts(g):
            pts += shape_points(g)
    footprints = children(root, "footprint")
    for fp in footprints:
        at = child(fp, "at")
        fx, fy = float(at[1]), float(at[2])
        rot = math.radians(float(at[3])) if len(at) > 3 else 0.0
        c, s = math.cos(rot), math.sin(rot)
        for g in fp[1:]:
            if isinstance(g, list) and g and str(g[0]).startswith("fp_") and on_edge_cuts(g):
                # KiCad rotates counter-clockwise on screen with y pointing down.
                pts += [(fx + x * c + y * s, fy - x * s + y * c) for x, y in shape_points(g)]
    copper = [lay for lay in child(root, "layers")[1:]
              if isinstance(lay, list) and str(lay[1]).endswith(".Cu")]
    gen = child(root, "generator_version")
    size = None
    if pts:
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        size = [round(max(xs) - min(xs), 1), round(max(ys) - min(ys), 1)]
    return {
        "size_mm": size,
        "copper_layers": len(copper),
        "footprints": len(footprints),
        "kicad": gen[1] if gen else None,
        "file_version": child(root, "version")[1],
    }


# ------------------------------------------------------------- images

def autotrim(img: Image.Image, pad: int = 16) -> Image.Image:
    """Crop away a uniform border the colour of the top-left pixel."""
    rgb = img.convert("RGB")
    bg = Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))
    diff = ImageChops.difference(rgb, bg).convert("L").point(lambda v: 255 if v > 24 else 0)
    box = diff.getbbox()
    if not box:
        return img
    l, t, r, b = box
    return img.crop((max(l - pad, 0), max(t - pad, 0),
                     min(r + pad, img.width), min(b + pad, img.height)))


def save_image(repo: str, d: pathlib.Path, path: str, crop, dst: pathlib.Path) -> dict:
    img = Image.open(d / path)
    img.load()
    if crop:
        w, h = img.size
        img = img.crop((round(crop[0] * w), round(crop[1] * h),
                        round(crop[2] * w), round(crop[3] * h)))
    img = autotrim(img)
    if img.width > MAX_WIDTH:
        img = img.resize((MAX_WIDTH, round(img.height * MAX_WIDTH / img.width)),
                         Image.LANCZOS)
    img = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB")
    img.save(dst, "WEBP", quality=82, method=6)
    return {"src": "/" + dst.as_posix(), "width": img.width, "height": img.height,
            "source": f"https://github.com/{OWNER}/{repo}/blob/HEAD/{path}"}


# --------------------------------------------------------------- main

def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    out = []
    for cfg in REPOS:
        name = cfg["repo"]
        print(f"{name} ...", file=sys.stderr)
        d = checkout(name)
        state = repo_state(name, d)
        entry = {"repo": name, "title": cfg["title"],
                 "blurb": cfg["blurb"] or state["description"],
                 "credit": cfg.get("credit"), **state, "boards": []}
        for b in cfg["boards"]:
            board = {"name": b["name"], "pcb": b["pcb"], "images": []}
            if b["pcb"]:
                board.update(board_stats((d / b["pcb"]).read_text()))
                board["pcb_url"] = f"{state['url']}/blob/{state['default_branch']}/{b['pcb']}"
                board["pcb_last_change"] = git(d, "log", "-1", "--format=%cs", "--", b["pcb"]).strip()
            for idx, (path, crop) in enumerate(b["images"]):
                slug = b["name"].replace(" ", "-")
                dst = ASSETS / f"{name}--{slug}-{idx}.webp"
                board["images"].append(save_image(name, d, path, crop, dst))
            entry["boards"].append(board)
        out.append(entry)
    out.sort(key=lambda e: e["last_commit"]["date"], reverse=True)
    data = {"snapshot_date": date.today().isoformat(), "repos": out}
    dst = pathlib.Path("_data/pcbs.yaml")
    dst.write_text("# Snapshot of the 2026 PCB repositories — regenerate with "
                   "scripts/fetch_pcbs.py\n"
                   + yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    print(f"wrote {dst}: {len(out)} repos, "
          f"{sum(len(e['boards']) for e in out)} boards", file=sys.stderr)


if __name__ == "__main__":
    main()

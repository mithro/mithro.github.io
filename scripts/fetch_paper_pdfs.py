# /// script
# requires-python = ">=3.11"
# ///
"""Mirror open-access PDFs of Tim's papers into papers/.

Sources verified 2026-08-09 (see _data/papers.yaml pdf fields). The two
ACM open-access PDFs are Cloudflare-guarded against non-browser clients
and are fetched separately via a real browser; this script skips them.
"""
import pathlib
import sys
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

PDFS = {
    "cfu-playground.pdf": "https://arxiv.org/pdf/2201.01863",
    "rapid-prototyping-lig-sensors.pdf": "https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=957346",
    "temp-sensor-generator.pdf": "https://blaauw.engin.umich.edu/wp-content/uploads/sites/342/2022/09/An-Open-Source-and-Autonomous-Temperature-Sensor-Generator-Verified-With-64-Instances-in-SkyWater-130-nm-for-Comprehensive-Design-Space-Exploration.pdf",
    "ascr-reimagining-codesign.pdf": "https://www.osti.gov/servlets/purl/1843574",
    "symbiflow-and-vpr.pdf": "https://ieeexplore.ieee.org/ielx7/40/9130972/09103284.pdf",
    "sscm-2024-index.pdf": "https://ieeexplore.ieee.org/ielx8/4563670/10752707/10795288.pdf",
    "missing-pieces-iccad20.pdf": "https://drive.google.com/uc?export=download&id=1GuwtsMjl40JIwpL6kzYGk7VVheVOJ8nm",
}

outdir = pathlib.Path("papers")
outdir.mkdir(parents=True, exist_ok=True)
failures = []
for name, url in PDFS.items():
    dest = outdir / name
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
    except Exception as e:
        print(f"FAIL {name}: {e}")
        failures.append(name)
        continue
    if not data.startswith(b"%PDF"):
        print(f"FAIL {name}: not a PDF ({data[:40]!r})")
        failures.append(name)
        continue
    dest.write_bytes(data)
    print(f"OK {name} ({len(data)} bytes)")
if failures:
    sys.exit(f"{len(failures)} failed: {failures}")

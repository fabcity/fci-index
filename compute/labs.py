#!/usr/bin/env python3
"""The Fab Lab directory, as facts, for the network map: where every lab is and whether it says it is active.

    python3 compute/labs.py --selftest     # no network: the trimming on a fake record
    python3 compute/labs.py                # one dated freeze from the archive, write compute/results/labs.json

The records are fablabs.io's (registry economic/community/fablabs-io). Its Terms of Use are not an open licence:
§7.3 forbids distributing platform content without fablabs.io's prior written authorisation, and §8.1 leaves each
lab the copyright in what it wrote. Tomas Diez, co-owner of fablabs.io, decided on 2026-10-14 that the Index's map
shows the directory. So this module keeps the directory FACTS only (name, city, country, coordinates, kind,
activity status, and the link to the lab's own page) and drops everything a lab authored or that identifies a
person: description, blurb, links, email, phone, street address, images. The licence text travels with the file.

It reads a dated monthly freeze from the Fab Lab network data archive (gitlab.fabcloud.org, fl-management/
fablab-network-data, archive/labs.json/), not the live endpoint, so a build can be pinned and repeated. File names
are not uniform; the newest is chosen on its first eight digits. LABS_SNAPSHOT=<file name> pins one.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import waste  # noqa: E402

HERE = Path(__file__).resolve().parent
PROJECT = urllib.parse.quote("fl-management/fablab-network-data", safe="")
API = f"https://gitlab.fabcloud.org/api/v4/projects/{PROJECT}/repository"
FOLDER = "archive/labs.json"
STATUS = {"active": "active", "planned": "planned", "closed": "closed"}   # anything else (none, "", corona) is "not stated"
KEEP = ("slug", "name", "city", "country_code", "kind_name")
LICENCE = ("Directory facts from fablabs.io, shown on the Fab City Index map by decision of Tomas Diez, co-owner of fablabs.io "
           "(2026-10-14). fablabs.io's Terms of Use apply and are not an open licence: each lab keeps the copyright in what it "
           "wrote, which is why only names, places, kinds and statuses are shown, each linking to the lab's own page.")


def newest(names: list[str]) -> str:
    """The freeze with the latest date, on the first eight digits of its name (the names are not uniform)."""
    dated = [(re.sub(r"\D", "", n)[:8], n) for n in names if n.endswith(".json")]
    return max(d for d in dated if len(d[0]) == 8)[1]


def trim(records: list[dict]) -> list[dict]:
    """Facts only, and only labs with a place on the map. Coordinates to four decimals (about 10 m)."""
    out = []
    for r in records:
        lat, lng = r.get("latitude"), r.get("longitude")
        if lat in (None, "") or lng in (None, ""):
            continue
        try:
            lat, lng = round(float(lat), 4), round(float(lng), 4)
        except (TypeError, ValueError):
            continue
        if not (-90 <= lat <= 90 and -180 <= lng <= 180) or (lat == 0 and lng == 0):
            continue
        row = {k: r.get(k) for k in KEEP}
        row.update(lat=lat, lng=lng, status=STATUS.get(r.get("activity_status") or "", "not stated"),
                   url=f"https://www.fablabs.io/labs/{r['slug']}")
        out.append(row)
    return sorted(out, key=lambda x: x["slug"])


def run() -> int:
    names = [x["name"] for x in waste._json(f"{API}/tree?path={urllib.parse.quote(FOLDER, safe='')}&per_page=100")]
    snap = os.environ.get("LABS_SNAPSHOT") or newest(names)
    raw = waste._json(f"{API}/files/{urllib.parse.quote(f'{FOLDER}/{snap}', safe='')}/raw?ref=main")
    labs = trim(raw)
    counts = {s: sum(1 for x in labs if x["status"] == s) for s in ("active", "planned", "closed", "not stated")}
    out = {"reads_as": "Every Fab Lab in the fablabs.io directory that gives a place, as directory facts: name, city, country, "
                       "coordinates, kind and the activity status the lab states. A status is the lab's own claim, not a check.",
           "licence": LICENCE, "snapshot": snap, "records_in_snapshot": len(raw), "on_the_map": len(labs), "counts": counts,
           "source": f"Fab Lab network data archive, gitlab.fabcloud.org/fl-management/fablab-network-data, {FOLDER}/{snap}",
           "labs": labs}
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "labs.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"{snap}: {len(raw)} records, {len(labs)} with a place; " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    return 0


def selftest() -> int:
    bad = 0

    def check(label, got, want):
        nonlocal bad
        ok = got == want
        bad += not ok
        print(f"  {'ok ' if ok else 'BAD'} {label}" + ("" if ok else f": got {got!r}, want {want!r}"))

    recs = [{"slug": "ping", "name": "PiNG", "city": "Nantes", "country_code": "FR", "kind_name": "fab_lab", "latitude": 47.218371,
             "longitude": -1.55362100000002, "activity_status": None, "email": "x@y.z", "phone": "1", "description": "ours", "blurb": "b",
             "address_1": "rue", "links": [{"url": "u"}]},
            {"slug": "a", "name": "A", "latitude": "41.39", "longitude": "2.19", "activity_status": "active", "kind_name": "mini_fab_lab"},
            {"slug": "nowhere", "name": "N", "latitude": None, "longitude": 2.0, "activity_status": "active"},
            {"slug": "null-island", "name": "Z", "latitude": 0, "longitude": 0, "activity_status": "closed"},
            {"slug": "c", "name": "C", "latitude": 10, "longitude": 10, "activity_status": "corona"}]
    out = trim(recs)
    check("labs without a place, or at 0,0, are left out", [x["slug"] for x in out], ["a", "c", "ping"])
    ping = out[-1]
    check("only facts are kept: no email, phone, address, description, blurb or links",
          sorted(ping), ["city", "country_code", "kind_name", "lat", "lng", "name", "slug", "status", "url"])
    check("coordinates to four decimals, strings read as numbers", (ping["lat"], ping["lng"], out[0]["lat"]), (47.2184, -1.5536, 41.39))
    check("a status the lab did not state, or corona, reads not stated", (ping["status"], out[1]["status"], out[0]["status"]),
          ("not stated", "not stated", "active"))
    check("each lab links to its own fablabs.io page", ping["url"], "https://www.fablabs.io/labs/ping")
    check("the newest freeze by its first eight digits, whatever the name's shape",
          newest(["2026.07.31_labs.json", "20260930_1907_labs.json", "2023.03.31 labs.json", "README.md"]), "20260930_1907_labs.json")
    print(f"\nlabs selftest: {bad} failed.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else run())

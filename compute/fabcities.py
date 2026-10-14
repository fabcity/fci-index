#!/usr/bin/env python3
"""The Fab City members as the network keeps them: official name, year of pledge, kind, continent, for the map.

    python3 compute/fabcities.py --selftest     # no network: the matching on fake rows
    python3 compute/fabcities.py                # one spreadsheet from the archive, write compute/results/fabcities.json

The Fab Lab network data archive (gitlab.fabcloud.org, fl-management/fablab-network-data, public/fabnetdata.xlsx,
refreshed monthly by the WG Fablabs & SDGs) carries a `fabcities` sheet: the 61 pledged members with their member
name, slug, kind (City, Region, Country), year of pledge, country and continent. It has no coordinates. This module
matches each row to the Index tracker's place (the tracker is the source of record for the list): by its slug
without the `fc-` prefix and without accents, then by a short alias table checked row by row on 2026-10-14. A row
or a place that matches nothing is listed, never dropped. Where the sheet and the tracker disagree (kind, country),
both are kept and the difference named, because neither is corrected here.
"""
from __future__ import annotations

import json
import sys
import unicodedata
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import atlas  # noqa: E402
import waste  # noqa: E402

HERE = Path(__file__).resolve().parent
PROJECT = urllib.parse.quote("fl-management/fablab-network-data", safe="")
API = f"https://gitlab.fabcloud.org/api/v4/projects/{PROJECT}/repository"
FILE = "public/fabnetdata.xlsx"
# Sheet slugs that are not the tracker's, checked against name, city and country on 2026-10-14.
ALIAS = {"bsd": "bergisches",            # Fab Region Bergische Städtedreieck: Solingen, Remscheid, Wuppertal
         "cptwn": "cape-town",           # Fab City Cape Town (the sheet files it under Saudi Arabia)
         "lund": "veberod",              # Fab City Lund; the tracker names Veberöd, in Lund municipality
         "monterey": "monterrey",        # Fab City Monterrey, Mexico
         "santiago": "santiago-de-chile"}
READS_AS = ("The Fab City members as the Fab Lab network data archive keeps them: the member's official name, the year it pledged, "
            "the kind it pledged as and its continent, matched to the Index tracker's places. Where the two disagree, both are kept.")
LICENCE = ("Fab City membership facts (names, pledge years, kinds) from the Fab Lab network data archive, maintained by the WG Fablabs & "
           "SDGs on gitlab.fabcloud.org; the repository states no licence. Shown as the network's own record of its members.")


def key(slug: str) -> str:
    """The sheet slug without `fc-` and without accents: fc-córdoba -> cordoba."""
    s = slug[3:] if slug.startswith("fc-") else slug
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))
    return ALIAS.get(s, s)


def match(rows: list[dict], places: dict[str, dict]) -> dict:
    """Sheet rows (header names as keys) against tracker places {slug: {name, country, territory}}. Pure."""
    members, unmatched = {}, []
    for r in rows:
        slug = key(r.get("Slug") or "")
        if slug not in places:
            unmatched.append({"sheet_slug": r.get("Slug"), "member": r.get("Fabcity member")})
            continue
        p = places[slug]
        try:
            pledge = int(float(r.get("Year of pledge") or ""))
        except ValueError:
            pledge = None
        m = {"member": r.get("Fabcity member"), "pledge": pledge, "kind": r.get("Kind"), "continent": r.get("Continent"),
             "city": r.get("City"), "country": r.get("Country"), "sheet_slug": r.get("Slug")}
        differs = [f"kind: the sheet says {m['kind']}, the tracker {p.get('territory')}"] if m["kind"] != p.get("territory") else []
        if m["country"] and p.get("country") and m["country"] != p["country"]:
            differs.append(f"country: the sheet says {m['country']}, the tracker {p['country']}")
        if differs:
            m["differs_from_tracker"] = differs
        members[slug] = m
    return {"members": dict(sorted(members.items())), "sheet_rows_unmatched": unmatched,
            "places_without_a_row": sorted(s for s in places if s not in members)}


def run() -> int:
    commit = waste._json(f"{API}/commits?path={urllib.parse.quote(FILE, safe='')}&per_page=1")[0]
    data = waste._raw(f"{API}/files/{urllib.parse.quote(FILE, safe='')}/raw?ref={commit['id']}")
    raw = waste._xlsx_rows(data, "fabcities")
    head = raw[0]
    rows = [{head[c]: r.get(c) for c in head} for r in raw[1:]]
    tracker = waste._json(atlas.TRACKER)
    places = {l["slug"]: {"name": l["name"], "country": l["country"], "territory": l["territory"]} for l in tracker["localities"]}
    out = {"reads_as": READS_AS, "licence": LICENCE,
           "source": f"gitlab.fabcloud.org/fl-management/fablab-network-data, {FILE}, sheet fabcities, commit {commit['short_id']} "
                     f"({commit['committed_date'][:10]}, \"{commit['title']}\")",
           "rows": len(rows), **match(rows, places)}
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "fabcities.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(rows)} rows, {len(out['members'])} matched; unmatched rows {out['sheet_rows_unmatched']}; places without a row "
          f"{out['places_without_a_row']}")
    for s, m in out["members"].items():
        if m.get("differs_from_tracker"):
            print(f"  {s}: {'; '.join(m['differs_from_tracker'])}")
    return 0


def selftest() -> int:
    bad = 0

    def check(label, got, want):
        nonlocal bad
        ok = got == want
        bad += not ok
        print(f"  {'ok ' if ok else 'BAD'} {label}" + ("" if ok else f": got {got!r}, want {want!r}"))

    check("the fc- prefix and accents go", [key("fc-córdoba"), key("fc-são-paulo"), key("fc-südburgenland"), key("fc-accra")],
          ["cordoba", "sao-paulo", "sudburgenland", "accra"])
    check("the alias table maps short names", [key("fc-bsd"), key("fc-cptwn"), key("fc-lund")], ["bergisches", "cape-town", "veberod"])
    rows = [{"Slug": "fc-accra", "Fabcity member": "Fab City Accra", "Year of pledge": "2026", "Kind": "City", "Continent": "Africa", "City": "Accra", "Country": "Ghana"},
            {"Slug": "fc-cptwn", "Fabcity member": "Fab City Cape Town", "Year of pledge": "2026", "Kind": "City", "Continent": "Africa", "Country": "Saudi Arabia"},
            {"Slug": "fc-kerala", "Fabcity member": "Fab City Kerala", "Year of pledge": "2019", "Kind": "City", "Country": "India"},
            {"Slug": "fc-nowhere", "Fabcity member": "Fab City Nowhere", "Year of pledge": ""}]
    places = {"accra": {"country": "Ghana", "territory": "City"}, "cape-town": {"country": "South Africa", "territory": "City"},
              "kerala": {"country": "India", "territory": "Region"}, "bhutan": {"country": "Bhutan", "territory": "Country"}}
    out = match(rows, places)
    check("matched members carry name, pledge year as a number, kind and continent",
          (out["members"]["accra"]["member"], out["members"]["accra"]["pledge"], out["members"]["accra"]["kind"]), ("Fab City Accra", 2026, "City"))
    check("a disagreement on kind or country is named, both kept",
          (out["members"]["kerala"]["differs_from_tracker"], out["members"]["cape-town"]["differs_from_tracker"]),
          (["kind: the sheet says City, the tracker Region"], ["country: the sheet says Saudi Arabia, the tracker South Africa"]))
    check("an agreeing row carries no difference", "differs_from_tracker" in out["members"]["accra"], False)
    check("a row with no place, and a place with no row, are listed, never dropped",
          (out["sheet_rows_unmatched"], out["places_without_a_row"]), ([{"sheet_slug": "fc-nowhere", "member": "Fab City Nowhere"}], ["bhutan"]))
    print(f"\nfabcities selftest: {bad} failed.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else run())

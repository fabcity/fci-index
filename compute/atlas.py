#!/usr/bin/env python3
"""The country bracket: what the country each place sits in buys and sells abroad, from the Atlas of Economic Complexity.

    python3 compute/atlas.py --selftest     # no network: the arithmetic on a small fake table
    python3 compute/atlas.py                # fetch the Atlas tables (about 43 MB), write compute/results/atlas-country.json

The Atlas (Growth Lab at Harvard University) publishes every country's goods exports and imports by product,
1995 to the latest year, as CC0 tables on Harvard Dataverse (doi:10.7910/DVN/T4CHWJ, registry
economic/planet/atlas-economic-complexity). Its resolution is a country, and no Index cell is a country, so
this is NOT a cell score. It is the national bracket a place's own trade sits inside, served beside each place
(api.mjs, `country_bracket`), for all the countries in the tracker at once.

Per country, latest year: exports, imports, exports over imports (a trade balance as a ratio, NOT the share of
consumption met by local production), the same by the Atlas's ten goods sectors, the share of the import bill
that falls in HS2 chapters the country already net-exports (goods it makes competitively and still buys), and
ECI. Three things travel with every row: re-exports are inside (the Netherlands most of all, Boeing's
transhipment objection at national scale); goods only, services are a separate Atlas table; a country is not
its cities. A tracker country with no Atlas row is listed as absent, never as zero.
"""
from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import waste  # noqa: E402

HERE = Path(__file__).resolve().parent
DOI = "10.7910/DVN/T4CHWJ"
DATAVERSE = "https://dataverse.harvard.edu/api/"
# Dataverse file ids, International Trade Data (HS 92) and Classifications. The bulk tables, not the API: the
# API docs say values may change without warning, and the registry entry says to prefer the tables.
FILES = {"country_year": 13685109, "sector_year": 13685114, "chapter_year": 13685112,
         "products": 13438093, "countries": 13809180}
TRACKER = "https://index.fab.city/api/coverage.json"
# Tracker country names that differ from the Atlas's short names.
TRACKER_NAMES = {"Korea, South": "South Korea"}
LICENCE = "CC0 1.0 (the Dataverse record); goods trade only, services are a separate Atlas table"
READS_AS = ("The country each place sits in, as the Atlas of Economic Complexity records its goods trade: what the whole "
            "country exports and imports, by sector, in current US dollars. Exports over imports is a trade balance "
            "written as a ratio, NOT the share of consumption met by local production: a country that exports cars and "
            "imports food can sit at 1.00 and feed nobody. Re-exports are inside the figures (a gateway country like the "
            "Netherlands most of all). A country's figure says nothing about its cities; it is the bracket a place's own "
            "trade sits inside.")


def _rows(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def bracket(tables: dict[str, str], tracker: dict) -> dict:
    """The bracket for every country in the tracker, from the Atlas CSV texts. Pure: no network."""
    places = {}
    for loc in tracker["localities"]:
        places[loc["country"]] = places.get(loc["country"], 0) + 1
    by_name = {r["country_name_short"]: r["country_iso3_code"] for r in _rows(tables["countries"])}
    iso_of = {c: by_name.get(TRACKER_NAMES.get(c, c)) for c in places}
    wanted = {iso for iso in iso_of.values() if iso}
    sector_name = {r["product_id"]: r["product_name"] for r in _rows(tables["products"]) if r["product_level"] == "1"}

    years = {}                                            # iso -> {year: (exports, imports, eci)}
    for r in _rows(tables["country_year"]):
        if r["country_iso3_code"] in wanted:
            years.setdefault(r["country_iso3_code"], {})[int(r["year"])] = (float(r["export_value"]), float(r["import_value"]), r["eci"])
    latest = {iso: max(ys) for iso, ys in years.items()}
    sectors, chapters = {}, {}
    for r in _rows(tables["sector_year"]):
        iso = r["country_iso3_code"]
        if iso in latest and int(r["year"]) == latest[iso]:
            sectors.setdefault(iso, {})[sector_name[r["product_id"]]] = (float(r["export_value"]), float(r["import_value"]))
    for r in _rows(tables["chapter_year"]):
        iso = r["country_iso3_code"]
        if iso in latest and int(r["year"]) == latest[iso]:
            x, m = float(r["export_value"]), float(r["import_value"])
            c = chapters.setdefault(iso, {"covered": 0.0, "imports": 0.0, "net_exported": 0, "reported": 0})
            c["imports"] += m
            c["reported"] += 1
            if m > 0 and x >= m:                          # a chapter it imports nothing of is neither covered nor a gap
                c["covered"] += m
                c["net_exported"] += 1

    ratio = lambda x, m: round(x / m, 2) if m else None   # noqa: E731  no imports: no ratio, never infinity
    out, absent = {}, []
    for country, n in sorted(places.items(), key=lambda kv: (-kv[1], kv[0])):
        iso = iso_of[country]
        if not iso or iso not in latest:
            absent.append(country)
            continue
        y = latest[iso]
        x, m, eci = years[iso][y]
        ch = chapters.get(iso) or {"covered": 0.0, "imports": 0.0, "net_exported": 0, "reported": 0}
        out[iso] = {
            "name": country, "places": n, "year": y, "exports_usd": x, "imports_usd": m, "exports_over_imports": ratio(x, m),
            "eci": float(eci) if eci else None,
            "sectors": {s: {"exports_usd": sx, "imports_usd": sm, "exports_over_imports": ratio(sx, sm)}
                        for s, (sx, sm) in sorted(sectors.get(iso, {}).items())},
            "imports_in_net_export_chapters_share": round(ch["covered"] / ch["imports"], 2) if ch["imports"] else None,
            "hs2_chapters_net_exported": ch["net_exported"], "hs2_chapters_reported": ch["reported"],
            "series": [{"year": yy, "exports_usd": xx, "imports_usd": mm, "exports_over_imports": ratio(xx, mm)}
                       for yy, (xx, mm, _) in sorted(years[iso].items())],
        }
    return {"reads_as": READS_AS, "licence": LICENCE, "year": max(latest.values()) if latest else None,
            "countries": out, "not_in_atlas": absent}


def run() -> int:
    tables = {k: waste._raw(f"{DATAVERSE}access/datafile/{v}").decode("utf-8") for k, v in FILES.items()}
    meta = waste._json(f"{DATAVERSE}datasets/:persistentId/?persistentId=doi:{DOI}")["data"]["latestVersion"]
    out = bracket(tables, waste._json(TRACKER))
    out["source"] = (f"Atlas of Economic Complexity, Growth Lab at Harvard University: International Trade Data (HS 92), "
                     f"doi:{DOI}, version {meta['versionNumber']} ({meta['releaseTime'][:10]}), tables hs92_country_year, "
                     f"hs92_country_product_year_1 and _2; Classifications doi:10.7910/DVN/3BAL1O")
    res = HERE / "results"
    res.mkdir(exist_ok=True)
    (res / "atlas-country.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"{'country':8} {'places':>6} {'year':>4} {'exports $bn':>11} {'imports $bn':>11} {'X/M':>5} {'in net-export chapters':>22} {'ECI':>6}")
    for iso, c in out["countries"].items():
        share = "none" if c["imports_in_net_export_chapters_share"] is None else f"{c['imports_in_net_export_chapters_share']:.0%}"
        print(f"{iso:8} {c['places']:>6} {c['year']:>4} {c['exports_usd'] / 1e9:>11.1f} {c['imports_usd'] / 1e9:>11.1f} "
              f"{c['exports_over_imports']!s:>5} {share:>22} {c['eci']!s:>6}")
    for country in out["not_in_atlas"]:
        print(f"{country}: not in the Atlas tables (absent, not zero)")
    return 0


def selftest() -> int:
    bad = 0

    def check(label, got, want):
        nonlocal bad
        ok = got == want
        bad += not ok
        print(f"  {'ok ' if ok else 'BAD'} {label}" + ("" if ok else f": got {got!r}, want {want!r}"))

    tables = {
        "countries": "country_id,country_iso3_code,country_name,country_name_short,in_rankings,former_country\n"
                     "724,ESP,Spain,Spain,True,False\n410,KOR,South Korea,South Korea,True,False\n",
        "products": "product_id,product_hs92_code,product_level,product_name,product_name_short\n"
                    "1,0,1,\"Textiles, garments, footwear and furniture\",Textiles\n2,1,1,\"Vegetables, animals, wood and paper\",Agriculture\n"
                    "100,01,2,Live animals,Live animals\n",
        "country_year": "country_id,country_iso3_code,year,export_value,import_value,eci,coi,diversity,growth_proj\n"
                        "724,ESP,2023,300,400,0.80,,,\n724,ESP,2024,369,398,0.81,,,\n410,KOR,2024,681,555,1.60,,,\n",
        "sector_year": "country_id,country_iso3_code,product_id,product_hs92_code,year,export_value,import_value\n"
                       "724,ESP,1,0,2024,20,30\n724,ESP,2,1,2024,50,0\n724,ESP,1,0,2023,1,1\n",
        "chapter_year": "country_id,country_iso3_code,product_id,product_hs92_code,year,export_value,import_value\n"
                        "724,ESP,100,01,2024,60,40\n724,ESP,101,02,2024,10,60\n724,ESP,102,03,2024,5,0\n724,ESP,100,01,2023,0,99\n",
    }
    tracker = {"localities": [{"country": "Spain"}, {"country": "Korea, South"}, {"country": "Bhutan"}, {"country": "Spain"}]}
    out = bracket(tables, tracker)
    es = out["countries"]["ESP"]
    check("latest year per country, and the ratio is exports over imports", (es["year"], es["exports_over_imports"]), (2024, 0.93))
    check("places counted per country from the tracker", (es["places"], out["countries"]["KOR"]["places"]), (2, 1))
    check("the tracker's 'Korea, South' finds the Atlas's South Korea", out["countries"]["KOR"]["eci"], 1.6)
    check("a tracker country with no Atlas row is absent, never zero", (out["not_in_atlas"], "BTN" in out["countries"]), (["Bhutan"], False))
    check("sectors by name, latest year only; a sector with no imports has no ratio",
          (es["sectors"]["Textiles, garments, footwear and furniture"]["exports_over_imports"],
           es["sectors"]["Vegetables, animals, wood and paper"]["exports_over_imports"]), (0.67, None))
    check("imports in net-export chapters: 40 of 100 covered; a chapter with no imports is neither covered nor a gap",
          (es["imports_in_net_export_chapters_share"], es["hs2_chapters_net_exported"], es["hs2_chapters_reported"]), (0.4, 1, 3))
    check("a country with no sector or chapter rows keeps its totals and gets no share",
          (out["countries"]["KOR"]["sectors"], out["countries"]["KOR"]["imports_in_net_export_chapters_share"]), ({}, None))
    check("the series is every year, oldest first", [s["year"] for s in es["series"]], [2023, 2024])
    check("countries come most places first, then by name", list(out["countries"]), ["ESP", "KOR"])
    print(f"\natlas selftest: {bad} failed.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else run())

#!/usr/bin/env python3
"""The country bracket, goods: of the value added in what the country buys, the share made at home, by industry.

    python3 compute/goods.py --selftest     # no network: the reading of a fake OECD slice
    python3 compute/goods.py                # two SDMX calls for every tracker country, write compute/results/goods-country.json

OECD Trade in Value Added (TiVA), 2025 edition, built from the OECD's inter-country input-output tables: dataflow
DSD_TIVA_MAINSH@DF_MAINSH on the sti-public SDMX host (registry economic/bioregion/oecd-tiva-sdmx). The measure
FD_VA_SH, with the country as its own counterpart, is the share of the value added embodied in the country's final
demand (what households, government and investors buy) that was created inside the country, by the industry that
created it. Spain, 2022: 72% over all activities, 38% for manufacturing, 6% for computers and electronics. It is
the production side the Atlas half (compute/atlas.py) lacks, in value-added terms rather than tonnes or products:
a self-supply ratio per industry with imports already netted, which is why it needs no capping.

Checked 2026-10-13: for a reporting country, the shares over all origin countries sum to 100 per industry (the W
counterpart reads 100), so REF_AREA is the buying country and COUNTERPART_AREA the origin. A country the tables
do not cover (Ghana, Tanzania, Bhutan, Georgia) has no rows and is listed absent, never zero. The host answers 429
after a few calls and 403 to lastNObservations, so the run makes two: the summary series for every country at
once, then every industry for every country in the summary's latest year, keeping the rows where the country is its
own counterpart. A country
figure beside each place (api.mjs, `country_bracket.goods`), never a cell, never a score input.
"""
from __future__ import annotations

import csv
import io
import json
import sys
import time
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import atlas  # noqa: E402
import waste  # noqa: E402

HERE = Path(__file__).resolve().parent
SDMX = "https://sdmx.oecd.org/sti-public/rest/data/OECD.STI.PIE,DSD_TIVA_MAINSH@DF_MAINSH,1.1/"
FROM = 2019                      # Boeing's year; the series runs to the tables' last year
SUMMARY = {"_T": "all_activities", "A": "agriculture_forestry_fishing", "BTE": "industry_except_construction",
           "C": "manufacturing", "C10T12": "food_beverages_tobacco"}
LICENCE = ("OECD Terms and Conditions, Data, Permitted Use (read 2026-10-13): you can extract from, download, copy, adapt, "
           "print, distribute, share and embed Data for any purpose, even for commercial use; credit the OECD, and carry the same "
           "acknowledgment requirement into any sub-licence. The OECD does not warrant it owns all rights in all Data. Cite: OECD "
           "(2025), Trade in Value Added (TiVA) 2025 edition, https://www.oecd.org/en/data/datasets/trade-in-value-added.html "
           "(accessed on 2026-10-13)")
READS_AS = ("The country each place sits in, as the OECD's trade in value added tables read it: of the value added in what "
            "the country's households, government and investors buy, the share that was created inside the country, by "
            "the industry that created it. 0.38 for manufacturing means 38% of the manufacturing value added embodied in "
            "what the country buys was made at home. Value added, not products or tonnes: a car assembled at home from "
            "imported parts counts only for the assembly. A country figure, never a city's: it is the bracket a place's own "
            "economy sits inside.")


def queries(isos: list[str], year: int) -> tuple[str, str]:
    """Two URLs, all countries at once: the summary activities as a series from FROM, and every activity in one year.
    The host answers 403 to lastNObservations, so the year is read from the summary first (latest_year)."""
    k = "+".join(sorted(isos))
    return (f"{SDMX}FD_VA_SH.{k}.{'+'.join(SUMMARY)}.{k}..A?startPeriod={FROM}&format=csvfilewithlabels",
            f"{SDMX}FD_VA_SH.{k}..{k}..A?startPeriod={year}&endPeriod={year}&format=csvfilewithlabels")


def latest_year(summary_text: str) -> int | None:
    years = [int(r["TIME_PERIOD"]) for r in _own(summary_text)]
    return max(years) if years else None


def _own(csv_text: str) -> list[dict]:
    """The rows where the country is its own counterpart, with a value."""
    return [r for r in csv.DictReader(io.StringIO(csv_text))
            if r.get("OBS_VALUE") not in (None, "") and r["REF_AREA"] == r["COUNTERPART_AREA"]]


def bracket(countries: dict[str, dict], summary_text: str, latest_text: str) -> dict:
    """Every tracker country from the two slices. Pure: no network."""
    summary, latest = {}, {}
    for r in _own(summary_text):
        summary.setdefault(r["REF_AREA"], {}).setdefault(r["ACTIVITY"], {})[int(r["TIME_PERIOD"])] = round(float(r["OBS_VALUE"]) / 100, 3)
    for r in _own(latest_text):
        latest.setdefault(r["REF_AREA"], []).append(r)
    out, absent = {}, []
    for country, v in countries.items():
        iso, s, rows = v["iso"], summary.get(v["iso"], {}), latest.get(v["iso"], [])
        if not iso or not rows:
            absent.append(country)
            continue
        year = max(int(r["TIME_PERIOD"]) for r in rows)
        inds = {r["ACTIVITY"]: {"name": r["Economic activity"], "domestic_share": round(float(r["OBS_VALUE"]) / 100, 3)}
                for r in rows if int(r["TIME_PERIOD"]) == year}
        years = sorted({y for a in s.values() for y in a})
        out[iso] = {"name": country, "places": v["places"], "year": year,
                    "unit": "share of value added in the country's final demand created in the country",
                    **{k: inds[c]["domestic_share"] if c in inds else None for c, k in SUMMARY.items()},
                    "series": [{"year": y, "all_activities": s.get("_T", {}).get(y), "manufacturing": s.get("C", {}).get(y)} for y in years],
                    "industries": dict(sorted(inds.items()))}
    return {"reads_as": READS_AS, "licence": LICENCE, "year": max(c["year"] for c in out.values()) if out else None,
            "countries": out, "not_in_tiva": absent}


def fetch(url: str, tries: int = 6) -> str:
    """waste._raw, plus a growing wait on 429 (30 s to 16 min): the sti-public host rate-limits for about ten minutes
    after a few calls, and its Retry-After header is shorter than that window."""
    for n in range(tries):
        try:
            return waste._raw(url).decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code != 429 or n == tries - 1:
                raise
            time.sleep(30 * 2 ** n)
    raise AssertionError("unreachable")


def run() -> int:
    tracker = waste._json(atlas.TRACKER)
    countries = atlas.countries_of(waste._raw(f"{atlas.DATAVERSE}access/datafile/{atlas.FILES['countries']}").decode("utf-8"), tracker)
    isos = [v["iso"] for v in countries.values() if v["iso"]]
    summary_text = fetch(queries(isos, FROM)[0])
    year = latest_year(summary_text)
    if year is None:
        raise SystemExit("the summary slice has no rows where a tracker country is its own counterpart")
    out = bracket(countries, summary_text, fetch(queries(isos, year)[1]))
    out["source"] = (f"OECD, Trade in Value Added (TiVA) 2025 edition, DSD_TIVA_MAINSH@DF_MAINSH, measure FD_VA_SH with the "
                     f"country as counterpart, {FROM}-{out['year']}: {SDMX}")
    res = HERE / "results"
    res.mkdir(exist_ok=True)
    (res / "goods-country.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"{'country':8} {'places':>6} {'year':>4} {'all':>5} {'agri':>5} {'indus':>5} {'manuf':>5} {'food':>5}")
    f = lambda v: "none" if v is None else f"{v:.0%}"   # noqa: E731
    for iso, c in out["countries"].items():
        print(f"{iso:8} {c['places']:>6} {c['year']:>4} {f(c['all_activities']):>5} {f(c['agriculture_forestry_fishing']):>5} "
              f"{f(c['industry_except_construction']):>5} {f(c['manufacturing']):>5} {f(c['food_beverages_tobacco']):>5}")
    for country in out["not_in_tiva"]:
        print(f"{country}: not in the TiVA tables (absent, not zero)")
    return 0


def selftest() -> int:
    bad = 0

    def check(label, got, want):
        nonlocal bad
        ok = got == want
        bad += not ok
        print(f"  {'ok ' if ok else 'BAD'} {label}" + ("" if ok else f": got {got!r}, want {want!r}"))

    head = "STRUCTURE,MEASURE,REF_AREA,ACTIVITY,Economic activity,COUNTERPART_AREA,UNIT_MEASURE,TIME_PERIOD,OBS_VALUE\n"
    row = lambda ref, act, name, cp, y, v: f"DF,FD_VA_SH,{ref},{act},{name},{cp},PT_FD_VA,{y},{v}\n"   # noqa: E731
    summary = head + "".join([row("ESP", "_T", "Total", "ESP", 2021, 70.5), row("ESP", "_T", "Total", "ESP", 2022, 71.976),
                              row("ESP", "C", "Manufacturing", "ESP", 2021, 37.0), row("ESP", "C", "Manufacturing", "ESP", 2022, 38.083),
                              row("ESP", "_T", "Total", "FRA", 2022, 3.1),              # France's share in Spain's demand: not ours
                              row("KOR", "_T", "Total", "KOR", 2022, 60.0)])
    latest = head + "".join([row("ESP", "_T", "Total", "ESP", 2022, 71.976), row("ESP", "C", "Manufacturing", "ESP", 2022, 38.083),
                             row("ESP", "C26", "Computers", "ESP", 2022, 5.668), row("ESP", "A", "Agriculture", "ESP", 2022, 52.125),
                             row("ESP", "BTE", "Industry", "ESP", 2022, ""), row("ESP", "C10T12", "Food", "ESP", 2022, 44.4),
                             row("ESP", "C27", "Electrical", "ESP", 2020, 19.0),       # an industry whose last value is older: dropped
                             row("ESP", "C", "Manufacturing", "FRA", 2022, 2.0)])
    countries = {"Spain": {"places": 1, "iso": "ESP", "m49": 724}, "Korea, South": {"places": 1, "iso": "KOR", "m49": 410},
                 "Ghana": {"places": 2, "iso": "GHA", "m49": 288}, "Bhutan": {"places": 1, "iso": None, "m49": None}}
    out = bracket(countries, summary, latest)
    es = out["countries"]["ESP"]
    check("latest year, shares read as fractions, own-counterpart rows only", (es["year"], es["all_activities"], es["manufacturing"]), (2022, 0.72, 0.381))
    check("the summary names its activities; one with no value is None, not zero", (es["food_beverages_tobacco"], es["industry_except_construction"]), (0.444, None))
    check("industries at the latest year only, by code, with the OECD label", (list(es["industries"]), es["industries"]["C26"]),
          (["A", "C", "C10T12", "C26", "_T"], {"name": "Computers", "domestic_share": 0.057}))
    check("the series carries total and manufacturing by year, another country's share never mixed in", es["series"],
          [{"year": 2021, "all_activities": 0.705, "manufacturing": 0.37}, {"year": 2022, "all_activities": 0.72, "manufacturing": 0.381}])
    check("a country with a summary but no latest rows is absent, never zero; so is one without an ISO3", out["not_in_tiva"], ["Korea, South", "Ghana", "Bhutan"])
    check("the two queries key every country as its own counterpart, the second in the summary's latest year",
          [q.split("/")[-1].replace("&format=csvfilewithlabels", "") for q in queries(["FRA", "ESP"], latest_year(summary))],
          ["FD_VA_SH.ESP+FRA._T+A+BTE+C+C10T12.ESP+FRA..A?startPeriod=2019", "FD_VA_SH.ESP+FRA..ESP+FRA..A?startPeriod=2022&endPeriod=2022"])
    check("no own rows: no year", latest_year(head), None)
    print(f"\ngoods selftest: {bad} failed.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else run())

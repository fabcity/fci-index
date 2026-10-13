#!/usr/bin/env python3
"""The country bracket, food: how much of what the country eats it grows, from FAOSTAT's Food Balance Sheets.

    python3 compute/food.py --selftest     # no network: the arithmetic on a small fake sheet
    python3 compute/food.py                # fetch FAOSTAT's bulk sheet (22 MB zip), write compute/results/food-country.json

FAO's Food Balance Sheets (registry economic/bioregion/faostat-food-balance-sheets, CC BY 4.0 under FAO's database
terms) carry, per country, year and commodity group, production, imports and exports in thousand tonnes and the
food supply in kcal per person per day. That is the one place where the full Fab City question, what a territory
consumes against what it makes, has an open national answer: the self-sufficiency ratio FAO itself uses,
SSR = production / (production + imports - exports), per group. The Atlas bracket (compute/atlas.py) gives trade
alone; this gives both sides, for food.

A country figure: a bracket beside each place (api.mjs, `country_bracket.food`), never a cell, never a score
input. A group FAO leaves blank (Spain grows no coffee) is "not covered", never zero, and the kcal-weighted
summary says how much of the diet it covers. The weighting follows Japan's MAFF calorie-based self-sufficiency
rate: each group's ratio, capped at 1, weighted by its share of the diet's calories.
"""
from __future__ import annotations

import csv
import io
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import atlas  # noqa: E402
import waste  # noqa: E402

HERE = Path(__file__).resolve().parent
FBS_ZIP = "https://bulks-faostat.fao.org/production/FoodBalanceSheets_E_All_Data.zip"
FBS_CSV = "FoodBalanceSheets_E_All_Data_NOFLAG.csv"
# FBS aggregate groups (item codes). The three totals (2901 Grand Total, 2903 Vegetal, 2941 Animal) carry no
# production and are used for calories only. Sugar crops and oilcrops overlap their processed groups in tonnes,
# which is why the summary weights by each group's calories as eaten, not by tonnes.
GROUPS = {2905: "Cereals", 2907: "Starchy roots", 2908: "Sugar crops", 2909: "Sugar and sweeteners", 2911: "Pulses",
          2912: "Tree nuts", 2913: "Oilcrops", 2914: "Vegetable oils", 2918: "Vegetables", 2919: "Fruits", 2922: "Stimulants",
          2923: "Spices", 2924: "Alcoholic beverages", 2928: "Miscellaneous", 2943: "Meat", 2945: "Offals", 2946: "Animal fats",
          2948: "Milk", 2949: "Eggs", 2960: "Fish and seafood", 2961: "Other aquatic products"}
TOTAL = 2901
ELEMENTS = {"5511": "production_kt", "5611": "imports_kt", "5911": "exports_kt", "664": "kcal_per_person_day"}
LICENCE = ("CC BY 4.0 (FAO Statistical Database Terms of Use), which also bars use in conjunction with the promotion of "
           "a commercial enterprise; cite FAO, FAOSTAT Food Balance Sheets")
READS_AS = ("The country each place sits in, as FAO's Food Balance Sheets record its food: for each commodity group, "
            "production against production plus imports minus exports, FAO's own self-sufficiency ratio. Above 1 the "
            "country grows more than it keeps; below 1 it eats what others grow. The summary weights each group's ratio, "
            "capped at 1, by the group's share of the diet's calories, and says how much of the diet the covered groups "
            "are. A country figure, never a city's: it is the bracket a place's own food system sits inside.")


def _num(v: str) -> float | None:
    return float(v) if v not in (None, "") else None


def sheet(csv_text: str, countries: dict[str, dict]) -> dict:
    """The food bracket for every tracker country, from the FBS CSV text (wide, one column per year). Pure."""
    m49_of = {v["m49"]: c for c, v in countries.items() if v["m49"]}
    cells = {}                                                   # (m49, item, element) -> {year: value}
    years = set()
    for r in csv.DictReader(io.StringIO(csv_text)):
        code = r["Area Code (M49)"].lstrip("'")
        if not code.isdigit() or int(code) not in m49_of or r["Element Code"] not in ELEMENTS:
            continue
        item = int(r["Item Code"])
        if item != TOTAL and item not in GROUPS:
            continue
        ys = {int(k[1:]): _num(v) for k, v in r.items() if k.startswith("Y") and k[1:].isdigit() and v != ""}
        years |= ys.keys()
        cells[(int(code), item, ELEMENTS[r["Element Code"]])] = ys
    out, absent = {}, []
    for country, v in countries.items():
        total = cells.get((v["m49"], TOTAL, "kcal_per_person_day")) if v["m49"] else None
        if not total:
            absent.append(country)
            continue
        year = max(total)
        groups, num, den, covered_kcal = {}, 0.0, 0.0, 0.0
        for item, name in GROUPS.items():
            g = {e: (cells.get((v["m49"], item, e)) or {}).get(year) for e in ELEMENTS.values()}
            p, m, x = g["production_kt"], g["imports_kt"], g["exports_kt"]
            ok = None not in (p, m, x) and (p + m - x) > 0
            g["ssr"] = round(p / (p + m - x), 2) if ok else None
            g["state"] = "measured" if ok else "not covered: FAO leaves a value blank" if None in (p, m, x) else "not covered: nothing kept"
            groups[name] = g
            w = g["kcal_per_person_day"] or 0.0
            if ok and w:
                num += w * min(1.0, p / (p + m - x))
                den += w
                covered_kcal += w
        t = total[year]
        out[v["iso"]] = {
            "name": country, "places": v["places"], "m49": v["m49"], "year": year,
            "kcal_per_person_day": t,
            "self_supply_kcal_weighted": round(num / den, 2) if den else None,
            "kcal_weight_covered_share": round(covered_kcal / t, 2) if t else None,
            "groups_measured": sum(g["ssr"] is not None for g in groups.values()), "groups": groups}
    return {"reads_as": READS_AS, "licence": LICENCE, "year": max(c["year"] for c in out.values()) if out else None,
            "years_in_sheet": [min(years), max(years)] if years else None, "countries": out, "not_in_fao": absent}


def run() -> int:
    tracker = waste._json(atlas.TRACKER)
    countries = atlas.countries_of(waste._raw(f"{atlas.DATAVERSE}access/datafile/{atlas.FILES['countries']}").decode("utf-8"), tracker)
    z = zipfile.ZipFile(io.BytesIO(waste._raw(FBS_ZIP)))
    out = sheet(z.read(FBS_CSV).decode("utf-8"), countries)
    out["source"] = (f"FAO, FAOSTAT Food Balance Sheets (2010-), bulk file {FBS_ZIP} ({FBS_CSV}), elements 5511, 5611, 5911 "
                     f"and 664, years {out['years_in_sheet']}; country codes from the Atlas classification (M49)")
    res = HERE / "results"
    res.mkdir(exist_ok=True)
    (res / "food-country.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"{'country':8} {'places':>6} {'year':>4} {'kcal/p/d':>8} {'self-supply (kcal-weighted)':>27} {'diet covered':>12} {'cereals':>7} {'meat':>5} {'veg':>5}")
    for iso, c in out["countries"].items():
        g = c["groups"]
        print(f"{iso:8} {c['places']:>6} {c['year']:>4} {c['kcal_per_person_day']:>8.0f} {c['self_supply_kcal_weighted']!s:>27} "
              f"{c['kcal_weight_covered_share']:>12.0%} {g['Cereals']['ssr']!s:>7} {g['Meat']['ssr']!s:>5} {g['Vegetables']['ssr']!s:>5}")
    for country in out["not_in_fao"]:
        print(f"{country}: not in the Food Balance Sheets (absent, not zero)")
    return 0


def selftest() -> int:
    bad = 0

    def check(label, got, want):
        nonlocal bad
        ok = got == want
        bad += not ok
        print(f"  {'ok ' if ok else 'BAD'} {label}" + ("" if ok else f": got {got!r}, want {want!r}"))

    head = "Area Code,Area Code (M49),Area,Item Code,Item Code (FBS),Item,Element Code,Element,Unit,Y2022,Y2023\n"
    row = lambda m49, item, el, y22, y23: f"203,'{m49},X,{item},S{item},I,{el},E,U,{y22},{y23}\n"   # noqa: E731
    text = head + "".join([
        row(724, 2901, "664", 3000, 3000),                       # Spain: total calories, latest year 2023
        row(724, 2905, "5511", 100, 120), row(724, 2905, "5611", 10, 270), row(724, 2905, "5911", 0, 30), row(724, 2905, "664", 700, 760),
        row(724, 2943, "5511", 70, 74), row(724, 2943, "5611", 6, 6), row(724, 2943, "5911", 30, 31), row(724, 2943, "664", 400, 400),
        row(724, 2922, "5511", "", ""), row(724, 2922, "5611", 8, 9), row(724, 2922, "5911", 5, 5), row(724, 2922, "664", 20, 23),
        row(724, 2923, "5511", "", 0), row(724, 2923, "5611", 1, 1), row(724, 2923, "5911", 1, 1), row(724, 2923, "664", 1, 1),
        row(410, 2901, "664", 3100, ""),                         # Korea: no 2023 total, so 2022 is its year
        row(410, 2905, "5511", 50, 55), row(410, 2905, "5611", 150, 160), row(410, 2905, "5911", 0, 0), row(410, 2905, "664", 900, 910),
    ])
    countries = {"Spain": {"places": 2, "iso": "ESP", "m49": 724}, "Korea, South": {"places": 1, "iso": "KOR", "m49": 410},
                 "Bhutan": {"places": 1, "iso": None, "m49": None}, "Ghana": {"places": 1, "iso": "GHA", "m49": 288}}
    out = sheet(text, countries)
    es = out["countries"]["ESP"]
    check("the year is the latest with a calorie total", (es["year"], out["countries"]["KOR"]["year"]), (2023, 2022))
    check("SSR = production / (production + imports - exports): cereals 120/360", es["groups"]["Cereals"]["ssr"], 0.33)
    check("meat above 1 is kept uncapped in the group: 74/49", es["groups"]["Meat"]["ssr"], 1.51)
    check("a blank production is not covered, never zero", (es["groups"]["Stimulants"]["ssr"], es["groups"]["Stimulants"]["state"]),
          (None, "not covered: FAO leaves a value blank"))
    check("nothing kept (0 + 1 - 1) is not covered, not infinity", es["groups"]["Spices"]["state"], "not covered: nothing kept")
    check("a group with no rows at all is not covered", es["groups"]["Eggs"]["ssr"], None)
    check("kcal-weighted, capped: (760 x 0.333 + 400 x 1) / 1160", es["self_supply_kcal_weighted"], 0.56)
    check("diet covered by measured groups: 1160 of 3000", (es["kcal_weight_covered_share"], es["groups_measured"]), (0.39, 2))
    check("a country without a sheet is absent, never zero; a country without an Atlas row too", out["not_in_fao"], ["Bhutan", "Ghana"])
    check("the M49 quote is stripped and places carried", (es["m49"], es["places"]), (724, 2))
    print(f"\nfood selftest: {bad} failed.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else run())

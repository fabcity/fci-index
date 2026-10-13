#!/usr/bin/env python3
"""Downscaling check: can a country's trade be split to a region by a key, and by how much is it wrong?

    python3 compute/downscale.py --selftest     # no network: the arithmetic on fake inputs
    python3 compute/downscale.py                # Atlas + Eurostat, write compute/results/downscale-check.json

Most of the tracker's 61 places have no customs data of their own. Three regions do (trade.regional_trade: Catalonia
from Idescat, Land Hamburg from Statistikamt Nord, Île-de-France from French customs), and that is what makes a
model checkable. This script models each of those regions' imports and exports from the COUNTRY's trade in the Atlas
of Economic Complexity (compute/atlas.py's tables) split by two keys, and sets the result against the measured
figure:

  population key   region's share of the country's population (demo_r_d2jan), one number for everything
  employment key   per Atlas goods sector, the region's share of the country's employment in the NACE divisions
                   that make that sector's goods (sbs_r_nuts06_r2 V16110 to 2020, sbs_r_nuts2021 EMP_LOC_NR from 2021)

The output is the ratio modelled / measured per region, year, direction and key. That ratio is the error bar any
downscaled figure for the other places would carry, and it is the reason this runs before anything is downscaled
for them. Nothing here is served on a page: it is a method result, read in compute/README.md.

What it cannot do: a region with no NUTS2 code in the measured rows (Paris as a département, the province of
Barcelona) is skipped, because the employment table is NUTS2; Boston is skipped because its key would be a US
table this pipeline does not read; a division the region suppresses drops out of its sector's key, and the row says
which. The Atlas is goods only, in US dollars, converted at Eurostat's annual average (ert_bil_eur_a).
"""
from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import atlas  # noqa: E402
import fabcity_index as fci  # noqa: E402
import waste  # noqa: E402

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results" / "fabcity-index-2019.json"
# The measured territories with a NUTS2 code. The others in regional_trade are listed with why they are skipped.
NUTS2 = {"Catalonia": "ES51", "Land Hamburg": "DE60", "Île-de-France": "FR10"}
# Atlas goods sectors (product level 1) to the NACE divisions that make those goods. Farming (A) is not in SBS, so
# the agriculture sector's key is its food, wood and paper manufacturing.
NACE = {"Textiles, garments, footwear and furniture": ["C13", "C14", "C15", "C31"],
        "Vegetables, animals, wood and paper": ["C10", "C11", "C12", "C16", "C17"],
        "Stone, glass and ceramics": ["C23"],
        "Minerals, fuels, ores and salts": ["B05", "B06", "B07", "B08", "B09", "C19"],
        "Metals": ["C24", "C25"],
        "Chemicals and plastics": ["C20", "C21", "C22"],
        "Transport vehicles": ["C29", "C30"],
        "Machinery and instruments": ["C28"],
        "Electronics": ["C26", "C27"],
        "Other": ["C32"]}
READS_AS = ("Modelled over measured. 1.00 means the key reproduces the region's customs figure; 0.50 means the model "
            "gives half of it. The population key is the naive split; the employment key splits each goods sector by "
            "where the country's workers in that industry are. Neither is a measurement, and the ratio is the error any "
            "downscaled figure for a place without customs data would carry.")


def employment(region: str, year: int, get=fci.fetch) -> dict[str, dict[str, float]]:
    """Persons employed by NACE division, for the region and its country, from the table that covers the year."""
    c = region[:2]
    if year <= 2020:
        d = get("sbs_r_nuts06_r2", geo=[region, c], time=year, indic_sb="V16110")
    else:
        d = get("sbs_r_nuts2021", geo=[region, c], time=year, indic_sbs="EMP_LOC_NR")
    dims, size, v = d["id"], d["size"], d["value"]
    strides, s = {}, 1
    for k in reversed(dims):
        strides[k], s = s, s * size[dims.index(k)]
    out = {}
    for geo, gi in d["dimension"]["geo"]["category"]["index"].items():
        out[geo] = {n: v[str(gi * strides["geo"] + ni * strides["nace_r2"])]
                    for n, ni in d["dimension"]["nace_r2"]["category"]["index"].items()
                    if str(gi * strides["geo"] + ni * strides["nace_r2"]) in v}
    return {"region": out.get(region, {}), "country": out.get(c, {})}


def keys(region: str, year: int, get=fci.fetch) -> dict:
    """The population key and the per-sector employment keys, with the divisions each one used."""
    c = region[:2]
    pop = fci.by(get("demo_r_d2jan", geo=[region, c], time=year, sex="T", age="TOTAL", unit="NR"), "geo")
    emp = employment(region, year, get)
    # A sector whose region suppresses a division falls back to the section key (all manufacturing, C): Hamburg 2019
    # publishes C30 (Airbus) but not C29 (cars), and the C30-only key gave Hamburg 13% of Germany's vehicle exports.
    section = (emp["region"]["C"] / emp["country"]["C"]) if emp["region"].get("C") is not None and emp["country"].get("C") else None
    sectors = {}
    for sector, divisions in NACE.items():
        used = [n for n in divisions if emp["region"].get(n) is not None and emp["country"].get(n)]
        missing = [n for n in divisions if n not in used]
        whole = bool(used) and not missing
        sectors[sector] = {"share": sum(emp["region"][n] for n in used) / sum(emp["country"][n] for n in used) if whole else section,
                           "nace_used": used if whole else ["C"], "nace_missing": missing,
                           "key": "sector divisions" if whole else "section C fallback" if section is not None else "none"}
    return {"population_share": pop[region] / pop[c], "employment": sectors,
            "employment_table": "sbs_r_nuts06_r2 V16110" if year <= 2020 else "sbs_r_nuts2021 EMP_LOC_NR"}


def national(iso: str, year: int, country_year: str, sector_year: str, products: str) -> dict | None:
    """The country's Atlas exports and imports for the year, total and by goods sector, in current USD."""
    total = next((r for r in csv.DictReader(io.StringIO(country_year)) if r["country_iso3_code"] == iso and int(r["year"]) == year), None)
    if not total:
        return None
    name = {r["product_id"]: r["product_name"] for r in csv.DictReader(io.StringIO(products)) if r["product_level"] == "1"}
    sectors = {name[r["product_id"]]: (float(r["export_value"]), float(r["import_value"]))
               for r in csv.DictReader(io.StringIO(sector_year)) if r["country_iso3_code"] == iso and int(r["year"]) == year}
    return {"exports_usd": float(total["export_value"]), "imports_usd": float(total["import_value"]), "sectors": sectors}


def check(row: dict, nat: dict, k: dict, usd_per_eur: float) -> dict:
    """One measured region-year against the two models. Measured values in EUR; the Atlas converted from USD."""
    eur = lambda usd: usd / usd_per_eur   # noqa: E731
    pop = k["population_share"]
    emp = {s: v["share"] for s, v in k["employment"].items()}
    by_emp = lambda i: sum(eur(v[i]) * emp[s] for s, v in nat["sectors"].items() if emp.get(s) is not None)  # noqa: E731  no key: the sector drops out
    model = {"population_key": {"imports_eur": eur(nat["imports_usd"]) * pop, "exports_eur": eur(nat["exports_usd"]) * pop},
             "employment_key": {"imports_eur": by_emp(1), "exports_eur": by_emp(0)}}
    out = {"city": row["city"], "territory": row["territory"], "nuts2": NUTS2[row["territory"]], "year": row["year"],
           "measured": {"imports_eur": row["imports_eur"], "exports_eur": row["exports_eur"], "provisional": row.get("provisional")},
           "national_atlas": {"imports_eur": round(eur(nat["imports_usd"])), "exports_eur": round(eur(nat["exports_usd"])), "usd_per_eur": usd_per_eur},
           "keys": {"population_share": round(pop, 4), "employment_table": k["employment_table"],
                    "employment_by_sector": {s: {"share": round(v["share"], 4) if v["share"] is not None else None, "key": v["key"],
                                                 "nace_used": v["nace_used"], "nace_missing": v["nace_missing"]} for s, v in k["employment"].items()}},
           "modelled": {kk: {d: round(x) for d, x in m.items()} for kk, m in model.items()},
           "modelled_over_measured": {kk: {d: round(m[d] / row[d], 2) if row.get(d) else None for d in ("imports_eur", "exports_eur")}
                                      for kk, m in model.items()}}
    return out


def run() -> int:
    results = json.loads(RESULTS.read_text(encoding="utf-8"))
    tables = {k: waste._raw(f"{atlas.DATAVERSE}access/datafile/{atlas.FILES[k]}").decode("utf-8") for k in ("country_year", "sector_year", "products")}
    iso = {"ES": "ESP", "DE": "DEU", "FR": "FRA"}
    rates = fci.by(fci.fetch("ert_bil_eur_a", currency="USD", statinfo="AVG"), "time")
    rows, skipped = [], []
    for r in results["regional_trade"]["rows"]:
        if r.get("no_data") or r.get("imports_eur") is None and r.get("exports_eur") is None:
            skipped.append({"city": r["city"], "year": r.get("year"), "why": r.get("no_data") or "no measured value in euros (Boston's exports are in dollars, and the key would need a US table)"})
            continue
        if r["territory"] not in NUTS2:
            skipped.append({"city": r["city"], "territory": r["territory"], "year": r["year"], "why": "no NUTS2 code: the employment table is NUTS2"})
            continue
        region = NUTS2[r["territory"]]
        nat = national(iso[region[:2]], r["year"], tables["country_year"], tables["sector_year"], tables["products"])
        if nat is None or str(r["year"]) not in rates:
            skipped.append({"city": r["city"], "territory": r["territory"], "year": r["year"], "why": "no Atlas or exchange-rate row for the year"})
            continue
        rows.append(check(r, nat, keys(region, r["year"]), rates[str(r["year"])]))
    out = {"reads_as": READS_AS, "rows": rows, "skipped": skipped,
           "source": "Atlas of Economic Complexity hs92 country_year and country_product_year_1 (CC0); Eurostat demo_r_d2jan, "
                     "sbs_r_nuts06_r2, sbs_r_nuts2021, ert_bil_eur_a (reuse with acknowledgement, 2011/833/EU); measured rows from "
                     "compute/trade.py regional_trade, each with its own licence"}
    (HERE / "results" / "downscale-check.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"{'territory':16} {'year':>4} {'measured M/X bn EUR':>20} {'pop key M/X':>12} {'emp key M/X':>12}")
    for r in rows:
        m, p, e = r["measured"], r["modelled_over_measured"]["population_key"], r["modelled_over_measured"]["employment_key"]
        print(f"{r['territory']:16} {r['year']:>4} {m['imports_eur'] / 1e9:>9.1f} / {m['exports_eur'] / 1e9:<8.1f} "
              f"{p['imports_eur']!s:>5} / {p['exports_eur']!s:<5} {e['imports_eur']!s:>5} / {e['exports_eur']!s:<5}")
    for s in skipped:
        print(f"skipped {s['city']} {s.get('territory', '')} {s.get('year') or ''}: {s['why']}")
    return 0


def selftest() -> int:
    bad = 0

    def ok(label, got, want):
        nonlocal bad
        good = got == want
        bad += not good
        print(f"  {'ok ' if good else 'BAD'} {label}" + ("" if good else f": got {got!r}, want {want!r}"))

    def js(dims: dict, values: dict) -> dict:                  # a JSON-stat answer with one value per cell
        ids = list(dims)
        size = [len(v) for v in dims.values()]
        return {"id": ids, "size": size, "value": values,
                "dimension": {k: {"category": {"index": {c: i for i, c in enumerate(v)}}} for k, v in dims.items()}}

    def get(dataset, **p):
        if dataset == "demo_r_d2jan":
            return js({"geo": ["ES51", "ES"]}, {"0": 7_500_000, "1": 47_000_000})
        if dataset == "sbs_r_nuts06_r2":                       # ES51 reports C13 but not C14, all of C23, no C32; section C 500 of 5000
            return js({"nace_r2": ["C", "C13", "C14", "C23", "C32"], "geo": ["ES51", "ES"]},
                      {"0": 500, "1": 5000, "2": 100, "3": 400, "5": 1000, "6": 50, "7": 100, "9": 300})
        raise AssertionError(dataset)

    k = keys("ES51", 2019, get)
    ok("population key is the region's share", round(k["population_share"], 4), 0.1596)
    tex = k["employment"]["Textiles, garments, footwear and furniture"]
    ok("a sector with every division reported uses them: C23 50/100", (k["employment"]["Stone, glass and ceramics"]["share"], k["employment"]["Stone, glass and ceramics"]["key"]), (0.5, "sector divisions"))
    ok("a sector with a suppressed division falls back to the section key, and says which were missing",
       (tex["share"], tex["key"], tex["nace_used"], tex["nace_missing"]), (0.1, "section C fallback", ["C"], ["C14", "C15", "C31"]))
    ok("a sector with nothing reported falls back too", k["employment"]["Other"]["key"], "section C fallback")
    ok("the table follows the year", (k["employment_table"], keys.__defaults__[0].__name__), ("sbs_r_nuts06_r2 V16110", "fetch"))
    cy = "country_id,country_iso3_code,year,export_value,import_value,eci\n724,ESP,2019,300,400,0.8\n724,ESP,2024,369,398,0.8\n"
    pr = "product_id,product_hs92_code,product_level,product_name\n1,0,1,\"Textiles, garments, footwear and furniture\"\n3,2,1,\"Stone, glass and ceramics\"\n100,01,2,Live animals\n"
    sy = ("country_id,country_iso3_code,product_id,product_hs92_code,year,export_value,import_value\n"
          "724,ESP,1,0,2019,200,100\n724,ESP,3,2,2019,100,300\n724,ESP,1,0,2024,1,1\n")
    nat = national("ESP", 2019, cy, sy, pr)
    ok("national totals and sectors for the year only", (nat["exports_usd"], nat["sectors"]), (300.0, {"Textiles, garments, footwear and furniture": (200.0, 100.0), "Stone, glass and ceramics": (100.0, 300.0)}))
    ok("a year the Atlas lacks is None", national("ESP", 2018, cy, sy, pr), None)
    row = {"city": "Barcelona", "territory": "Catalonia", "year": 2019, "imports_eur": 100.0, "exports_eur": 50.0, "provisional": False}
    c = check(row, nat, k, 2.0)                                # 2 USD per EUR: national 150 X / 200 M EUR
    ok("population key: 200 x 0.1596 = 31.9 M, 150 x 0.1596 = 23.9 X", c["modelled"]["population_key"], {"imports_eur": 32, "exports_eur": 24})
    ok("employment key: textiles at the 0.1 fallback (100 X, 50 M), stone at 0.5 (50 X, 150 M), in EUR", c["modelled"]["employment_key"], {"imports_eur": 80, "exports_eur": 35})
    ok("modelled over measured", c["modelled_over_measured"], {"population_key": {"imports_eur": 0.32, "exports_eur": 0.48}, "employment_key": {"imports_eur": 0.8, "exports_eur": 0.7}})
    print(f"\ndownscale selftest: {bad} failed.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else run())

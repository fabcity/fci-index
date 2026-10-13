#!/usr/bin/env python3
"""Downscaling: can a country's trade be split to a region by a key, by how much is it wrong, and where may it be used?

    python3 compute/downscale.py --selftest     # no network: the arithmetic and the place rules on fake inputs
    python3 compute/downscale.py                # Atlas + Eurostat + the registry's places.yaml, write compute/results/downscale-check.json

Most of the tracker's 61 places have no customs data of their own. Three regions do (trade.regional_trade: Catalonia
from Idescat, Land Hamburg from Statistikamt Nord, Île-de-France from French customs), and that is what makes a
model checkable. Part one, the CHECK, models each of those regions' imports and exports from the COUNTRY's trade in
the Atlas of Economic Complexity (compute/atlas.py's tables) split by two keys, and sets the result against the
measured figure:

  population key   region's share of the country's population (demo_r_d2jan), one number for everything
  employment key   per Atlas goods sector, the region's share of the country's employment in the NACE divisions
                   that make that sector's goods (sbs_r_nuts06_r2 V16110 to 2020, sbs_r_nuts2021 EMP_LOC_NR from 2021)

The ratio modelled / measured is the error bar any downscaled figure carries. The check found it is not one number:
within a fifth for Catalonia, which makes things, and 2-5x under for Hamburg (a port's customs trade lands for the
whole country) and Île-de-France (customs attribute trade to head offices).

Part two, the PLACES, reads the registry's places.yaml at main's commit, the way api.mjs reads index.json. Each
place carries `nuts2` (NUTS 2024, `+` joining the units a place spans) and `kind`, a list of traits. A place with
`seaport` or `national-capital` is refused, a `country` row has the Atlas bracket itself, a place without a NUTS2
code has no key; the rest are modelled for the latest Atlas year, by both keys, with the check's error bar for a
place that makes things attached. Nothing here is served on a page: results/downscale-check.json is a method
result read in compute/README.md, and whether a modelled bracket reaches a page is a maintainer's decision.
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
REGISTRY_API = "https://api.github.com/repos/fabcity/awesome-fabcity-data/commits/main"
PLACES_AT = "https://raw.githubusercontent.com/fabcity/awesome-fabcity-data/{}/places.yaml"
# The measured territories with a NUTS2 code, the tracker place each belongs to, and the TERRITORY's traits, which are
# not the place's: Barcelona is a seaport city, but Catalonia is a region of eight million with a port in it, and the
# check found its customs trade follows its factories. Land Hamburg is a city-state that is a port; Île-de-France
# holds the head offices. The others in regional_trade are listed with why they are skipped. Cross-checked against
# places.yaml's nuts2 at run time.
NUTS2 = {"Catalonia": ("ES51", "barcelona", []), "Land Hamburg": ("DE60", "hamburg", ["seaport"]), "Île-de-France": ("FR10", "paris", ["national-capital"])}
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
# Traits in places.yaml that refuse a national key, with the measured reason.
REFUSE = {"seaport": "a port's customs trade lands for the whole country (the check: Hamburg 3-5x under)",
          "national-capital": "customs attribute trade to head offices (the check: Île-de-France 2x under)",
          "country": "a country row carries the Atlas bracket itself"}
READS_AS = ("Modelled over measured. 1.00 means the key reproduces the region's customs figure; 0.50 means the model "
            "gives half of it. The population key is the naive split; the employment key splits each goods sector by "
            "where the country's workers in that industry are. Neither is a measurement, and the ratio is the error any "
            "downscaled figure for a place without customs data would carry.")
PLACES_READ_AS = ("For every tracker place: whether a national figure may be split down to it, and why. Refused for a "
                  "seaport or a national capital (the check says how wrong that would be), not possible without a NUTS2 "
                  "code, allowed otherwise. The modelled rows are the NUTS2 region that holds the place, not the place: "
                  "Schwaben for Augsburg, Bretagne for Brest. They are modelled, never measured, and carry the error bar "
                  "the check measured for a region that makes things.")


# ---- the registry's places --------------------------------------------------------------------------------------

def parse_places(text: str) -> list[dict]:
    """places.yaml without PyYAML: it is the registry's own regular file (`- slug:` blocks, `key: value` lines,
    `[a, b]` lists, "quoted" strings). Anything else in it would be a schema change to notice."""
    places, cur = [], None
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s == "places:":
            continue
        if s.startswith("- "):
            cur = {}
            places.append(cur)
            s = s[2:]
        k, _, v = s.partition(":")
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            v = [x.strip() for x in v[1:-1].split(",") if x.strip()]
        elif len(v) >= 2 and v[0] == v[-1] == '"':
            v = v[1:-1].replace('\\"', '"')
        cur[k.strip()] = v
    return places


def places_at_main() -> tuple[str, list[dict]]:
    sha = waste._json(REGISTRY_API)["sha"]
    return sha, parse_places(waste._raw(PLACES_AT.format(sha)).decode("utf-8"))


def eligibility(places: list[dict]) -> list[dict]:
    """Where a national key may be applied, place by place, from `kind` and `nuts2`."""
    out = []
    for p in places:
        traits = p.get("kind") or []
        refused = [t for t in traits if t in REFUSE]
        if refused:
            allowed, why = False, "refused: " + "; ".join(REFUSE[t] for t in refused)
        elif not p.get("nuts2"):
            allowed, why = False, "no NUTS2 code, and the employment key is a Eurostat regional table" + (f" ({p['nuts_note']})" if p.get("nuts_note") else "")
        else:
            allowed, why = True, "a NUTS2 key and no refusing trait; kind_note: " + (p.get("kind_note") or "")
        out.append({"slug": p["slug"], "name": p["name"], "country": p["country"], "kind": traits, "nuts2": p.get("nuts2"),
                    "downscale": allowed, "why": why})
    return out


# ---- the keys ---------------------------------------------------------------------------------------------------

def employment(region: str, year: int, get=fci.fetch) -> dict[str, dict[str, float]]:
    """Persons employed by NACE division, for the region (summed over its `+` units) and its country, from the table
    that covers the year. A division one unit does not report is absent for the region, never a partial sum."""
    units = region.split("+")
    c = units[0][:2]
    if year <= 2020:
        d = get("sbs_r_nuts06_r2", geo=[*units, c], time=year, indic_sb="V16110")
    else:
        d = get("sbs_r_nuts2021", geo=[*units, c], time=year, indic_sbs="EMP_LOC_NR")
    dims, size, v = d["id"], d["size"], d["value"]
    strides, s = {}, 1
    for k in reversed(dims):
        strides[k], s = s, s * size[dims.index(k)]
    out = {}
    for geo, gi in d["dimension"]["geo"]["category"]["index"].items():
        out[geo] = {n: v[str(gi * strides["geo"] + ni * strides["nace_r2"])]
                    for n, ni in d["dimension"]["nace_r2"]["category"]["index"].items()
                    if str(gi * strides["geo"] + ni * strides["nace_r2"]) in v}
    region_sum = {n: sum(out.get(u, {})[n] for u in units)
                  for n in out.get(units[0], {}) if all(n in out.get(u, {}) for u in units)}
    return {"region": region_sum, "country": out.get(c, {})}


def keys(region: str, year: int, get=fci.fetch) -> dict:
    """The population key and the per-sector employment keys, with the divisions each one used. When the year's
    employment table has nothing for the region, the year before is tried once, and the row says which was used."""
    units = region.split("+")
    c = units[0][:2]
    pop = fci.by(get("demo_r_d2jan", geo=[*units, c], time=year, sex="T", age="TOTAL", unit="NR"), "geo")
    emp, emp_year = None, None
    for y in (year, year - 1):
        emp = employment(region, y, get)
        if emp["region"].get("C") is not None:
            emp_year = y
            break
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
    return {"population_share": sum(pop[u] for u in units) / pop[c], "employment": sectors, "employment_year": emp_year,
            "employment_table": "none" if emp_year is None else "sbs_r_nuts06_r2 V16110" if emp_year <= 2020 else "sbs_r_nuts2021 EMP_LOC_NR"}


# ---- the national side, and the model ---------------------------------------------------------------------------

def national(iso: str, year: int, country_year: str, sector_year: str, products: str) -> dict | None:
    """The country's Atlas exports and imports for the year, total and by goods sector, in current USD."""
    total = next((r for r in csv.DictReader(io.StringIO(country_year)) if r["country_iso3_code"] == iso and int(r["year"]) == year), None)
    if not total:
        return None
    name = {r["product_id"]: r["product_name"] for r in csv.DictReader(io.StringIO(products)) if r["product_level"] == "1"}
    sectors = {name[r["product_id"]]: (float(r["export_value"]), float(r["import_value"]))
               for r in csv.DictReader(io.StringIO(sector_year)) if r["country_iso3_code"] == iso and int(r["year"]) == year}
    return {"exports_usd": float(total["export_value"]), "imports_usd": float(total["import_value"]), "sectors": sectors}


def model(nat: dict, k: dict, usd_per_eur: float) -> dict:
    """The region's imports and exports in EUR by each key. A sector with no key drops out of the employment model."""
    eur = lambda usd: usd / usd_per_eur   # noqa: E731
    pop = k["population_share"]
    emp = {s: v["share"] for s, v in k["employment"].items()}
    by_emp = lambda i: sum(eur(v[i]) * emp[s] for s, v in nat["sectors"].items() if emp.get(s) is not None)  # noqa: E731
    return {"population_key": {"imports_eur": eur(nat["imports_usd"]) * pop, "exports_eur": eur(nat["exports_usd"]) * pop},
            "employment_key": {"imports_eur": by_emp(1), "exports_eur": by_emp(0)}}


def key_summary(k: dict) -> dict:
    return {"population_share": round(k["population_share"], 4), "employment_table": k["employment_table"], "employment_year": k["employment_year"],
            "employment_by_sector": {s: {"share": round(v["share"], 4) if v["share"] is not None else None, "key": v["key"],
                                         "nace_used": v["nace_used"], "nace_missing": v["nace_missing"]} for s, v in k["employment"].items()}}


def check(row: dict, nat: dict, k: dict, usd_per_eur: float, place_kind: list[str]) -> dict:
    """One measured region-year against the two models. Measured values in EUR; the Atlas converted from USD."""
    m = model(nat, k, usd_per_eur)
    code, _, territory_kind = NUTS2[row["territory"]]
    return {"city": row["city"], "territory": row["territory"], "nuts2": code, "year": row["year"],
            "kind": territory_kind, "place_kind": place_kind,
            "measured": {"imports_eur": row["imports_eur"], "exports_eur": row["exports_eur"], "provisional": row.get("provisional")},
            "national_atlas": {"imports_eur": round(nat["imports_usd"] / usd_per_eur), "exports_eur": round(nat["exports_usd"] / usd_per_eur), "usd_per_eur": usd_per_eur},
            "keys": key_summary(k),
            "modelled": {kk: {d: round(x) for d, x in mm.items()} for kk, mm in m.items()},
            "modelled_over_measured": {kk: {d: round(mm[d] / row[d], 2) if row.get(d) else None for d in ("imports_eur", "exports_eur")}
                                       for kk, mm in m.items()}}


def error_bar(rows: list[dict]) -> dict | None:
    """What the check measured for territories with no refusing trait: the range of modelled / measured by key."""
    plain = [r for r in rows if not any(t in REFUSE for t in r["kind"])]
    if not plain:
        return None
    rng = lambda key, d: (min(r["modelled_over_measured"][key][d] for r in plain), max(r["modelled_over_measured"][key][d] for r in plain))  # noqa: E731
    return {"from": sorted({f"{r['territory']} {r['year']}" for r in plain}),
            **{key: {d: rng(key, d) for d in ("imports_eur", "exports_eur")} for key in ("population_key", "employment_key")}}


def modelled_place(e: dict, nat: dict, k: dict, usd_per_eur: float, year: int, bar: dict | None) -> dict:
    m = model(nat, k, usd_per_eur)
    return {"slug": e["slug"], "name": e["name"], "country": e["country"], "nuts2": e["nuts2"], "year": year, "state": "modelled",
            "reads_as": f"the NUTS2 region {e['nuts2']} that holds {e['name']}, not {e['name']} itself; a national figure split by a key, never measured",
            "modelled": {kk: {d: round(x) for d, x in mm.items()} for kk, mm in m.items()},
            "error_bar_modelled_over_measured": bar, "keys": key_summary(k),
            "national_atlas": {"imports_eur": round(nat["imports_usd"] / usd_per_eur), "exports_eur": round(nat["exports_usd"] / usd_per_eur), "usd_per_eur": usd_per_eur}}


# ---- the run ----------------------------------------------------------------------------------------------------

def run() -> int:
    results = json.loads(RESULTS.read_text(encoding="utf-8"))
    tables = {k: waste._raw(f"{atlas.DATAVERSE}access/datafile/{atlas.FILES[k]}").decode("utf-8") for k in ("country_year", "sector_year", "products", "countries")}
    rates = fci.by(fci.fetch("ert_bil_eur_a", currency="USD", statinfo="AVG"), "time")
    sha, places = places_at_main()
    by_slug = {p["slug"]: p for p in places}
    iso = {c: v["iso"] for c, v in atlas.countries_of(tables["countries"], {"localities": [{"country": p["country"]} for p in places]}).items()}

    # Part one: the check against the measured regions.
    rows, skipped = [], []
    for r in results["regional_trade"]["rows"]:
        if r.get("no_data") or r.get("imports_eur") is None and r.get("exports_eur") is None:
            skipped.append({"city": r["city"], "year": r.get("year"), "why": r.get("no_data") or "no measured value in euros (Boston's exports are in dollars, and the key would need a US table)"})
            continue
        if r["territory"] not in NUTS2:
            skipped.append({"city": r["city"], "territory": r["territory"], "year": r["year"], "why": "no NUTS2 code: the employment table is NUTS2"})
            continue
        region, slug, _ = NUTS2[r["territory"]]
        if by_slug[slug].get("nuts2") != region:
            raise SystemExit(f"places.yaml says {slug} is in {by_slug[slug].get('nuts2')}, this script says {region}: fix one")
        nat = national(iso[by_slug[slug]["country"]], r["year"], tables["country_year"], tables["sector_year"], tables["products"])
        if nat is None or str(r["year"]) not in rates:
            skipped.append({"city": r["city"], "territory": r["territory"], "year": r["year"], "why": "no Atlas or exchange-rate row for the year"})
            continue
        rows.append(check(r, nat, keys(region, r["year"]), rates[str(r["year"])], by_slug[slug].get("kind") or []))
    bar = error_bar(rows)

    # Part two: every place, and the modelled regions for those where a key may be applied.
    elig = eligibility(places)
    year = max(int(r["year"]) for r in csv.DictReader(io.StringIO(tables["country_year"])))
    modelled, not_modelled = [], []
    for e in elig:
        if not e["downscale"]:
            continue
        nat = national(iso.get(e["country"]), year, tables["country_year"], tables["sector_year"], tables["products"]) if iso.get(e["country"]) else None
        if nat is None or str(year) not in rates:
            not_modelled.append({"slug": e["slug"], "why": "no Atlas or exchange-rate row for the year"})
            continue
        k = keys(e["nuts2"], year)
        if k["employment_year"] is None:
            not_modelled.append({"slug": e["slug"], "why": f"no employment row for {e['nuts2']} in {year} or {year - 1}"})
            continue
        modelled.append(modelled_place(e, nat, k, rates[str(year)], year, bar))

    out = {"reads_as": READS_AS, "rows": rows, "skipped": skipped, "error_bar_modelled_over_measured": bar,
           "places": {"reads_as": PLACES_READ_AS, "registry_commit": sha, "year": year,
                      "counts": {"places": len(elig), "allowed": sum(e["downscale"] for e in elig), "modelled": len(modelled)},
                      "eligibility": elig, "modelled": modelled, "not_modelled": not_modelled},
           "source": "Atlas of Economic Complexity hs92 country_year and country_product_year_1 (CC0); Eurostat demo_r_d2jan, "
                     "sbs_r_nuts06_r2, sbs_r_nuts2021, ert_bil_eur_a (reuse with acknowledgement, 2011/833/EU); measured rows from "
                     f"compute/trade.py regional_trade, each with its own licence; places.yaml at awesome-fabcity-data {sha[:7]}"}
    (HERE / "results" / "downscale-check.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")

    print(f"{'territory':16} {'year':>4} {'measured M/X bn EUR':>20} {'pop key M/X':>12} {'emp key M/X':>12}  kind")
    for r in rows:
        m, p, e = r["measured"], r["modelled_over_measured"]["population_key"], r["modelled_over_measured"]["employment_key"]
        print(f"{r['territory']:16} {r['year']:>4} {m['imports_eur'] / 1e9:>9.1f} / {m['exports_eur'] / 1e9:<8.1f} "
              f"{p['imports_eur']!s:>5} / {p['exports_eur']!s:<5} {e['imports_eur']!s:>5} / {e['exports_eur']!s:<5}  territory {r['kind']}, place {r['place_kind']}")
    for s in skipped:
        print(f"skipped {s['city']} {s.get('territory', '')} {s.get('year') or ''}: {s['why']}")
    c = out["places"]["counts"]
    print(f"\nplaces.yaml @ {sha[:7]}: {c['places']} places, {c['allowed']} where a key may be applied, {c['modelled']} modelled for {year}")
    for e in elig:
        if not e["downscale"]:
            print(f"  {e['slug']:24} no   {e['why'][:100]}")
    print(f"\n{'place':24} {'region':10} {'emp yr':>6} {'pop key M/X bn EUR':>19} {'emp key M/X bn EUR':>19}")
    for m in modelled:
        p, e = m["modelled"]["population_key"], m["modelled"]["employment_key"]
        print(f"{m['name']:24} {m['nuts2']:10} {m['keys']['employment_year']:>6} {p['imports_eur'] / 1e9:>8.1f} / {p['exports_eur'] / 1e9:<8.1f} {e['imports_eur'] / 1e9:>8.1f} / {e['exports_eur'] / 1e9:<8.1f}")
    for n in not_modelled:
        print(f"  {n['slug']}: {n['why']}")
    if bar:
        print(f"\nerror bar, from {bar['from']}: employment key {bar['employment_key']}, population key {bar['population_key']}")
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
    ok("the table and year follow the year", (k["employment_table"], k["employment_year"]), ("sbs_r_nuts06_r2 V16110", 2019))

    # A `+` region: two French NUTS2 summed; a division one unit lacks is absent; the 2024 table is empty, 2023 serves.
    def get_fr(dataset, **p):
        if dataset == "demo_r_d2jan":
            return js({"geo": ["FRK1", "FRK2", "FR"]}, {"0": 1_000_000, "1": 7_000_000, "2": 68_000_000})
        if dataset == "sbs_r_nuts2021":
            if p["time"] == 2024:
                return js({"nace_r2": ["C", "C23"], "geo": ["FRK1", "FRK2", "FR"]}, {})
            return js({"nace_r2": ["C", "C23"], "geo": ["FRK1", "FRK2", "FR"]}, {"0": 100, "1": 300, "2": 4000, "3": 10, "5": 100})  # FRK2 lacks C23
        raise AssertionError(dataset)
    kf = keys("FRK1+FRK2", 2024, get_fr)
    ok("a + region sums its units: (100 + 300) / 4000, population (1 + 7) / 68", (kf["employment"]["Stone, glass and ceramics"]["share"], round(kf["population_share"], 4)), (0.1, 0.1176))
    ok("a division one unit lacks is absent for the region, so the sector falls back", kf["employment"]["Stone, glass and ceramics"]["key"], "section C fallback")
    ok("an empty year falls back to the year before, and says so", (kf["employment_year"], kf["employment_table"]), (2023, "sbs_r_nuts2021 EMP_LOC_NR"))

    cy = "country_id,country_iso3_code,year,export_value,import_value,eci\n724,ESP,2019,300,400,0.8\n724,ESP,2024,369,398,0.8\n"
    pr = "product_id,product_hs92_code,product_level,product_name\n1,0,1,\"Textiles, garments, footwear and furniture\"\n3,2,1,\"Stone, glass and ceramics\"\n100,01,2,Live animals\n"
    sy = ("country_id,country_iso3_code,product_id,product_hs92_code,year,export_value,import_value\n"
          "724,ESP,1,0,2019,200,100\n724,ESP,3,2,2019,100,300\n724,ESP,1,0,2024,1,1\n")
    nat = national("ESP", 2019, cy, sy, pr)
    ok("national totals and sectors for the year only", (nat["exports_usd"], nat["sectors"]), (300.0, {"Textiles, garments, footwear and furniture": (200.0, 100.0), "Stone, glass and ceramics": (100.0, 300.0)}))
    ok("a year the Atlas lacks is None", national("ESP", 2018, cy, sy, pr), None)
    row = {"city": "Barcelona", "territory": "Catalonia", "year": 2019, "imports_eur": 100.0, "exports_eur": 50.0, "provisional": False}
    c = check(row, nat, k, 2.0, [])                            # 2 USD per EUR: national 150 X / 200 M EUR
    ok("population key: 200 x 0.1596 = 31.9 M, 150 x 0.1596 = 23.9 X", c["modelled"]["population_key"], {"imports_eur": 32, "exports_eur": 24})
    ok("employment key: textiles at the 0.1 fallback (100 X, 50 M), stone at 0.5 (50 X, 150 M), in EUR", c["modelled"]["employment_key"], {"imports_eur": 80, "exports_eur": 35})
    ok("modelled over measured", c["modelled_over_measured"], {"population_key": {"imports_eur": 0.32, "exports_eur": 0.48}, "employment_key": {"imports_eur": 0.8, "exports_eur": 0.7}})
    port = check({**row, "territory": "Land Hamburg", "city": "Hamburg"}, nat, k, 2.0, ["seaport"])
    ok("the territory's kind, not the place's, decides the error bar: Catalonia counts although Barcelona is a seaport",
       (check(row, nat, k, 2.0, ["seaport"])["kind"], port["kind"]), ([], ["seaport"]))
    ok("the error bar comes from the territories with no refusing trait only", error_bar([c, port])["employment_key"], {"imports_eur": (0.8, 0.8), "exports_eur": (0.7, 0.7)})
    ok("no plain region, no error bar", error_bar([port]), None)

    text = ('# a comment\nplaces:\n  - slug: augsburg\n    name: "Augsburg"\n    country: "Germany"\n    nuts2: DE27\n    nuts3: DE271\n    kind: []\n'
            '    kind_note: "nothing read today"\n  - slug: hamburg\n    name: "Hamburg"\n    country: "Germany"\n    nuts2: DE60\n    kind: [seaport]\n'
            '    kind_note: "Port of Hamburg, 96,984 thousand t (Eurostat, read \\"today\\")"\n  - slug: accra\n    name: "Accra"\n    country: "Ghana"\n'
            '    kind: [national-capital]\n    kind_note: "national capital"\n  - slug: plymouth\n    name: "Plymouth"\n    country: "United Kingdom"\n'
            '    nuts_note: "the UK left NUTS"\n    kind: []\n    kind_note: "x"\n  - slug: bhutan\n    name: "Bhutan"\n    country: "Bhutan"\n    kind: [country]\n    kind_note: "a country row"\n')
    places = parse_places(text)
    ok("places.yaml parses: lists, quotes, escaped quotes, optional keys", (len(places), places[1]["kind"], places[1]["kind_note"][-13:], "nuts2" in places[3]),
       (5, ["seaport"], 'read "today")', False))
    e = {x["slug"]: x for x in eligibility(places)}
    ok("a plain place with a NUTS2 code may be downscaled", (e["augsburg"]["downscale"], e["augsburg"]["nuts2"]), (True, "DE27"))
    ok("a seaport is refused with the measured reason", (e["hamburg"]["downscale"], e["hamburg"]["why"][:37]), (False, "refused: a port's customs trade lands"))
    ok("a capital is refused; a place without NUTS2 is not possible, with its note; a country row is refused",
       (e["accra"]["downscale"], e["plymouth"]["downscale"], "the UK left NUTS" in e["plymouth"]["why"], e["bhutan"]["downscale"]), (False, False, True, False))
    mp = modelled_place(e["augsburg"], nat, k, 2.0, 2019, error_bar([c]))
    ok("a modelled place says it is the region, modelled, with the error bar", (mp["state"], mp["nuts2"], "not Augsburg itself" in mp["reads_as"], mp["error_bar_modelled_over_measured"]["employment_key"]["imports_eur"]),
       ("modelled", "DE27", True, (0.8, 0.8)))
    print(f"\ndownscale selftest: {bad} failed.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else run())

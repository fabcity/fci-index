#!/usr/bin/env python3
"""The country bracket, materials: of the materials the country consumes, the share extracted inside it.

    python3 compute/materials.py --selftest     # no network: the reading of a fake OECD slice
    python3 compute/materials.py                # one OECD SDMX call, write compute/results/materials-country.json

OECD economy-wide material flow accounts (registry economic/bioregion/oecd-material-flows-sdmx; OECD terms: any use
including commercial, credit the OECD): DSD_MATERIAL_RESOURCES@DF_MATERIAL_RESOURCES on the public SDMX host, in
tonnes, for every country the tracker names, the small ones included. Domestic material consumption (DMC) is
domestic extraction used (DEU) plus imports minus exports, so the share of what the country consumes that it
extracted itself is DEU over DMC: above 1 the country extracts more than it keeps and exports the rest. Imports and
exports are published separately here, unlike the energy half, and the material footprint (MF, the raw materials
embodied in what the country consumes, wherever they were extracted) stands beside DMC as the consumption-based
view. All in tonnes, so a tonne of sand and a tonne of copper count the same; the four material groups tell them
apart in the place's JSON. A country figure beside each place (api.mjs, `country_bracket.materials`), never a cell.
"""
from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import atlas  # noqa: E402
import waste  # noqa: E402

HERE = Path(__file__).resolve().parent
SDMX = "https://sdmx.oecd.org/public/rest/data/OECD.ENV.EPI,DSD_MATERIAL_RESOURCES@DF_MATERIAL_RESOURCES,1.0/"
FROM = 2019
MEASURES = {"DEU": "domestic_extraction_mt", "IMP": "imports_mt", "EXP": "exports_mt", "DMC": "domestic_material_consumption_mt", "MF": "material_footprint_mt"}
GROUPS = {"TOT": "total", "BIO": "biomass", "MET": "metals", "IND": "non_metallic_minerals", "FUEL": "fossil_energy_materials"}
LICENCE = ("OECD Terms and Conditions, Data, Permitted Use (read 2026-10-13): any purpose including commercial, credit the OECD, "
           "same acknowledgment in sub-licences. Cite: OECD (2025), Material resources (economy-wide material flow accounts), "
           "https://sdmx.oecd.org/public/rest/dataflow/OECD.ENV.EPI/DSD_MATERIAL_RESOURCES@DF_MATERIAL_RESOURCES/1.0 (accessed on 2026-10-13)")
READS_AS = ("The country each place sits in, as the OECD's material flow accounts read it: of the materials the country consumes, "
            "in tonnes, the share it extracted inside its own borders. Above 1 the country extracts more than it keeps and exports "
            "the rest. Tonnes weigh sand and copper alike; the four groups in the place's JSON tell them apart. The material "
            "footprint beside it counts the raw materials embodied in what the country consumes wherever they were dug. A country "
            "figure, never a city's.")


def query(isos: list[str]) -> str:
    return (f"{SDMX}{'+'.join(sorted(isos))}.A.{'+'.join(MEASURES)}.T.{'+'.join(GROUPS)}?startPeriod={FROM}&format=csvfilewithlabels")


def read(csv_text: str) -> dict[str, dict]:
    """Per ISO3: tonnes by measure and group and year (unit multiplier applied, so plain tonnes), from the OECD CSV."""
    out = {}
    for r in csv.DictReader(io.StringIO(csv_text)):
        if r.get("UNIT_MEASURE") != "T" or r.get("OBS_VALUE") in (None, "") or r["MEASURE"] not in MEASURES or r["GROUP"] not in GROUPS:
            continue
        t = float(r["OBS_VALUE"]) * 10 ** int(r.get("UNIT_MULT") or 0)
        out.setdefault(r["REF_AREA"], {}).setdefault(r["GROUP"], {}).setdefault(r["MEASURE"], {})[int(r["TIME_PERIOD"])] = t
    return out


def bracket(countries: dict[str, dict], data: dict[str, dict]) -> dict:
    """Every tracker country: the latest year with both DEU and DMC for the total, the groups that year, and the series. Pure."""
    out, absent = {}, []
    for country, v in countries.items():
        iso = v["iso"]
        tot = (data.get(iso) or {}).get("TOT") if iso else None
        years = sorted(set(tot.get("DEU", {})) & set(tot.get("DMC", {}))) if tot else []
        if not years:
            absent.append(country)
            continue
        y = years[-1]
        mt = lambda m, g="TOT", yy=y: (data[iso].get(g, {}).get(m, {}).get(yy))   # noqa: E731
        ratio = lambda g, yy=y: (round(mt("DEU", g, yy) / mt("DMC", g, yy), 3) if mt("DEU", g, yy) is not None and mt("DMC", g, yy) else None)  # noqa: E731
        out[iso] = {"name": country, "places": v["places"], "year": y,
                    "made_at_home": ratio("TOT"),
                    "position": "net exporter" if (mt("EXP") or 0) > (mt("IMP") or 0) else "net importer",
                    **{k: round(mt(m) / 1e6, 1) if mt(m) is not None else None for m, k in MEASURES.items()},
                    "imports_share_of_consumption": round(mt("IMP") / mt("DMC"), 3) if mt("IMP") is not None and mt("DMC") else None,
                    "footprint_over_consumption": round(mt("MF") / mt("DMC"), 2) if mt("MF") is not None and mt("DMC") else None,
                    "groups": {name: {"made_at_home": ratio(g), "domestic_material_consumption_mt": round(mt("DMC", g) / 1e6, 1) if mt("DMC", g) is not None else None}
                               for g, name in GROUPS.items() if g != "TOT"},
                    "series": [{"year": yy, "made_at_home": ratio("TOT", yy)} for yy in years]}
    return {"reads_as": READS_AS, "licence": LICENCE, "year": max(c["year"] for c in out.values()) if out else None,
            "countries": out, "not_in_oecd": absent}


def run() -> int:
    tracker = waste._json(atlas.TRACKER)
    countries = atlas.countries_of(waste._raw(f"{atlas.DATAVERSE}access/datafile/{atlas.FILES['countries']}").decode("utf-8"), tracker)
    isos = [v["iso"] for v in countries.values() if v["iso"]]
    out = bracket(countries, read(waste._raw(query(isos)).decode("utf-8")))
    out["source"] = (f"OECD, Material resources: economy-wide material flow accounts, DSD_MATERIAL_RESOURCES@DF_MATERIAL_RESOURCES, measures "
                     f"{', '.join(MEASURES)} in tonnes, groups {', '.join(GROUPS)}, {FROM}-{out['year']}: {SDMX}")
    res = HERE / "results"
    res.mkdir(exist_ok=True)
    (res / "materials-country.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"{'country':8} {'places':>6} {'year':>4} {'made at home':>12} {'position':>12} {'DMC Mt':>8} {'imports/DMC':>11} {'footprint/DMC':>13}")
    for iso, c in out["countries"].items():
        print(f"{iso:8} {c['places']:>6} {c['year']:>4} {c['made_at_home']:>12.2f} {c['position']:>12} {c['domestic_material_consumption_mt']:>8.0f} "
              f"{c['imports_share_of_consumption']!s:>11} {c['footprint_over_consumption']!s:>13}")
    for country in out["not_in_oecd"]:
        print(f"{country}: not in the accounts (absent, not zero)")
    return 0


def selftest() -> int:
    bad = 0

    def check(label, got, want):
        nonlocal bad
        ok = got == want
        bad += not ok
        print(f"  {'ok ' if ok else 'BAD'} {label}" + ("" if ok else f": got {got!r}, want {want!r}"))

    head = "REF_AREA,FREQ,MEASURE,UNIT_MEASURE,GROUP,TIME_PERIOD,OBS_VALUE,UNIT_MULT\n"
    row = lambda iso, m, g, y, v, u="T", mult="6": f"{iso},A,{m},{u},{g},{y},{v},{mult}\n"   # noqa: E731
    text = head + "".join([row("ESP", "DEU", "TOT", 2024, 372), row("ESP", "DMC", "TOT", 2024, 447), row("ESP", "IMP", "TOT", 2024, 234), row("ESP", "EXP", "TOT", 2024, 159),
                           row("ESP", "MF", "TOT", 2024, 688), row("ESP", "DEU", "TOT", 2023, 360), row("ESP", "DMC", "TOT", 2023, 450),
                           row("ESP", "DEU", "MET", 2024, 1), row("ESP", "DMC", "MET", 2024, 10),
                           row("ESP", "DEU", "TOT", 2024, 7.9, "T_PS", "0"),               # per-person rows are not tonnes: ignored
                           row("BTN", "DEU", "TOT", 2024, 24.3), row("BTN", "DMC", "TOT", 2024, 22.0), row("BTN", "IMP", "TOT", 2024, 1.0), row("BTN", "EXP", "TOT", 2024, 3.3),
                           row("GHA", "DEU", "TOT", 2024, 322), row("GHA", "DMC", "TOT", 2025, "")])   # Ghana: no year with both
    data = read(text)
    countries = {"Spain": {"places": 1, "iso": "ESP", "m49": 724}, "Bhutan": {"places": 1, "iso": "BTN", "m49": 64},
                 "Ghana": {"places": 2, "iso": "GHA", "m49": 288}, "Kosovo": {"places": 1, "iso": None, "m49": None}}
    out = bracket(countries, data)
    es, bt = out["countries"]["ESP"], out["countries"]["BTN"]
    check("tonnes with the multiplier applied, per-person rows ignored", data["ESP"]["TOT"]["DEU"][2024], 372e6)
    check("made at home = extraction / consumption: 372 / 447", (es["year"], es["made_at_home"], es["position"]), (2024, 0.832, "net importer"))
    check("imports over consumption, footprint over consumption, Mt rounded", (es["imports_share_of_consumption"], es["footprint_over_consumption"], es["domestic_material_consumption_mt"]), (0.523, 1.54, 447.0))
    check("a group's own ratio; a group with no rows has none", (es["groups"]["metals"]["made_at_home"], es["groups"]["biomass"]["made_at_home"]), (0.1, None))
    check("a net exporter reads above 1", (bt["made_at_home"], bt["position"]), (1.105, "net exporter"))
    check("the series needs both extraction and consumption in a year", [s["year"] for s in es["series"]], [2023, 2024])
    check("a country with no year holding both is absent, never zero; so is one without an ISO3", out["not_in_oecd"], ["Ghana", "Kosovo"])
    check("the query keys countries, measures, tonnes and groups", query(["FRA", "ESP"]).split("/")[-1].split("?")[0], "ESP+FRA.A.DEU+IMP+EXP+DMC+MF.T.TOT+BIO+MET+IND+FUEL")
    print(f"\nmaterials selftest: {bad} failed.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else run())

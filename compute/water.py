#!/usr/bin/env python3
"""The country bracket, water: of the renewable water the country has, the share that originates inside its borders.

    python3 compute/water.py --selftest     # no network: the reading of a fake AQUASTAT answer
    python3 compute/water.py                # one FAO query, write compute/results/water-country.json

FAO AQUASTAT (registry environmental/bioregion/fao-aquastat; CC BY 4.0 under FAO's Statistical Database Terms of Use,
which name AQUASTAT, decided by Tomas Diez on 2026-10-14 over the catalogue's CC BY-NC-SA label). The dissemination system answers a BigQuery endpoint with a published SQL
and four parameters. Water is not traded like goods, so "made at home" here is where the water comes from: one
minus the DEPENDENCY RATIO, the share of a country's total renewable water resources that flows in from other
countries. Beside it, how much of what it has the country withdraws in a year. Resources are long-term averages
that AQUASTAT repeats each year; withdrawals move. A country figure beside each place (api.mjs,
`country_bracket.water`), never a cell, never a score input.
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
SQL = "https://data.apps.fao.org/catalog/dataset/945666e6-7803-4621-b8ef-cfd885a84596/resource/4a000a1b-24f0-4328-aab6-b9b525892090/download/query_en.sql"
API = "https://api.data.apps.fao.org/api/v2/bigquery"
VARIABLES = {"4192": "dependency_ratio", "4157": "internal_renewable_km3", "4182": "external_renewable_km3",
             "4188": "total_renewable_km3", "4263": "freshwater_withdrawal_km3"}
YEARS = [2022, 2021, 2020, 2019, 2018]
LICENCE = ("CC BY 4.0 under FAO's Statistical Database Terms of Use, whose Annex 1 names AQUASTAT, with the clause against use in "
           "the promotion of a commercial enterprise (decided by Tomas Diez, 2026-10-14; FAO's data catalogue labels the dissemination "
           "dataset CC BY-NC-SA 4.0, read as a catalogue default). Cite FAO, AQUASTAT, https://data.apps.fao.org/aquastat/")
READS_AS = ("The country each place sits in, as FAO's AQUASTAT reads its water: of the renewable water the country has in a year, "
            "the share that originates inside its own borders (one minus the dependency ratio, the share flowing in from other "
            "countries). Beside it, the share of what it has that it withdraws. Water is not bought abroad like goods; this says "
            "whose rain it lives on. Resources are long-term averages repeated each year. A country figure, never a city's.")


def query(years=YEARS) -> str:
    return f"{API}?sql_url={SQL}&area=World&type=country&variable={','.join(VARIABLES)}&year={','.join(map(str, years))}"


def read(csv_text: str) -> dict[int, dict]:
    """Per M49 code: per variable, the latest year's value and AQUASTAT's symbol (I imputed, E estimate, A actual)."""
    out = {}
    for r in csv.DictReader(io.StringIO(csv_text)):
        if r.get("VariableCode") not in VARIABLES or r.get("Value") in (None, "") or not r.get("m49", "").strip():
            continue
        m49, y = int(r["m49"]), int(r["Year"])
        slot = out.setdefault(m49, {"name": r["Country"]}).setdefault(VARIABLES[r["VariableCode"]], {})
        if "year" not in slot or y > slot["year"]:
            slot.update(year=y, value=float(r["Value"]), symbol=r.get("Symbol", ""))
    return out


def bracket(countries: dict[str, dict], data: dict[int, dict]) -> dict:
    out, absent = {}, []
    for country, v in countries.items():
        d = data.get(v["m49"]) if v["m49"] else None
        dep = (d or {}).get("dependency_ratio")
        if not dep:
            absent.append(country)
            continue
        val = lambda k: ((d.get(k) or {}).get("value"))   # noqa: E731
        tot, wd = val("total_renewable_km3"), val("freshwater_withdrawal_km3")
        out[v["iso"]] = {"name": country, "places": v["places"], "year": dep["year"],
                         "made_at_home": round(1 - dep["value"] / 100, 3),
                         "dependency_ratio": round(dep["value"] / 100, 3),
                         "internal_renewable_km3": val("internal_renewable_km3"), "external_renewable_km3": val("external_renewable_km3"),
                         "total_renewable_km3": tot, "freshwater_withdrawal_km3": wd,
                         "withdrawal_year": (d.get("freshwater_withdrawal_km3") or {}).get("year"),
                         "withdrawal_share_of_renewable": round(wd / tot, 3) if wd is not None and tot else None,
                         "symbols": {k: (d.get(k) or {}).get("symbol") for k in VARIABLES.values()}}
    return {"reads_as": READS_AS, "licence": LICENCE, "year": max(c["year"] for c in out.values()) if out else None,
            "symbols_mean": "AQUASTAT symbols: I imputed or carried forward, E estimate, A actual (official)",
            "countries": out, "not_in_aquastat": absent}


def run() -> int:
    tracker = waste._json(atlas.TRACKER)
    countries = atlas.countries_of(waste._raw(f"{atlas.DATAVERSE}access/datafile/{atlas.FILES['countries']}").decode("utf-8"), tracker)
    out = bracket(countries, read(waste._raw(query()).decode("utf-8")))
    out["source"] = (f"FAO AQUASTAT dissemination system, BigQuery endpoint with the published query (variables {', '.join(VARIABLES)}, "
                     f"years {YEARS[-1]}-{YEARS[0]}): {API}")
    res = HERE / "results"
    res.mkdir(exist_ok=True)
    (res / "water-country.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"{'country':8} {'places':>6} {'year':>4} {'from inside':>11} {'depends':>8} {'renewable km3':>13} {'withdraws':>9} {'of it':>6}")
    for iso, c in out["countries"].items():
        print(f"{iso:8} {c['places']:>6} {c['year']:>4} {c['made_at_home']:>11.2f} {c['dependency_ratio']:>8.2f} {c['total_renewable_km3']!s:>13} "
              f"{c['freshwater_withdrawal_km3']!s:>9} {c['withdrawal_share_of_renewable']!s:>6}")
    for country in out["not_in_aquastat"]:
        print(f"{country}: not in AQUASTAT (absent, not zero)")
    return 0


def selftest() -> int:
    bad = 0

    def check(label, got, want):
        nonlocal bad
        ok = got == want
        bad += not ok
        print(f"  {'ok ' if ok else 'BAD'} {label}" + ("" if ok else f": got {got!r}, want {want!r}"))

    head = "VariableGroup,Country,Subgroup,Variable,IsAggregate,Year,Value,Unit,Symbol,m49,VariableCode\n"
    row = lambda c, m, code, y, v, s="I": f"Water resources,{c},x,x,false,{y},{v},u,{s},{m},{code}\n"   # noqa: E731
    text = head + "".join([row("Spain", "724", "4192", 2021, 26.9), row("Spain", "724", "4192", 2022, 26.905829), row("Spain", "724", "4157", 2022, 111.2),
                           row("Spain", "724", "4182", 2022, 0.3), row("Spain", "724", "4188", 2022, 111.5), row("Spain", "724", "4263", 2021, 29.02, "A"),
                           row("Bhutan", "64", "4192", 2022, 0.0), row("Bhutan", "64", "4188", 2022, 78.0), row("Bhutan", "64", "4263", 2022, 0.3379),
                           row("Ghana", "288", "4188", 2022, 56.2),                       # Ghana: resources but no dependency ratio
                           row("World", "", "4192", 2022, 1.0)])                        # no m49: ignored
    data = read(text)
    countries = {"Spain": {"places": 1, "iso": "ESP", "m49": 724}, "Bhutan": {"places": 1, "iso": "BTN", "m49": 64},
                 "Ghana": {"places": 2, "iso": "GHA", "m49": 288}, "Kosovo": {"places": 1, "iso": None, "m49": None}}
    out = bracket(countries, data)
    es, bt = out["countries"]["ESP"], out["countries"]["BTN"]
    check("the latest year per variable, with its symbol", (data[724]["dependency_ratio"]["year"], data[724]["freshwater_withdrawal_km3"]["symbol"]), (2022, "A"))
    check("from inside = 1 - dependency: a fake Spain at 26.9% reads 73%", (es["year"], es["made_at_home"], es["dependency_ratio"]), (2022, 0.731, 0.269))
    check("withdrawal over total renewable, with the withdrawal's own year", (es["withdrawal_share_of_renewable"], es["withdrawal_year"]), (0.26, 2021))
    check("a dependency of 0 is a country living on its own rain, present not absent", (bt["made_at_home"], bt["withdrawal_share_of_renewable"]), (1.0, 0.004))
    check("no dependency ratio is absent, never zero; so is no ISO3", out["not_in_aquastat"], ["Ghana", "Kosovo"])
    check("the query carries the published SQL, the five variables and the years", query([2022, 2021]).split("?")[1],
          f"sql_url={SQL}&area=World&type=country&variable=4192,4157,4182,4188,4263&year=2022,2021")
    print(f"\nwater selftest: {bad} failed.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else run())

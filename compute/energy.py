#!/usr/bin/env python3
"""The country bracket, energy: of the energy the country uses, the share it produces itself.

    python3 compute/energy.py --selftest     # no network: the arithmetic on a fake World Bank answer
    python3 compute/energy.py                # two World Bank API calls, write compute/results/energy-country.json

The World Bank's World Development Indicators (registry economic/planet/worldbank-wdi; the series' own License_Type
reads CC BY-4.0, compiled by the Bank from IEA energy statistics) publish EG.IMP.CONS.ZS, net energy imports as a
share of energy use: gross imports less gross exports, over use, where use is production plus imports minus exports
plus stock changes. So the share of its energy use a country produces itself is one minus that, and a negative net
import share is a net exporter producing more than it uses. The Bank retired the production and use series in
tonnes of oil equivalent, so gross imports and exports are not published separately here: the energy half says
"made at home" and "net imports", never imports alone. EG.USE.PCAP.KG.OE, energy use per person, gives the scale.

A country figure beside each place (api.mjs, `country_bracket.energy`), never a cell, never a score input. A country
the series does not cover (Bhutan) is absent, never zero.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import atlas  # noqa: E402
import waste  # noqa: E402

HERE = Path(__file__).resolve().parent
WB = "https://api.worldbank.org/v2/country/all/indicator/{}?format=json&date={}:{}&per_page=20000"
NET_IMPORTS, USE_PER_PERSON = "EG.IMP.CONS.ZS", "EG.USE.PCAP.KG.OE"
FROM = 2015
LICENCE = ("World Bank World Development Indicators, CC BY-4.0 (the series' own License_Type, read 2026-10-13), compiled by the "
           "World Bank from IEA energy statistics; cite The World Bank: World Development Indicators, EG.IMP.CONS.ZS and EG.USE.PCAP.KG.OE")
READS_AS = ("The country each place sits in, as the World Bank reads its energy: of the energy the country uses, the share it "
            "produces itself, which is one minus its net energy imports as a share of use. Above 1 the country produces more "
            "than it uses and exports the rest. Net imports are imports less exports, so a country that imports oil and exports "
            "gas can read as self-supplied; gross imports are not published here. A country figure, never a city's.")


def latest(rows: list[dict], year_from: int = FROM) -> dict[str, dict]:
    """Per ISO3, the latest non-null value and the series, from the Bank's flat rows."""
    out = {}
    for r in rows:
        iso, v = r.get("countryiso3code"), r.get("value")
        if not iso or v is None or int(r["date"]) < year_from:
            continue
        s = out.setdefault(iso, {"series": {}})
        s["series"][int(r["date"])] = v
    for iso, s in out.items():
        y = max(s["series"])
        s["year"], s["value"] = y, s["series"][y]
    return out


def bracket(countries: dict[str, dict], net: dict[str, dict], use: dict[str, dict]) -> dict:
    """Every tracker country from the two series. Pure: no network."""
    out, absent = {}, []
    for country, v in countries.items():
        iso = v["iso"]
        n = net.get(iso) if iso else None
        if n is None:
            absent.append(country)
            continue
        share = n["value"] / 100
        u = use.get(iso)
        out[iso] = {"name": country, "places": v["places"], "year": n["year"],
                    "net_imports_share_of_use": round(share, 3),
                    "made_at_home": round(1 - share, 3),
                    "position": "net exporter" if share < 0 else "net importer" if share > 0 else "balanced",
                    "energy_use_kg_oe_per_person": round(u["value"]) if u else None, "energy_use_year": u["year"] if u else None,
                    "series": [{"year": y, "net_imports_share_of_use": round(x / 100, 3), "made_at_home": round(1 - x / 100, 3)}
                               for y, x in sorted(n["series"].items())]}
    return {"reads_as": READS_AS, "licence": LICENCE, "year": max(c["year"] for c in out.values()) if out else None,
            "countries": out, "not_in_wdi": absent}


def run() -> int:
    tracker = waste._json(atlas.TRACKER)
    countries = atlas.countries_of(waste._raw(f"{atlas.DATAVERSE}access/datafile/{atlas.FILES['countries']}").decode("utf-8"), tracker)
    year_to = 2100                                             # the API ignores a future bound and returns what it has
    net_raw, use_raw = (waste._json(WB.format(ind, FROM, year_to)) for ind in (NET_IMPORTS, USE_PER_PERSON))
    for raw, ind in ((net_raw, NET_IMPORTS), (use_raw, USE_PER_PERSON)):
        if not isinstance(raw, list) or len(raw) < 2 or not isinstance(raw[1], list):
            raise SystemExit(f"{ind}: the World Bank answered {str(raw)[:200]}")
    out = bracket(countries, latest(net_raw[1]), latest(use_raw[1]))
    out["source"] = (f"World Bank WDI API v2, {NET_IMPORTS} (net energy imports, % of energy use) and {USE_PER_PERSON} (energy use, kg of oil "
                     f"equivalent per person), {FROM}-{out['year']}, database last updated {net_raw[0].get('lastupdated')}")
    res = HERE / "results"
    res.mkdir(exist_ok=True)
    (res / "energy-country.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"{'country':8} {'places':>6} {'year':>4} {'made at home':>12} {'net imports':>11} {'position':>12} {'kg oe/person':>12}")
    for iso, c in out["countries"].items():
        print(f"{iso:8} {c['places']:>6} {c['year']:>4} {c['made_at_home']:>12.2f} {c['net_imports_share_of_use']:>11.2f} {c['position']:>12} {c['energy_use_kg_oe_per_person']!s:>12}")
    for country in out["not_in_wdi"]:
        print(f"{country}: not in the series (absent, not zero)")
    return 0


def selftest() -> int:
    bad = 0

    def check(label, got, want):
        nonlocal bad
        ok = got == want
        bad += not ok
        print(f"  {'ok ' if ok else 'BAD'} {label}" + ("" if ok else f": got {got!r}, want {want!r}"))

    row = lambda iso, y, v: {"countryiso3code": iso, "date": str(y), "value": v}   # noqa: E731
    net = latest([row("ESP", 2023, 76.8), row("ESP", 2024, 78.4), row("ESP", 2010, 70.0), row("IDN", 2024, -92.8), row("IDN", 2025, None),
                  row("", 2024, 5.0), row("GHA", 2024, -5.1)])
    use = latest([row("ESP", 2024, 2400.4), row("IDN", 2023, 900.0)])
    check("latest non-null year per country; rows before FROM, null and codeless rows ignored", (net["ESP"]["year"], net["ESP"]["value"], sorted(net["ESP"]["series"])), (2024, 78.4, [2023, 2024]))
    countries = {"Spain": {"places": 1, "iso": "ESP", "m49": 724}, "Indonesia": {"places": 5, "iso": "IDN", "m49": 360},
                 "Bhutan": {"places": 1, "iso": "BTN", "m49": 64}, "Kosovo": {"places": 1, "iso": None, "m49": None}}
    out = bracket(countries, net, use)
    es, idn = out["countries"]["ESP"], out["countries"]["IDN"]
    check("made at home = 1 - net imports share: Spain 22%", (es["made_at_home"], es["net_imports_share_of_use"], es["position"]), (0.216, 0.784, "net importer"))
    check("a net exporter reads above 1", (idn["made_at_home"], idn["position"]), (1.928, "net exporter"))
    check("energy use per person carried with its own year; None when the series lacks the country", (es["energy_use_kg_oe_per_person"], es["energy_use_year"], idn["energy_use_year"]), (2400, 2024, 2023))
    check("the series is per year, oldest first", [s["year"] for s in es["series"]], [2023, 2024])
    check("a country the series lacks is absent, never zero; so is one without an ISO3", out["not_in_wdi"], ["Bhutan", "Kosovo"])
    check("the bracket's year is the latest across countries", out["year"], 2024)
    print(f"\nenergy selftest: {bad} failed.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else run())

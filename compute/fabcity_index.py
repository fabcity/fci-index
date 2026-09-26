#!/usr/bin/env python3
"""An open Fab City Index, on Boeing's 2024 recipe: how much of what a place consumes it could make.

    python3 compute/fabcity_index.py --selftest        # no network: the arithmetic reproduces Hamburg's 37
    python3 compute/fabcity_index.py                   # fetch Eurostat, write compute/results/

Boeing (2024, Springer ch. 9, CC-BY) scored Hamburg 37 out of 100 for 2019. Across 16 macro-sectors he set
local production value against local consumption spending (capped at 100%), weighted each sector in per mille
by the consumer price index basket (or by his estimate where no consumption data exists), and summed. His
inputs were mostly Statistikamt Nord series, which are not an open API. This script does three things:

  1. reference     Boeing's own sector values (boeing2024.json) through the same arithmetic. Must give 37.
  2. open-hamburg  the sectors that CAN be re-derived from open Eurostat data, recomputed for Hamburg 2019
                   and substituted into his table; every other sector carries his value, flagged.
  3. goods         the same open sectors only, for Hamburg, Cataluna and Ile-de-France, weighted by each
                   country's own HICP basket, so the three are comparable. This is a partial index, and it
                   measures CAPACITY: a region that makes for export caps at 100%. See README "What it shows".

The open model, per sector s and region r (country c):
  production(s,r)  = sum over NACE n in s of  production value(n,c) x employed(n,r) / employed(n,c)
  consumption(s,r) = sum over COICOP k in s of household spending(k,c) x population(r) / population(c) / (1+VAT)
  ratio(s,r)       = min(1, production / consumption)
Both are modelled from national totals: regional production by employment share, regional consumption by
population share. Neither is a regional measurement, and the results say "modelled" for that reason.

Data: Eurostat (reuse authorised with acknowledgement, Commission Decision 2011/833/EU).
  sbs_r_nuts06_r2  V16110  persons employed by NACE, region      sbs_na_ind_r2  V12120/V16110  national
  nama_10_co3_p3   CP_MEUR household spending by COICOP, national demo_r_d2jan  population
  prc_hicp_inw     HICP item weights, per mille
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import waste  # noqa: E402

HERE = Path(__file__).resolve().parent
REF = json.loads((HERE / "boeing2024.json").read_text(encoding="utf-8"))
EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
YEAR = 2019                    # Boeing's year: the last before the pandemic moved every series
REGIONS = {"DE60": "Hamburg", "ES51": "Cataluna (Barcelona)", "FR10": "Ile-de-France (Paris)"}

# The sectors open data can re-derive, and how. Boeing's table names NACE divisions and a COICOP "weighting
# from" note; the COICOP lists below are the consumer goods those divisions make, chosen so that production
# and consumption describe the same goods. Where that differs from Boeing's table, `differs` says how.
OPEN = {
    "Food and beverages":    {"nace": ["C10", "C11"], "coicop": ["CP01", "CP021"], "reduced": ["CP01"],
                              "differs": "none"},
    "Textiles and clothing": {"nace": ["C13", "C14", "C15"], "coicop": ["CP03", "CP052"], "reduced": [],
                              "differs": "none"},
    "Chemical products":     {"nace": ["C21"], "coicop": ["CP061"], "reduced": [],
                              "differs": "pharmaceuticals only (C21 vs medical products). Boeing's C19-C22 vs all of "
                                         "COICOP 06 sets refinery output, which he calls a port artefact, against "
                                         "hospital services."},
    "IT and communication":  {"nace": ["C26"], "coicop": ["CP082", "CP091"], "reduced": [],
                              "differs": "equipment only (phones, audio-visual and IT). All of COICOP 08 is mostly "
                                         "telecom services, which C26 does not make."},
    "Other goods":           {"nace": ["C23", "C32"],
                              "coicop": ["CP051", "CP054", "CP055", "CP056", "CP092", "CP093", "CP095"], "reduced": [],
                              "differs": "none: the groups Boeing lists in his text (p. 122)"},
}
# Not re-derived, and why, so the gap is on the record rather than silent.
NOT_OPEN = {
    "Metals": "Boeing sets it against investment, not household spending; no open regional investment by asset.",
    "Machinery and equipment": "as Metals.",
    "Vehicles and transport equipment": "C29 is suppressed for Hamburg (confidentiality); C30 is Airbus, which "
                                        "makes no consumer vehicles, so it cannot stand in.",
    "Repair": "needs COICOP 07.2.3 and production value for G45/S95, neither published at that detail.",
    "Waste and recycling": "Hamburg's only open machine-readable figure is the Urban Audit total, with no recovery "
                           "split. Barcelona, Paris and Santiago do have one: see trash_out.",
}
# Trash out, per city: Boeing's year and the latest each source has (Santiago's latest CSV year is 2022).
WASTE_YEARS = {"Barcelona": [YEAR, 2024], "Paris": [YEAR, 2024], "Santiago": [YEAR, 2022], "Hamburg": [YEAR, 2024]}
VAT = {"DE": (0.07, 0.19), "ES": (0.10, 0.21), "FR": (0.055, 0.20)}   # (reduced, standard) in 2019


def fetch(dataset: str, **params) -> dict:
    q = "&".join(f"{k}={v}" for k, vs in params.items() for v in (vs if isinstance(vs, list) else [vs]))
    url = f"{EUROSTAT}{dataset}?format=JSON&lang=EN&{q}"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "fci-compute"}), timeout=120) as r:
        return json.loads(r.read())


def by(d: dict, dim: str) -> dict[str, float]:
    """One dimension's values, the others having been fixed to a single member by the query."""
    return {code: d["value"][str(i)] for code, i in d["dimension"][dim]["category"]["index"].items()
            if str(i) in d["value"]}


def weight_of(hicp: dict[str, float], code: str) -> float | None:
    return hicp.get(code, hicp.get(code + "0"))      # HICP codes a one-member class as CP0820 for CP082


def index(rows: list[dict]) -> float:
    """Boeing's number: sum of capped ratio x weight, over the weights present, on 0-100."""
    w = sum(r["weight"] for r in rows)
    return 100 * sum(min(1.0, r["ratio"]) * r["weight"] for r in rows) / w


def reference_rows() -> list[dict]:
    return [{"sector": s["sector"], "ratio": s["ratio"], "weight": s["weight_cpi"] or s["weight_estimate"]}
            for s in REF["sectors"]]


def open_sectors(region: str, get=fetch) -> dict:
    """The OPEN sectors for one region, with every input kept so a reader can redo the sum."""
    c = region[:2]
    emp_r = by(get("sbs_r_nuts06_r2", geo=region, time=YEAR, indic_sb="V16110"), "nace_r2")
    emp_c = by(get("sbs_na_ind_r2", geo=c, time=YEAR, indic_sb="V16110"), "nace_r2")
    pv_c = by(get("sbs_na_ind_r2", geo=c, time=YEAR, indic_sb="V12120"), "nace_r2")
    hfce = by(get("nama_10_co3_p3", geo=c, time=YEAR, unit="CP_MEUR"), "coicop")
    pop = by(get("demo_r_d2jan", geo=[region, c], time=YEAR, sex="T", age="TOTAL", unit="NR"), "geo")
    share = pop[region] / pop[c]
    reduced, standard = VAT[c]
    out = {}
    for s, spec in OPEN.items():
        used = [n for n in spec["nace"] if emp_r.get(n) is not None and emp_c.get(n) and pv_c.get(n) is not None]
        prod = sum(pv_c[n] * emp_r[n] / emp_c[n] for n in used)
        cons = sum(hfce[k] * share / (1 + (reduced if k in spec["reduced"] else standard))
                   for k in spec["coicop"] if k in hfce)
        out[s] = {
            # No division reporting is no data, never a zero: a suppressed sector must drop out of the
            # index, not pull it down (Ile-de-France's pharma, 2019, is the case that caught this).
            "ratio": min(1.0, prod / cons) if used and cons else None,
            "raw_ratio": round(prod / cons, 2) if used and cons else None,
            "production_meur": round(prod, 1), "consumption_meur": round(cons, 1),
            "nace_used": used, "nace_missing": [n for n in spec["nace"] if n not in used],
            "coicop_missing": [k for k in spec["coicop"] if k not in hfce],
            "state": "no data" if not used else "modelled" + (", partial" if len(used) < len(spec["nace"]) else ""),
            "differs_from_boeing": spec["differs"],
        }
    return out


def run() -> None:
    res = HERE / "results"
    res.mkdir(exist_ok=True)
    ref = reference_rows()
    ref_idx = index(ref)

    # 2. open-hamburg: substitute what open data re-derives, carry the rest, flag both.
    ham = open_sectors("DE60")
    rows = []
    for r in ref:
        o = ham.get(r["sector"])
        if o and o["ratio"] is not None:
            rows.append({**r, "ratio": o["ratio"], "boeing_ratio": r["ratio"], "source": "open, " + o["state"]})
        else:
            rows.append({**r, "boeing_ratio": r["ratio"],
                         "source": "Boeing 2024, carried" + (f": {NOT_OPEN[r['sector']]}" if r["sector"] in NOT_OPEN else "")})
    open_weight = sum(r["weight"] for r in rows if r["source"].startswith("open"))

    # 3. goods: the open sectors only, each country's HICP basket, three regions.
    goods = {}
    for region, name in REGIONS.items():
        secs = ham if region == "DE60" else open_sectors(region)
        hicp = by(fetch("prc_hicp_inw", geo=region[:2], time=YEAR), "coicop")
        grows, missing_w = [], []
        for s, o in secs.items():
            ws = [weight_of(hicp, k) for k in OPEN[s]["coicop"]]
            missing_w += [k for k, w in zip(OPEN[s]["coicop"], ws) if w is None]
            if o["ratio"] is not None:
                grows.append({"sector": s, "ratio": o["ratio"], "weight": sum(w for w in ws if w)})
        goods[region] = {"name": name, "goods_index": round(index(grows), 1) if grows else None,
                         "weight_covered_per_mille": round(sum(r["weight"] for r in grows), 2),
                         "hicp_codes_without_weight": missing_w, "sectors": secs}

    out = {
        "method": "Boeing 2024 recipe; see compute/README.md. Eurostat, reuse with acknowledgement (2011/833/EU).",
        "year": YEAR,
        "reference": {"index": round(ref_idx, 2), "published": REF["published_index"], "rows": ref},
        "open_hamburg": {"index": round(index(rows), 1), "open_weight_per_mille": round(open_weight, 2),
                         "rows": rows},
        "goods_capacity": {
            "reads_as": "Production CAPACITY against local demand, capped at 100% per sector. It is not self-supply: "
                        "a region that makes goods for the rest of its country and for export caps at 100% although "
                        "its residents may buy almost none of it. Utopies put Paris's self-sufficiency at 8.7% (2018). "
                        "Telling capacity from self-supply needs trade data: awesome-fabcity-data#42.",
            "regions": goods},
    }
    out["trash_out"] = {
        "reads_as": "Residual municipal waste per capita is the proposed PITO 'trash out' measure "
                    "(awesome-fabcity-data#42). recovery_share is also Boeing's input for macro-sector 16. The four "
                    "sources count different things; each row says what, and they are not comparable until aligned.",
        "rows": waste.trash_out(WASTE_YEARS)}
    (res / f"fabcity-index-{YEAR}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"reference (Boeing's inputs)        {ref_idx:5.1f}   published {REF['published_index']}")
    print(f"Hamburg, open sectors substituted  {index(rows):5.1f}   ({open_weight:.0f} of 1000 per mille re-derived)")
    for w in out["trash_out"]["rows"]:
        print(f"trash out {w['city']:18} {w['year']}  " + (w.get("error") or
              f"generated {w['generated_kg_per_capita']} kg/cap  residual {w['residual_kg_per_capita']} kg/cap  "
              f"recovery {w['recovery_share']}"))
    for region, g in goods.items():
        print(f"goods capacity  {g['name']:28} {g['goods_index']!s:>5}   (HICP weight covered {g['weight_covered_per_mille']}; capacity, not self-supply)")


def selftest() -> int:
    bad = 0

    def check(label, got, want):
        nonlocal bad
        ok = got == want
        bad += not ok
        print(f"[{' ok ' if ok else 'FAIL'}] {label}: {got!r}" + ("" if ok else f", wanted {want!r}"))

    s = REF["sectors"]
    check("Table 9.3 CPI column sums as printed", round(sum(x["weight_cpi"] or 0 for x in s), 2), 664.05)
    check("Table 9.3 estimate column sums as printed", round(sum(x["weight_estimate"] or 0 for x in s), 2), 335.95)
    check("every sector has exactly one weight", all((x["weight_cpi"] is None) != (x["weight_estimate"] is None) for x in s), True)
    check("Boeing's inputs reproduce his 37", round(index(reference_rows())), 37)
    check("a ratio over 1 is capped", index([{"ratio": 2.0, "weight": 1}]), 100.0)

    # open_sectors on made-up numbers, so the arithmetic is checked without the network.
    def fake(dataset, **p):
        vals = {"sbs_r_nuts06_r2": {"C10": 10, "C11": 0, "C21": 5},           # region employs 10% of C10
                "sbs_na_ind_r2": {"V16110": {"C10": 100, "C11": 10, "C21": 50},
                                  "V12120": {"C10": 1000, "C11": 100, "C21": 500}},
                "nama_10_co3_p3": {"CP01": 1070, "CP021": 0, "CP061": 119},
                "demo_r_d2jan": {"XX01": 10, "XX": 100}}[dataset]
        if dataset == "sbs_na_ind_r2":
            vals = vals[p["indic_sb"]]
        dim = {"sbs_r_nuts06_r2": "nace_r2", "sbs_na_ind_r2": "nace_r2", "nama_10_co3_p3": "coicop", "demo_r_d2jan": "geo"}[dataset]
        codes = list(vals)
        return {"dimension": {dim: {"category": {"index": {k: i for i, k in enumerate(codes)}}}},
                "value": {str(i): vals[k] for i, k in enumerate(codes)}}

    VAT["XX"] = (0.07, 0.19)
    o = open_sectors("XX01", get=fake)
    f = o["Food and beverages"]
    check("production = national PV x regional employment share", f["production_meur"], 100.0)
    check("consumption = national spending x population share, net of VAT", f["consumption_meur"], 100.0)
    check("food ratio", f["ratio"], 1.0)
    check("a division the region does not report is listed, not zeroed", o["Textiles and clothing"]["nace_missing"], ["C13", "C14", "C15"])
    check("pharma 5/50 x 500 = 50 against 119 x 0.1 / 1.19 = 10, capped", o["Chemical products"]["ratio"], 1.0)
    check("the uncapped ratio is kept, so capacity for export stays visible", o["Chemical products"]["raw_ratio"], 5.0)
    check("a sector with no reporting division has no ratio, not zero", o["Textiles and clothing"]["ratio"], None)
    check("and says so", o["Textiles and clothing"]["state"], "no data")
    del VAT["XX"]

    # waste.barcelona: residual per capita from the residual fraction, recovery from separate collection.
    b = waste.barcelona(2024, get=lambda u: [{"poblaci": "1000", "suma_fracci_resta": "300",
                                              "total_recollida_selectiva": "100"}])
    check("waste: residual kg per capita = residual t x 1000 / population", b["residual_kg_per_capita"], 300.0)
    check("waste: generated = residual + separate collection", b["generated_kg_per_capita"], 400.0)
    check("waste: recovery share = separate / generated", b["recovery_share"], 0.25)
    # waste.santiago: decimal commas, thousands dots, one comuna only, recovery by declared treatment.
    csv_text = ("id_comuna;cantidad_toneladas;tratamiento_nivel_1\n13101;1.000,5;Eliminación\n"
                "13101;99,5;Valorización\n13102;5000;Eliminación\n").encode()
    sg = waste.santiago(2022, get=lambda u: {"result": {"resources": [{"name": "2022: x", "format": "CSV", "url": "u"}]}},
                        raw=lambda u: csv_text)
    check("waste: RETC '1.000,5' reads as 1000.5, and other comunas are left out", sg["generated_t"], 1100)
    check("waste: RETC recovery share by declared treatment", sg["recovery_share"], round(99.5 / 1100, 3))
    check("waste: no population means no per-capita figure, not a guess", sg["generated_kg_per_capita"], None)
    blank = waste.santiago(2019, get=lambda u: {"result": {"resources": [{"name": "2019: x", "format": "CSV", "url": "u"}]}},
                           raw=lambda u: b"id_comuna;cantidad_toneladas;tratamiento_nivel_1\n13101;10;\n")
    check("waste: a year with no treatment recorded has no recovery share, not 0%", blank["recovery_share"], None)
    print(f"\nfabcity_index selftest: {bad} failed.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else run())

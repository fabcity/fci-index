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
import trade  # noqa: E402

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
    "Waste and recycling": "Boeing's 24.8% is a recycling share. The open Hamburg data (Statistikamt Nord Q II 9, see "
                           "trash_out) gives separate collection, 40.0% in 2019, which is not recycling; substituting "
                           "it would mix two measures.",
}
# Trash out, per city: Boeing's year and the latest each source has (Santiago's latest CSV year is 2022).
WASTE_YEARS = {"Barcelona": [YEAR, 2024], "Catalonia": [YEAR, 2024], "Paris": [YEAR, 2024], "Santiago": [YEAR, 2022], "Region Metropolitana": [YEAR, 2022], "Hamburg": [YEAR, 2024],
               "Germany": [YEAR, 2024], "Spain": [YEAR, 2024], "France": [YEAR, 2024]}
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


def consumption(region: str, year: int = YEAR, get=fetch) -> dict[str, dict]:
    """Households' spending on each OPEN sector's goods in the region, M EUR net of VAT: the country's spending by
    COICOP, scaled by the region's share of the population. Germany's COICOP detail on Eurostat ends in 2022."""
    c = region[:2]
    hfce = by(get("nama_10_co3_p3", geo=c, time=year, unit="CP_MEUR"), "coicop")
    pop = by(get("demo_r_d2jan", geo=[region, c], time=year, sex="T", age="TOTAL", unit="NR"), "geo")
    share = pop[region] / pop[c]
    reduced, standard = VAT[c]
    return {s: {"consumption_meur": sum(hfce[k] * share / (1 + (reduced if k in spec["reduced"] else standard))
                                        for k in spec["coicop"] if k in hfce),
                "coicop_missing": [k for k in spec["coicop"] if k not in hfce]}
            for s, spec in OPEN.items()}


def open_sectors(region: str, get=fetch) -> dict:
    """The OPEN sectors for one region, with every input kept so a reader can redo the sum."""
    c = region[:2]
    emp_r = by(get("sbs_r_nuts06_r2", geo=region, time=YEAR, indic_sb="V16110"), "nace_r2")
    emp_c = by(get("sbs_na_ind_r2", geo=c, time=YEAR, indic_sb="V16110"), "nace_r2")
    pv_c = by(get("sbs_na_ind_r2", geo=c, time=YEAR, indic_sb="V12120"), "nace_r2")
    spend = consumption(region, YEAR, get)
    out = {}
    for s, spec in OPEN.items():
        used = [n for n in spec["nace"] if emp_r.get(n) is not None and emp_c.get(n) and pv_c.get(n) is not None]
        prod = sum(pv_c[n] * emp_r[n] / emp_c[n] for n in used)
        cons = spend[s]["consumption_meur"]
        out[s] = {
            # No division reporting is no data, never a zero: a suppressed sector must drop out of the
            # index, not pull it down (Ile-de-France's pharma, 2019, is the case that caught this).
            "ratio": min(1.0, prod / cons) if used and cons else None,
            "raw_ratio": round(prod / cons, 2) if used and cons else None,
            "production_meur": round(prod, 1), "consumption_meur": round(cons, 1),
            "nace_used": used, "nace_missing": [n for n in spec["nace"] if n not in used],
            "coicop_missing": spend[s]["coicop_missing"],
            "state": "no data" if not used else "modelled" + (", partial" if len(used) < len(spec["nace"]) else ""),
            "differs_from_boeing": spec["differs"],
        }
    return out


TRADE_YEAR = 2022   # the latest year with both Hamburg's measured turnover (E I 1) and Germany's COICOP spending


# Idescat publishes activity groups, not NACE divisions. Where a group is wider than Boeing's sector it says so.
CAT_GROUPS = {
    "Food and beverages": ["Industries of food products", "Production of beverages and of tobacco products"],
    "Textiles and clothing": ["Manufacture of textiles, leather, footwear. Tailoring"],
    "Chemical products": ["Manufacture of pharmaceutical products"],
    "IT and communication": ["Manufacture of computer, electronic and optical material and equipment"],
    "Other goods": ["Other non-metal mineral products industries", "Furniture making and other manufacturing industries"],
}
CAT_DIFFERS = {"Food and beverages": "the beverages group includes tobacco (C12)",
               "Other goods": "the group joins furniture (C31) with other manufacturing (C32)"}


def trade_adjust(spend: dict, divisions: dict, codes: dict | None = None) -> dict:
    """Each OPEN sector twice: measured turnover against local consumption (capacity), and the same with sales abroad
    taken out (trade-adjusted). A division counts only where both its turnover and its foreign turnover are published,
    so the two ratios cover the same plants. `codes` maps each sector to the source's own keys (default: its NACE
    divisions). Thousand euro in, M EUR out."""
    out = {}
    for s, spec in OPEN.items():
        cons = spend[s]["consumption_meur"]
        got = {n: divisions.get(n) for n in (codes or {}).get(s, spec["nace"])}
        used = [n for n, v in got.items() if v and v[0] is not None and v[1] is not None]
        made = sum(got[n][0] for n in used) / 1000
        home = sum(got[n][0] - got[n][1] for n in used) / 1000
        ok = bool(used) and cons > 0
        out[s] = {"measured_meur": round(made, 1), "sold_abroad_meur": round(made - home, 1), "domestic_meur": round(home, 1),
                  "consumption_meur": round(cons, 1),
                  "capacity": min(1.0, made / cons) if ok else None, "trade_adjusted": min(1.0, home / cons) if ok else None,
                  "raw_capacity": round(made / cons, 2) if ok else None, "raw_trade_adjusted": round(home / cons, 2) if ok else None,
                  "nace_used": used, "nace_missing": [n for n in got if n not in used],
                  "state": "no data" if not used else "measured" + (", partial" if len(used) < len(got) else "")}
    return out


def with_open(ref: list[dict], sectors: dict, key: str, label: str) -> list[dict]:
    """Boeing's rows with the OPEN sectors' ratio replaced where there is one; the rest carried, as in open_hamburg."""
    return [{**r, "ratio": sectors[r["sector"]][key], "boeing_ratio": r["ratio"], "source": f"{label}, {sectors[r['sector']]['state']}"}
            if r["sector"] in sectors and sectors[r["sector"]][key] is not None
            else {**r, "boeing_ratio": r["ratio"], "source": "Boeing 2024, carried"} for r in ref]


def trade_variant(region: str, year: int, reading: dict, codes: dict | None, label: str, carry: bool, get=fetch) -> dict:
    """One region's open sectors measured, twice: capacity, and sales abroad taken out. Always as a goods index over
    those sectors alone, weighted by the country's HICP basket (comparable across regions, like goods_capacity).
    With carry, also as Boeing's full index, the other eleven sectors carrying his ratios; they are Hamburg's, so only
    Hamburg carries them."""
    secs = trade_adjust(consumption(region, year, get), reading["divisions"], codes)
    hicp = by(get("prc_hicp_inw", geo=region[:2], time=year), "coicop")
    w = {s: sum(x for x in (weight_of(hicp, k) for k in OPEN[s]["coicop"]) if x) for s in OPEN}
    def goods(key):
        rows = [{"ratio": o[key], "weight": w[s]} for s, o in secs.items() if o[key] is not None]
        return round(index(rows), 1) if rows else None
    out = {"year": year, "goods_capacity_index": goods("capacity"), "goods_trade_adjusted_index": goods("trade_adjusted"),
           "goods_weight_per_mille": round(sum(w[s] for s, o in secs.items() if o["capacity"] is not None), 2),
           "concept": reading["concept"], "sectors": secs}
    if carry:
        ref = reference_rows()
        adj = with_open(ref, secs, "trade_adjusted", label)
        out.update(capacity_index=round(index(with_open(ref, secs, "capacity", label)), 1),
                   trade_adjusted_index=round(index(adj), 1), rows=adj)
    return out


def hamburg_trade_adjusted(year: int = TRADE_YEAR, get=fetch, raw=waste._raw) -> dict:
    ei = trade.nord_manufacturing(year, raw)
    if ei is None:
        return {"year": year, "no_data": f"no E I 1 annual edition for {year} on statistik-nord.de"}
    out = trade_variant("DE60", year, {**ei, "divisions": {"C" + k: v for k, v in ei["divisions"].items()}}, None,
                        f"E I 1 {year}", True, get)
    return {
        "reads_as": f"Hamburg's index with the five open sectors measured, {year}: capacity counts everything Hamburg's plants "
                    "make against what its households buy; trade-adjusted takes out what they sell abroad. The difference is "
                    "the trade effect. Still an UPPER bound on self-supply: sales to the rest of Germany count as local, and "
                    "only plants with 20 or more people are covered. The other eleven sectors carry Boeing's 2019 ratios.",
        **out, "source": f"Statistikamt Nord E I 1 {year}, table T2_1: {ei['url']}; Eurostat "
                         f"nama_10_co3_p3 and demo_r_d2jan {year}",
        "licence": trade.NORD_E_I_1_LICENCE}


def barcelona_trade_adjusted(year: int = YEAR, get=fetch, raw=waste._raw) -> dict:
    eie = trade.idescat_industry(year, raw)
    if eie is None:
        return {"year": year, "no_data": f"Idescat's industrial survey has no {year} table"}
    out = trade_variant("ES51", year, eie, CAT_GROUPS, f"Idescat EIE {year}", False, get)
    for s, why in CAT_DIFFERS.items():
        out["sectors"][s]["differs_from_boeing"] = why
    return {
        "reads_as": f"Catalonia's index (Barcelona's region, ES51) with the five open sectors measured, {year}: capacity counts "
                    "everything Catalan industry sells against what Catalan households buy; trade-adjusted takes out what it "
                    "sells abroad, as a goods index over those sectors (Spain's HICP weights). A loose UPPER bound on "
                    "self-supply: sales to the rest of Spain count as local, and most of what is not exported goes there. "
                    "No full index: Boeing's other eleven ratios are Hamburg's.",
        **out, "source": f"Idescat, based on INE's Structural Business Statistics in the Industrial Sector, {year}: "
                         f"{eie['url']}; Eurostat nama_10_co3_p3 and demo_r_d2jan {year}",
        "licence": trade.IDESCAT_LICENCE}


BR_DIFFERS = {"IT and communication": "consumption is phones and accessories only: POF puts TVs and computers inside "
                                      "appliances, with fridges, so capacity is overstated",
              "Food and beverages": "consumption is food at home (alcohol included), not meals out"}


def brazil_trade_adjusted(year: int = YEAR, get=waste._json, post=None) -> list[dict]:
    """São Paulo state and Pernambuco (for Recife): IBGE's measured production against POF household spending, and
    with exports (ComexStat, by state of production, converted at the year's average rate) taken out. A goods index
    over the five sectors, weighted by each state's own spending on them."""
    prod, usd = trade.brazil_production(year, get), trade.brazil_exports_usd(year, post)
    rate, spend = trade.brl_per_usd(year, get), trade.pof_spending(get)
    out = []
    for state, city in (("São Paulo", "São Paulo"), ("Pernambuco", "Recife")):
        divisions = {c: (v, usd[state][c] * rate / 1000) for c, v in prod[state].items() if v is not None}
        secs = trade_adjust({s: {"consumption_meur": v} for s, v in spend[state].items()}, divisions)
        for s, why in BR_DIFFERS.items():
            secs[s]["differs_from_boeing"] = why
        def goods(key):
            rows = [{"ratio": o[key], "weight": spend[state][s]} for s, o in secs.items() if o[key] is not None]
            return round(index(rows), 1) if rows else None
        out.append({"city": city, "territory": f"{state} (state)", "year": year, "currency": "BRL (M R$ in the sector rows)",
                    "goods_capacity_index": goods("capacity"), "goods_trade_adjusted_index": goods("trade_adjusted"),
                    "brl_per_usd": rate, "sectors": secs,
                    "source": f"IBGE PIA-Empresa {year} (SIDRA 1849, gross value of production); ComexStat exports {year} "
                              "by state of production; IBGE POF 2017-2018 (SIDRA 6715, 6972, 6977); BCB SGS 3694",
                    "licence": trade.BR_LICENCE})
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
    out["gateway"] = {
        "reads_as": "Economic|Bioregion's gateway row: goods in and out through the territory's ports and airports, "
                    "in tonnes, reported separately, sea and air as separate rows. Throughput, not consumption. Boston and "
                    "Santiago are listed with why they have no data.",
        "rows": trade.gateway([YEAR, 2024])}
    out["hamburg_trade_adjusted"] = hamburg_trade_adjusted()
    out["barcelona_trade_adjusted"] = [barcelona_trade_adjusted(y) for y in (YEAR, TRADE_YEAR)]
    out["brazil_trade_adjusted"] = {
        "reads_as": "São Paulo and Recife, read as their states (no city figures exist): measured production against what "
                    "households buy, and with exports taken out, as a goods index weighted by the state's own spending. An "
                    "UPPER bound on self-supply: sales to the rest of Brazil count as local. Exports are products by state of "
                    "production, a proxy for the same firms' sales abroad. Production is 2019, spending is the 2017-2018 "
                    "survey in its own reais (prices rose about 4% to 2019).",
        "rows": brazil_trade_adjusted()}
    out["regional_trade"] = {
        "reads_as": "Economic|Region's external-trade row: goods exported and imported by the territory, in euros (and "
                    "tonnes where the source has them), each reported separately and never netted. Customs trade of the territory, not its "
                    "gateways' throughput, and not trade with the rest of the country. Cities without an open reader "
                    "yet are listed with why.",
        "rows": trade.regional_trade([YEAR, 2024])}
    (res / f"fabcity-index-{YEAR}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"reference (Boeing's inputs)        {ref_idx:5.1f}   published {REF['published_index']}")
    print(f"Hamburg, open sectors substituted  {index(rows):5.1f}   ({open_weight:.0f} of 1000 per mille re-derived)")
    h = out["hamburg_trade_adjusted"]
    if "no_data" not in h:
        print(f"Hamburg {h['year']}, measured capacity    {h['capacity_index']:5.1f}   trade-adjusted {h['trade_adjusted_index']:.1f} "
              f"(upper bound: sales to the rest of Germany count as local)")
        print(f"Hamburg {h['year']}, open goods only     {h['goods_capacity_index']:5.1f}   trade-adjusted {h['goods_trade_adjusted_index']:.1f}")
    for b in out["barcelona_trade_adjusted"]:
        print(f"Catalonia {b['year']}, open goods only   " + (b.get("no_data") or
              f"{b['goods_capacity_index']:5.1f}   trade-adjusted {b['goods_trade_adjusted_index']:.1f} "
              "(loose upper bound: sales to the rest of Spain count as local)"))
    for w in out["trash_out"]["rows"]:
        print(f"trash out {w['city']:18} {w['year']}  " + (w.get("error") or
              f"generated {w['generated_kg_per_capita']} kg/cap  residual {w['residual_kg_per_capita']} kg/cap  "
              f"recovery {w['recovery_share']}"))
    for g in out["gateway"]["rows"]:
        t = lambda v: "no data" if v is None else f"{v:,} t"
        print(f"gateway   {g['city']:18} {g['year'] or '':4} {g.get('mode', ''):3}  " + (g.get("no_data") or g.get("error") or
              f"in {t(g['inwards_t'])}  out {t(g['outwards_t'])}  ({g['port']})"))
    for r in out["regional_trade"]["rows"]:
        cur = "USD" if "exports_usd" in r else "EUR"   # Boston's metro exports are in dollars, never converted
        money = lambda v: "no data" if v is None else f"{v / 1e9:,.1f} bn {cur}"
        t = lambda v: "no data" if v is None else f"{v / 1e6:,.1f} Mt"
        print(f"regional  {r['city']:18} {r['year'] or '':4}  " + (r.get("no_data") or r.get("error") or
              f"imports {money(r.get('imports_' + cur.lower()))} / {t(r['imports_t'])}  exports "
              f"{money(r.get('exports_' + cur.lower()))} / {t(r['exports_t'])}  "
              f"({r['territory']}{', provisional' if r['provisional'] else ''})"))
    for b in out["brazil_trade_adjusted"]["rows"]:
        print(f"{b['city']:9} ({b['territory']}) {b['year']}, goods  {b['goods_capacity_index']:5.1f}   trade-adjusted "
              f"{b['goods_trade_adjusted_index']:.1f} (upper bound: the rest of Brazil counts as local)")
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
    cat = waste.catalonia(2024, get=lambda u: [{"sum_suma_fracci_resta": "2000", "sum_total_recollida_selectiva": "2000",
                                                "sum_poblaci": "8000", "count": "948"}])
    check("waste: Catalonia residual per capita from the server-side sums", cat["residual_kg_per_capita"], 250.0)
    check("waste: and says how many municipalities it summed", cat["municipalities"], 948)
    check("waste: a year with no rows is no data, not zero",
          waste.catalonia(1990, get=lambda u: [{"count": "0"}]), None)
    # waste.santiago: decimal commas, thousands dots, one comuna only, recovery by declared treatment.
    csv_text = ("id_comuna;cantidad_toneladas;tratamiento_nivel_1\n13101;1.000,5;Eliminación\n"
                "13101;99,5;Valorización\n13102;5000;Eliminación\n").encode()
    sg = waste.santiago(2022, get=lambda u: {"result": {"resources": [{"name": "2022: x", "format": "CSV", "url": "u"}]}},
                        raw=lambda u: csv_text, pop=lambda c, y: None)
    check("waste: RETC '1.000,5' reads as 1000.5, and other comunas are left out", sg["generated_t"], 1100)
    check("waste: RETC recovery share by declared treatment", sg["recovery_share"], round(99.5 / 1100, 3))
    check("waste: no population means no per-capita figure, not a guess", sg["generated_kg_per_capita"], None)
    res = lambda u: {"result": {"resources": [{"name": "2022: x", "format": "CSV", "url": "u"}]}}
    pc = waste.santiago(2022, get=res, raw=lambda u: csv_text, pop=lambda c, y: 1100)
    check("waste: comuna per capita = tonnes x 1000 / population", pc["generated_kg_per_capita"], 1000.0)
    check("waste: residual = everything not declared recovered", pc["residual_kg_per_capita"], round(1000.5 * 1000 / 1100, 1))
    rm = waste.santiago(2022, get=res, raw=lambda u: csv_text + b"5101;7;Eliminaci\xc3\xb3n\n", code="13",
                        pop=lambda c, y: {"13": 6100}[c])
    check("waste: a region sums its comunas by code prefix (13101 + 13102, not 5101)", rm["generated_t"], 6100)
    check("waste: and is named as the region", rm["city"], "Region Metropolitana (region)")
    part = waste.santiago(2022, get=res, raw=lambda u: csv_text + b"13103;400;\n", pop=lambda c, y: 1000, code="13103")
    check("waste: tonnes with no treatment recorded are reported, not counted as residual",
          (part["treatment_not_recorded_t"], part["residual_kg_per_capita"], part["recovery_share"]), (400, None, None))
    mix = waste.santiago(2022, get=res, raw=lambda u: csv_text + b"13101;900;\n", pop=lambda c, y: 2000)
    check("waste: recovery is a share of the recorded tonnes only", mix["recovery_share"], round(99.5 / 1100, 3))
    check("waste: and residual leaves the unrecorded 900 t out", mix["residual_kg_per_capita"], round(1000.5 * 1000 / 2000, 1))
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "p.csv"
        f.write_text("# provenance\ncomuna,nombre,region,2022\n13101,Santiago,13,500\n13102,Cerrillos,13,80\n5101,Valparaiso,5,300\n")
        check("population: a comuna by its 5-digit code", waste.population_cl("13101", 2022, f), 500)
        check("population: a region sums its comunas", waste.population_cl("13", 2022, f), 580)
        check("population: a year outside the file is no data", waste.population_cl("13101", 2040, f), None)

    # waste.national: JSON-stat picking, the benchmark arithmetic, and missing trade values staying missing.
    def js(dims: dict, values: dict) -> dict:
        ids = list(dims)
        d = {"id": ids, "size": [len(dims[k]) for k in ids],
             "dimension": {k: {"category": {"index": {c: i for i, c in enumerate(dims[k])}}} for k in ids}, "value": {}}
        for coords, v in values.items():
            pos = 0
            for k, c in zip(ids, coords):
                pos = pos * len(dims[k]) + dims[k].index(c)
            d["value"][str(pos)] = v
        return d
    mun = js({"geo": ["XX"], "wst_oper": ["GEN", "RCY"]}, {("XX", "GEN"): 500, ("XX", "RCY"): 200})
    check("_pick: a value by its codes", waste._pick(mun, wst_oper="RCY"), 200)
    check("_pick: an unknown code is no data", waste._pick(mun, wst_oper="PRP_REU"), None)
    try:
        waste._pick(mun)
        check("_pick: an unfixed dimension with several members raises", "no error", "ValueError")
    except ValueError:
        check("_pick: an unfixed dimension with several members raises", "ValueError", "ValueError")
    rate = js({"geo": ["XX"]}, {("XX",): 40.0})
    parts = ["INT_EU27_2020", "EXT_EU27_2020"]
    full = js({"stk_flow": ["EXP", "IMP"], "partner": parts},
              {("EXP", parts[0]): 10, ("EXP", parts[1]): 5, ("IMP", parts[0]): 3, ("IMP", parts[1]): 2})
    fake = lambda trade: (lambda u: mun if "env_wasmun" in u else rate if "cei_wm011" in u else trade)
    waste.COUNTRY["XX"] = "Testland"
    n = waste.national("XX", 2024, get=fake(full))
    check("national: residual = generated minus recycled", n["residual_kg_per_capita"], 300.0)
    check("national: recovery = the official recycling rate", n["recovery_share"], 0.4)
    check("national: exports and imports sum both partners, net = exports - imports",
          (n["waste_exported_t"], n["waste_imported_t"], n["net_waste_export_t"]), (15, 5, 10))
    gap = js({"stk_flow": ["EXP", "IMP"], "partner": parts}, {("EXP", parts[0]): 10, ("IMP", parts[0]): 3, ("IMP", parts[1]): 2})
    g = waste.national("XX", 2024, get=fake(gap))
    check("national: a missing partner value leaves exports and net as no data, not a partial sum",
          (g["waste_exported_t"], g["net_waste_export_t"], g["waste_imported_t"]), (None, None, 5))
    del waste.COUNTRY["XX"]

    # waste.hamburg: Statistikamt Nord's flagged numbers, a real (tiny) xlsx, and the split arithmetic.
    check("_num: '413,6 r' is 413.6", waste._num("413,6 r"), 413.6)
    check("_num: '·' (withheld) is no data", waste._num("·"), None)
    import io, zipfile
    def xlsx(rows: list[list], sheet_name: str = "T1_1") -> bytes:
        cols = "ABCDEFGHIJ"
        sheet = "".join(f'<row r="{i+1}">' + "".join(
            f'<c r="{cols[j]}{i+1}" t="inlineStr"><is><t>{v}</t></is></c>' if isinstance(v, str) else f'<c r="{cols[j]}{i+1}"><v>{v}</v></c>'
            for j, v in enumerate(r) if v is not None) + "</row>" for i, r in enumerate(rows))
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w") as z:
            z.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                       'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                       f'<sheet name="{sheet_name}" sheetId="1" r:id="rId1"/></sheets></workbook>')
            z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
                       'relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
            z.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/'
                       f'main"><sheetData>{sheet}</sheetData></worksheet>')
        return b.getvalue()
    book = xlsx([["Jahr", "insgesamt"], ["2024", 1000, "400,0 r", 600, 100, 250, 50, 5]])
    check("_xlsx_rows: cells by column letter, inline and numeric",
          (waste._xlsx_rows(book, "T1_1")[1]["A"], waste._xlsx_rows(book, "T1_1")[1]["D"]), ("2024", "600"))
    h = waste.hamburg(2024, raw=lambda u: book)
    check("hamburg: population from the report's own per-head basis", h["population"], 2500)
    check("hamburg: residual = Haus- und Sperrmüll per head", h["residual_kg_per_capita"], 240.0)
    check("hamburg: recovery = organics + recyclables + electrical over total", h["recovery_share"], 0.4)
    check("hamburg: a year not in the table is no data", waste.hamburg(2031, raw=lambda u: book), None)

    # trade.port: directions kept apart, thousand tonnes to tonnes, a missing direction stays missing.
    ports = js({"direct": ["IN", "OUT", "TOTAL"]}, {("IN",): 30.5, ("OUT",): 20.0, ("TOTAL",): 50.5})
    pt = trade.port("Barcelona", 2024, get=lambda u: ports)
    check("trade: inwards and outwards reported separately, in tonnes", (pt["inwards_t"], pt["outwards_t"]), (30500, 20000))
    half = js({"direct": ["IN", "OUT", "TOTAL"]}, {("IN",): 30.5, ("TOTAL",): 50.5})
    check("trade: a direction the port did not report is no data, not zero",
          trade.port("Hamburg", 2024, get=lambda u: half)["outwards_t"], None)
    empty = js({"direct": ["IN", "OUT", "TOTAL"]}, {})
    check("trade: a port absent for a year says why (HAROPA before 2021)",
          trade.port("Paris", 2019, get=lambda u: empty)["no_data"].startswith("HAROPA was formed in 2021"), True)
    check("trade: Boston and Santiago appear, each saying why they have no data",
          sorted(r["city"] for r in trade.gateway([]) if r.get("no_data")), ["Boston", "Santiago"])
    # trade.airport: a city's airports summed, unloaded is inwards, and one missing airport blanks that direction.
    air = {"FR_LFPG": js({"tra_meas": ["FRM_LD", "FRM_NLD"]}, {("FRM_LD",): 900.4, ("FRM_NLD",): 800.0}),
           "FR_LFPO": js({"tra_meas": ["FRM_LD", "FRM_NLD"]}, {("FRM_LD",): 50.0, ("FRM_NLD",): 20.0})}
    ap = trade.airport("Paris", 2024, get=lambda u: air["FR_LFPG" if "FR_LFPG" in u else "FR_LFPO"])
    check("trade: Paris airports summed, unloaded = inwards, loaded = outwards",
          (ap["mode"], ap["inwards_t"], ap["outwards_t"]), ("air", 820, 950))
    air["FR_LFPO"] = js({"tra_meas": ["FRM_LD", "FRM_NLD"]}, {("FRM_LD",): 50.0})
    ap = trade.airport("Paris", 2024, get=lambda u: air["FR_LFPG" if "FR_LFPG" in u else "FR_LFPO"])
    check("trade: one airport missing a direction blanks it, not a partial sum",
          (ap["inwards_t"], ap["outwards_t"], ap["total_t"], ap["missing"]), (None, 950, None, "not reported for 2024: Paris Orly"))
    # JSON-stat as arrays (Idescat): index and value lists, and a status flag read by position.
    arr = {"id": ["PROV", "CONCEPT"], "size": [2, 2], "value": [1.0, 2.0, 3.0, None],
           "dimension": {"PROV": {"category": {"index": ["08", "TOTAL"]}},
                         "CONCEPT": {"category": {"index": ["A", "B"]}}}, "status": {"2": "p"}}
    check("_pick: an array index and array values", (waste._pick(arr, PROV="TOTAL", CONCEPT="A"),
                                                     waste._pick(arr, PROV="08", CONCEPT="B")), (3.0, 2.0))
    check("_pick: a null in the value array is no data", waste._pick(arr, PROV="TOTAL", CONCEPT="B"), None)
    check("_status: the flag at the same position", (waste._status(arr, PROV="TOTAL", CONCEPT="A"),
                                                    waste._status(arr, PROV="08", CONCEPT="A")), ("p", None))
    # trade.regional: thousand euro to euro, kg to tonnes, a missing weight stays missing, provisional carried.
    concepts = ["VALUE_IMP", "VALUE_EXP", "WEIGHT_IMP", "WEIGHT_EXP"]
    idx = js({"PROV": ["08", "TOTAL"], "CONCEPT": concepts},
             {("08", "VALUE_IMP"): 100.5, ("08", "VALUE_EXP"): 80.0, ("08", "WEIGHT_IMP"): 2500400.0,
              ("TOTAL", "VALUE_IMP"): 150.0, ("TOTAL", "VALUE_EXP"): 90.0, ("TOTAL", "WEIGHT_IMP"): 4000.0,
              ("TOTAL", "WEIGHT_EXP"): 3000.0})
    idx["status"] = {"4": "p"}                       # TOTAL, VALUE_IMP
    rb = trade.regional("Barcelona", 2024, get=lambda u: idx)
    check("regional: euros and tonnes, imports and exports apart",
          (rb[0]["imports_eur"], rb[0]["exports_eur"], rb[0]["imports_t"]), (100500, 80000, 2500))
    check("regional: a weight not reported is no data, not zero", rb[0]["exports_t"], None)
    check("regional: provisional values are flagged, per territory", (rb[0]["provisional"], rb[1]["provisional"]), (False, True))
    check("regional: cities without a reader say why",
          sorted(r["city"] for r in trade.regional_trade([]) if r.get("no_data")), ["Santiago"])
    # trade.hamburg: the next edition's final figure first, the year's own provisional one as the fallback.
    def nord(this, last):                            # a T1_1 sheet: header flags, then the Insgesamt row
        return xlsx([["Tabelle 1"], [None, "2025a" if this == 2025 else f"{this}a", f"{last}b", "%",
                                     "2025a" if this == 2025 else f"{this}a", f"{last}b", "%"],
                     ["Europa", 9, 9, 0, 9, 9, 0], ["Insgesamt", this * 10.0, last * 10.0, 0, this, last, 0]])
    books = {"j25": nord(2025, 2024), "j24": nord(2024, 2023)}
    ckan = lambda u: {"result": {"results": [{"resources": [{"url": f"https://x/G_III_1_G_III_3_{k}_HH_nach_Laendern.xlsx"}]}
                                             for k in books if u.split("q=G_III_1_G_III_3_")[1].startswith(k + "&")]}}
    fetch = lambda u: books[next(k for k in books if f"_{k}_" in u)]
    h24, h25 = trade.hamburg(2024, get=ckan, raw=fetch)[0], trade.hamburg(2025, get=ckan, raw=fetch)[0]
    check("hamburg trade: the next edition's final figure, thousand euro to euro",
          (h24["imports_eur"], h24["exports_eur"], h24["provisional"], "2025 edition" in h24["source"]),
          (20240000, 2024000, False, True))
    check("hamburg trade: no next edition, so the year's own figure, flagged provisional",
          (h25["imports_eur"], h25["provisional"], "2025 edition" in h25["source"]), (20250000, True, True))
    check("hamburg trade: no edition at all is no data, not zero", trade.hamburg(2031, get=ckan, raw=fetch)[0]["no_data"][:16],
          "no annual editio")
    check("hamburg trade: values only, tonnes stay empty", (h24["imports_t"], h24["exports_t"]), (None, None))
    mismatch = xlsx([["Tabelle 1"], [None, "2024a", "2023b", "%", "2023b", "2024a", "%"], ["Insgesamt", 1, 2, 0, 3, 4, 0]])
    try:
        trade._nord_totals(mismatch)
        check("hamburg trade: an imports/exports header mismatch raises", "no error", "ValueError")
    except ValueError:
        check("hamburg trade: an imports/exports header mismatch raises", "ValueError", "ValueError")
    # trade.paris: French customs' file summed by département and region, in euros; a year it lacks is no data.
    def qdf(flow, vals):                             # Region, Dep, Flux, ..., one column per year
        return xlsx([["Region", "Dep", "Flux", "CodeA129", "Pays", "annee2024_valeur_en_euros", "annee2025_valeur_en_euros"]] +
                    [["03", dep, flow, "C10A", "DE", a, b] for dep, a, b in vals], sheet_name="qdf")
    zb = io.BytesIO()
    with zipfile.ZipFile(zb, "w") as z:
        z.writestr(zipfile.ZipInfo("REGION_03_A_IMPORT.xlsx", (2026, 9, 3, 0, 0, 0)), qdf("Import", [("75", 100.4, 1), ("75", 50, 1), ("92", 1000, 1)]))
        z.writestr(zipfile.ZipInfo("REGION_03_A_EXPORT.xlsx", (2026, 9, 3, 0, 0, 0)), qdf("Export", [("75", 30, 1), ("92", 300, 1)]))
    fake = lambda u: zb.getvalue()
    p24 = trade.paris(2024, raw=fake)
    check("paris trade: département 75 and the region summed apart, in euros",
          [(r["code"], r["imports_eur"], r["exports_eur"]) for r in p24], [("75", 150, 30), ("03", 1150, 330)])
    check("paris trade: the citation DGDDI asks for", p24[0]["source"].startswith("source : douanes françaises, résultats de septembre 2026"), True)
    check("paris trade: a year the file does not carry is no data, saying which years it has",
          (trade.paris(2019, raw=fake)[0]["imports_eur"], trade.paris(2019, raw=fake)[0]["no_data"]),
          (None, "the customs file carries only 2024, 2025"))
    check("paris trade: nothing to say about provisional, so it says nothing", p24[0]["provisional"], None)
    # trade.boston: the next Q4 workbook's revised annual first, the year's own as the fallback; dollars stay dollars.
    import urllib.error
    def metro(edition, prev_val, this_val):
        return xlsx([["U.S. Exports by Metropolitan Area"], [None, f"{edition} Q4", f"{edition - 1} Q4", f"{edition} Annual", f"{edition - 1} Annual"],
                     ["Total Exports", 1, 1, 9, 9], [trade.BOSTON_MSA, 1, 1, this_val, prev_val]], sheet_name=f"Q4{edition}")
    workbooks = {2025: metro(2025, 29935.6, 30541.3)}
    def fetch_q4(u):
        y = int(u.rsplit("metroq4", 1)[1][:4])
        if y not in workbooks:
            raise urllib.error.HTTPError(u, 404, "Not Found", {}, None)
        return workbooks[y]
    b24, b25 = trade.boston(2024, raw=fetch_q4)[0], trade.boston(2025, raw=fetch_q4)[0]
    check("boston trade: next year's workbook, million dollars to dollars, not provisional",
          (b24["exports_usd"], b24["provisional"], "Q4 2025" in b24["source"]), (29935600000, False, True))
    check("boston trade: no next workbook yet (404), so the first release, flagged provisional",
          (b25["exports_usd"], b25["provisional"]), (30541300000, True))
    check("boston trade: exports only, and never in euros", (b24["imports_usd"], "exports_eur" in b24), (None, False))
    check("boston trade: no workbook at all is no data", trade.boston(2031, raw=fetch_q4)[0]["no_data"][:6], "no Q4 ")
    # waste._raw: a 404 is an answer and fails at once; only server errors are retried.
    calls, real_open = [], waste.urllib.request.urlopen
    def not_found(req, timeout=None):
        calls.append(1)
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)
    waste.urllib.request.urlopen = not_found
    try:
        waste._raw("https://example.org/missing")
    except urllib.error.HTTPError:
        pass
    finally:
        waste.urllib.request.urlopen = real_open
    check("_raw: a 404 is tried once, not four times", len(calls), 1)
    # trade.nord_manufacturing: own-production columns when the edition has them, '·' is unknown, the second path on 404.
    ei_book = xlsx([["2. Umsatz, Auslandsumsatz"], ["WZ 2008", "Bezeichnung", "Umsatz", None, None, None, None, "Ums. a. Eigenerzeug."],
                    [None, None, "2022", "%", "2022", None, None, "2022"],
                    ["10", "Nahrung", 4000, 1, 1600, 1, 1, 3200, 1360], ["11", "Getraenke", 110, 1, 85, 1, 1, 100, 80],
                    ["13", "Textilien", "·", "·", "·", "·", "·", "·", "·"], ["10.1", "Schlachten", 300, 1, 1, 1, 1, 200, 1]],
                   sheet_name="T2_1")
    def ei_fetch(u):
        if "E_I_1_j_H" not in u:
            raise urllib.error.HTTPError(u, 404, "Not Found", {}, None)
        return ei_book
    ei = trade.nord_manufacturing(2022, raw=ei_fetch)
    check("E I 1: own-production turnover and its foreign part, the second path after a 404",
          (ei["concept"], ei["divisions"]["10"], "E_I_1_j_H" in ei["url"]), ("turnover from own production", (3200.0, 1360.0), True))
    check("E I 1: a suppressed division is unknown, not zero; groups like 10.1 are left out",
          (ei["divisions"]["13"], "10.1" in ei["divisions"]), ((None, None), False))
    # trade_adjust: capacity and trade-adjusted over the same plants; a division without its foreign part drops from both.
    spend = {s: {"consumption_meur": 1000.0, "coicop_missing": []} for s in OPEN}
    ta = trade_adjust(spend, {"C10": (600000.0, 200000.0), "C11": (100000.0, 50000.0), "C23": (300000.0, None), "C32": (400000.0, 100000.0),
                              "C26": (1500000.0, 1200000.0)})
    check("trade_adjust: food, sales abroad taken out", (ta["Food and beverages"]["capacity"], ta["Food and beverages"]["trade_adjusted"]),
          (0.7, 0.45))
    check("trade_adjust: capacity caps at 1, trade-adjusted can still be low", (ta["IT and communication"]["capacity"],
          ta["IT and communication"]["trade_adjusted"]), (1.0, 0.3))
    check("trade_adjust: C23 without foreign turnover drops from both ratios, flagged partial",
          (ta["Other goods"]["capacity"], ta["Other goods"]["state"], ta["Other goods"]["nace_missing"]), (0.4, "measured, partial", ["C23"]))
    check("trade_adjust: nothing published is no data, which carries Boeing's ratio", ta["Textiles and clothing"]["capacity"], None)
    # trade.idescat_industry: the year the file names, abroad = rest of the EU + rest of the world, thousand euro.
    eie_csv = ("\ufeffIndustrial sector. Turnover.\n2019\nUnits: Thousand euros.\n,Spain,Rest of European Union,Rest of the world,Total\n"
               "Industries of food products,19690,4848,2437,26975\n\"Manufacture of textiles, leather, footwear. Tailoring\",2601,1449,507,4557\n")
    eie = trade.idescat_industry(2019, raw=lambda u: eie_csv.encode("utf-8"))
    check("Idescat EIE: total and sold abroad (EU + rest of the world), a quoted label kept whole",
          (eie["divisions"]["Industries of food products"], eie["divisions"]["Manufacture of textiles, leather, footwear. Tailoring"]),
          ((26975.0, 7285.0), (4557.0, 1956.0)))
    check("Idescat EIE: a file for another year is no data (plain t=2019 silently returns the latest year)",
          trade.idescat_industry(2022, raw=lambda u: eie_csv.encode("utf-8")), None)
    check("Idescat EIE: the year goes in as YYYY00", "t=201900" in trade.IDESCAT_EIE.format(year=2019), True)
    # trade_adjust with a source's own groups, and trade_variant without carried ratios: a goods index only.
    groups = {"Industries of food products": (600000.0, 200000.0)}
    tg = trade_adjust(spend, groups, {"Food and beverages": ["Industries of food products", "Beverages"]})
    check("trade_adjust: groups instead of divisions, a missing group makes it partial",
          (tg["Food and beverages"]["capacity"], tg["Food and beverages"]["state"]), (0.6, "measured, partial"))
    def fake_get(dataset, **p):
        if dataset == "nama_10_co3_p3":
            return js({"coicop": ["CP01", "CP021"]}, {("CP01",): 1100.0, ("CP021",): 121.0})
        if dataset == "demo_r_d2jan":
            return js({"geo": ["ES51", "ES"]}, {("ES51",): 1.0, ("ES",): 1.0})
        return js({"coicop": ["CP01", "CP021"]}, {("CP01",): 150.0, ("CP021",): 10.0})
    tv = trade_variant("ES51", 2019, {"divisions": groups, "concept": "turnover"}, CAT_GROUPS, "test", False, get=fake_get)
    check("trade_variant: no carried ratios for Barcelona, a goods index over the measured sectors",
          ("capacity_index" in tv, tv["goods_capacity_index"], tv["goods_weight_per_mille"]), (False, 54.5, 160.0))   # 600 / (1100/1.10 + 121/1.21)
    # Brazil: SIDRA rows by code, ComexStat's missing divisions as no exports, USD at the year's rate, POF x 12 x families.
    def br_get(u):
        if "bcdata.sgs.3694" in u:
            return [{"data": "01/01/2019", "valor": "4.0"}]
        if "/t/1849/" in u:
            return [{}, {"D1C": "35", "D4C": "116911", "V": "1000"}, {"D1C": "35", "D4C": "117159", "V": "..."},
                    {"D1C": "26", "D4C": "116911", "V": "500"}]
        if "/t/6977/" in u:
            return [{}, {"D1C": "35", "V": "10"}, {"D1C": "26", "V": "5"}]
        return [{}] + [{"D1C": uf, "D5C": c, "V": "1000"} for uf in ("35", "26") for c in u.split("/c12190/")[1].split("/")[0].split(",")]
    br_post = lambda b: {"data": {"list": [{"state": "São Paulo", "coIsicDivision": "10", "metricFOB": "50"}]}}
    prod = trade.brazil_production(2019, get=br_get)
    check("Brazil production: by state and division, an unpublished cell ('...') is None, never zero",
          (prod["São Paulo"]["C10"], prod["São Paulo"]["C26"], prod["Pernambuco"]["C10"]), (1000.0, None, 500.0))
    ex = trade.brazil_exports_usd(2019, post=br_post)
    check("ComexStat: a division it does not list exported nothing", (ex["São Paulo"]["C10"], ex["Pernambuco"]["C10"]), (50.0, 0.0))
    check("POF: per family per month x 12 x families, M R$", trade.pof_spending(get=br_get)["São Paulo"]["Food and beverages"], 0.12)
    br = brazil_trade_adjusted(2019, get=br_get, post=br_post)
    check("Brazil: exports in R$ thousand (50 US$ x 4.0 / 1000) taken out of 1,000 thousand R$",
          (br[0]["city"], br[0]["sectors"]["Food and beverages"]["measured_meur"], br[0]["sectors"]["Food and beverages"]["sold_abroad_meur"]),
          ("São Paulo", 1.0, 0.0))
    check("Brazil: a state without a published division drops it; Recife reads Pernambuco", (br[1]["city"], br[1]["territory"],
          br[0]["sectors"]["IT and communication"]["capacity"]), ("Recife", "Pernambuco (state)", None))
    blank = waste.santiago(2019, get=lambda u: {"result": {"resources": [{"name": "2019: x", "format": "CSV", "url": "u"}]}},
                           raw=lambda u: b"id_comuna;cantidad_toneladas;tratamiento_nivel_1\n13101;10;\n")
    check("waste: a year with no treatment recorded has no recovery share, not 0%", blank["recovery_share"], None)
    print(f"\nfabcity_index selftest: {bad} failed.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else run())

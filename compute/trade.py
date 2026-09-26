"""Gateway flows: goods in and out through a territory's ports and airports, Economic|Bioregion's third minimum indicator.

The row (awesome-fabcity-data#36, #38) is "Goods imported and exported through the territory's ports and airports,
t/yr, inwards and outwards reported separately". It is the physical boundary flow a territory's material account
would start from, not the account: a port's throughput is not its hinterland's consumption, transhipment never enters
the local economy, and road and rail are not in it. That is why this module reports tonnes and never a ratio.

  Barcelona  Eurostat mar_mg_aa_pwhd, port ES_2ESBCN
  Hamburg    the same table, DE_1DEHAM (Germany's largest port, which is why Boeing left trade out of his index)
  Paris      HAROPA (Le Havre and Rouen), FR_1FR001: Paris's sea gateway on the Seine, not a port in Paris
  Boston     no data: US Census trade by port (porths) needs an API key, which this pipeline does not hold
  Santiago   no data yet: Chile's customs declarations are monthly RAR/ZIP files, not read here
Airports come from Eurostat avia_gooa, freight and mail in tonnes: Barcelona El Prat, Hamburg, and for Paris the sum
of Charles de Gaulle and Orly. Sea and air stay separate rows (mode "sea" / "air"), never added into one figure.
"""
from __future__ import annotations

import re

import waste  # the JSON-stat reader, the xlsx reader and the retrying fetch live there

TABLE = "mar_mg_aa_pwhd"   # gross weight of goods handled in the top EU ports, thousand tonnes, by direction
LICENCE = "Eurostat reuse policy, 2011/833/EU"
PORTS = {
    "Barcelona": ("ES_2ESBCN", "Barcelona"),
    "Hamburg": ("DE_1DEHAM", "Hamburg"),
    "Paris": ("FR_1FR001", "HAROPA (Le Havre and Rouen), Paris's sea gateway on the Seine"),
}
# Why a port can be missing for a year, where the reason is known.
NOT_REPORTED = {"FR_1FR001": "HAROPA was formed in 2021; before that Le Havre and Rouen reported separately, and "
                             "Rouen is not in this top-20 table"}
AIR_TABLE = "avia_gooa"     # freight and mail loaded and unloaded at the main airports, tonnes
AIRPORTS = {
    "Barcelona": [("ES_LEBL", "Barcelona El Prat")],
    "Hamburg": [("DE_EDDH", "Hamburg")],
    "Paris": [("FR_LFPG", "Paris Charles de Gaulle"), ("FR_LFPO", "Paris Orly")],
}
# Regional trade, Economic|Region's external-trade row: customs trade of the territory, not of its gateways.
IDESCAT = "https://api.idescat.cat/taules/v2/comest/18132/5/prov/data"
IDESCAT_LICENCE = ("Idescat reuse conditions: cite the source, do not alter, state the update date. No named licence; "
                   "open-equivalence not yet confirmed (awesome-fabcity-data#51)")
REGIONS = {"Barcelona": [("08", "Province of Barcelona"), ("TOTAL", "Catalonia")]}
# Hamburg: Statistikamt Nord's annual report G III 1 / G III 3, found through the Transparenzportal's CKAN, because
# the file names drift (j23 is `..._Rev.xlsx`, older editions sit in another folder).
NORD_CKAN = "https://suche.transparenz.hamburg.de/api/3/action/package_search?q=G_III_1_G_III_3_j{yy}&rows=20"
NORD_LICENCE = ("dl-de-by-2.0 on the Transparenzportal; the file's own imprint permits extracts with attribution and "
                "reserves other rights")
NO_REGIONAL = {
    "Paris": "French customs publish regional trade as HTML tables (filed in #51), not read yet.",
    "Boston": "Only metro-area exports are open (filed in #51), not read yet; no imports are published below state level.",
    "Santiago": "No open regional trade source: the Banco Central's terms are revocable (awesome-fabcity-data#50).",
}
NO_DATA = {
    "Boston": "US Census trade by port (porths) needs an API key, which this pipeline does not hold.",
    "Santiago": "Chile's customs declarations (Servicio Nacional de Aduanas) are monthly RAR/ZIP files, not read yet.",
}


def port(city: str, year: int, get=waste._json) -> dict:
    code, what = PORTS[city]
    d = get(f"{waste.EUROSTAT}{TABLE}?format=JSON&lang=EN&rep_mar={code}&unit=THS_T&time={year}")
    kt = {k: waste._pick(d, direct=k) for k in ("IN", "OUT", "TOTAL")}
    row = {"city": city, "year": year, "port": what, "code": code,
            "inwards_t": None if kt["IN"] is None else round(kt["IN"] * 1000),
            "outwards_t": None if kt["OUT"] is None else round(kt["OUT"] * 1000),
            "total_t": None if kt["TOTAL"] is None else round(kt["TOTAL"] * 1000),
            "mode": "sea", "counts": "gross weight of goods handled by the port, inwards and outwards; "
                      "throughput, not the hinterland's consumption",
            "source": f"Eurostat {TABLE}, rep_mar={code}", "licence": LICENCE}
    if all(v is None for v in kt.values()):
        row["no_data"] = NOT_REPORTED.get(code, "the port is not in the table for this year")
    return row


def airport(city: str, year: int, get=waste._json) -> dict:
    """A city's airports summed. If any airport misses a direction, that direction is no data, never a partial sum."""
    inw, outw, missing = 0, 0, []
    for code, name in AIRPORTS[city]:
        d = get(f"{waste.EUROSTAT}{AIR_TABLE}?format=JSON&lang=EN&freq=A&unit=T&schedule=TOTAL&tra_cov=TOTAL"
                f"&rep_airp={code}&tra_meas=FRM_LD&tra_meas=FRM_NLD&time={year}")
        i, o = waste._pick(d, tra_meas="FRM_NLD"), waste._pick(d, tra_meas="FRM_LD")   # unloaded in, loaded out
        inw, outw = (None if i is None or inw is None else inw + i), (None if o is None or outw is None else outw + o)
        if i is None or o is None:
            missing.append(name)
    codes = [c for c, _ in AIRPORTS[city]]
    row = {"city": city, "year": year, "port": " + ".join(n for _, n in AIRPORTS[city]), "code": "+".join(codes),
           "mode": "air", "inwards_t": None if inw is None else round(inw),
           "outwards_t": None if outw is None else round(outw),
           "total_t": None if inw is None or outw is None else round(inw + outw),
           "counts": "freight and mail unloaded (inwards) and loaded (outwards) at the airport; hub airports "
                     "tranship, so this is throughput, not the city's consumption",
           "source": f"Eurostat {AIR_TABLE}, rep_airp={','.join(codes)}", "licence": LICENCE}
    if missing:
        row["missing"] = f"not reported for {year}: {', '.join(missing)}"
    return row


def regional(city: str, year: int, get=waste._json) -> list[dict]:
    """Exports and imports of the city's territories, in euros and tonnes, each direction and unit kept apart."""
    places = REGIONS[city]
    d = get(f"{IDESCAT}?lang=en&YEAR={year}&TOD=TOTAL&TARIC=TOTAL&MOD_TRANS=TOTAL&PROV={','.join(c for c, _ in places)}"
            "&CONCEPT=VALUE_IMP,VALUE_EXP,WEIGHT_IMP,WEIGHT_EXP")
    rows = []
    for code, name in places:
        v = {c: waste._pick(d, PROV=code, CONCEPT=c) for c in ("VALUE_IMP", "VALUE_EXP", "WEIGHT_IMP", "WEIGHT_EXP")}
        eur = lambda k: None if v[k] is None else round(v[k] * 1000)     # thousand euro
        t = lambda k: None if v[k] is None else round(v[k] / 1000)       # kilograms
        row = {"city": city, "year": year, "territory": name, "code": code,
               "imports_eur": eur("VALUE_IMP"), "exports_eur": eur("VALUE_EXP"),
               "imports_t": t("WEIGHT_IMP"), "exports_t": t("WEIGHT_EXP"),
               "provisional": any(waste._status(d, PROV=code, CONCEPT=c) == "p" for c in v),
               "counts": "goods crossing the Spanish customs border, attributed to the declarant's province; trade "
                         "with the rest of Spain is not in it; no balance is drawn",
               "source": f"Idescat comest 18132, AEAT customs, PROV={code}, updated {d.get('updated')}",
               "licence": IDESCAT_LICENCE}
        if all(x is None for x in v.values()):
            row["no_data"] = "the territory is not in the table for this year"
        rows.append(row)
    return rows


def _nord_edition(edition: int, get=waste._json) -> str | None:
    """The URL of Statistikamt Nord's annual trade report by partner country for that year, or None if not published."""
    yy = f"{edition % 100:02d}"
    found = get(NORD_CKAN.format(yy=yy))["result"]["results"]
    urls = [x["url"] for p in found for x in p.get("resources", [])
            if f"_j{yy}_HH_nach_Laendern" in x["url"] and x["url"].endswith(".xlsx")]
    return urls[0] if urls else None


def _nord_totals(book: bytes) -> dict[int, tuple]:
    """{year: (imports, exports in thousand euro, final)} from sheet T1_1's `Insgesamt` row. Each edition holds two
    years, and its header flags each one `a` (may still change through revision) or `b` (final)."""
    rows = waste._xlsx_rows(book, "T1_1")
    head = next(r for r in rows if re.fullmatch(r"\d{4}[ab]", (r.get("B") or "").strip()))
    total = next(r for r in rows if (r.get("A") or "").strip().startswith("Insgesamt"))
    out = {}
    for imp, exp in (("B", "E"), ("C", "F")):       # Einfuhr this year / last year, Ausfuhr the same
        label = head[imp].strip()
        if head.get(exp, "").strip() != label:
            raise ValueError(f"T1_1 header: imports column {imp} says {label}, exports column {exp} does not")
        out[int(label[:4])] = (waste._num(total.get(imp)), waste._num(total.get(exp)), label[4] == "b")
    return out


def hamburg(year: int, get=waste._json, raw=waste._raw) -> list[dict]:
    """Land Hamburg's imports and exports, in euros. The next year's edition carries the final figure, so it is read
    first; the year's own edition is the fallback, and its figure is provisional."""
    row = {"city": "Hamburg", "year": year, "territory": "Land Hamburg", "code": "02",
           "imports_t": None, "exports_t": None,
           "counts": "imports are general trade (they include goods entering customs warehouses whose destination is "
                     "not yet known) and exports special trade (goods made or last processed in Hamburg), so no balance "
                     "is meaningful; values only, no tonnes; trade with other Länder is not in it",
           "licence": NORD_LICENCE}
    for edition in (year + 1, year):
        url = _nord_edition(edition, get)
        found = _nord_totals(raw(url)).get(year) if url else None
        if found:
            imp, exp, final = found
            return [dict(row, imports_eur=None if imp is None else round(imp * 1000),
                         exports_eur=None if exp is None else round(exp * 1000), provisional=not final,
                         source=f"Statistikamt Nord G III 1 / G III 3, {edition} edition, T1_1 Insgesamt: {url}")]
    return [dict(row, imports_eur=None, exports_eur=None, provisional=False, source="Statistikamt Nord G III 1 / G III 3",
                 no_data=f"no annual edition for {year} or {year + 1} on the Transparenzportal")]


READERS = {"Barcelona": lambda y: regional("Barcelona", y), "Hamburg": hamburg}


def regional_trade(years: list[int]) -> list[dict]:
    rows = []
    for city, read in READERS.items():
        for y in years:
            try:
                rows += read(y)
            except Exception as e:                   # the API down must not blank the rest of the run
                rows.append({"city": city, "year": y, "error": f"{type(e).__name__}: {e}"[:200]})
    rows += [{"city": city, "year": None, "no_data": why} for city, why in NO_REGIONAL.items()]
    return rows


def gateway(years: list[int]) -> list[dict]:
    rows = []
    for city in PORTS:
        for read in (port, airport):
            for y in years:
                try:
                    rows.append(read(city, y))
                except Exception as e:               # one gateway down must not blank the others
                    rows.append({"city": city, "year": y, "mode": "sea" if read is port else "air",
                                 "error": f"{type(e).__name__}: {e}"[:200]})
    rows += [{"city": city, "year": None, "no_data": why} for city, why in NO_DATA.items()]
    return rows

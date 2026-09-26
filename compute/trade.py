"""Gateway flows: goods in and out through a territory's ports, Economic|Bioregion's third minimum indicator.

The row (awesome-fabcity-data#36, #38) is "Goods imported and exported through the territory's ports and airports,
t/yr, inwards and outwards reported separately". It is the physical boundary flow a territory's material account
would start from, not the account: a port's throughput is not its hinterland's consumption, transhipment never enters
the local economy, and road and rail are not in it. That is why this module reports tonnes and never a ratio.

  Barcelona  Eurostat mar_mg_aa_pwhd, port ES_2ESBCN
  Hamburg    the same table, DE_1DEHAM (Germany's largest port, which is why Boeing left trade out of his index)
  Paris      HAROPA (Le Havre and Rouen), FR_1FR001: Paris's sea gateway on the Seine, not a port in Paris
  Boston     no data: US Census trade by port (porths) needs an API key, which this pipeline does not hold
  Santiago   no data yet: Chile's customs declarations are monthly RAR/ZIP files, not read here
Airports (Eurostat avia_gooa) are not read yet, so these are ports only and say so.
"""
from __future__ import annotations

import waste  # the JSON-stat reader and the retrying fetch live there

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
            "counts": "gross weight of goods handled by the port, inwards and outwards; ports only, no airports; "
                      "throughput, not the hinterland's consumption",
            "source": f"Eurostat {TABLE}, rep_mar={code}", "licence": LICENCE}
    if all(v is None for v in kt.values()):
        row["no_data"] = NOT_REPORTED.get(code, "the port is not in the table for this year")
    return row


def gateway(years: list[int]) -> list[dict]:
    rows = []
    for city in PORTS:
        for y in years:
            try:
                rows.append(port(city, y))
            except Exception as e:                   # one port down must not blank the others
                rows.append({"city": city, "year": y, "error": f"{type(e).__name__}: {e}"[:200]})
    rows += [{"city": city, "year": None, "no_data": why} for city, why in NO_DATA.items()]
    return rows

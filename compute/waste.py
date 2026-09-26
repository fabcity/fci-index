"""Trash out: the waste half of PITO, per city, from the open sources filed in awesome-fabcity-data.

The measure proposed on awesome-fabcity-data#42 is residual municipal waste per capita: what is not
separately collected for recovery, so what goes to landfill, incineration, mechanical treatment or out of the
territory. Its companions are waste generated per capita and the recovery share. The recovery share is also
Boeing's input for macro-sector 16, "Waste and recycling", which he scored for Hamburg as a 24.8% recycling
share.

Every value says what it counts, because the four sources do not count the same thing:
  Barcelona  collected municipal waste; recovery = separate collection (not the same as recycled)
  Paris      household waste only; recovery = the sorted streams
  Santiago   declared municipal waste; recovery = tonnes whose declared treatment is "Valorizacion"
  Hamburg    municipal waste generated, total only: no split, so no residual and no recovery share
"""
from __future__ import annotations

import csv
import http.client
import io
import time
import json
import urllib.request

UA = {"User-Agent": "fci-compute"}
SOCRATA = "https://analisi.transparenciacatalunya.cat/resource/69zu-w48s.json"
PARIS = ("https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/"
         "quantite-de-dechets-produits-et-tries-par-habitant-et-par-an/records?limit=100")
RETC = "https://datosretc.mma.gob.cl/api/3/action/package_show?id=generacion-municipal-de-residuos-no-peligrosos"
EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"


def _raw(url: str, tries: int = 4) -> bytes:
    # ponytail: fixed backoff, enough for datosretc.mma.gob.cl's 502/503s and truncated reads (26 Sep 2026).
    for n in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return r.read()
        except (OSError, http.client.IncompleteRead):
            if n == tries - 1:
                raise
            time.sleep(5 * (n + 1))


def _json(url: str):
    return json.loads(_raw(url))


def _row(city, year, *, gen_t=None, gen_kg=None, residual_kg=None, recovery=None, pop=None, counts, source, licence):
    if gen_kg is None and gen_t is not None and pop:
        gen_kg = gen_t * 1000 / pop
    return {"city": city, "year": year, "population": pop,
            "generated_t": None if gen_t is None else round(gen_t),
            "generated_kg_per_capita": None if gen_kg is None else round(gen_kg, 1),
            "residual_kg_per_capita": None if residual_kg is None else round(residual_kg, 1),
            "recovery_share": None if recovery is None else round(recovery, 3),
            "counts": counts, "source": source, "licence": licence}


def barcelona(year: int, get=_json) -> dict:
    r = get(f"{SOCRATA}?$where=codi_municipi='80193'%20AND%20any='{year}'")[0]
    pop, residual, separate = float(r["poblaci"]), float(r["suma_fracci_resta"]), float(r["total_recollida_selectiva"])
    return _row("Barcelona", year, gen_t=residual + separate, pop=pop, residual_kg=residual * 1000 / pop,
                recovery=separate / (residual + separate),
                counts="collected municipal waste; recovery = separate collection, which is not the same as recycled",
                source="Generalitat de Catalunya 69zu-w48s", licence="Llicència oberta d'ús d'informació – Catalunya")


def paris(year: int, get=_json) -> dict | None:
    recs = [x for x in get(PARIS)["results"] if x["annee"] == str(year)]
    if not recs:
        return None
    total = sum(x["quantite"] for x in recs)
    residual = sum(x["quantite"] for x in recs if "résiduelles" in x["type_de_dechets"])
    return _row("Paris", year, gen_kg=total, residual_kg=residual, recovery=(total - residual) / total,
                counts="household waste only, kg per inhabitant; recovery = the sorted streams",
                source="Ville de Paris, quantite-de-dechets-produits-et-tries-par-habitant-et-par-an",
                licence="Licence Ouverte (Etalab)")


def santiago(year: int, get=_json, raw=_raw, comuna: str = "13101") -> dict | None:
    """Comuna Santiago (13101) by default. Only the CSV years are read (2014-2022); 2023-24 are XLSX."""
    res = [x for x in get(RETC)["result"]["resources"]
           if x["name"].startswith(str(year)) and x.get("format", "").upper() == "CSV"]
    if not res:
        return None
    text = raw(res[0]["url"]).decode("utf-8-sig", errors="replace")
    rows = [r for r in csv.DictReader(io.StringIO(text), delimiter=";" if text.count(";") > text.count(",") else ",")
            if r.get("id_comuna") == comuna]
    tonnes = lambda rs: sum(float(r["cantidad_toneladas"].replace(".", "").replace(",", ".")) for r in rs)
    total = tonnes(rows)
    recovered = tonnes([r for r in rows if r.get("tratamiento_nivel_1", "").startswith("Valoriz")])
    # The 2019 file leaves tratamiento_nivel_1 empty on every row: that is "not recorded", not 0% recovered.
    stated = any(r.get("tratamiento_nivel_1", "").strip() for r in rows)
    return _row("Santiago (comuna)", year, gen_t=total, recovery=recovered / total if total and stated else None,
                counts="tonnes declared through SINADER by municipal generators; recovery = declared treatment "
                       "'Valorizacion'" + ("" if stated else " (treatment not recorded this year)") + ". Totals "
                       "move with who declares (comuna Santiago: 209 kt in 2019, 116 kt in 2022). No population "
                       "in the source, so nothing per capita yet.",
                source="RETC Chile, generacion-municipal-de-residuos-no-peligrosos", licence="CC-BY (CKAN: cc-by)")


def hamburg(year: int, get=_json) -> dict | None:
    def one(indic: str):
        d = get(f"{EUROSTAT}urb_{'cenv' if indic.startswith('EN') else 'cpop1'}?format=JSON&lang=EN"
                f"&cities=DE002C&indic_ur={indic}&time={year}")
        return next(iter(d["value"].values()), None)
    kt, pop = one("EN4008V"), one("DE1001V")
    if kt is None:
        return None
    return _row("Hamburg", year, gen_t=kt * 1000, pop=pop,
                counts="municipal waste generated (domestic and commercial), total only: no recovery split, "
                       "so no residual and no recovery share",
                source="Eurostat Urban Audit urb_cenv EN4008V, population urb_cpop1 DE1001V",
                licence="Eurostat reuse policy, 2011/833/EU")


def trash_out(years: dict[str, list[int]]) -> list[dict]:
    fns = {"Barcelona": barcelona, "Paris": paris, "Santiago": santiago, "Hamburg": hamburg}
    out = []
    for city, ys in years.items():
        for y in ys:
            try:
                r = fns[city](y)
            except Exception as e:                   # one source down must not blank the others
                r = {"city": city, "year": y, "error": f"{type(e).__name__}: {e}"[:200]}
            if r:
                out.append(r)
    return out

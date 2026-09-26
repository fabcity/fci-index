"""Trash out: the waste half of PITO, per city, from the open sources filed in awesome-fabcity-data.

The measure proposed on awesome-fabcity-data#42 is residual municipal waste per capita: what is not
separately collected for recovery, so what goes to landfill, incineration, mechanical treatment or out of the
territory. Its companions are waste generated per capita and the recovery share. The recovery share is also
Boeing's input for macro-sector 16, "Waste and recycling", which he scored for Hamburg as a 24.8% recycling
share.

Every value says what it counts, because the four sources do not count the same thing:
  Barcelona  collected municipal waste; recovery = separate collection (not the same as recycled)
  Catalonia  the same, summed over every municipality: Environmental|Region's waste row
  Paris      household waste only; recovery = the sorted streams
  Santiago   declared municipal waste; recovery = tonnes whose declared treatment is "Valorizacion";
             per capita from INE's projections (a comuna, or the whole Region Metropolitana)
  Hamburg    municipal waste generated, total only: no split, so no residual and no recovery share
"""
from __future__ import annotations

import csv
import http.client
import io
import json
import sys
import time
import urllib.request
from pathlib import Path

UA = {"User-Agent": "fci-compute"}
SOCRATA = "https://analisi.transparenciacatalunya.cat/resource/69zu-w48s.json"
PARIS = ("https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/"
         "quantite-de-dechets-produits-et-tries-par-habitant-et-par-an/records?limit=100")
RETC = "https://datosretc.mma.gob.cl/api/3/action/package_show?id=generacion-municipal-de-residuos-no-peligrosos"
EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
# INE Chile, population estimates and projections 2002-2035 (base 2017) by comuna, sex, area and age group.
# Served with an .xlsx name but it is a ';'-separated Latin-1 CSV, 4.8 MB, from a server that runs at a few KB/s,
# so the pipeline reads a committed extract (per comuna and year) and extract_ine() rebuilds it from the source.
INE_URL = ("https://www.ine.gob.cl/docs/default-source/proyecciones-de-poblacion/cuadros-estadisticos/base-2017/"
           "estimaciones-y-proyecciones-2002-2035-comuna-y-%C3%A1rea-urbana-y-rural.xlsx")
INE_EXTRACT = Path(__file__).resolve().parent / "data" / "ine-chile-poblacion-comunas-2002-2035.csv"


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


def catalonia(year: int, get=_json) -> dict | None:
    """Environmental|Region's waste row: every Catalan municipality in 69zu-w48s, summed server-side.

    The dataset holds one row per municipality and no Catalonia total, so the sum double-counts nothing.
    The population sum is kept in the row, so a reader can check it against Catalonia's official figure.
    """
    q = ("$select=sum(suma_fracci_resta),sum(total_recollida_selectiva),sum(poblaci),count(*)"
         f"&$where=any='{year}'")
    r = get(f"{SOCRATA}?{q}")[0]
    if int(r.get("count", 0)) == 0:
        return None
    pop = float(r["sum_poblaci"])
    residual, separate = float(r["sum_suma_fracci_resta"]), float(r["sum_total_recollida_selectiva"])
    out = _row("Catalonia (region)", year, gen_t=residual + separate, pop=pop, residual_kg=residual * 1000 / pop,
               recovery=separate / (residual + separate),
               counts=f"sum of {r['count']} municipalities' collected municipal waste; recovery = separate collection",
               source="Generalitat de Catalunya 69zu-w48s, summed", licence="Llicència oberta d'ús d'informació – Catalunya")
    out["municipalities"] = int(r["count"])
    return out


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


def extract_ine(src: bytes, out: Path = INE_EXTRACT) -> int:
    """INE's file, summed over sex, area and age, to one row per comuna: code, name, region, 2002..2035."""
    rows = list(csv.DictReader(io.StringIO(src.decode("latin-1")), delimiter=";"))
    years = [c.split()[-1] for c in rows[0] if c.startswith("Poblacion ")]
    acc: dict[str, dict] = {}
    for r in rows:
        a = acc.setdefault(r["Comuna"], {"name": r["Nombre Comuna"], "region": r["Region"], **{y: 0 for y in years}})
        for y in years:
            a[y] += int(r[f"Poblacion {y}"])
    out.parent.mkdir(exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        f.write("# INE Chile, Estimaciones y proyecciones de poblacion 2002-2035 (base 2017), summed over sex, area\n"
                "# and age group per comuna. Source: " + INE_URL + "\n"
                "# Licence: CC BY-SA 4.0 (ine.gob.cl/terminos-de-uso-y-licencia-de-datos-abiertos). A figure derived\n"
                "# from it is shared under the same licence. Rebuild: python3 compute/waste.py --extract-ine\n")
        w = csv.writer(f)
        w.writerow(["comuna", "nombre", "region", *years])
        for code in sorted(acc, key=int):
            a = acc[code]
            w.writerow([code, a["name"], a["region"], *(a[y] for y in years)])
    return len(acc)


def population_cl(code: str, year: int, path: Path = INE_EXTRACT) -> int | None:
    """A comuna (5 digits, e.g. 13101) or a region (its 1-2 digit code, e.g. 13): INE's projection for 30 June."""
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if not l.startswith("#")]
    rows = list(csv.DictReader(lines))
    if str(year) not in rows[0]:
        return None
    hits = [r for r in rows if (r["comuna"] == code if len(code) == 5 else r["region"] == code)]
    return sum(int(r[str(year)]) for r in hits) or None


def santiago(year: int, get=_json, raw=_raw, code: str = "13101", pop=population_cl) -> dict | None:
    """Comuna Santiago (13101) by default; a 1-2 digit code is a whole region (13 = Region Metropolitana).
    Only the CSV years are read (2014-2022); 2023-24 are XLSX."""
    res = [x for x in get(RETC)["result"]["resources"]
           if x["name"].startswith(str(year)) and x.get("format", "").upper() == "CSV"]
    if not res:
        return None
    text = raw(res[0]["url"]).decode("utf-8-sig", errors="replace")
    region = len(code) < 5
    rows = [r for r in csv.DictReader(io.StringIO(text), delimiter=";" if text.count(";") > text.count(",") else ",")
            if (r.get("id_comuna", "")[:-3] == code if region else r.get("id_comuna") == code)]
    tonnes = lambda rs: sum(float(r["cantidad_toneladas"].replace(".", "").replace(",", ".")) for r in rs)
    total = tonnes(rows)
    # Rows with no treatment are "not recorded", never "not recovered": all of 2019, and 0.28 Mt of the Region
    # Metropolitana's 2022 rows (the same rows spell the region with non-breaking spaces, so filter by code).
    # Recovery and residual are therefore shares of the tonnes whose treatment IS recorded.
    recorded = [r for r in rows if r.get("tratamiento_nivel_1", "").strip()]
    known = tonnes(recorded)
    recovered = tonnes([r for r in recorded if r["tratamiento_nivel_1"].startswith("Valoriz")])
    stated = bool(recorded)
    people = pop(code, year)
    out = _row("Region Metropolitana (region)" if region and code == "13" else ("Santiago (comuna)" if code == "13101" else code),
               year, gen_t=total, pop=people,
               residual_kg=(known - recovered) * 1000 / people if people and stated else None,
               recovery=recovered / known if stated else None,
               counts="tonnes declared through SINADER by municipal generators, per INE's projected population; "
                      "recovery = declared treatment 'Valorizacion', residual = the rest of the tonnes whose "
                      "treatment is recorded; treatment_not_recorded_t is outside both" +
                      ("" if stated else " (treatment not recorded this year, so no residual or recovery)") +
                      ". Totals move with who declares (comuna Santiago: 209 kt in 2019, 116 kt in 2022).",
               source="RETC Chile, generacion-municipal-de-residuos-no-peligrosos; population INE Chile projections "
                      "(base 2017)",
               licence="RETC CC-BY + INE CC-BY-SA-4.0: the per-capita figure is shared under CC-BY-SA-4.0")
    out["treatment_not_recorded_t"] = round(total - known)
    return out


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
    fns = {"Barcelona": barcelona, "Catalonia": catalonia, "Paris": paris, "Santiago": santiago,
           "Region Metropolitana": lambda y: santiago(y, code="13"), "Hamburg": hamburg}
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


if __name__ == "__main__" and "--extract-ine" in sys.argv:
    src = Path(sys.argv[-1]).read_bytes() if sys.argv[-1].endswith((".csv", ".xlsx")) else _raw(INE_URL)
    print(f"wrote {INE_EXTRACT.name}: {extract_ine(src)} comunas")

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
  Hamburg    waste collected by the public collection, Statistikamt Nord Q II 9: residual = Haus- und Sperrmüll,
             recovery = separate collection
  National   Germany, Spain, France from Eurostat: generated, generated minus recycled, the official recycling
             rate, and waste exported and imported. The benchmark each city row names in `country`.
"""
from __future__ import annotations

import csv
import http.client
import io
import json
import sys
import time
import urllib.error
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
        except urllib.error.HTTPError as e:
            if e.code < 500 or n == tries - 1:   # a 404 is an answer (a file not published yet), not a hiccup
                raise
            time.sleep(5 * (n + 1))
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


def _xlsx_rows(data: bytes, sheet: str) -> list[list[str]]:
    """One worksheet's cell texts, by row and column letter order. Standard library only."""
    import re
    import xml.etree.ElementTree as ET
    import zipfile
    m = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    r_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    z = zipfile.ZipFile(io.BytesIO(data))
    shared = ([''.join(t.text or '' for t in si.iter(m + 't')) for si in ET.fromstring(z.read('xl/sharedStrings.xml'))]
              if 'xl/sharedStrings.xml' in z.namelist() else [])
    rels = {r.get('Id'): r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
    target = next(rels[s.get(r_ns + 'id')] for s in ET.fromstring(z.read('xl/workbook.xml')).iter(m + 'sheet')
                  if s.get('name') == sheet).lstrip('/')
    rows = []
    for row in ET.fromstring(z.read(target if target.startswith('xl/') else 'xl/' + target)).iter(m + 'row'):
        cells = {}
        for c in row.iter(m + 'c'):
            v, inline = c.find(m + 'v'), c.find(m + 'is')
            col = re.sub(r'\d', '', c.get('r'))
            if inline is not None:                     # t="inlineStr": the text sits in <is><t>, not in <v>
                cells[col] = ''.join(t.text or '' for t in inline.iter(m + 't'))
            elif v is not None:
                cells[col] = shared[int(v.text)] if c.get('t') == 's' else v.text
        rows.append(cells)
    return rows


def _num(cell: str | None) -> float | None:
    """A Statistikamt Nord number: '430.4166', or '413,6 r' with a decimal comma and a correction flag."""
    if cell is None:
        return None
    t = cell.strip().split(' ')[0].replace(',', '.')
    try:
        return float(t)
    except ValueError:
        return None                                    # '·' (secret), '–' (zero is written as a number), etc.


# Statistikamt Nord, Statistischer Bericht Q II 9 - j 24 HH, "Abfallentsorgung in Hamburg 2024, Teil 3: Einsammlung von
# Abfällen". Table T1_1 carries 2012-2024. The report's own notice permits extracts only; the same file is published on
# Hamburg's Transparenzportal under dl-de/by-2.0, which is the licence this reads it under (awesome-fabcity-data).
HAMBURG_Q2_9 = "https://www.statistik-nord.de/fileadmin/Dokumente/Q_II_9_j_24_HH.xlsx"


def hamburg(year: int, raw=_raw) -> dict | None:
    """Waste collected by Hamburg's public collection, with its split: Haus- und Sperrmüll (residual), separately
    collected organics and recyclables (Wertstoffe), electrical equipment, other."""
    row = next((r for r in _xlsx_rows(raw(HAMBURG_Q2_9), "T1_1") if (r.get("A") or "").strip() == str(year)), None)
    if row is None:
        return None
    total, per_head, residual = _num(row.get("B")), _num(row.get("C")), _num(row.get("D"))
    separate = [_num(row.get(k)) for k in ("E", "F", "G")]   # organics, recyclables, electrical equipment
    if None in (total, per_head, residual) or None in separate:
        return None
    pop = total * 1000 / per_head                         # the report's own population basis
    out = _row("Hamburg", year, gen_t=total, pop=pop, residual_kg=residual * 1000 / pop,
               recovery=sum(separate) / total,
               counts="waste collected by the public collection; residual = Haus- und Sperrmüll; recovery = separate "
                      "collection (organics, recyclables, electrical equipment), which is not recycling. Boeing's "
                      "24.8% for 2019 is a recycling share, a different measure.",
               source="Statistikamt Nord, Statistischer Bericht Q II 9 - j 24 HH, table T1_1",
               licence="dl-de/by-2.0 (Hamburg Transparenzportal)")
    out["population"] = round(pop)
    return out


def _pos(d: dict, **fixed) -> int | None:
    """Where a cell sits in a JSON-stat response: fixed dimensions by code, every other dimension a single member.
    JSON-stat allows a category index and the values as an object or an array: Eurostat sends objects, Idescat arrays."""
    pos = 0
    for dim, size in zip(d["id"], d["size"]):
        index = d["dimension"][dim]["category"]["index"]
        if isinstance(index, list):
            index = {c: i for i, c in enumerate(index)}
        if dim in fixed:
            if fixed[dim] not in index:
                return None
            pos = pos * size + index[fixed[dim]]
        elif size == 1:
            pos = pos * size
        else:
            raise ValueError(f"dimension {dim} has {size} members and was not fixed")
    return pos


def _at(block, pos: int):
    """The entry at pos in a JSON-stat value or status block, which may be an object, an array or one shared string."""
    if isinstance(block, dict):
        return block.get(str(pos))
    if isinstance(block, list):
        return block[pos] if pos < len(block) else None
    return block


def _pick(d: dict, **fixed) -> float | None:
    """One value from a JSON-stat response."""
    pos = _pos(d, **fixed)
    return None if pos is None else _at(d["value"], pos)


def _status(d: dict, **fixed) -> str | None:
    """The status flag of that value ('p' provisional at Idescat), or None."""
    pos = _pos(d, **fixed)
    return None if pos is None else _at(d.get("status"), pos)


COUNTRY = {"DE": "Germany", "ES": "Spain", "FR": "France"}


def national(country: str, year: int, get=_json) -> dict | None:
    """The national benchmark, from Eurostat's own tables (awesome-fabcity-data#46): municipal waste generated and
    recycled per capita (env_wasmun), the official recycling rate (cei_wm011) and waste traded across the border
    (env_wastrdmp, which answers only to filtered queries)."""
    base = f"{EUROSTAT}{{}}?format=JSON&lang=EN&geo={country}&time={year}"
    mun = get(base.format("env_wasmun") + "&unit=KG_HAB&wst_oper=GEN&wst_oper=RCY")
    gen, rcy = _pick(mun, wst_oper="GEN"), _pick(mun, wst_oper="RCY")
    if gen is None:
        return None
    rate = _pick(get(base.format("cei_wm011")))
    trade = get(base.format("env_wastrdmp") + "&rawmat=TOTAL&unit=T&partner=INT_EU27_2020&partner=EXT_EU27_2020")
    flow = {f: [_pick(trade, stk_flow=f, partner=p) for p in ("INT_EU27_2020", "EXT_EU27_2020")] for f in ("EXP", "IMP")}
    tonnes = {f: sum(v) if None not in v else None for f, v in flow.items()}
    out = _row(f"{COUNTRY[country]} (national)", year, gen_kg=gen,
               residual_kg=gen - rcy if rcy is not None else None,
               recovery=rate / 100 if rate is not None else None,
               counts="national municipal waste, kg per inhabitant; residual here = generated minus recycled "
                      "(material recycling, composting and digestion), recovery = Eurostat's official recycling rate. "
                      "The city rows count separate collection, which is not recycling, so the two are not the same "
                      "measure.",
               source="Eurostat env_wasmun, cei_wm011, env_wastrdmp",
               licence="Eurostat reuse policy, 2011/833/EU")
    out["waste_exported_t"], out["waste_imported_t"] = tonnes["EXP"], tonnes["IMP"]
    out["net_waste_export_t"] = (tonnes["EXP"] - tonnes["IMP"]
                                 if None not in (tonnes["EXP"], tonnes["IMP"]) else None)
    return out


CITY_COUNTRY = {"Barcelona": "ES", "Catalonia": "ES", "Paris": "FR", "Hamburg": "DE",
                "Santiago": "CL", "Region Metropolitana": "CL"}


def trash_out(years: dict[str, list[int]]) -> list[dict]:
    fns = {"Barcelona": barcelona, "Catalonia": catalonia, "Paris": paris, "Santiago": santiago,
           "Region Metropolitana": lambda y: santiago(y, code="13"), "Hamburg": hamburg,
           **{name: (lambda y, c=code: national(c, y)) for code, name in COUNTRY.items()}}
    out = []
    for city, ys in years.items():
        for y in ys:
            try:
                r = fns[city](y)
            except Exception as e:                   # one source down must not blank the others
                r = {"city": city, "year": y, "error": f"{type(e).__name__}: {e}"[:200]}
            if r:
                if city in CITY_COUNTRY:                 # so a city row can be read against its country's
                    r["country"] = CITY_COUNTRY[city]
                out.append(r)
    return out


if __name__ == "__main__" and "--extract-ine" in sys.argv:
    src = Path(sys.argv[-1]).read_bytes() if sys.argv[-1].endswith((".csv", ".xlsx")) else _raw(INE_URL)
    print(f"wrote {INE_EXTRACT.name}: {extract_ine(src)} comunas")

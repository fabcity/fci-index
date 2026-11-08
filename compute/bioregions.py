#!/usr/bin/env python3
"""The ecoregion and the river basin every place and country sits in, and the two map layers that show them.

    python3 compute/bioregions.py --selftest            # no network, no duckdb: slimming and ranking on toy shapes
    python3 compute/bioregions.py ../fci-3-prototype    # fetch both sources (~190 MB, cached), write the layers and
                                                        # compute/results/bioregions.json

The only compute script that is not standard-library Python: polygon clipping and simplification need DuckDB with its
spatial extension (pip install duckdb; 1.5 or later for ST_CoverageSimplify).

Ecoregions: RESOLVE Ecoregions 2017 (Dinerstein et al. 2017, BioScience 67(6): 534-545), 846 terrestrial ecoregions in
14 biomes and 8 realms, CC-BY 4.0 (every record carries LICENSE "CC-BY 4.0"). Registry: environmental/bioregion/
resolve-ecoregions-2017.

Bioregions: river basins at HydroBASINS level 4 (Lehner & Grill 2013), 1,342 basins. The registry already names
HydroBASINS as the Index's bioregion boundary (environmental/bioregion/hydrosheds-hydrobasins). The same polygons are
published in HydroATLAS/BasinATLAS v1.0 (Linke et al. 2019, Scientific Data 6: 283) under CC-BY 4.0, and that is the
licence this layer is shown under. HydroBASINS' own download carries the HydroSHEDS v1 licence agreement, which forbids
distributing the data "as a stand-alone product"; the files are fetched from there only because BasinATLAS's figshare
copy (several GB) does not serve scripted downloads. One Earth's 185 bioregions would be the obvious other choice and are
CC BY-NC 4.0, behind a request form, so not used.

Neither layer is a measurement. An ecoregion is the vegetation a place would carry without people, drawn at continental
scale in 2017; its "Nature Needs Half" category is from forest loss to 2015 and protected areas in 2016. A basin has no
name, only its Pfafstetter code, so it is described by the ecoregions it spans and the places inside it.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = Path(os.environ.get("BIOREGIONS_CACHE") or HERE / ".cache" / "bioregions")
ECO_URL = "https://storage.googleapis.com/teow2016/Ecoregions2017.zip"
HB_URL = "https://data.hydrosheds.org/file/HydroBASINS/standard/hybas_{}_lev04_v1c.zip"
HB_REGIONS = ("af", "ar", "as", "au", "eu", "gr", "na", "sa", "si")
TOL = 0.05        # degrees, about 5 km: the drawn layers, simplified as one coverage so shared borders stay shared
MIN_AREA = 0.02   # square degrees, about 250 km2 at the equator: smaller islands and holes leave the drawn layers
DP = 2            # decimals in the drawn layers, about 1 km
SHARE_TOL = 0.01  # degrees: the shapes the shares are computed on
NEAREST = 0.25    # degrees: a centre that falls in the sea takes the nearest shape within this, and says so
ECO_LICENCE = ("RESOLVE Ecoregions 2017, Dinerstein et al. (2017) BioScience 67(6): 534-545, doi:10.1093/biosci/bix014. "
               "CC-BY 4.0. Simplified for the web by the Fab City Index.")
HB_LICENCE = ("River basins at HydroBASINS level 4 (Lehner & Grill 2013, Hydrological Processes 27(15): 2171-2186), as published "
              "in HydroATLAS/BasinATLAS v1.0 (Linke et al. 2019, Scientific Data 6: 283) under CC-BY 4.0. Simplified for the web "
              "by the Fab City Index. Data available at www.hydrosheds.org.")


def ring_area(r: list) -> float:
    """Planar area of a closed ring, in square degrees (the shoelace formula)."""
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(r, r[1:]))) / 2


def slim(polys: list, min_area: float = MIN_AREA, dp: int = DP) -> dict | None:
    """A feature's polygons for the web: parts and holes under min_area go, coordinates rounded to dp, repeats dropped.
    A feature made only of small parts keeps its largest, so no ecoregion or basin disappears from the map."""
    polys = [p for p in polys if p and len(p[0]) >= 4]
    if not polys:
        return None
    keep = [p for p in polys if ring_area(p[0]) >= min_area] or [max(polys, key=lambda p: ring_area(p[0]))]
    out = []
    for p in keep:
        rings = []
        for i, r in enumerate(p):
            if i and ring_area(r) < min_area:
                continue
            rr = []
            for x, y in r:
                q = [round(x, dp), round(y, dp)]
                if not rr or rr[-1] != q:
                    rr.append(q)
            if len(rr) >= 4:
                rings.append(rr)
        if rings:
            out.append(rings)
    return {"type": "MultiPolygon", "coordinates": out} if out else None


def ranked(rows: list, floor: float = 0.01) -> dict:
    """(owner, item, area) rows -> {owner: [(item, share), ...]}, largest first, shares of the owner's own total, items
    under the floor left out. The total is the sum of the rows, so a country's sea or an unmapped edge is not counted."""
    tot, by = defaultdict(float), defaultdict(list)
    for owner, item, area in rows:
        tot[owner] += area
        by[owner].append((item, area))
    return {o: [(i, round(a / tot[o], 3)) for i, a in sorted(v, key=lambda x: -x[1]) if tot[o] and a / tot[o] >= floor]
            for o, v in by.items()}


def fetch(url: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    dest = CACHE / url.rsplit("/", 1)[1]
    if not dest.exists():
        print(f"fetching {url}")
        tmp = dest.with_suffix(".part")
        urllib.request.urlretrieve(url, tmp)
        tmp.rename(dest)
    return dest


def unzip(z: Path) -> Path:
    d = z.with_suffix("")
    if not d.exists():
        zipfile.ZipFile(z).extractall(d)
    return d


def layer(c, table: str, props) -> dict:
    """The table as one simplified coverage, slimmed per feature, as a GeoJSON FeatureCollection."""
    rows = c.sql(f"""WITH s AS (SELECT list(id ORDER BY id) ids, ST_CoverageSimplify(list(geom ORDER BY id), {TOL}::DOUBLE) g FROM {table}),
                     d AS (SELECT ids, unnest(ST_Dump(g)) AS u FROM s)
                     SELECT ids[u.path[1]], ST_AsGeoJSON(u.geom) FROM d""").fetchall()
    parts = defaultdict(list)
    for i, g in rows:
        gj = json.loads(g)
        parts[i].extend(gj["coordinates"] if gj["type"] == "MultiPolygon" else [gj["coordinates"]] if gj["type"] == "Polygon" else [])
    feats = []
    for i in sorted(parts):
        geom = slim(parts[i])
        if geom:
            feats.append({"type": "Feature", "properties": props(i), "geometry": geom})
    return {"type": "FeatureCollection", "features": feats}


def run(site: Path) -> int:
    import duckdb
    eco_dir = unzip(fetch(ECO_URL))
    hb = [next(unzip(fetch(HB_URL.format(r))).glob("*.shp")) for r in HB_REGIONS]
    c = duckdb.connect()
    c.sql("INSTALL spatial; LOAD spatial")
    c.sql(f"""CREATE TABLE eco AS SELECT ECO_ID::INT AS id, ECO_NAME AS nm, BIOME_NAME AS biome, REALM AS realm, NNH_NAME AS nnh,
              COLOR AS col, ST_MakeValid(geom) AS geom FROM ST_Read('{next(eco_dir.glob("*.shp"))}') WHERE ECO_ID > 0""")
    c.sql("CREATE TABLE hb AS " + " UNION ALL ".join(
        f"SELECT HYBAS_ID::BIGINT AS id, PFAF_ID::INT AS pfaf, SUB_AREA AS area, ST_MakeValid(geom) AS geom FROM ST_Read('{f}')" for f in hb))
    c.sql(f"CREATE TABLE eco_s AS SELECT id, ST_MakeValid(ST_SimplifyPreserveTopology(geom, {SHARE_TOL})) AS geom FROM eco")
    c.sql(f"CREATE TABLE hb_s AS SELECT id, ST_MakeValid(ST_SimplifyPreserveTopology(geom, {SHARE_TOL})) AS geom FROM hb")
    eco = {r[0]: dict(zip(("id", "name", "biome", "realm", "nnh", "color"), r)) for r in c.sql("SELECT id, nm, biome, realm, nnh, col FROM eco").fetchall()}
    hbs = {r[0]: {"id": r[0], "pfaf": r[1], "area_km2": round(r[2])} for r in c.sql("SELECT id, pfaf, area FROM hb").fetchall()}
    area = "ST_Area_Spheroid(ST_FlipCoordinates({}))"   # DuckDB's spheroid functions read lat/lon order

    # Every place's centre, on the full-resolution shapes
    coords = json.loads((site / "data" / "coordinates.json").read_text())["coordinates"]
    c.sql("CREATE TABLE pt (slug VARCHAR, geom GEOMETRY)")
    c.executemany("INSERT INTO pt VALUES (?, ST_Point(?, ?))", [(s, lng, lat) for s, (lat, lng) in coords.items()])

    def locate(table: str) -> dict:
        found = dict(c.sql(f"SELECT pt.slug, t.id FROM pt JOIN {table} t ON ST_Contains(t.geom, pt.geom)").fetchall())
        near = c.sql(f"""SELECT slug, id, km FROM (SELECT pt.slug, t.id,
                           ST_Distance_Spheroid(ST_FlipCoordinates(pt.geom)::POINT_2D, ST_FlipCoordinates(ST_ClosestPoint(t.geom, pt.geom))::POINT_2D) / 1000 AS km,
                           row_number() OVER (PARTITION BY pt.slug ORDER BY ST_Distance(t.geom, pt.geom)) AS k
                         FROM pt JOIN {table} t ON ST_DWithin(t.geom, pt.geom, {NEAREST}) WHERE pt.slug NOT IN (SELECT unnest(?::VARCHAR[])))
                         WHERE k = 1""", params=[list(found)]).fetchall()
        out = {s: (i, "inside") for s, i in found.items()}
        out.update({s: (i, f"nearest, {km:.0f} km away") for s, i, km in near})
        return out

    eco_at, hb_at = locate("eco"), locate("hb")
    places = {}
    for s in sorted(coords):
        e, b = eco_at.get(s), hb_at.get(s)
        places[s] = {"ecoregion": {**{k: v for k, v in eco[e[0]].items() if k != "color"}, "how": e[1]} if e else None,
                     "basin": {**hbs[b[0]], "how": b[1]} if b else None}

    # Countries: the share of each country's land in each ecoregion and basin, on the site's own outlines
    c.sql(f"CREATE TABLE ctry AS SELECT iso, ST_MakeValid(geom) AS geom FROM ST_Read('{site / 'data' / 'countries.geojson'}')")
    share = lambda t: ranked(c.sql(f"""SELECT k.iso, t.id, {area.format('ST_Intersection(k.geom, t.geom)')} FROM ctry k
                                       JOIN {t} t ON ST_Intersects(k.geom, t.geom)""").fetchall())
    ce, cb = share("eco_s"), share("hb_s")
    countries = {iso: {"ecoregions": [{"id": i, "name": eco[i]["name"], "biome": eco[i]["biome"], "realm": eco[i]["realm"], "share": sh} for i, sh in ce.get(iso, [])],
                       "basins": [{"id": i, "pfaf": hbs[i]["pfaf"], "area_km2": hbs[i]["area_km2"], "share": sh} for i, sh in cb.get(iso, [])]}
                 for iso in sorted(set(ce) | set(cb))}

    # Basins: the ecoregions each one spans, which is how a basin with no name is described
    be = ranked(c.sql(f"SELECT b.id, e.id, {area.format('ST_Intersection(b.geom, e.geom)')} FROM hb_s b JOIN eco_s e ON ST_Intersects(b.geom, e.geom)").fetchall(), 0.05)
    in_basin = defaultdict(list)
    for s, p in places.items():
        if p["basin"]:
            in_basin[p["basin"]["id"]].append(s)

    eco_geo = layer(c, "eco", lambda i: {"id": i, "n": eco[i]["name"], "b": eco[i]["biome"], "r": eco[i]["realm"], "h": eco[i]["nnh"], "c": eco[i]["color"]})
    hb_geo = layer(c, "hb", lambda i: {"id": i, "p": hbs[i]["pfaf"], "a": hbs[i]["area_km2"],
                                       "e": [[eco[e]["name"], round(sh * 100)] for e, sh in be.get(i, [])[:3]], "fc": in_basin.get(i, [])})
    eco_geo["licence"], hb_geo["licence"] = ECO_LICENCE, HB_LICENCE
    for name, geo in (("ecoregions.geojson", eco_geo), ("basins.geojson", hb_geo)):
        (site / "data" / name).write_text(json.dumps(geo, ensure_ascii=False, separators=(",", ":")) + "\n")
        print(f"{name}: {len(geo['features'])} features, {(site / 'data' / name).stat().st_size // 1024} KB")

    out = {"reads_as": "The terrestrial ecoregion and the river basin (HydroBASINS level 4) each place's published centre sits in, "
                       "and the ecoregions and basins each country's land falls in. Context for a place, never a cell or a score.",
           "does_not_claim": "An ecoregion is the vegetation a place would carry without people, at continental scale; a city inside "
                             "a forest ecoregion is not a forest. Its Nature Needs Half category is from forest loss to 2015 and "
                             "protected areas in 2016. Country shares are on Natural Earth 1:110m outlines, so small islands and "
                             "coasts are rough. A centre that falls in the sea takes the nearest shape and says so.",
           "licence": {"ecoregions": ECO_LICENCE, "basins": HB_LICENCE},
           "sources": {"ecoregions": ECO_URL, "basins": HB_URL.format("<region>")},
           "places": places, "countries": countries}
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "bioregions.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    missing = [s for s, p in places.items() if not p["ecoregion"] or not p["basin"]]
    print(f"bioregions.json: {len(places)} places ({len(missing)} without a shape: {', '.join(missing) or 'none'}), {len(countries)} countries")
    return 0


def selftest() -> int:
    bad = 0

    def check(label, got, want):
        nonlocal bad
        ok = got == want
        bad += not ok
        print(f"  {'ok ' if ok else 'BAD'} {label}" + ("" if ok else f": got {got!r}, want {want!r}"))

    sq = lambda x, y, s: [[x, y], [x + s, y], [x + s, y + s], [x, y + s], [x, y]]
    check("the shoelace area of a 2 x 2 square", ring_area(sq(0, 0, 2)), 4.0)
    g = slim([[sq(0, 0, 1)], [sq(5, 5, 0.1)]], min_area=0.02)
    check("an islet under the floor leaves the drawn layer", len(g["coordinates"]), 1)
    g = slim([[sq(0, 0, 0.1)], [sq(5, 5, 0.12)]], min_area=0.02)
    check("a feature made only of islets keeps its largest, so it stays on the map", g["coordinates"][0][0][0], [5, 5])
    g = slim([[sq(0, 0, 4), sq(1, 1, 0.1), sq(2, 2, 1)]], min_area=0.02)
    check("a small hole is filled, a large one kept", len(g["coordinates"][0]), 2)
    g = slim([[[[0.001, 0.001], [1.004, 0.002], [1.0, 1.0], [0.0, 1.0], [0.004, 0.004]]]], min_area=0.02, dp=2)
    check("coordinates rounded, and a point that rounds onto the one before is dropped", g["coordinates"][0][0], [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]])
    check("a feature with no usable ring is None", slim([[[[0, 0], [1, 1]]]]), None)
    r = ranked([("ESP", 7, 60.0), ("ESP", 3, 39.5), ("ESP", 9, 0.5), ("IDN", 1, 2.0)])
    check("shares of the owner's own total, largest first, under 1 % left out", r["ESP"], [(7, 0.6), (3, 0.395)])
    check("one item is the whole", r["IDN"], [(1, 1.0)])
    print(f"\nbioregions selftest: {bad} failed.")
    return 1 if bad else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if len(sys.argv) < 2:
        sys.exit("usage: python3 compute/bioregions.py <site source dir, e.g. ../fci-3-prototype> | --selftest")
    sys.exit(run(Path(sys.argv[1]).resolve()))

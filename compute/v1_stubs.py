#!/usr/bin/env python3
"""Stubs for the two indicators proposed for Method v1, in review. Not adapters: nothing here fetches on a
schedule, writes to results/, or reaches api.mjs, and nothing will until reviewers accept the proposal.

    python3 compute/v1_stubs.py --selftest     # no network

    capacity_ownership_share  of the machines mapped in a place, the share owned by local public bodies,
                              cooperatives, residents or locally held firms
    local_model_share         of the design and production nodes a place reports, the share whose inference
                              runs on local hardware or on open weights the node can inspect and retrain

Every reader FAILS CLOSED. With no data an indicator is {"state": "unmeasured", "value": None, "why": ...}.
It is never 0 by default. The score (fci-score.js, v1) then counts it 0 inside its cells, as v0 counts a
cell with no source, but the API and the pages keep saying "unmeasured", so a reader can tell a place that
reported nothing from one that reported none.

Three readers:

fablabs_per_place   labs per place from the fablabs.io directory. Read from the Fab Lab network data archive
                    through labs.py (a dated, pinnable freeze), not api.fablabs.io/0/labs.json: the live
                    endpoint says the legacy API "has now been removed" and still answers, and a score has
                    to be repeatable. The fablabs.io records have NO owner or organisation-type field, so
                    `ownership` is always None here and waits for a node_report. The records are not openly
                    licensed (registry economic/community/fablabs-io): Tomas Diez's 14 Oct decision covers
                    showing the directory on the map, and using a count in a score is a new use for the
                    reviewers to rule on.
okw_per_place       entries per place from Open Know-Where as Maps of Making and OHM serve it, with any
                    ownership or organisation-type field that is present. Read 7 Nov 2026: OHM's okw/spaces
                    has `access_type` null in all 3,194 records, and Maps of Making has no such field (its
                    `capacity` is 0 in all of them). 2,412 of the records are harvested fablabs.io records.
node_report         what a lab or a city reports per node, against node-report.schema.json in the registry.
                    This is the only reader that can produce either indicator.
"""
from __future__ import annotations

import datetime as dt
import sys

LOCAL_OWNERS = {"local_public", "cooperative", "resident", "local_firm"}
OWNERS = LOCAL_OWNERS | {"outside_firm", "outside_public", "unknown"}
LOCAL_RUNTIMES = {"local_hardware", "open_weights_local"}
RUNTIMES = LOCAL_RUNTIMES | {"closed_api", "none"}
OWNERSHIP_KEYS = ("owner_type", "ownership", "organisation_type", "organization_type", "access_type", "owner")


def unmeasured(why: str) -> dict:
    return {"state": "unmeasured", "value": None, "why": why}


def _same_place(city: str | None, place: dict) -> bool:
    # ponytail: name match only. It misses metro areas and every region-sized place (Bali, Catalonia); the
    # upgrade is a point-in-polygon on the place's boundary, or a radius from fci-3-prototype/data/coordinates.json.
    return bool(city) and city.strip().casefold() == place["name"].strip().casefold()


def fablabs_per_place(labs: list[dict], places: list[dict]) -> dict:
    """labs: labs.trim() output (facts only). places: [{slug, name}]. A count, never an ownership share."""
    out = {}
    for p in places:
        mine = [x for x in labs if _same_place(x.get("city"), p)]
        out[p["slug"]] = {"labs": len(mine), "active": sum(1 for x in mine if x.get("status") == "active"),
                          "ownership": None,
                          "ownership_why": "fablabs.io records carry no owner or organisation type; it waits for a node_report"}
    return out


def okw_per_place(spaces: list[dict], places: list[dict]) -> dict:
    """spaces: OHM okw/spaces rows, or Maps of Making feature properties. Passes through an ownership field only
    where one is present and filled; the share stays unmeasured until every counted space has one."""
    out = {}
    for p in places:
        mine = [s for s in spaces if _same_place(s.get("city"), p)]
        typed = [next(s[k] for k in OWNERSHIP_KEYS if s.get(k)) for s in mine if any(s.get(k) for k in OWNERSHIP_KEYS)]
        out[p["slug"]] = {"entries": len(mine), "with_ownership_field": len(typed), "ownership_values": sorted(set(typed)),
                          "capacity_ownership_share": unmeasured(
                              "no entry here says who owns it" if mine and not typed else
                              "some entries here do not say who owns them" if mine and len(typed) < len(mine) else
                              "no entries matched this place" if not mine else
                              "an ownership field is present, but mapping its values to the owner types is for the reviewers")}
    return out


def check_report(r: dict) -> list[str]:
    """Why a report cannot be counted, or [] if it can. The trust boundary: reports come from outside."""
    why = []
    if not isinstance(r.get("place"), str) or not r["place"]:
        why.append("no place")
    nodes = r.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return why + ["no nodes"]
    for i, n in enumerate(nodes):
        at = f"node {i}"
        if not isinstance(n, dict) or not isinstance(n.get("id"), str) or not n.get("id"):
            why.append(f"{at}: no id")
            continue
        at = f"node {n['id']}"
        if not isinstance(n.get("machines"), int) or isinstance(n.get("machines"), bool) or n["machines"] < 0:
            why.append(f"{at}: machines must be a whole number, 0 or more")
        if n.get("owner_type") not in OWNERS:
            why.append(f"{at}: owner_type must be one of {sorted(OWNERS)}")
        if n.get("model_runtime") not in RUNTIMES:
            why.append(f"{at}: model_runtime must be one of {sorted(RUNTIMES)}")
        try:
            if dt.date.fromisoformat(str(n.get("date"))) > dt.date.today():
                why.append(f"{at}: date is in the future")
        except ValueError:
            why.append(f"{at}: date must be YYYY-MM-DD")
    return why


def shares(reports: list[dict], place: str) -> dict:
    """Both indicators for one place from its reports. The latest report of each node counts; a report that fails
    check_report counts for nothing. `year` is the OLDEST counted node's, so the age discount bites on the stalest
    part of the answer: old data can lower a share's weight, never raise it."""
    latest, rejected = {}, []
    for r in reports:
        if r.get("place") != place:
            continue
        bad = check_report(r)
        if bad:
            rejected.append(bad)
            continue
        for n in r["nodes"]:
            if n["id"] not in latest or n["date"] > latest[n["id"]]["date"]:
                latest[n["id"]] = n
    nodes = list(latest.values())
    out = {"nodes_reported": len(nodes), "reports_rejected": rejected}

    owned = [n for n in nodes if n["owner_type"] != "unknown" and n["machines"] > 0]
    machines = sum(n["machines"] for n in owned)
    out["machines_owner_unknown"] = sum(n["machines"] for n in nodes if n["owner_type"] == "unknown")
    out["capacity_ownership_share"] = (
        {"state": "measured", "value": round(sum(n["machines"] for n in owned if n["owner_type"] in LOCAL_OWNERS) / machines, 3),
         "year": int(min(str(n["date"]) for n in owned)[:4]), "machines": machines}
        if machines else unmeasured("no node here reports machines with a known owner"))

    running = [n for n in nodes if n["model_runtime"] != "none"]
    out["local_model_share"] = (
        {"state": "measured", "value": round(sum(1 for n in running if n["model_runtime"] in LOCAL_RUNTIMES) / len(running), 3),
         "year": int(min(str(n["date"]) for n in running)[:4]), "nodes": len(running)}
        if running else unmeasured("no node here reports running a model"))
    return out


def selftest() -> int:
    bad = 0

    def check(label, got, want):
        nonlocal bad
        ok = got == want
        bad += not ok
        print(f"  {'ok ' if ok else 'BAD'} {label}" + ("" if ok else f": got {got!r}, want {want!r}"))

    places = [{"slug": "nantes", "name": "Nantes"}, {"slug": "bali", "name": "Bali"}]
    labs = [{"slug": "ping", "city": "Nantes", "status": "not stated"}, {"slug": "b", "city": " nantes ", "status": "active"}]
    f = fablabs_per_place(labs, places)
    check("labs counted per place by city name", (f["nantes"]["labs"], f["nantes"]["active"], f["bali"]["labs"]), (2, 1, 0))
    check("fablabs.io never yields an ownership", f["nantes"]["ownership"], None)

    spaces = [{"city": "Nantes", "access_type": None}, {"city": "Nantes", "ownership": "cooperative"}]
    o = okw_per_place(spaces, places)
    check("OKW passes through an ownership field where one is filled", o["nantes"]["ownership_values"], ["cooperative"])
    check("OKW with half its entries untyped stays unmeasured", o["nantes"]["capacity_ownership_share"]["state"], "unmeasured")
    check("no OKW entries is unmeasured, not 0", o["bali"]["capacity_ownership_share"]["value"], None)

    check("no reports: both unmeasured, never 0", [shares([], "bali")[k]["state"] for k in ("capacity_ownership_share", "local_model_share")],
          ["unmeasured", "unmeasured"])
    node = lambda i, m, o, r, d: {"id": i, "machines": m, "owner_type": o, "model_runtime": r, "date": d}
    reps = [
        {"place": "bali", "nodes": [node("lab-a", 6, "cooperative", "local_hardware", "2024-03-01"),
                                    node("lab-b", 2, "outside_firm", "closed_api", "2026-06-01"),
                                    node("shed", 3, "unknown", "none", "2026-06-01")]},
        {"place": "bali", "nodes": [node("lab-a", 4, "cooperative", "open_weights_local", "2026-09-01")]},   # replaces lab-a's 2024 row
        {"place": "bali", "nodes": [node("lab-x", 9, "resident", "teleport", "2026-01-01")]},                # rejected, counts nothing
        {"place": "other", "nodes": [node("lab-z", 9, "resident", "local_hardware", "2026-01-01")]},
    ]
    s = shares(reps, "bali")
    check("ownership share: local machines over machines with a known owner", s["capacity_ownership_share"]["value"], round(4 / 6, 3))
    check("unknown owners are counted apart, not as outside", s["machines_owner_unknown"], 3)
    check("model share: local runtimes over nodes running a model", s["local_model_share"]["value"], 0.5)
    check("a node's latest report wins, and year is the oldest counted node's", s["capacity_ownership_share"]["year"], 2026)
    check("a malformed report is rejected with its reason", s["reports_rejected"], [[f"node lab-x: model_runtime must be one of {sorted(RUNTIMES)}"]])
    check("a future date is rejected", check_report({"place": "bali", "nodes": [node("n", 1, "resident", "none", "2999-01-01")]}),
          ["node n: date is in the future"])
    check("a boolean is not a machine count", bool(check_report({"place": "bali", "nodes": [node("n", True, "resident", "none", "2026-01-01")]})), True)
    print(f"\nv1 stubs selftest: {bad} failed.")
    return 1 if bad else 0


if __name__ == "__main__":
    if "--selftest" not in sys.argv:
        print("stubs only: run with --selftest. Nothing here reads a live source until v1 is accepted.")
        sys.exit(2)
    sys.exit(selftest())

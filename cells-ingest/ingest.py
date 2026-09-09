#!/usr/bin/env python3
"""
cells-ingest — the cable between a PLANETAI node and the FCI spine.

    GET  <node>/cells                  →  fci-cells-v0 rows
    POST/PATCH  Airtable Observations  →  what index.fab.city/api/cells/<city>.json serves

`cells-worker` READS the spine. This FILLS it. Both sides already agree on the same
eight fields — city, cell, value, unit, source, observed_at, state, notes — because
planetai-node's app/index.py::_row() emits exactly the Airtable column set documented
in ../cells-worker/README.md. So this is a transport, not a translator. Keep it that
way: if you catch yourself renaming a field in here, fix the schema instead.

TIER RULE (planetai-node ARCHITECTURE.md §2)
    Only the node that is the designated Index publisher for a pilot runs this.
    Individual (home / business) nodes feed their parent via push_aggregates() and
    never write to the spine. Set FCI_PUBLISHER=1 on exactly one node per pilot city.
    Without it this script refuses to run, so a home node cannot start publishing by
    accident just because someone copied a .env.

PROVENANCE RULE (planetai-node app/index.py)
    State is never upgraded here. A portal or a model is 'partial' whatever its
    quality; only the node gets to say 'live'. This script will downgrade a bad state
    to 'mock' and will never promote one.

WHY UPSERT AND NOT APPEND
    cells-worker keeps the newest row per cell key, so appending would work and would
    also grow the table forever and make it unreadable by a human. One row per
    (city, cell), patched in place, keeps the spine the size of the matrix.

Usage
    export FCI_AIRTABLE_TOKEN=pat...     # scope: data.records:read + data.records:write, this base only
    export FCI_NODE_URL=http://localhost:8080
    export FCI_CITY=bali
    export FCI_PUBLISHER=1
    python3 ingest.py --dry-run          # prints the diff, writes nothing
    python3 ingest.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE_ID = "appmNQaDGEFE9VcYh"          # FCI Observations — same base cells-worker reads
TABLE = "Observations"
API = "https://api.airtable.com/v0"

# cells-worker/worker.js hardcodes this list; a city outside it 404s on the read side,
# so writing one here would be invisible. Keep the two in step.
ALLOWED_CITIES = ["barcelona", "boston", "santiago", "bali"]

VALID_STATES = {"live", "partial", "mock"}
PILLARS = ("Environmental", "Social", "Economic", "Governance")
SCALES = ("Community", "City", "Region", "Bioregion", "Planet")
VALID_CELLS = {f"{p}|{s}" for p in PILLARS for s in SCALES}


def _get(url: str, token: str | None = None) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def _send(url: str, token: str, payload: dict, method: str) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def fetch_cells(node_url: str) -> list[dict]:
    """The node's own honest answer about what it can compute. We do not second-guess it."""
    doc = _get(node_url.rstrip("/") + "/cells")
    return doc if isinstance(doc, list) else doc.get("cells", [])


def existing_rows(token: str, city: str) -> dict[str, str]:
    """cell key -> record id, for rows already in the spine for this city."""
    out, offset = {}, None
    formula = urllib.parse.quote(f"LOWER({{city}})='{city}'")
    while True:
        url = f"{API}/{BASE_ID}/{urllib.parse.quote(TABLE)}?pageSize=100&filterByFormula={formula}"
        if offset:
            url += f"&offset={offset}"
        data = _get(url, token)
        for rec in data.get("records", []):
            key = (rec.get("fields") or {}).get("cell")
            if key:
                out.setdefault(key, rec["id"])
        offset = data.get("offset")
        if not offset:
            return out


def normalise(row: dict, city: str) -> dict | None:
    """Map one node cell to one Airtable row. Rejects anything that would dirty the spine."""
    cell = (row.get("cell") or "").strip()
    if cell not in VALID_CELLS:
        print(f"  skip: '{cell}' is not one of the 20 Pillar|Scale keys", file=sys.stderr)
        return None
    if row.get("value") is None:
        print(f"  skip: {cell} has no value", file=sys.stderr)
        return None
    state = (row.get("state") or "mock").lower()
    if state not in VALID_STATES:
        print(f"  warn: {cell} state '{state}' unknown, recording as mock", file=sys.stderr)
        state = "mock"
    return {
        "city": city,
        "cell": cell,
        "value": float(row["value"]),
        "unit": row.get("unit") or "",
        "source": row.get("source") or "planetai-node",
        "observed_at": row.get("observed_at") or datetime.now(timezone.utc).isoformat(),
        "state": state,
        "notes": row.get("notes") or "",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="print what would be written, write nothing")
    ap.add_argument("--city", default=os.getenv("FCI_CITY", ""))
    ap.add_argument("--node", default=os.getenv("FCI_NODE_URL", "http://localhost:8080"))
    a = ap.parse_args()

    city = a.city.strip().lower()
    if city not in ALLOWED_CITIES:
        print(f"city must be one of {ALLOWED_CITIES} — cells-worker will not serve anything else", file=sys.stderr)
        return 2
    if not a.dry_run and os.getenv("FCI_PUBLISHER") != "1":
        print("refusing to write: FCI_PUBLISHER is not 1.\n"
              "Only the designated Index publisher for a pilot writes to the spine; every other node\n"
              "feeds its parent instead (ARCHITECTURE.md §2). Use --dry-run to see what this node would send.",
              file=sys.stderr)
        return 3
    token = os.getenv("FCI_AIRTABLE_TOKEN", "")
    if not token and not a.dry_run:
        print("set FCI_AIRTABLE_TOKEN (data.records:read + data.records:write on this base)", file=sys.stderr)
        return 2

    try:
        rows = fetch_cells(a.node)
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as e:
        print(f"node unreachable at {a.node}/cells: {e}", file=sys.stderr)
        return 1
    print(f"node reports {len(rows)} cell row(s)")

    fields = [f for f in (normalise(r, city) for r in rows) if f]

    # The node can legitimately emit two rows for one cell key (packs/open-data-health does:
    # datasets_fresh_pct and datasets_total are both Governance|City). The spine holds one row
    # per cell, so collapse here, keeping the most recent, and say so rather than silently losing one.
    best: dict[str, dict] = {}
    for f in fields:
        prev = best.get(f["cell"])
        if prev is None:
            best[f["cell"]] = f
        else:
            keep, drop = (f, prev) if f["observed_at"] >= prev["observed_at"] else (prev, f)
            best[f["cell"]] = keep
            print(f"  note: two rows for {f['cell']}; keeping '{keep['unit']}', dropping '{drop['unit']}'")

    if a.dry_run:
        print(json.dumps(list(best.values()), indent=1))
        print(f"\n[dry run] {len(best)} row(s) would be written to {BASE_ID}/{TABLE}")
        return 0

    known = existing_rows(token, city)
    created = updated = 0
    for cell, f in sorted(best.items()):
        try:
            if cell in known:
                _send(f"{API}/{BASE_ID}/{urllib.parse.quote(TABLE)}/{known[cell]}", token, {"fields": f}, "PATCH")
                updated += 1
                print(f"  updated {cell} = {f['value']} {f['unit']} [{f['state']}]")
            else:
                _send(f"{API}/{BASE_ID}/{urllib.parse.quote(TABLE)}", token,
                      {"records": [{"fields": f}], "typecast": True}, "POST")
                created += 1
                print(f"  created {cell} = {f['value']} {f['unit']} [{f['state']}]")
        except urllib.error.HTTPError as e:
            print(f"  FAILED {cell}: HTTP {e.code} {e.read().decode()[:200]}", file=sys.stderr)

    print(f"\n{created} created, {updated} updated → https://index.fab.city/api/cells/{city}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

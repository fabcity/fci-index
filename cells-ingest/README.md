# cells-ingest — filling the spine

`cells-worker/` **reads** the FCI spine. This **fills** it.

```
planetai-node  GET /cells
      │
      ▼
  ingest.py            ← you are here
      │
      ▼
Airtable  appmNQaDGEFE9VcYh · Observations       ← the spine
      │
      ▼
cells-worker  →  index.fab.city/api/cells/<city>.json
```

Both ends already agree on the same eight fields — `city, cell, value, unit, source,
observed_at, state, notes` — because `planetai-node/app/index.py::_row()` emits exactly the
column set documented in `../cells-worker/README.md`. This script is a transport, not a
translator. If you find yourself renaming a field in it, fix the schema instead.

## How it works

Five steps, each of which can only lose rows, never invent them.

**1 · Fetch.** `GET <node>/cells`. The node has already done the hard part: `app/index.py` ran each
pack's SQL as the read-only `planetai_ro` role, checked how many local hourly buckets exist in the
last 24h, and refused to let any pack claim `live` without them. Whatever comes back is the node's
own honest answer. This script does not re-judge it.

**2 · Normalise.** Each row is checked against three things and dropped if it fails any:

- `cell` must be one of the 20 `Pillar|Scale` keys. Four rows already sitting in the spine use
  invented scales (`Environmental|Beach`, `Environmental|Harbor`, `Environmental|Industrial`,
  `Environmental|Residential`) and are invisible to every surface — this is the check that stops
  more of them arriving.
- `value` must not be null. A pack that returns no value has nothing to say this hour.
- `state` must be `live`, `partial` or `mock`. Anything else is recorded as `mock`, never promoted.

**3 · Collapse.** The spine holds one row per cell, but a node can legitimately emit two rows with
the same key — `packs/open-data-health` emits `datasets_fresh_pct` **and** `datasets_total`, both
as `Governance|City`. The most recent wins, and the script prints which metric it dropped. The
worker's newest-wins rule would do the same thing silently; printing it is the only difference,
and it is the difference between a known limitation and a mystery.

**4 · Diff.** `filterByFormula=LOWER({city})='<city>'` fetches the rows already in the spine for
this city and builds a `cell → record_id` map. Nothing outside this city is read or touched, so
running the Bali publisher can never disturb Barcelona's row.

**5 · Write.** `PATCH` where the cell already exists, `POST` where it does not. One row per
`(city, cell)`, forever. Appending would also work — `cells-worker` sorts by `observed_at` and
takes the newest — but the spine would grow by twenty rows an hour and stop being something a
person can open and read. It is a twenty-cell matrix; it should look like one.

Failures are per-row: an HTTP error on one cell prints and the rest continue. A partial publish is
better than an aborted one, because every row carries its own `observed_at` and the worker only
ever shows the newest.

### Why this is a transport and not a pipeline

There is no transformation in here worth the name — no unit conversion, no aggregation, no scoring.
That is deliberate. `planetai-node/app/index.py::_row()` emits exactly the eight columns
`../cells-worker/README.md` specifies, because both were written against the same `fci-cells-v0`
shape. The moment this script starts translating between them, the two schemas have drifted and the
fix belongs upstream, not here.


## The tier rule

From `planetai-node/ARCHITECTURE.md` §2: aggregation of Index cells stops at Region, and each
tier owns its own cell keys. So **exactly one node per pilot writes to the spine** — the node at
the top of that pilot's chain. Everything below it federates upward with `push_aggregates()`
and never touches Airtable.

| node | `NODE_KIND` | `NODE_SCALE` | writes to spine? |
|---|---|---|---|
| a house, a business | `home` / `business` | `community` | **no** — pushes to its parent |
| a banjar, a lab | `community` | `community` | no — pushes to the city node |
| a district / municipality | `district` | `city` | **yes**, if it is the pilot publisher |
| a province / metro | — | `region` | yes, where there is no city node above it |

The script refuses to write unless `FCI_PUBLISHER=1`, so a home node cannot start publishing
because somebody copied a `.env`.

## Wiring a pilot

The full step-by-step for the first one is in **[`BALI.md`](BALI.md)** — pre-flight, choosing the
publisher, the Denpasar portal, token scope, dry run, publish, verify, cron, and what will not turn
green. The short version:

```bash
export FCI_AIRTABLE_TOKEN=pat...        # data.records:read + data.records:write, this base only
export FCI_NODE_URL=http://<node>:8080
export FCI_CITY=bali
python3 ingest.py --dry-run             # prints the rows, writes nothing
FCI_PUBLISHER=1 python3 ingest.py
curl -s https://index.fab.city/api/cells/bali.json | python3 -m json.tool
```

`NODE_CITY` on the node must be exactly one of `barcelona` `boston` `santiago` `bali`, lowercase, or
`cells-worker` will not serve the rows and you will debug the wrong end.

## What it will not do

- **Upgrade a state.** A portal or a model is `partial` whatever its quality; only the node
  decides `live`, and it only says so when it has the local hourly buckets to back it
  (`app/index.py`). This script can downgrade an unrecognised state to `mock`; it never promotes.
- **Invent a cell.** Anything outside the 20 `Pillar|Scale` keys is dropped with a message. Four
  of the seven rows that were in the spine before this existed used invented scales
  (`Environmental|Beach`, `Environmental|Harbor`, …) and were invisible to every surface.
- **Write a city `cells-worker` will not serve.** `ALLOWED_CITIES` is hardcoded in the worker;
  the same list is hardcoded here. Keep the two in step or the row goes nowhere.
- **Append.** One row per `(city, cell)`, patched in place. The worker keeps the newest row per
  cell anyway, so appending would work and would also grow the spine forever.

## Known collision

`packs/open-data-health/cells.yml` defines **two** cells with the same key `Governance|City` —
`datasets_fresh_pct` and `datasets_total`. The spine holds one row per cell, so one of them
loses. This script keeps the most recent and prints which one it dropped, rather than losing it
silently the way the worker's newest-wins rule would. The real fix is upstream: give the two
metrics different cell keys, or fold them into one value with the other in `notes`.

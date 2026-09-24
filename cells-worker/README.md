# fci-cells — the thin-slice read API (S1)

Serves `GET /api/cells/barcelona.json` (and the other three pilots) from the Airtable spine.
This is the v0 stand-in for the architecture doc's §5.1 city-node read API — same JSON shape,
so the eventual Postgres node replaces it without touching the surfaces.

## Airtable spine — create once (S1 step 3)

Base: **`FCI Observations`** · Table: **`Observations`** · Fields (exact names, lowercase):

| Field | Type | Notes |
|---|---|---|
| `city` | Single line text | `barcelona` · `boston` · `santiago` · `bali` |
| `cell` | Single line text | `Pillar|Scale`, e.g. `Environmental|City` (canonical scales only) |
| `value` | Number | the observation |
| `unit` | Single line text | e.g. `µg/m³ PM2.5 (hourly mean)` |
| `source` | Single line text | e.g. `Smart Citizen kit #14231 — manual seed` |
| `observed_at` | Date (include time, GMT) | ISO |
| `state` | Single select | `live` / `partial` / `mock` |
| `notes` | Long text | provenance notes |

Seed row for the S1 exit test: `barcelona · Environmental|City · 18.4 · µg/m³ PM2.5 (hourly mean) ·
Smart Citizen kit — manual seed · <now> · partial · "S1 hand-written seed; replaced by the S2 adapter."`

Token: Airtable → Builder hub → personal access token, scope `data.records:read`, access: this base only.

## Deploy

```bash
cd fci-index/cells-worker
# paste BASE_ID into wrangler.toml [vars] first
wrangler secret put AIRTABLE_TOKEN
wrangler deploy            # prints https://fci-cells.<subdomain>.workers.dev
curl https://fci-cells.<subdomain>.workers.dev/api/cells/barcelona.json
```

For staging, paste that URL into `fci-3-prototype/js/live.js` as `window.FCI_LIVE_ENDPOINT`
(one commented line at the top), rebuild, redeploy Pages. On production the zone route
`index.fab.city/api/cells/*` makes same-origin work with no config.

---

# /api/coverage.json — the 61 localities

`GET https://index.fab.city/api/coverage.json` · format `fci-coverage-v0`

The Coverage Tracker holds the network: 61 localities × the 8 per-territory cells, with the
admin chain, the portal, the budget ladder, and the registry ids each cell was filled with.
Until 2026-09-24 it was reachable only with an Airtable token, which is the single reason
index.fab.city showed four pilot cities instead of sixty-one.

## Where it is generated, and why here

**Decided 2026-09-24: a route on this Worker, not a scheduled job committing a file.**

`scripts/build_index.py` in `awesome-fabcity-data` is the worked precedent and the right one for
*that* file — but it inverts here, and the difference is which way the source of record points:

| | `index.json` | `coverage.json` |
|---|---|---|
| source of record | **git** — 237 YAML files in PRs | **Airtable** — the harvest task writes it |
| so a committed file is | the artefact of the source | a *copy* of the source, able to go stale |
| what a CI gate can assert | regenerate and diff — real | "was the cron alive?" — weaker |

Three things settled it:

1. **No new credential.** This Worker already holds `AIRTABLE_TOKEN` (`data.records:read`) on
   base `appmNQaDGEFE9VcYh`, and the Coverage Tracker is a table *in that same base*. A
   scheduled job needs an Airtable token as a GitHub secret — in a repo whose deploy Action
   **has never had its secrets set**. Zero new secrets beats one new secret.
2. **No staleness to gate.** A committed copy can silently lag the tracker by however long the
   cron has been broken. A read-through cannot: worst case it returns 502, which is loud.
   `Cache-Control: max-age=300` bounds the lag at five minutes, by construction.
3. **It would be the sixth copy.** The locality list already exists in five places. The fix is
   fewer copies, and a committed export is one more thing that can disagree with the tracker.

The cost, stated plainly: `index.fab.city` now depends on Airtable being up to render a city
list, where `index.json` depends only on a CDN. That is the trade. If Airtable's availability
ever becomes the problem, the upgrade path is a KV cache in front of this route — not a
committed file, which reintroduces the copy.

## Freshness — two stamps, and they answer different questions

- `generated_at` — when *this response* was assembled. Always now. Says nothing about the data.
- `last_harvested` — the newest `Last harvested` across all 61 rows. **This is the one that
  means something**: when a human last added anything to the tracker. If it stops moving, the
  harvest has stopped, and no amount of fresh `generated_at` hides that.

## The three states of a cell, which are not two

Every cell carries `state`, and collapsing these throws away 258 real findings:

| state | means | renders as |
|---|---|---|
| `found` | carries ≥1 registry id | the sources |
| `checked-empty` | somebody looked and wrote down that there is nothing | **a result**, not a gap |
| `blank` | nobody has looked yet | absent |

`checked_empty` is also a separate boolean, because a cell can be both — a source was found
*and* the rest of the cell was checked and is empty. Zagreb `Environmental | City` is one.
The prose in `text` is the finding: it names what was checked. Do not drop it.

## The regex is load-bearing

Registry ids are matched on a **closed vocabulary** —
`{environmental|social|economic|governance}/{planet|bioregion|region|city|community}/{slug}`.

A bare `\w+/\w+/\S+` also matches URL path fragments, which the harvest notes are full of
(`fr/api/explore`, `hr/ckan/dataset`), and reports **~77 broken references that do not exist**.
There are zero. `test.mjs` pins this with the real Zagreb row.

## Checks

```bash
node test.mjs      # parser: three states, closed vocabulary, derived counts
```

Every number in the payload is derived from the records in the same response. There are no
constants in `counts`. If a number here disagrees with the tracker, this code is wrong.

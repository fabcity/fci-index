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
2. **Staleness is bounded and visible.** A committed copy can silently lag the tracker by
   however long the cron has been broken. This route serves from a KV cache (below) that
   refreshes itself 10 minutes after the last build, plus `Cache-Control: max-age=300` in the
   browser: about fifteen minutes of lag in normal running. If Airtable is down, the last good
   export keeps being served and its `generated_at` shows how old it is.
3. **It would be the sixth copy.** The locality list already exists in five places. The fix is
   fewer copies, and a committed export is one more thing that can disagree with the tracker.

The cost, stated plainly: the export still comes from Airtable, and a read takes about 4.5 s.

## The KV cache (2026-09-25)

KV namespace `fci-cells-fci-coverage`, bound as `COVERAGE`, holds the last good export under
`coverage.json`, stamped with its build time in the key's metadata. `serveCoverage()`:

| KV holds | age | response | Airtable |
|---|---|---|---|
| nothing | | waits for Airtable, `X-Coverage-Cache: miss`; 502 if Airtable fails | read now |
| an export | < 10 min | served, `hit; age=N` | not touched |
| an export | ≥ 10 min | served at once, `stale; age=N` | refreshed after the response |

The key never expires, so an Airtable outage serves the last good export instead of a 502.
Only the first request after the key is empty waits. `node test.mjs` covers every row above.
Not a committed file: that would reintroduce the copy.

## Freshness — two stamps, and they answer different questions

- `generated_at` — when this export was built from the tracker. With the KV cache it can be up
  to ten minutes old in normal running, more if Airtable is down. Says nothing about the data.
- `last_harvested` — the newest `Last harvested` across all 61 rows. **This is the one that
  means something**: when a human last added anything to the tracker. If it stops moving, the
  harvest has stopped, and no amount of fresh `generated_at` hides that.

## The four states of a cell, which are not two

Every cell carries `state`. Collapsing these throws away the harvest:

| state | means | renders as |
|---|---|---|
| `found` | carries >=1 registry id | the sources |
| `checked-empty` | somebody looked and wrote down that there is nothing | **a result**, not a gap |
| `noted` | somebody looked, wrote what they found, and it is not a registry source | **a finding**, not a gap |
| `blank` | genuinely empty — nobody has looked | absent |

`noted` exists because of a real bug, caught 2026-09-24 against production. An earlier version
had three states and let any cell with prose but no slug and no marker fall through to `blank`.
That misfiled **60 of 488 cells** — paragraphs like *"Data EXISTS and is machine-readable;
OPENLY LICENSED = NO"* rendered as "nobody has looked". Exactly **5** cells are truly empty.

That is the worst failure this export can have. The whole point is that absence is honest, and
calling a paragraph absence is a lie in the same family as inventing a number — it just fails in
the other direction. `test.mjs` pins it with the real Accra row.

`checked_empty` is also a separate boolean, because a cell can be both — a source was found
*and* the rest of the cell was checked and is empty. Zagreb `Environmental | City` is one; 82
cells are. The prose in `text` is the finding: it names what was checked. Do not drop it.

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

## `slug` is derived, and it does not join to the readings API

The tracker has **no id field**. `Locality` is free text and the primary field, so this export
derives `slug` from it. That gives the surfaces a stable key instead of hardcoding names — but
it does **not** line up with `/api/cells/{city}.json` for every pilot:

| tracker `Locality` | derived `slug` | readings API serves | joins? |
|---|---|---|---|
| Barcelona | `barcelona` | `barcelona` | yes |
| Boston | `boston` | `boston` | yes |
| Bali | `bali` | `bali` | yes |
| **Santiago de Chile** | `santiago-de-chile` | `santiago` | **no** |

Left unresolved deliberately. Picking one silently renames a locality in whichever system loses,
and the right fix is a real id column in the tracker — which is a click in the Airtable UI, not
something the API can do (the PAT has no schema scope). Until then any surface joining these two
feeds must treat Santiago as a known exception and say so, not quietly drop it.

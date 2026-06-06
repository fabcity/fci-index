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

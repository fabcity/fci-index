# FCI 3.0 — Deploy Runbook

One Cloudflare Pages project, one domain, three routes (per `FCI_3.0_Deployment_Plan_2026-06-06.md` §0, approved 6 June):

| Route | Source folder | Surface |
|---|---|---|
| `index.fab.city/` | `../fci-3-prototype/` | Public prototype |
| `index.fab.city/atlas/` | `../fci-matryoshka-viz/` | Aggregation atlas |
| `index.fab.city/operate/` | `../fci-ingestion-tool/` | Operator workbench |

The three source folders in the FAB CITY workspace stay canonical — edit there, never in `public/`. `build.sh` assembles + rewrites cross-links + injects the beta feedback line (and Plausible, on `--prod`).

## One-time setup (~20 min, needs your Cloudflare auth)

```bash
npm install -g wrangler
wrangler login                                   # browser auth — your account, holds the fab.city zone
cd "<workspace>/fci-index"
./build.sh                                       # sanity: expect "assembled: 22 pages · unrewritten cross-links: 0"
wrangler pages project create fci-index --production-branch main
```

## Every deploy

```bash
./build.sh
wrangler pages deploy public --branch staging    # → stable preview URL, share with tier 1 only
# walk the staging URL (phone + laptop), then:
./build.sh --prod
wrangler pages deploy public --branch main       # → production
```

## Custom domain (once, after first production deploy)

Cloudflare dashboard → Pages → `fci-index` → Custom domains → add `index.fab.city`.
Same-account zone ⇒ CNAME + cert are automatic. If `fab.city` turns out to live elsewhere, add a CNAME `index` → `fci-index.pages.dev` at the registrar instead.

## Email + feedback (tier 2/3 — deployment plan §5)

- Cloudflare Email Routing on `fab.city`: alias `index@fab.city` → forward to Tomas (+ methodology co-author when confirmed). The footer mailto on every page is the entire tier-2 feedback mechanism.
- Tier-3 form endpoint: `feedback-worker/` (separate tiny Worker → Airtable). Deploy only when tier 3 starts:

```bash
cd feedback-worker
wrangler secret put AIRTABLE_TOKEN               # a scoped PAT, base-only
wrangler deploy
```

## Rollback

Pages keeps every deployment: dashboard → Deployments → "Rollback to this deployment". That is the whole disaster-recovery story for a static site.

## Discipline

- **Staging before production, always.** Tier 2 sees `index.fab.city`, never a `.pages.dev` URL.
- v0 labels, mock pills, ρ "protocol pending" qualifiers ship as-is — they are the design, not an apology. When methodology v1 lands, the swap is a data.js edit + redeploy.
- Before tier 2 goes out: `/operate/` gets its "demonstration workbench — accounts arrive with M+2" banner reviewed, and the stale-date pass re-checked (done 2026-06-06).

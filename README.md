# fci-index

The Fab City Index — **index.fab.city**. This repo holds the build script that assembles the site,
the Cloudflare Workers that move data in and out of it, and the writer that connects a PLANETAI node
to it.

The Index measures how far a city has got toward producing nearly everything it consumes by 2054,
across twenty cells: four pillars (Environmental, Social, Economic, Governance) × five scales
(Community, City, Region, Bioregion, Planet).

---

## What is *not* in this repo

Read this before cloning and expecting to build.

**The pages live in three other repos.** `build.sh` assembles `public/` from three private repos,
each checked out as a sibling of this one in the FAB CITY workspace:

| repo, checked out at | becomes | surface |
|---|---|---|
| [`fabcity/fci-3-prototype`](https://github.com/fabcity/fci-3-prototype) → `../fci-3-prototype/` | `/` | the public site: cities, city, map, ranking, matrix, method |
| [`fabcity/fci-matryoshka-viz`](https://github.com/fabcity/fci-matryoshka-viz) → `../fci-matryoshka-viz/` | `/atlas/` | the aggregation atlas |
| [`fabcity/fci-ingestion-tool`](https://github.com/fabcity/fci-ingestion-tool) → `../fci-ingestion-tool/` | `/operate/` | the workbench: bench, coverage, sources, source review, intake, review, sovereignty |

So a clone of this repo alone cannot rebuild the site. `build.sh` checks for all three and exits if
any is missing. It reads their **working trees as they are**, uncommitted changes included, so pull
all three before a production build. The three site repos take direct pushes to `main`; this one
merges through pull requests.

**`public/` is generated and gitignored.** Edit the site repos, never `public/`; the build drops a
`DO-NOT-EDIT.txt` there to say so.

---

## Layout

```
build.sh              assembles the three sites into public/, rewrites cross-links, strips
                      internal comments, injects the feedback line, writes _redirects and
                      _routes.json, and runs the gates below
check_tokens.py       every var(--…) a page uses is defined, build.sh's own markup included
check_exports.py      every window.FCI reference resolves
wrangler.toml         Cloudflare Pages project config (output: public/)
README_DEPLOY.md      the deploy runbook: staging, production, custom domain, rollback
functions/operate/    Pages middleware: sends the workbench's act pages from *.pages.dev
                      to index.fab.city, where Cloudflare Access asks for sign-in

cells-worker/         READ  · GET index.fab.city/api/cells/<city>.json   ← Airtable Observations
                      READ  · GET index.fab.city/api/coverage.json       ← Airtable Coverage Tracker
cells-ingest/         WRITE · GET <node>/cells → Airtable Observations    ← the spine writer
feedback-worker/      POST /api/feedback → Airtable "FCI Beta Feedback" (not configured, see below)

public/               generated. gitignored. do not edit.
```

**The build fails rather than ship** if any of these break: the three `css/tokens.css` copies stop
being identical, the three `css/nav.css` copies drift, a page uses an undefined token or a
`window.FCI` export that does not exist, a page loses its structure, an internal link points at
nothing, a cross-link is left unrewritten, or the redirect rule count changes. Each gate exists
because something got past the others.

---

## Where the data comes from

Nothing the site shows as data is a file in this repo. It reads three live feeds:

| feed | source of record | what it says |
|---|---|---|
| `/api/coverage.json` | Airtable, base `appmNQaDGEFE9VcYh`, table `FCI Coverage Tracker` | the 61 pledged places × 8 cells: which registered sources could fill each one, and whether anyone has looked |
| `/api/cells/<city>.json` | Airtable, same base, table `Observations` (the spine) | what a node has actually measured |
| `index.json` | [`awesome-fabcity-data`](https://github.com/fabcity/awesome-fabcity-data), read from `raw.githubusercontent.com` | what each registered source is, its licence, status and reviews |

The spine, end to end:

```
PLANETAI node                     app/index.py computes cells from pack SQL,
  GET /cells                      and refuses `live` without local hourly buckets
      │
      ▼
cells-ingest/ingest.py            upsert, one row per (city, cell)
      │
      ▼
Airtable · Observations           THE SPINE: city, cell, value, unit, source,
      │                           observed_at, state, notes
      ▼
cells-worker/worker.js            newest row per cell → fci-cells-v0
      │
      ▼
index.fab.city/api/cells/<city>.json
      │
      ▼
fci-3-prototype/js/city.js        city.html?locality=<slug> shows whether a node
                                  has ever reported a reading for that place
```

`/api/coverage.json` is served from a KV cache (`COVERAGE`) and refreshed in the background after
ten minutes, so an Airtable outage serves the last good copy. The `X-Coverage-Cache` response header
says whether a request was a miss, a hit or stale. The route matches the exact path only: add a
query string and the request falls through to Pages, which answers **200 with the home page**. Check
the body, never the status.

Two rules the code enforces and the pages honour:

- **`live` means measured at an address.** A portal or a model is `partial` however good it is.
  Nothing downstream may upgrade a state.
- **Aggregation stops at Region.** Bioregion and Planet enter as boundary conditions; they publish
  context downward and are never rolled up.

The four cities the cells worker will serve are hardcoded in `ALLOWED_CITIES`: `barcelona`,
`boston`, `santiago`, `bali`. Any other slug gets `404 {"error":"unknown city"}`, so a node
publishing under another `city` value writes rows that nothing will show. The Coverage Tracker has no
id column, so its slugs are derived from the place name, and `santiago-de-chile` does not match the
worker's `santiago`. `cells-worker/test.mjs` pins that mismatch until the tracker gets a `slug`
column.

---

## Build and deploy

Build from the checkout that has `main` checked out. Full runbook in
**[`README_DEPLOY.md`](README_DEPLOY.md)**. In short:

```bash
./build.sh                                     # every gate passes; "unrewritten cross-links: 0"
wrangler pages deploy public --branch staging  # walk it on phone and laptop
./build.sh --prod                              # adds Plausible
wrangler pages deploy public --branch main
```

`FCI_OUT=/some/dir ./build.sh` assembles somewhere else without touching `public/`. Rollback is
Pages → Deployments → "Rollback to this deployment".

A Pages preview has **no `/api/*`**: those are Worker routes on `index.fab.city` only, so the
network lists on a preview show the feed error. That is expected. JS is served with
`max-age=14400`, so a browser that visited in the last four hours can run old scripts against new
pages after a deploy; hard-refresh before calling it broken.

The workers deploy separately, each from its own folder with `wrangler deploy`, each with its own
scoped Airtable PAT as a secret. `cells-worker` needs `data.records:read`. `cells-ingest` needs read
**and** write and is the only thing in the system that may write to the spine.

---

## Where it actually stands

As of 26 September 2026. Worth being plain about, because the site is honest about it and the repo
should be too.

- **Barcelona is the only city with a real observation**, and it is a single hand-typed seed row
  from 6 June 2026 (`Environmental|City`, Smart Citizen kit, `partial`). Boston, Santiago and Bali
  answer `"count": 0`. No node writes to the spine on a schedule yet.
- **The invented numbers are gone.** The city pages used to render twenty scores and a scoreboard,
  sixty of them from a seeded random number generator. One `city.html` template now shows what the
  three feeds actually say for any of the 61 places. The four old `city-*.html` pages 301 to
  `/cities`.
- **Methodology v0, in review.** The v0 labels, the mock pills on the matrix and the "under review"
  qualifiers on ρ ship on purpose. They are the design, not an apology.
- **Coverage is counted out of 20.** The tracker holds 8 cells per place, so the other 12 count as
  having no source, and the cities page says so.
- **`feedback-worker` is not configured.** `BASE_ID` is still `appXXXXXXXXXXXXXX`, and its route
  is not deployed: a POST to `/api/feedback` answers 405. Feedback goes to the address in every
  page's footer.
- **The workbench's act pages** (intake, review queue, sovereignty) sit behind Cloudflare Access on
  `index.fab.city`. `functions/operate/_middleware.js` sends the same paths on `*.pages.dev` there
  too. Deployments older than that middleware still serve them openly until Access covers preview
  deployments in the Pages settings.

---

## Related repos

| repo | what it does |
|---|---|
| [`fci-3-prototype`](https://github.com/fabcity/fci-3-prototype), [`fci-matryoshka-viz`](https://github.com/fabcity/fci-matryoshka-viz), [`fci-ingestion-tool`](https://github.com/fabcity/fci-ingestion-tool) | the pages. See the first section. |
| [`planetai-node`](https://github.com/fabcity/planetai-node) | the node. Computes the cells this Index serves. `ARCHITECTURE.md` §2 is the tier contract. |
| [`awesome-fabcity-data`](https://github.com/fabcity/awesome-fabcity-data) | the open-data source registry. The site reads its generated `index.json` at runtime; reviews arrive through its source-review issue form. |
| [`planetai-coordination`](https://github.com/fabcity/planetai-coordination) | decision log, reviews, tracks, pilots, waves. |

To wire a pilot end to end, start at [`cells-ingest/BALI.md`](cells-ingest/BALI.md).

---

Questions and beta feedback: **index@fab.city**

# For the agent working with the Fab City Index

This repository builds **index.fab.city**: the script that assembles the site, the Workers behind its `/api/*`
routes, the open calculation in `compute/`, and `api.mjs`, which publishes every place's index at build. The pages
themselves live in three other repositories that are not public, so most people who arrive here want the data, or
want their city's data to improve, and both happen elsewhere. The README is for people; this file routes you.

## What the person in front of you is asking for

| the person says | go to | then do this |
|---|---|---|
| "what is my city's index?", "give me the data", "can I use it in my report?" | `https://index.fab.city/api/v0/` | Read `index.json` (all 61 places), `index.csv`, or `places/<slug>.json`. Quote the `status` with the number: a `simulated` place has a range `[0, DIDO]`, never one score. Scores are CC BY 4.0; each input keeps its own licence. Never compute a score yourself from a page. |
| "my city has no data", "add a source for X" | [`awesome-fabcity-data`](https://github.com/fabcity/awesome-fabcity-data) and its `AGENTS.md` | A source is filed there, as a `candidate`, from the person's account. The Index reads that registry live; nothing is added here. |
| "our node should publish to the Index" | [`planetai-node`](https://github.com/fabcity/planetai-node), `skills/publish-to-index/SKILL.md` | Establish the tier first: one node per pilot writes, a home node never does. The writer is `cells-ingest/` here and needs a per-pilot token issued by hand. |
| "add a measured result for a place" (trade, waste, material use) | `compute/README.md` | A script in `compute/`, standard-library Python, whose result lands in `compute/results/`. It reaches a score only if `api.mjs`'s `MEASURED` section maps it to a cell, and that mapping is a decision for a maintainer: propose it in the pull request. |
| "this page is wrong", "a link is broken" | an issue here, or `index@fab.city` | The pages are not in this repository. Say which URL and what it shows. |
| "change the build, a gate, a Worker" | `README.md` and `README_DEPLOY.md` | A pull request here. Run the build before you open it (below). Deploying is a maintainer's. |

## Before you open a pull request

The build needs the three page repositories checked out beside this one (`../fci-3-prototype`,
`../fci-matryoshka-viz`, `../fci-ingestion-tool`), which only maintainers can clone. With them:

```
FCI_OUT=/tmp/fci-check ./build.sh      # assembles elsewhere; every gate; ends "unrewritten cross-links: 0 (must be 0)"
python3 compute/fabcity_index.py --selftest   # no network; must reproduce Hamburg's 37
node cells-worker/test.mjs             # when you touched the cells worker
```

Without them, say so in the pull request: a change to `compute/` can be checked on its own with its self-test.

## What must hold

- **Absence is not zero.** A cell with no data, a cell checked and found empty, a cell nobody looked at and a cell
  outside the tracker are four different states, and a page or an answer that draws any of them as 0 is wrong in the
  same way an invented number is.
- **Simulated is a range.** With no measured cell, a place's index is `[0, DIDO]`. Never one number.
- **`live` means measured at an address.** A portal or a model is `partial` however good it is. Nothing downstream
  upgrades a state.
- **Aggregation stops at Region.** Bioregion and Planet are boundary conditions, never rolled up.
- **No invented numbers.** Every figure comes from a source someone can open. If one is missing, the page and the
  API say "not measured".
- **`/api/coverage.json` with a query string is the home page**, with status 200: the Worker route matches the
  exact path. Check the body, never the status code.
- **Secrets stay in Wrangler.** The Workers' Airtable tokens are `wrangler secret`s. Never in a file, a commit, a
  log or a pull request.

# Method v1 proposal: two indicators read inside cells

Branch `index-v1-ownership-and-local-models`, in four repositories. Nothing here is merged, deployed or opened
against main. The one-page version for the review is [SUMMARY.md](SUMMARY.md). The method page text is
[method.diff](method.diff).

## 1. Where things live today (v0, 7 Nov 2026)

The matrix is four pillars (Environmental, Social, Economic, Governance) by five scales (Community, City, Region,
Bioregion, Planet). The brief's Neighbourhood is Community and its Society is Social.

| Topic | Where it is | What it does to a score |
|---|---|---|
| Fab-lab and distributed-manufacturing capacity | Registry cell `Economic\|Community`, minimum indicator "Fab labs and open workshops within reach". `data.js` also names fab-lab catchment under `Economic\|City`. Entries: `fablabs-io` and `fablabs-network-data-archive` have `feeds_cells: []` on purpose, because the records are not openly licensed. `maps-of-making` and `open-hardware-manager` feed `Economic\|Community`, licence not stated. `compute/labs.py` reads a dated archive freeze for the network map only. | Only through DIDO, as "a source exists" |
| Open data and sensing | `Governance\|City` and `Governance\|Region` (open datasets published, datasets updated in 90 days, read by `packs/open-data-health`); sensing in `Environmental\|Community` and `Environmental\|City`. | Only through DIDO, as "a source exists" |
| Data-sovereignty or transparency policy | `Governance\|Community` names "data sovereignty at neighbourhood scale" in `data.js` only. `Governance\|City` holds transparency portals (`transparenzportal-hamburg`). No entry measures a sovereignty policy; OONI, at Planet scale, is the only entry that mentions sovereignty. | None |

**How a cell with more than one indicator is scored: it isn't, in v0.** The registry's `cells/*.yaml` list
several `minimum_indicators` per cell, with unit and aggregation, but no weights, and no code reads them into a
score. `fci-score.js` reads a cell into DIDO as 1 if any live or candidate registry source names the place in it,
else 0. It reads a cell into PITO as one measured share `s_c`, and only `Economic|Region` is measured anywhere
(10 places). The method page's §4 describes DIDO as a weighted mean of graded scores; the code has never done that.

Two more things the brief assumed and the code does not do:

- **The age discount works only on PITO.** Full weight to two years, falling to nothing at twelve (2014). DIDO has
  no discount.
- **Governance cells carry no PITO weight** (0.0 / 1.0) and `Social|City` carries 0.1. A measured value placed in
  them through PITO would move nothing, and placing an ownership share in PITO would change what PITO means.

So the only way these two indicators can move a score without changing the formula is through a graded DIDO term.
That is the route chosen on 7 Nov.

## 2. The proposal

FCI = DIDO · (1 − PITO) · ρ, the pillars, the scales, the v0 weight table, PITO and ρ all stay as they are. Only a
cell's DIDO term changes, and only in the five cells below:

```
d_c = (1 − Σ_i w_ci) · o_c  +  Σ_i w_ci · x_i · f_i
```

`o_c` is v0's yes or no for the cell, `x_i` the place's share in [0,1], `f_i` the existing age discount (1 to two
years, then 1 − (age − 2)/10, 0 at twelve). An indicator nobody reported has `x_i = 0`, the DIDO rule for missing
data, and the code returns it as `unmeasured`, never as a reading of zero. Leave `sub` out and `fci-score.js` is v0
exactly; every page still calls it that way.

### The weight inside each cell

Each indicator a cell lists counts the same. With `n` listed before v1, a new one gets `1/(n+1)` and the yes or no
keeps `n/(n+1)`, because it already stands for those `n`.

| Cell | v0 PITO / DIDO | listed before v1 | capacity_ownership_share | local_model_share | yes or no keeps |
|---|---|---|---|---|---|
| Economic × Community | 0.3 / 0.7 | 3 | 1/4 | | 3/4 |
| Economic × City | 0.5 / 0.5 | 4 | 1/5 | | 4/5 |
| Governance × City | 0.0 / 1.0 | 5 (one is ρ) | 1/7 | 1/7 | 5/7 |
| Social × City | 0.1 / 0.9 | 3 | | 1/4 | 3/4 |
| Governance × Region | 0.0 / 1.0 | 3 | | 1/4 | 3/4 |

This rule was picked over a hand-set number because v0's weights are "documented assignments derived from what the cell
measures", and the registry is where a cell says what it measures. Counting its list needs no judgement call per cell. It has a known weakness: the weights move whenever the registry adds an indicator to one
of these cells, so v1 freezes them in `data.js` (`SUBINDICATORS_V1`), counted on 7 Nov 2026.

### Effect on the weighted means

DIDO weights sum to 12.4. The new indicators carry `Σ w_dido · w_ci = 1.036` of that, 8.4%. Run with
`node compute/v1_effect.mjs ../fci-3-prototype-v1`, which first checks that v0 from the new code equals the
published `/api/v0/` for all 61 places, to the digit. Full table: `compute/results/v1-effect.json`.

On day one, when no place has reported:

- **41 of 61 places lose DIDO,** 0.032 on average (0.022 across all 61). The 20 that don't move either have no open source at all
  (17) or have sources only in other cells (Occitanie, Oulu, Südburgenland).
- **The largest drop is 0.084**, for a place open in all five cells. Only Barcelona is: DIDO 0.621 → 0.537, FCI
  0.454 → 0.393.
- **Ranking:** among places with a measured cell, Boston (4th) and São Paulo (5th) swap. Among the simulated places,
  18 move because they lose different amounts: Cambridge and Somerville (0.081 → 0.058) fall below Curitiba,
  Sorocaba and Yucatán (0.073 → 0.065).
- **A place that reports a share of 1 gets v0 back.** The script asserts this for every place open in all five
  cells, and asserts that absence never raises DIDO and a report never lowers it.

| Place | Rank | DIDO v0 → v1 day one | FCI v0 → v1 day one |
|---|---|---|---|
| Barcelona | 1 → 1 | 0.621 → 0.537 | 0.454 → 0.393 |
| Charlotte | 2 → 2 | 0.613 → 0.552 | 0.236 → 0.213 |
| Santiago de Chile | 3 → 3 | 0.363 → 0.314 | 0.208 → 0.180 |
| Boston | 4 → 5 | 0.444 → 0.374 | 0.113 → 0.095 |
| São Paulo | 5 → 4 | 0.218 → 0.192 | 0.109 → 0.096 |
| Recife | 6 → 6 | 0.298 → 0.249 | 0.108 → 0.090 |
| Kamakura | 7 → 7 | 0.177 → 0.149 | 0.089 → 0.075 |
| Hamburg | 8 → 8 | 0.282 → 0.233 | 0.073 → 0.060 |
| Bali | 9 → 9 | 0.363 → 0.308 | 0.037 → 0.031 |
| Puebla | 10 → 10 | 0.040 → 0.032 | 0.031 → 0.024 |

Hamburg's 0.073 and Paris's range are the Index's own v0 computation. Boeing's Hamburg 37.00 (2024) and Utopies'
Paris 37.58 (2018) are published results of other studies; they sit in `PUBLISHED_SCORES` and the method text,
and nothing on this branch recomputes or edits them.

## 3. The stubs

`compute/v1_stubs.py`, standard-library Python, `--selftest` only. None of them fetches anything, writes to
`results/`, or reaches `api.mjs`. Every reader returns `{"state": "unmeasured", "value": null, "why": ...}` when it
has no data.

- **fablabs.io.** Labs per place, from the archive freeze `labs.py` already reads, not `api.fablabs.io/0/labs.json`.
  The live endpoint says its legacy API "has now been removed" and still answers, and a score has to be
  repeatable. `ownership` is always null: no fablabs.io record has an owner or organisation-type field.
- **Open Know-Where.** Entries per place from OHM's `okw/spaces` or Maps of Making, with any ownership field
  passed through. Read on 7 Nov: OHM's `access_type` is null in all 3,194 records, Maps of Making has no such field,
  and its `capacity` is 0 in every record. 2,412 of these records are harvested fablabs.io records.
- **node_report.** The only reader that can produce either share. The schema is in the registry,
  `schema/node-report.schema.json`, with `docs/node-report.example.yaml`. Per node: machines, owner type, model
  runtime, date. The stub checks every report again in code, since reports come from outside, and keeps the latest
  report per node. A share's year is that of its oldest counted node, so age can only lower it.

Place matching in the two directory stubs is by city name, which misses metro areas and every region-sized place
(Bali, Catalonia). That is marked in the code, with the upgrade path.

## 4. The tracker

The registry cells now list the two indicators with `id` and `proposed_in: Method v1, in review`. The Coverage
page (`/operate/matrix-coverage`) reads them from the registry and shows one row per indicator and cell, "0 of 61
places reporting, unmeasured". The 20-cell count, the home bar and its partition check are untouched, because
these are indicators inside cells. The Airtable tracker is not changed: its token has no schema scope, and the
proposal does not need it.

## 5. For the reviewers

Places where v1 touches something already marked v0 or under review. The method text names each, and none is
decided on this branch.

1. **The v0 weight table (§3).** The weights inside a cell are a new layer on top of it. Economic × Community is
   one of the three cells whose v0 split already needs a better argument.
2. **Missing data counts 0 in DIDO (v0).** v1 carries the rule from cells down to indicators.
3. **The age discount (v0)** works only on PITO. v1 applies it inside DIDO for the first time.
4. **§4 against the code.** The page describes graded DIDO and the code reads 1 or 0. v1 is a first step towards
   the graded version; the page's general formula should be rewritten to match whatever is accepted.
5. **ρ.** Governance × City lists ρ among its indicators, so ρ is one of the five its yes or no stands for when the
   weights are counted. ρ's rule and its place in the formula are untouched.
6. **The `complete` label** asks every cell to have open data. Whether it should also need these shares is open.

Decisions the proposal makes that a reviewer may want to change:

- `unknown` owners are counted apart from both local and outside. Counting them as outside would lower every share.
- A node with `model_runtime: none` is left out of `local_model_share`. Counting it would reward running no model.
- One value per place enters every cell an indicator is listed in. At Community scale the neighbourhood's own
  share would be better, and node reports carry a node location for that later.
- Using a fablabs.io lab count in a score would be a new use of records that are not openly licensed. The
  14 Oct 2026 decision covers showing the directory on the map. The stub produces the count and nothing reads it.

Not done, and why:

- `api.mjs` doesn't publish v1 scores and no page shows them. That waits for the reviewers.
- No `reports/` folder or intake for node reports. It waits for the method to be accepted, then needs a review path
  like `reviews/`.
- `build_index.py` doesn't count reports, so the Coverage page states 0 directly. Count reports there when
  `reports/` exists.

## 6. Files changed

| Repository | Files |
|---|---|
| fabcity/awesome-fabcity-data | `cells/economic-community.yaml`, `cells/economic-city.yaml`, `cells/governance-city.yaml`, `cells/social-city.yaml`, `cells/governance-region.yaml`, `schema/cell.schema.json`, `schema/node-report.schema.json` (new), `docs/node-report.example.yaml` (new), `tests/test_schema.py`, `index.json` (regenerated) |
| fabcity/fci-3-prototype | `js/data.js`, `js/fci-score.js`, `method.html`, `css/main.css` (scroll margin for the new anchor) |
| fabcity/fci-ingestion-tool | `js/coverage.js`, `matrix-coverage.html` |
| fabcity/fci-index | `compute/v1_stubs.py` (new), `compute/v1_effect.mjs` (new), `compute/results/v1-effect.json` (new), `compute/README.md`, `docs/v1-ownership-and-local-models/` (new: this file, `SUMMARY.md`, `method.diff`) |

**Merge order, when accepted:** fci-3-prototype and fci-ingestion-tool first, then the registry. The registry's
`index.json` is read live, so the Coverage page lists the indicators the moment it merges.

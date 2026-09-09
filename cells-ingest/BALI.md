# Publishing Bali to the Fab City Index

A runbook. Read `README.md` first for what the tool is; this is how to actually get Bali onto
`index.fab.city/api/cells/bali.json`.

## What this is, and what it isn't

It is **not** a data-collection exercise. The Bali node already computes Index cells — that is what
`app/index.py` does on every node, every poll. `planetai-node/docs/COVERAGE.md` records node #1
filling **seven of twenty cells** as of 7 September 2026, and everything in that table (sea
temperature, the Bali Air Dispatch adapter, "air was first because Bali has the sensors and the burn
season") says node #1 is the Bali node. Confirm that before you rely on it — step 1 does.

So the job is not to make Bali measure something. It is to carry what Bali already measures the last
hop into the spine. Those seven cells have been computed and discarded every hour for months because
nothing was listening.

---

## 1 · Pre-flight

Run these against the Bali node before changing anything.

```bash
NODE=http://<bali-node>:8080

curl -s $NODE/health | head -c 200          # is it up
curl -s $NODE/cells   | python3 -m json.tool # what does it think it can say
curl -s $NODE/rho     | python3 -m json.tool # the always-computable cell
```

**Check `city` on every row of `/cells`.** It comes from `NODE_CITY` and it must be exactly `bali`,
lowercase. `cells-worker` matches on `fields.city == "bali"` and its `ALLOWED_CITIES` list has four
entries; a node set to `denpasar`, `ubud` or `Bali` will publish rows that no surface will ever
serve. This is the single most likely way to do everything right and see nothing.

```bash
curl -s $NODE/cells | python3 -c "import sys,json; print({r['city'] for r in json.load(sys.stdin)})"
```

If it is wrong, fix `NODE_CITY=bali` in the node's `.env` and restart before going on.

**Note which states come back.** Anything sourced from a portal or a model is `partial` by design —
`index.py` will not let a pack claim `live` without local hourly buckets behind it. If you see
`live` on `Environmental|Community`, the node has its own sensor and real data. That is the cell
worth protecting.

---

## 2 · Decide the publisher

Per `planetai-node/ARCHITECTURE.md` §2 and the tier table in `README.md`: exactly one node per pilot
writes to the spine.

Bali today almost certainly has one node, which is a community-scale node at an address. Making it
the pilot publisher is a **temporary compromise** — it means an address is speaking for an island.
That is acceptable for a prototype and should be written down as debt, because the moment a second
Bali node exists (a Denpasar district node, a second banjar) they will both write
`Environmental|Community` under `city: bali` and the newest one silently wins.

When that happens, the fix is in the tier, not in this script: the city node aggregates its children
and becomes the sole publisher. Until then, set `FCI_PUBLISHER=1` on exactly one machine and keep a
note of which.

---

## 3 · Widen coverage — the Denpasar portal

One environment variable on the node. The generic `sources.py::ckan()` adapter reads any CKAN portal
and `packs/open-data-health` turns it into `Governance|City`.

```
CKAN_PORTALS=satudata-denpasar=https://satudata.denpasarkota.go.id
```

Verify the portal answers first. It is CKAN 2.8.3, and its `robots.txt` disallows `/api/` — a
crawler will not fetch it; the node's `httpx` client is not a crawler, and running it is your call:

```bash
# datasets_total
curl -s 'https://satudata.denpasarkota.go.id/api/3/action/package_search?rows=0' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['success'], d['result']['count'])"

# datasets_fresh_90d  (cutoff = today minus 90 days; 2026-06-11 for a 2026-09-09 run)
curl -s 'https://satudata.denpasarkota.go.id/api/3/action/package_search?rows=0&fq=metadata_modified:%5B2026-06-11T00:00:00Z%20TO%20NOW%5D' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['success'], d['result']['count'])"
```

Expect roughly 1,028 total (wave 1's count, licence `Lainnya (Domain Publik)` on nearly all of them).
If the second number is 0 against a non-zero first, the portal is an archive rather than a live
open-data programme — which is precisely the DIDO signal the cell exists to carry. Publish it
anyway; a real zero is a finding, and it is the honest starting number for Denpasar.

The Bali entry is also the interesting one politically: at ~1,028 near-public-domain datasets,
Denpasar's catalogue is more openly licensed than Barcelona's, Boston's or Santiago's. That is worth
knowing before anyone assumes the European pilots lead on open data.

---

## 4 · Token

`cells-worker`'s token is `data.records:read` by design and cannot write. Make a second one:

Airtable → Builder hub → personal access token → scopes **`data.records:read`** and
**`data.records:write`** → access: the **FCI Observations** base only. Nothing else, no other base.

```bash
export FCI_AIRTABLE_TOKEN=pat...
```

Keep it out of the repo and out of chat. It writes to the table that feeds a public site.

---

## 5 · Dry run

```bash
export FCI_NODE_URL=$NODE
export FCI_CITY=bali
python3 ingest.py --dry-run
```

Read the output properly before going further:

- **How many rows survived?** Anything dropped prints to stderr with the reason.
- **Any `Governance|City` collapse notice?** Expected if the CKAN portal is wired — the pack emits
  two metrics under one key. Note which one it kept.
- **Are the states right?** A portal showing `live` would mean something is wrong upstream.
- **Is `observed_at` recent?** A stale timestamp means the node's poll loop is stuck, not that the
  publish failed.

---

## 6 · Publish

```bash
FCI_PUBLISHER=1 python3 ingest.py
```

The script refuses without that flag, which is what stops a home node publishing because somebody
copied a `.env`. Output names every cell created or updated.

Bali writes only rows where `city == "bali"`, and the diff step reads only those rows, so this
cannot touch Barcelona's seed row or any other pilot.

---

## 7 · Verify

```bash
curl -s https://index.fab.city/api/cells/bali.json | python3 -m json.tool
```

You should get `format: "fci-cells-v0"`, a `count`, and a `cells` object keyed by `Pillar|Scale`.
If the endpoint 404s, the zone route is not live and the staging worker is
`https://fci-cells.tomas-74b.workers.dev/api/cells/bali.json`.

---

## 8 · Make it visible on the site

**The API will have the data and the Bali page will not show it.** Only `public/city-barcelona.html`
carries the `<div id="live-feed">` mount and loads `js/live.js`; the other three city pages have
neither. Publishing to the spine gets Bali into the API, not onto the page.

Two lines in `public/city-bali.html` fix it — the mount where the strip should appear, and the
script tag — but note that `live.js` currently hardcodes the Barcelona endpoint. Making it work for
any city means parameterising it, e.g. reading a `data-city` attribute off the mount. That is a
small, separate change and it should be made once for all four pilots rather than four times.

Separately: `live.js` "deliberately does NOT flip pills or override cell scores; a later slice does
that." So even with the strip in place, the twenty-cell matrix on the Bali page keeps rendering the
mock values from `public/js/data.js`. Real cells in the API and mock cells in the matrix will coexist
until that later slice is written. Anyone shown the page needs to be told which is which, or the
prototype quietly becomes a misrepresentation.

---

## 9 · Cron

Hourly, offset from the node's own aggregate push so they do not collide:

```
17 * * * * cd /path/to/cells-ingest && FCI_PUBLISHER=1 /usr/bin/python3 ingest.py >> /var/log/fci-ingest.log 2>&1
```

---

## 10 · What to watch

| symptom | cause |
|---|---|
| `node unreachable` | node down, or `FCI_NODE_URL` wrong. The script exits 1 and writes nothing. |
| rows published, API empty | `NODE_CITY` is not exactly `bali`. Step 1. |
| `skip: '<key>' is not one of the 20` | a pack is emitting a non-canonical cell key. Fix the pack. |
| everything `partial`, nothing `live` | expected unless the node has its own sensors with 24h of local hourly buckets. Not a bug. |
| a cell stops updating | the node's poll loop or that pack's SQL failed; `index.py` logs and skips rather than publishing a stale value. Check the node, not this script. |
| two metrics fighting over `Governance|City` | the known `open-data-health` collision. Give them distinct keys upstream. |

## 11 · What will not turn green

Worth saying before anyone expects a green honeycomb.

`index.py` enforces that `live` means measured here, with enough local hourly buckets to back it.
Every portal and every model is `partial` whatever its quality. So the Denpasar portal cell, the
Open-Meteo cells, and anything from a statistical API will sit at `partial` permanently and
correctly. Only Bali's own sensors can produce a green cell — which is the whole argument for the
node existing, and the reason the harvest alone was never going to light up the map.

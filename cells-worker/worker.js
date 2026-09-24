/**
 * FCI 3.0 — cells read-API (thin slice, S1 2026-06-06).
 * GET /api/cells/:city.json     → latest observation per cell from the Airtable spine.
 * GET /api/coverage.json        → the 61 Fab City localities × 8 per-territory cells, exported
 *                                 from the FCI Coverage Tracker in the same base.
 * v0 simplification of the architecture doc's §5.1 public read format. Read-only; the
 * full city-node (Postgres/FastAPI) replaces this post-methodology-v1 — same JSON shape.
 *
 * Setup:  wrangler secret put AIRTABLE_TOKEN   (scoped PAT: data.records:read on the base)
 *         set BASE_ID in wrangler.toml [vars] after creating the base
 *         wrangler deploy   → note the workers.dev URL for staging's live.js
 */
const TABLE = "Observations";
const ALLOWED_CITIES = ["barcelona", "boston", "santiago", "bali"];

/* ---- coverage: the locality list, exported from the tracker ------------------------------ */

const COVERAGE_TABLE = "FCI Coverage Tracker";

/* The 8 per-territory cells. Bioregion and Planet are harvested globally (Regime 2) and
   Community is node collection (Regime 3); neither is tracked per locality. */
const CELL_KEYS = ["Environmental", "Social", "Economic", "Governance"]
  .flatMap((p) => ["City", "Region"].map((sc) => `${p} | ${sc}`));

/* Registry ids, closed vocabulary on the first two segments. This constraint is the whole
   point: a bare /\w+\/\w+\/\S+/ also matches URL path fragments the harvest notes are full
   of (`fr/api/explore`, `hr/ckan/dataset`) and reports ~77 references that do not exist. */
const SLUG_RE =
  /\b(?:environmental|social|economic|governance)\/(?:planet|bioregion|region|city|community)\/[a-z0-9-]+\b/g;

/** A cell is one of three things, and they are NOT the same thing.
 *  found         — carries at least one registry id
 *  checked-empty — somebody looked and wrote down that there is nothing. 258 of these exist.
 *  blank         — nobody has looked yet
 *  `checked_empty` stays a separate flag because a cell can be both: a source was found AND
 *  the rest of the cell was checked and is empty (Zagreb Environmental|City is one). */
export function parseCell(text) {
  const raw = (text || "").trim();
  const slugs = [...new Set(raw.match(SLUG_RE) || [])].sort();
  const checkedEmpty = /checked-empty/i.test(raw);
  return {
    state: slugs.length ? "found" : checkedEmpty ? "checked-empty" : "blank",
    slugs,
    checked_empty: checkedEmpty,
    text: raw,
  };
}

/** tracker records → the v0 coverage document. Every count is derived here; none is a constant. */
export function mapCoverage(records) {
  const localities = records
    .map((r) => {
      const f = r.fields || {};
      const cells = {};
      for (const k of CELL_KEYS) cells[k] = parseCell(f[k]);
      const name = f.Locality || "";
      return {
        name,
        /* Derived, because the tracker has no id field — `Locality` is free text and the
           primary field. Emitted so the surfaces have a stable key instead of hardcoding
           names. NOTE: this does NOT join to /api/cells/{city}.json for every pilot —
           "Santiago de Chile" slugs to santiago-de-chile, and that API serves `santiago`.
           Three of the four pilots match; that one does not. Unresolved on purpose. */
        slug: name.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""),
        country: f.Country || "",
        territory: f.Territory || "",
        member_status: f["Member status"] || "",
        wave: f.Wave ?? null,
        wave_status: f["Wave status"] || "",
        admin_chain: f["Admin chain"] || "",
        portal_url: f["Portal URL"] || "",
        portal_type: f["Portal type"] || "",
        budget: {
          community: f["Budget \u00b7 community"] || "",
          city: f["Budget \u00b7 city"] || "",
          region: f["Budget \u00b7 region"] || "",
          national: f["Budget \u00b7 national"] || "",
        },
        cells,
        last_harvested: f["Last harvested"] || null,
      };
    })
    .sort((a, b) => a.name.localeCompare(b.name));

  const all = localities.flatMap((l) => CELL_KEYS.map((k) => l.cells[k]));
  const slugs = new Set(all.flatMap((c) => c.slugs));
  const harvested = localities.map((l) => l.last_harvested).filter(Boolean).sort();

  return {
    format: "fci-coverage-v0",
    generated_at: new Date().toISOString(),
    /* The freshness that matters. `generated_at` only says when this file was assembled;
       this says when a human last added anything to the thing it was assembled from. */
    last_harvested: harvested.length ? harvested[harvested.length - 1] : null,
    source_of_record: "Airtable · FCI Coverage Tracker (tbl9tfpEsxoxQAh0w)",
    note:
      "GENERATED EXPORT, one way. Airtable is the source of record for this table — the harvest " +
      "task writes it and git does not. Nothing may sync git into the Coverage Tracker. Values " +
      "here are read-only; to change one, change the tracker.",
    cell_keys: CELL_KEYS,
    counts: {
      localities: localities.length,
      cell_slots: all.length,
      found: all.filter((c) => c.state === "found").length,
      checked_empty: all.filter((c) => c.state === "checked-empty").length,
      blank: all.filter((c) => c.state === "blank").length,
      distinct_slugs: slugs.size,
      links: all.reduce((n, c) => n + c.slugs.length, 0),
    },
    localities,
  };
}

function corsHeaders(origin) {
  const ok =
    origin &&
    (/^http:\/\/localhost(:\d+)?$/.test(origin) ||
      /^https:\/\/([a-z0-9-]+\.)?fci-index\.pages\.dev$/.test(origin) ||
      origin === "https://index.fab.city" ||
      origin === "https://planetai.fab.city"); // fix 2026-06-08: observatory consumes the cells API (FC_Surface_Constellation §6)
  return {
    "Access-Control-Allow-Origin": ok ? origin : "https://index.fab.city",
    "Vary": "Origin",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Cache-Control": "public, max-age=300",
    "Content-Type": "application/json; charset=utf-8",
  };
}

/** newest record per cell key → v0 cells document */
export function mapRecords(city, records) {
  const cells = {};
  for (const r of records) {
    const f = r.fields || {};
    if ((f.city || "").toLowerCase() !== city) continue;
    const key = f.cell;
    if (!key) continue;
    const prev = cells[key];
    if (!prev || new Date(f.observed_at || 0) > new Date(prev.observed_at || 0)) {
      cells[key] = {
        value: f.value,
        unit: f.unit || "",
        source: f.source || "",
        observed_at: f.observed_at || null,
        state: (f.state || "mock").toLowerCase(),
        notes: f.notes || "",
      };
    }
  }
  return {
    city,
    format: "fci-cells-v0",
    generated_at: new Date().toISOString(),
    count: records.filter((r) => ((r.fields || {}).city || "").toLowerCase() === city).length,
    cells,
  };
}

export default {
  async fetch(req, env) {
    const origin = req.headers.get("origin");
    const headers = corsHeaders(origin);
    if (req.method === "OPTIONS") return new Response(null, { headers });

    const path = new URL(req.url).pathname;

    if (path === "/api/coverage.json") {
      const recs = [];
      let offset = "";
      /* 61 today, one page. Paginated anyway: the network grows, and pageSize=100 with no
         loop would silently serve the first 100 localities as if they were all of them. */
      do {
        const u =
          `https://api.airtable.com/v0/${env.BASE_ID}/${encodeURIComponent(COVERAGE_TABLE)}` +
          `?pageSize=100${offset ? `&offset=${encodeURIComponent(offset)}` : ""}`;
        const cr = await fetch(u, { headers: { Authorization: `Bearer ${env.AIRTABLE_TOKEN}` } });
        if (!cr.ok)
          return new Response(JSON.stringify({ error: "tracker unreachable", status: cr.status }), {
            status: 502,
            headers,
          });
        const cd = await cr.json();
        recs.push(...(cd.records || []));
        offset = cd.offset || "";
      } while (offset);
      return new Response(JSON.stringify(mapCoverage(recs), null, 1), { headers });
    }

    const m = path.match(/^\/api\/cells\/([a-z]+)\.json$/);
    if (!m || !ALLOWED_CITIES.includes(m[1]))
      return new Response(JSON.stringify({ error: "unknown city" }), { status: 404, headers });
    const city = m[1];

    const url =
      `https://api.airtable.com/v0/${env.BASE_ID}/${encodeURIComponent(TABLE)}` +
      `?pageSize=100&sort%5B0%5D%5Bfield%5D=observed_at&sort%5B0%5D%5Bdirection%5D=desc`;
    const r = await fetch(url, { headers: { Authorization: `Bearer ${env.AIRTABLE_TOKEN}` } });
    if (!r.ok)
      return new Response(JSON.stringify({ error: "spine unreachable", status: r.status }), { status: 502, headers });
    const data = await r.json();
    return new Response(JSON.stringify(mapRecords(city, data.records || []), null, 1), { headers });
  },
};

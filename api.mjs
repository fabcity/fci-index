// The public API, /api/v0/: every place's Fab City Index as static JSON (and one CSV), written at build time.
//
//   node api.mjs <site source dir> <out dir>
//
// Scores come from the same js/fci-score.js the pages run, on the registry as it is at build time. The pages
// recompute on the live registry, so a place's open-data count can be ahead of this file until the next deploy;
// every file says which registry it read (`registry_generated`).
//
// What the pipeline measured (compute/results/) is mapped to cells and indicators here, and nowhere else:
// MEASURED says which result is which cell's score s_c for which place. A result that is not in MEASURED
// reaches no score.
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const [site, out] = process.argv.slice(2);
if (!site || !out) { console.error("usage: node api.mjs <site source dir> <out dir>"); process.exit(2); }
const HERE = path.dirname(fileURLToPath(import.meta.url));
const RESULTS = "compute/results/fabcity-index-2019.json";
const REGISTRY = "https://raw.githubusercontent.com/fabcity/awesome-fabcity-data/main/index.json";
const TRACKER = "https://index.fab.city/api/coverage.json";
const BASE = "https://index.fab.city";
const REPO = "https://github.com/fabcity/fci-index/blob/main/";

// The site's weights and scoring, run as the browser runs them.
const ctx = { window: {} };
vm.createContext(ctx);
for (const f of ["js/data.js", "js/fci-score.js"]) vm.runInContext(fs.readFileSync(path.join(site, f), "utf8"), ctx, { filename: f });
const { FCI, FCI_SCORE } = ctx.window;
if (!FCI || !FCI_SCORE) throw new Error("js/data.js or js/fci-score.js did not load");

const results = JSON.parse(fs.readFileSync(path.join(HERE, RESULTS), "utf8"));
const get = async (u) => { const r = await fetch(u); if (!r.ok) throw new Error(`${u} returned ${r.status}`); return r.json(); };
const [registry, tracker] = await Promise.all([get(REGISTRY), get(TRACKER)]);

/* ---- what the pipeline measured, by place ------------------------------------------------------------ */
const place = (m, slug) => (m[slug] = m[slug] || { cells: {}, indicators: [], boundaries: [] });
const measured = {};

// Economic|Region: goods made in the region against what its households buy, with sales abroad taken out.
const goods = [
  ...results.barcelona_trade_adjusted.filter((b) => !b.no_data).map((b) => ({ slug: "barcelona", territory: "Catalonia", ref: "fabcity/fci-index#24", ...b })),
  ...[results.hamburg_trade_adjusted].filter((b) => !b.no_data).map((b) => ({ slug: "hamburg", territory: "Land Hamburg", ref: "fabcity/fci-index#23", ...b })),
  ...results.brazil_trade_adjusted.rows.map((b) => ({ slug: { "São Paulo": "sao-paulo", Recife: "recife" }[b.city], ref: "fabcity/fci-index#25", ...b })),
  ...(results.santiago_trade_adjusted ? results.santiago_trade_adjusted.rows : []).map((b) => ({ slug: "santiago-de-chile", ref: "fabcity/fci-index#29", ...b })),
];
const UPPER = { barcelona: "sales to the rest of Spain still count as local", hamburg: "sales to the rest of Germany still count as local; plants with 20 or more people only",
                "sao-paulo": "sales to the rest of Brazil still count as local; read as the state", recife: "sales to the rest of Brazil still count as local; read as Pernambuco state",
                "santiago-de-chile": "sales to the rest of Chile still count as local; read as the Región Metropolitana" };
// Places whose goods series change household survey between years: a trend across them is not like for like.
const SURVEY_BREAK = { "santiago-de-chile": "the two years use different household budget surveys (2016-17 and 2021-22) and product codes" };
for (const slug of new Set(goods.map((g) => g.slug))) {
  const series = goods.filter((g) => g.slug === slug).sort((a, b) => a.year - b.year);
  const last = series[series.length - 1];
  place(measured, slug).cells["Economic|Region"] = {
    s: Math.round(last.goods_trade_adjusted_index * 10) / 1000, year: last.year, territory: last.territory,
    what: "goods self-supply: the share of household goods spending the region's own industry could cover, with its sales abroad taken out (five open sectors)",
    caveat: `an upper bound: ${UPPER[slug]}`, source: last.source, licence: last.licence, pipeline: last.ref,
    series: series.map((g) => ({ year: g.year, s: Math.round(g.goods_trade_adjusted_index * 10) / 1000 })),
  };
  place(measured, slug).indicators.push({
    id: "goods-self-supply", label: "Goods self-supply, sales abroad taken out", unit: "index, 0-100", better: "higher",
    cell: "Economic|Region", territory: last.territory, caveat: `an upper bound: ${UPPER[slug]}` + (SURVEY_BREAK[slug] ? `; ${SURVEY_BREAK[slug]}` : ""),
    comparable_across_years: !SURVEY_BREAK[slug], source: last.source, pipeline: last.ref,
    series: series.map((g) => ({ year: g.year, value: g.goods_trade_adjusted_index })),
  });
}

// Environmental|City and |Region: residual municipal waste and separate collection. Not a cell score: no
// method turns kilograms into s_c yet, so these are indicators the report follows, never inputs to the FCI.
const WASTE = { Barcelona: ["barcelona", "City"], "Catalonia (region)": ["barcelona", "Region"], Paris: ["paris", "City"],
                "Santiago (comuna)": ["santiago-de-chile", "City"], "Region Metropolitana (region)": ["santiago-de-chile", "Region"], Hamburg: ["hamburg", "City"] };
for (const [name, [slug, scale]] of Object.entries(WASTE)) {
  const rows = results.trash_out.rows.filter((r) => r.city === name && !r.error).sort((a, b) => a.year - b.year);
  if (!rows.length) continue;
  const base = { cell: `Environmental|${scale}`, territory: name.replace(/ \((region|comuna)\)$/, ""), counts: rows[0].counts, source: rows[0].source, licence: rows[0].licence, pipeline: "fabcity/fci-index compute/waste.py" };
  const santiago = slug === "santiago-de-chile";
  const caveat = santiago ? "tonnes declared by operators; the total changes with who declares, so years are not comparable" : null;
  place(measured, slug).indicators.push(
    { id: `residual-waste-${scale.toLowerCase()}`, label: "Residual municipal waste per person", unit: "kg per person per year", better: "lower", caveat, comparable_across_years: !santiago, ...base,
      series: rows.filter((r) => r.residual_kg_per_capita != null).map((r) => ({ year: r.year, value: r.residual_kg_per_capita })) },
    { id: `recovery-${scale.toLowerCase()}`, label: "Share collected separately", unit: "% of municipal waste", better: "higher", caveat, comparable_across_years: !santiago, ...base,
      series: rows.filter((r) => r.recovery_share != null).map((r) => ({ year: r.year, value: Math.round(r.recovery_share * 1000) / 10 })) });
}

// Material use against a per-person safe level: the one planetary comparison with both sides sourced.
const SAFE_MATERIALS = { low: 6, high: 8, unit: "t per person per year",
  source: "UNEP International Resource Panel (2011), Decoupling natural resource use and environmental impacts from economic growth; Bringezu (2015), Resources 4(1)" };
const cfm = (results.material_flows ? results.material_flows.rows : []).filter((r) => !r.no_data && r.dmc_t_per_capita != null).sort((a, b) => a.year - b.year);
if (cfm.length) {
  const last = cfm[cfm.length - 1];
  const p = place(measured, "barcelona");
  p.indicators.push({ id: "material-use", label: "Domestic material consumption per person", unit: "t per person per year", better: "lower",
    cell: "Economic|Bioregion", territory: last.territory, counts: last.counts, source: last.source, licence: last.licence, pipeline: "fabcity/fci-index compute/trade.py materials()",
    caveat: "a floor on the footprint: imports count by their own weight, not the materials used to make them",
    series: cfm.map((r) => ({ year: r.year, value: r.dmc_t_per_capita })) });
  p.boundaries.push({ id: "material-use", boundary: "Resource extraction, a driver of land-system change and biosphere loss", label: "Material use",
    value: last.dmc_t_per_capita, year: last.year, unit: SAFE_MATERIALS.unit, territory: last.territory, measure: "domestic material consumption (DMC)",
    safe: [SAFE_MATERIALS.low, SAFE_MATERIALS.high], safe_source: SAFE_MATERIALS.source, value_is: "floor",
    reading: last.dmc_t_per_capita > SAFE_MATERIALS.high ? "over: even this floor is above the safe range"
           : "not conclusive: this floor is inside or under the safe range, and the full footprint (raw material equivalents) is not measured here",
    source: last.source });
}

// The planet's status, the same for every place. Status only: Richardson et al. publish control variables,
// not one comparable level, so no number is shown for them.
const PLANET = {
  source: "Richardson, K. et al. (2023), Earth beyond six of nine planetary boundaries, Science Advances 9(37), eadh2458",
  boundaries: [
    ["Climate change", "transgressed"], ["Biosphere integrity", "transgressed"], ["Land-system change", "transgressed"],
    ["Freshwater change", "transgressed"], ["Biogeochemical flows (nitrogen, phosphorus)", "transgressed"], ["Novel entities", "transgressed"],
    ["Ocean acidification", "close to the boundary"], ["Atmospheric aerosol loading", "within, regional exceedances"], ["Stratospheric ozone depletion", "within"],
  ].map(([label, status]) => ({ label, status })),
};

/* ---- scores ----------------------------------------------------------------------------------------------- */
const sources = FCI_SCORE.sourcesByPlace(registry);
const places = tracker.localities.map((l) => ({ slug: l.slug, name: l.name, country: l.country, territory: l.territory }));
const known = new Set(places.map((p) => p.slug));
const stray = Object.keys(measured).filter((s) => !known.has(s));
if (stray.length) throw new Error(`measured places not in the tracker: ${stray.join(", ")}`);

const now = new Date().toISOString();
const head = { format: "fci-api-v0", generated: now, registry_generated: registry.generated, tracker_harvested: tracker.last_harvested,
  pipeline: REPO + RESULTS, method: `${BASE}/method#worked`, licence: "Scores: CC BY 4.0, Fab City Foundation. Each input keeps its own licence, named where it is used." };
const summaries = [];
fs.mkdirSync(path.join(out, "places"), { recursive: true });
for (const p of places) {
  const m = measured[p.slug] || { cells: {}, indicators: [], boundaries: [] };
  const sc = FCI_SCORE.score(FCI, sources[p.slug], m.cells);
  // The label and the number must agree: a simulated place carries a range and no number, a scored one the product.
  const ok = sc.status === "simulated" ? sc.fci == null && sc.fci_range[0] === 0 && sc.fci_range[1] === sc.dido && !Object.keys(m.cells).length
                                       : Math.abs(sc.fci - sc.dido * sc.one_minus_pito) < 0.002 && sc.cells_measured === Object.keys(m.cells).length;
  if (!ok) throw new Error(`${p.slug}: score and label disagree (${JSON.stringify({ status: sc.status, fci: sc.fci, dido: sc.dido })})`);
  const actions = FCI_SCORE.actions(sc, p);
  const links = { page: `${BASE}/city?locality=${p.slug}`, report: `${BASE}/report?locality=${p.slug}`, json: `${BASE}/api/v0/places/${p.slug}.json` };
  const { cells, ...summary } = sc;
  summaries.push({ ...p, ...summary, links });
  fs.writeFileSync(path.join(out, "places", `${p.slug}.json`), JSON.stringify({ ...head, place: p, score: summary, actions,
    cells: cells.map((c) => ({ ...c, sources: c.sources.map((s) => s.id) })), indicators: m.indicators, boundaries: m.boundaries, planet: PLANET, links }, null, 1) + "\n");
}
const count = (s) => summaries.filter((x) => x.status === s).length;
if (count("complete") + count("partial") + count("simulated") !== places.length) throw new Error("statuses do not partition the places");
fs.writeFileSync(path.join(out, "index.json"), JSON.stringify({ ...head, counts: { places: places.length, complete: count("complete"), partial: count("partial"), simulated: count("simulated") },
  statuses: FCI_SCORE.STATUS, places: summaries }, null, 1) + "\n");
fs.writeFileSync(path.join(out, "measured.json"), JSON.stringify({ ...head, places: measured, planet: PLANET }, null, 1) + "\n");
const csvCell = (v) => (v == null ? "" : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v));
const COLS = ["slug", "name", "country", "territory", "status", "fci", "fci_low", "fci_high", "dido", "one_minus_pito", "rho", "cells_open", "cells_measured", "pito_weight_measured_share"];
fs.writeFileSync(path.join(out, "index.csv"), [COLS.join(","), ...summaries.map((s) => [s.slug, s.name, s.country, s.territory, s.status, s.fci,
  s.fci_range && s.fci_range[0], s.fci_range ? s.fci_range[1] : s.fci, s.dido, s.one_minus_pito, s.rho, s.cells_open, s.cells_measured,
  Math.round(1000 * s.pito_weight_measured[0] / s.pito_weight_measured[1]) / 1000].map(csvCell).join(","))].join("\n") + "\n");
console.log(`api v0: ${places.length} places (${count("partial")} partial, ${count("simulated")} simulated, ${count("complete")} complete) · registry ${registry.generated}`);

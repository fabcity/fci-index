// What the v1 proposal (graded DIDO, two indicators inside cells) would do to every place's score, beside v0.
//
//   node compute/v1_effect.mjs <site dir with the v1 data.js and fci-score.js>
//
// Reads the live /api/v0/ (the place list and the measured cells) and the registry at the commit that API was
// built from, so v0 here must equal production to the digit, and the script fails if it does not. Then it scores
// every place three ways: v0; v1 on day one, when no place has reported either indicator; and v1 if every place
// reported 1, which must give v0 back. Writes compute/results/v1-effect.json. Nothing here reaches the site.
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const [site] = process.argv.slice(2);
if (!site) { console.error("usage: node compute/v1_effect.mjs <site source dir>"); process.exit(2); }
const HERE = path.dirname(fileURLToPath(import.meta.url));
const API = "https://index.fab.city/api/v0";
const UA = { "user-agent": "Mozilla/5.0" };   // index.fab.city answers a bare client with a bot check

const ctx = { window: {} };
vm.createContext(ctx);
for (const f of ["js/data.js", "js/fci-score.js"]) vm.runInContext(fs.readFileSync(path.join(site, f), "utf8"), ctx, { filename: f });
const { FCI, FCI_SCORE } = ctx.window;
assert.ok(FCI.SUBINDICATORS_V1, "this data.js has no SUBINDICATORS_V1: point at the v1 branch");

const get = async (u) => { const r = await fetch(u, { headers: UA }); if (!r.ok) throw new Error(`${u} returned ${r.status}`); return r.json(); };
const [index, measured] = await Promise.all([get(`${API}/index.json`), get(`${API}/measured.json`)]);
const registry = await get(`https://raw.githubusercontent.com/fabcity/awesome-fabcity-data/${measured.registry_commit}/index.json`);
const src = FCI_SCORE.sourcesByPlace(registry);
const year = index.places[0].scored_in;

const touched = {};
Object.values(FCI.SUBINDICATORS_V1).forEach((d) => Object.entries(d.cells).forEach(([c, w]) => (touched[c] = (touched[c] || 0) + w)));
const all = (sub) => Object.fromEntries(Object.keys(FCI.SUBINDICATORS_V1).map((id) => [id, sub]));
const rows = index.places.map((p) => {
  const cells = (measured.places[p.slug] || { cells: {} }).cells;
  const v0 = FCI_SCORE.score(FCI, src[p.slug], cells, year);
  const day1 = FCI_SCORE.score(FCI, src[p.slug], cells, year, {});
  const full = FCI_SCORE.score(FCI, src[p.slug], cells, year, all({ value: 1, year }));
  // v0 here is production's v0, and an indicator every place reports at 1 changes nothing.
  // As JSON: arrays made inside the vm context have another realm's prototype, which deepEqual refuses.
  const same = (a, b, why) => assert.equal(JSON.stringify(a), JSON.stringify(b), why);
  same([v0.dido, v0.fci, v0.fci_range], [p.dido, p.fci, p.fci_range], `${p.slug}: v0 differs from production`);
  // Absence never raises a score and a report never lowers one. Where every touched cell is already open,
  // a full report is v0 exactly; where one is not, the report itself adds DIDO, which is the point of reporting.
  assert.ok(day1.dido <= v0.dido && full.dido >= v0.dido, `${p.slug}: v1 moved DIDO the wrong way`);
  if (Object.keys(touched).every((c) => (src[p.slug] || {})[c])) same([full.dido, full.fci], [v0.dido, v0.fci], `${p.slug}: v1 at full report is not v0`);
  const show = (s) => s.fci != null ? s.fci : s.fci_range;
  return { slug: p.slug, name: p.name, status: v0.status, cells_open: v0.cells_open,
           dido_v0: v0.dido, dido_v1_day_one: day1.dido, dido_change: Math.round((day1.dido - v0.dido) * 1000) / 1000, dido_v1_full_report: full.dido,
           fci_v0: show(v0), fci_v1_day_one: show(day1) };
});

// The arithmetic, by hand, for the one case it is easy to state: a place open in all five proposed cells loses
// sum over those cells of w_dido * (weight of the new indicators there), over the total DIDO weight.
const W = FCI.WEIGHTS, total = FCI.PILLARS.reduce((n, p) => n + FCI.SCALES.reduce((m, s) => m + W[p][s].dido, 0), 0);
const ceiling = Object.entries(touched).reduce((n, [c, w]) => { const [p, s] = c.split("|"); return n + W[p][s].dido * w; }, 0) / total;
const allFive = rows.filter((r) => Object.keys(touched).every((c) => (src[r.slug] || {})[c]));
allFive.forEach((r) => assert.ok(Math.abs(r.dido_change + ceiling) < 0.002, `${r.slug}: expected -${ceiling.toFixed(3)}`));

const out = {
  format: "fci-v1-effect-0", generated: new Date().toISOString(), scored_in: year,
  api_generated: index.generated, registry_commit: measured.registry_commit,
  reads_as: "Each place's DIDO and FCI under Method v0 (as published) and under the v1 proposal on the day it would start, "
          + "when no place has reported either new indicator, so both count 0 inside their cells. A simulated place's FCI is a range.",
  dido_weight_total: total, cells_touched: touched,
  largest_possible_dido_drop: Math.round(ceiling * 1000) / 1000,
  places_open_in_all_touched_cells: allFive.map((r) => r.slug),
  places_whose_dido_falls: rows.filter((r) => r.dido_change < 0).length,
  places: rows.sort((a, b) => a.dido_change - b.dido_change || a.slug.localeCompare(b.slug)),
};
// The ranking page's order: partial places by FCI, then simulated ones by the top of their range. Equal scores share a rank.
const rank = (key) => {
  const top = (r) => Array.isArray(r[key]) ? r[key][1] : r[key];
  const band = (r) => (r.status === "simulated" ? 1 : 0);
  const sorted = [...rows].sort((a, b) => band(a) - band(b) || top(b) - top(a));
  return Object.fromEntries(sorted.map((r) => [r.slug, 1 + sorted.findIndex((q) => band(q) === band(r) && top(q) === top(r))]));
};
const [r0, r1] = [rank("fci_v0"), rank("fci_v1_day_one")];
rows.forEach((r) => Object.assign(r, { rank_v0: r0[r.slug], rank_v1_day_one: r1[r.slug] }));
out.rank_changes = rows.filter((r) => r.rank_v0 !== r.rank_v1_day_one).map((r) => ({ slug: r.slug, from: r.rank_v0, to: r.rank_v1_day_one }));
fs.mkdirSync(path.join(HERE, "results"), { recursive: true });
fs.writeFileSync(path.join(HERE, "results", "v1-effect.json"), JSON.stringify(out, null, 1) + "\n");

const f = (x) => Array.isArray(x) ? `${x[0]}–${x[1]}` : x.toFixed(3);
console.log(`v0 matches production for all ${rows.length} places (API ${index.generated}, registry ${measured.registry_commit.slice(0, 7)})`);
console.log(`rank changes: ${out.rank_changes.map((c) => `${c.slug} ${c.from}→${c.to}`).join(", ") || "none"}`);
console.log(`DIDO falls for ${out.places_whose_dido_falls} of ${rows.length}; at most ${out.largest_possible_dido_drop} (open in all five cells: ${allFive.length})`);
for (const r of out.places.filter((r) => r.dido_change < 0))
  console.log(`  ${r.name.padEnd(24)} ${r.status.padEnd(9)} DIDO ${r.dido_v0.toFixed(3)} → ${r.dido_v1_day_one.toFixed(3)}   FCI ${f(r.fci_v0)} → ${f(r.fci_v1_day_one)}`);

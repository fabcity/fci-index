/**
 * node test.mjs   — exits non-zero if the parse breaks.
 *
 * The fixtures are verbatim excerpts of real Coverage Tracker rows (read 2026-09-24), not
 * invented text, because every trap in this parser is a thing the harvest notes actually do.
 */
import assert from "node:assert/strict";
import { parseCell, mapCoverage } from "./worker.js";

/* ---- parseCell: the three states are three different things ---------------------------- */

// Zagreb · Governance|Region — a found source whose prose is full of URL path fragments.
const zagrebGovReg = `FOUND. slug governance/region/data-gov-hr
https://data.gov.hr/ckan/dataset

National CKAN. API base is /ckan/api/3/action/* - the domain-root path silently redirects.
LICENCE REGIME, license_id facet read 2026-09-11: open-license 2,998, cc-by 312.

checked-empty: no joint procurement, inter-municipal agreements or policy-harmonisation
instruments found as datasets.`;

const zg = parseCell(zagrebGovReg);
assert.deepEqual(zg.slugs, ["governance/region/data-gov-hr"], "one slug, and only one");
assert.equal(zg.state, "found");
// The cell is BOTH: a source was found and the rest of the cell was checked and is empty.
assert.equal(zg.checked_empty, true, "a found cell can also carry a checked-empty finding");

// The trap. `hr/ckan/dataset` is a URL path, not a registry id. A bare \w+/\w+/\S+ regex
// reports ~77 of these as broken references; the closed vocabulary is what makes it zero.
assert.ok(!zg.slugs.some((s) => s.includes("ckan")), "URL path fragments are not registry ids");
for (const trap of ["fr/api/explore", "hr/ckan/dataset", "en/dataset/foo", "v1/api/bar"]) {
  assert.deepEqual(parseCell(`see https://x.example/${trap}`).slugs, [], `not a slug: ${trap}`);
}

// Amsterdam · Governance|Region — two sources in one cell, numbered prose.
const amsGovReg = `FOUND, two sources.

1. slug governance/region/data-overheid-nl - https://data.overheid.nl/
The national register, run by KOOP. Licence CC-0.

2. slug governance/region/tenderned-aankondigingen - https://data.overheid.nl/dataset/...
Every Dutch public procurement notice, publisher PIANOo, licence CC-0 (1.0).

checked-empty: no joint procurement instrument specific to Noord-Holland.`;

assert.deepEqual(
  parseCell(amsGovReg).slugs,
  ["governance/region/data-overheid-nl", "governance/region/tenderned-aankondigingen"],
  "both sources, deduped and sorted",
);

// Sao Paulo · Environmental|City — checked, genuinely nothing. This is a RESULT, not a gap.
const spEnvCity = `checked-empty: nothing Sao Paulo-published is reachable. Checked for
MFA/material consumption, recycling rate and waste tonnage, GPC GHG inventory, renewable
share, green space per capita, PM2.5 stations. All would sit on the city portal, which is
robots-disallowed.`;

const sp = parseCell(spEnvCity);
assert.equal(sp.state, "checked-empty");
assert.deepEqual(sp.slugs, []);
assert.ok(sp.text.length > 0, "the prose IS the finding — what was checked must survive");

// Accra · Social|City — REAL TEXT, and the regression that matters most in this file.
// Prose, no registry id, no checked-empty marker. An earlier three-state parser dropped this
// to `blank`, rendering 60 cells that carry real findings as "nobody has looked". The whole
// point of this export is that absence is honest; calling a paragraph absence is the worst
// failure available to it.
const accraSocCity = `Data EXISTS and is machine-readable; OPENLY LICENSED = NO. Three separate
answers, kept separate. data.gov.gh (CKAN, 531 packages) holds district- and region-resolved
social indicators, but the catalogue carries no open licence.`;

const ac = parseCell(accraSocCity);
assert.equal(ac.state, "noted", "prose with no slug and no marker is a FINDING, not a gap");
assert.deepEqual(ac.slugs, []);
assert.equal(ac.checked_empty, false);
assert.ok(ac.text.includes("OPENLY LICENSED = NO"), "the finding survives");

// Nobody has looked. Distinct from checked-empty AND from noted, and must render differently.
for (const blank of [undefined, null, "", "   "]) {
  const b = parseCell(blank);
  assert.equal(b.state, "blank", `blank: ${JSON.stringify(blank)}`);
  assert.equal(b.checked_empty, false);
}

// A slug appearing twice in one cell is one link, not two.
assert.deepEqual(
  parseCell("economic/city/x and again economic/city/x").slugs,
  ["economic/city/x"],
  "deduped within a cell",
);

/* ---- mapCoverage: counts are derived, and all 8 cells always exist --------------------- */

const doc = mapCoverage([
  {
    fields: {
      Locality: "Zagreb",
      Country: "Croatia",
      Territory: "City",
      "Member status": "Active",
      "Wave status": "done",
      "Portal URL": "https://data.zagreb.hr/dataset",
      "Last harvested": "2026-09-11",
      "Governance | Region": zagrebGovReg,
      "Environmental | City": "FOUND. slug environmental/city/zagreb-geoportal-kvaliteta-zraka",
    },
  },
  {
    fields: {
      Locality: "Amsterdam",
      Country: "Netherlands",
      "Last harvested": "2026-09-12",
      "Governance | Region": amsGovReg,
      "Environmental | City": spEnvCity,
      "Social | City": accraSocCity,
    },
  },
]);

assert.equal(doc.format, "fci-coverage-v0");
assert.equal(doc.counts.localities, 2);
assert.equal(doc.counts.cell_slots, 16, "2 localities x 8 cells, always — no ragged rows");
assert.equal(Object.keys(doc.localities[0].cells).length, 8);
assert.equal(doc.localities[0].name, "Amsterdam", "sorted by name");
assert.equal(doc.localities[0].slug, "amsterdam");

// The join key the tracker does not have. Pinned so the mismatch is visible, not discovered
// again in six months: the readings API serves `santiago`, the tracker says "Santiago de Chile".
assert.equal(mapCoverage([{ fields: { Locality: "Santiago de Chile" } }]).localities[0].slug,
  "santiago-de-chile", "does NOT equal the readings API's `santiago` — unresolved, see README");
assert.equal(mapCoverage([{ fields: { Locality: "Sao Paulo" } }]).localities[0].slug, "sao-paulo");

// Accents FOLD, they do not become separators. The harvest ASCII-folded every name it
// wrote, so this was invisible until "Auvergne-Rone-Alpes" was corrected to its real
// spelling in the tracker and slugged to `auvergne-rh-ne-alpes` — a locality the atlas
// would then silently fail to place, because its coordinate is keyed on the slug.
for (const [name, want] of [
  ["Auvergne-Rh\u00f4ne-Alpes", "auvergne-rhone-alpes"],
  ["S\u00e3o Paulo", "sao-paulo"],
  ["C\u00f3rdoba", "cordoba"],
  ["Malm\u00f6", "malmo"],
]) {
  assert.equal(mapCoverage([{ fields: { Locality: name } }]).localities[0].slug, want,
    `${name} must fold, not split`);
}

// 3 found, 1 checked-empty, 1 noted, 11 blank.
assert.equal(doc.counts.found, 3);
assert.equal(doc.counts.checked_empty, 1);
assert.equal(doc.counts.noted, 1);
assert.equal(doc.counts.blank, 11);
// The four states partition the slots exactly. If this ever fails, a cell is being counted
// twice or lost — which is how the `noted` bug hid.
assert.equal(
  doc.counts.found + doc.counts.checked_empty + doc.counts.noted + doc.counts.blank,
  doc.counts.cell_slots,
  "the four states partition the cell slots",
);

// 4 distinct slugs, 4 links (no slug is shared between these two rows).
assert.equal(doc.counts.distinct_slugs, 4);
assert.equal(doc.counts.links, 4);

// The freshness stamp that means something: the newest harvest, not the build time.
assert.equal(doc.last_harvested, "2026-09-12", "max across rows, not the first row");
assert.ok(doc.note.includes("source of record"), "the payload says which way the sync runs");

console.log("ok — parse, four states, closed vocabulary, derived counts");

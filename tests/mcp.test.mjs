// node --test tests/mcp.test.mjs: the MCP server knows the fourteen readings, and states them as the place page does
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import * as MCP from "../functions/mcp.js";

// the place page's own state logic, from the sibling repo (the path is built in two parts)
const CD = createRequire(import.meta.url)(fileURLToPath(new URL("../../" + "fci-ingestion-tool/js/city-data.js", import.meta.url)));
const R = (n) => ({ id: "R" + n, name: "Reading " + n, plain: "What " + n + " asks", unit: "t/yr", years: [2023, 2024, 2025], held_by: "City office",
  prompt: "Look for {reading_name} in {place_name} ({place_slug}), for {years}, in {unit}." });
const fig = (state) => ({ year: 2025, state, value: 1, unit: "t/yr" });
const REG = {
  readings: [1, 2, 3, 4, 5, 6, 7].map(R),
  places: [{ slug: "x", name: "Xville", country: "X" }, { slug: "y", name: "Yton", country: "Y" }],
  fictional: [{ slug: "uqbar", name: "Uqbar" }],
  observations: [{ place: "x", reading: "R1", figures: [fig("live")] }, { place: "x", reading: "R2", figures: [fig("candidate")] },
    { place: "x", reading: "R3", figures: [{ year: 2025, state: "held" }] }, { place: "x", reading: "R4", figures: [{ year: 2025, state: "not-held" }] }],
  entries: [{ id: "a/b/c", name: "C", status: "candidate", places: ["x"], tags: ["city-sent", "reading-r5"] },
    { id: "a/b/d", name: "D", status: "live", places: ["x", "y"], tags: ["reading-r6"] }],
};

test("the reading tools and the find_reading prompt are listed", () => {
  for (const t of ["list_readings", "get_reading"]) assert.ok(MCP.TOOLS.some((x) => x.name === t), t);
  assert.ok(MCP.PROMPTS.some((p) => p.name === "find_reading"));
  assert.match(MCP.INSTRUCTIONS, /fourteen readings/);
});

test("every reading's state for every place is the place page's state", () => {
  for (const p of ["x", "y"]) for (const r of REG.readings) assert.equal(MCP.statusFor(r, p, REG), CD.statusFor(r, p, REG), `${p} ${r.id}`);
  assert.deepEqual(REG.readings.map((r) => MCP.statusFor(r, "x", REG)),
    ["checked", "figure sent", "held by the city", "not held anywhere", "source sent", "in the registry, to review", "not looked for yet"]);
});

test("get_reading gives one reading for one place with its brief and the page to send it from", () => {
  const out = MCP.readingFor(REG, "x", "R2");
  assert.equal(out.state, "figure sent"); assert.equal(out.answered, true); assert.equal(out.figures.length, 1);
  assert.equal(out.brief, CD.promptFor(REG.readings[1], REG.places[0]));
  assert.equal(out.send, "https://index.fab.city/operate/city-data?place=x#R2");
  assert.deepEqual(MCP.readingFor(REG, "x", "R6").sources.map((s) => s.id), ["a/b/d"]);
});

test("without a reading, all of them for the place; an unknown place or reading says what exists", () => {
  const all = MCP.readingFor(REG, "x");
  assert.equal(all.readings.length, 7); assert.equal(all.answered, 5);
  assert.throws(() => MCP.readingFor(REG, "nowhere"), /no place/); assert.throws(() => MCP.readingFor(REG, "x", "R99"), /R1 to R7/);
});

test("find_reading for a whole place names only the readings it has not answered", () => {
  const t = MCP.findReadingText(REG, "x");
  assert.match(t, /R6/); assert.match(t, /R7/); assert.doesNotMatch(t, /\bR1\b|\bR2\b/);
  assert.match(t, /get_reading/); assert.match(t, /file nothing/i);
  assert.equal(MCP.findReadingText(REG, "x", "R7"), CD.promptFor(REG.readings[6], REG.places[0]));
});

test("over JSON-RPC, get_reading and find_reading answer from the collection", async () => {
  const real = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify(REG), { status: 200, headers: { "content-type": "application/json" } });
  try {
    const rpc = async (method, params) => (await (await MCP.onRequest({ request: new Request("https://index.fab.city/mcp", { method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" }, body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }) }) })).json()).result;
    assert.ok((await rpc("tools/list", {})).tools.some((t) => t.name === "get_reading"));
    assert.equal(JSON.parse((await rpc("tools/call", { name: "get_reading", arguments: { place: "x", reading: "R2" } })).content[0].text).state, "figure sent");
    assert.match((await rpc("prompts/get", { name: "find_reading", arguments: { place: "x" } })).messages[0].content.text, /Still open, 2 of 7/);
  } finally { globalThis.fetch = real; }
});

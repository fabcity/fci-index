/* The Fab City Index as an MCP server, for whichever agent a person already uses.
   POST /mcp is a stateless Streamable HTTP endpoint (JSON-RPC 2.0): initialize, tools/list, tools/call,
   prompts/list, prompts/get, ping. Everything it answers is read from the site's own open API and the
   public registry on every call, so it is never a second copy of either. No account, no session, no
   writes: a source is still filed by a person, from the add-source page or their own GitHub account.
   GET /mcp says how to connect. */
const PROTOCOL = "2025-06-18";
const SITE = "https://index.fab.city";
const REGISTRY = "https://raw.githubusercontent.com/fabcity/awesome-fabcity-data/main/index.json";
const PILLARS = ["Environmental", "Social", "Economic", "Governance"];
const SCALES = ["Community", "City", "Region", "Bioregion", "Planet"];

const INSTRUCTIONS = `The Fab City Index measures how far each of 61 pledged cities and regions has got toward making
what it consumes, across twenty cells (four pillars by five scales). Scores are CC BY 4.0; each source keeps its
own licence. Rules an answer must keep: a "simulated" place has a range [0, DIDO], never one number; absence is not
zero (a cell with no source, one checked and found empty, one nobody looked at, and one not followed per place are
four different states); a cell can hold several sources, so "N of 20" counts cells, never sources. To improve a
place's data, a person files a candidate source (prompt add_source) or reads one for a real place (prompt
review_source); you do the research, they file it in their name.`;

const TOOLS = [
  { name: "list_places", description: "Every place in the Index with its status (complete, partial, simulated), index or range, and DIDO.",
    inputSchema: { type: "object", properties: { status: { type: "string", enum: ["complete", "partial", "simulated"] } } } },
  { name: "get_place", description: "One place: its score and label, its twenty cells with the sources that name it, what would move it, and why it has no number if it is blocked.",
    inputSchema: { type: "object", properties: { slug: { type: "string", description: "The place's slug, e.g. barcelona, santiago-de-chile" } }, required: ["slug"] } },
  { name: "list_sources", description: "Registered open-data sources, filtered by place, Index cell (Pillar|Scale), status or a search word.",
    inputSchema: { type: "object", properties: { place: { type: "string" }, cell: { type: "string", description: "e.g. Economic|Region" },
      status: { type: "string", enum: ["candidate", "live", "stale", "paywalled", "deprecated", "planned"] }, q: { type: "string" } } } },
  { name: "get_source", description: "One registry entry in full, with the definitions of the cells it feeds and its reviews.",
    inputSchema: { type: "object", properties: { id: { type: "string", description: "pillar/scale/slug, e.g. environmental/city/openaq" } }, required: ["id"] } },
  { name: "review_queue", description: "Sources waiting on a reader: candidates first. Filter by place to get what a city champion can review.",
    inputSchema: { type: "object", properties: { place: { type: "string" } } } },
  { name: "cell_definition", description: "What one Index cell requires (minimum indicators) and what it must not claim.",
    inputSchema: { type: "object", properties: { cell: { type: "string", description: "Pillar|Scale, e.g. Social|City" } }, required: ["cell"] } },
  { name: "how_to_contribute", description: "The two ways to improve a place's data, the pages that do it, and the four rules for agent-assisted work.",
    inputSchema: { type: "object", properties: {} } },
];

const PROMPTS = [
  { name: "review_source", description: "Read one registered source for a real place and write the review the person files.",
    arguments: [{ name: "entry", description: "registry id, e.g. environmental/city/openaq", required: true },
                { name: "territory", description: "the real place it is read for", required: true }] },
  { name: "add_source", description: "Find an open dataset for an empty cell of a place and write the candidate entry the person files.",
    arguments: [{ name: "place", description: "the place's slug", required: true }, { name: "cell", description: "Pillar|Scale; omit to pick an empty one", required: false }] },
];

async function getJSON(url) {
  const r = await fetch(url, { headers: { accept: "application/json", "user-agent": "fci-mcp/0.1" }, cf: { cacheTtl: 300, cacheEverything: true } });
  if (!r.ok) throw new Error(`${url} answered ${r.status}`);
  return r.json();
}
const registry = () => getJSON(REGISTRY);
const trimEntry = (e) => ({ id: e.id, name: e.name, status: e.status, url: e.url, api: e.api || null, license: e.license,
  pillar: e.pillar, scale: e.scale, feeds_cells: e.feeds_cells || [], places: e.places || [], auth: e.auth || "none",
  reviews: (e.reviews || []).length, review_url: `${SITE}/operate/source-review?entry=${encodeURIComponent(e.id)}` });
const names = (e, place) => (e.places || []).includes(place) || (e.pilot_relevance || []).some((p) => p === place || (p === "santiago" && place === "santiago-de-chile"));

async function call(name, a = {}) {
  switch (name) {
    case "list_places": {
      const d = await getJSON(`${SITE}/api/v0/index.json`);
      const rows = (d.places || d).filter((p) => !a.status || p.status === a.status);
      return { generated: d.generated, count: rows.length, places: rows };
    }
    case "get_place": {
      const slug = String(a.slug || "").toLowerCase().trim();
      const d = await getJSON(`${SITE}/api/v0/places/${encodeURIComponent(slug)}.json`).catch(() => null);
      if (!d || d.format !== "fci-api-v0") throw new Error(`no place with the slug "${slug}"; list_places has every slug`);
      return { place: d.place, score: d.score, cells: d.cells, actions: d.actions, blocked: d.blocked, links: d.links,
               profile: `${SITE}/city?locality=${slug}`, review_queue: `${SITE}/operate/source-review?locality=${slug}`,
               add_source: `${SITE}/operate/add-source?locality=${slug}` };
    }
    case "list_sources": {
      const reg = await registry();
      const q = (a.q || "").toLowerCase();
      const rows = reg.entries.filter((e) =>
        (!a.place || names(e, a.place)) && (!a.cell || (e.feeds_cells || []).includes(a.cell)) && (!a.status || e.status === a.status) &&
        (!q || `${e.name} ${e.id} ${e.license} ${(e.tags || []).join(" ")}`.toLowerCase().includes(q))).map(trimEntry);
      return { registry_generated: reg.generated, count: rows.length, sources: rows };
    }
    case "get_source": {
      const reg = await registry();
      const e = reg.entries.find((x) => x.id === a.id);
      if (!e) throw new Error(`no entry with the id "${a.id}"; ids are pillar/scale/slug`);
      const cells = (reg.cells || []).filter((c) => (e.feeds_cells || []).includes(c.cell));
      return { entry: e, cells, review_url: `${SITE}/operate/source-review?entry=${encodeURIComponent(e.id)}` };
    }
    case "review_queue": {
      const reg = await registry();
      const usable = (e) => !!e.adapter || (e.reviews || []).some((r) => r.verdict === "usable" || r.verdict === "usable-with-caveats");
      const rows = reg.entries.filter((e) => (e.status === "candidate" || (e.status === "live" && !usable(e))) && (!a.place || names(e, a.place)))
        .sort((x, y) => (x.status === "candidate" ? 0 : 1) - (y.status === "candidate" ? 0 : 1)).map(trimEntry);
      return { count: rows.length, candidates: rows.filter((r) => r.status === "candidate").length, queue: rows,
               page: `${SITE}/operate/source-review${a.place ? `?locality=${encodeURIComponent(a.place)}` : ""}` };
    }
    case "cell_definition": {
      const reg = await registry();
      const c = (reg.cells || []).find((x) => x.cell === a.cell);
      if (!c) throw new Error(`no cell "${a.cell}"; cells are ${PILLARS.map((p) => `${p}|<scale>`).join(", ")} with scales ${SCALES.join(", ")}`);
      return c;
    }
    case "how_to_contribute":
      return { text: HOW };
    default:
      throw new Error(`unknown tool ${name}`);
  }
}

const HOW = `Two ways to improve a place's data, both filed by a person in their own name.

1. Review a source: read one registered source for a real place and record what you found (licence, endpoint,
   admin-code, vintage, field-fit) with a verdict: usable, usable-with-caveats or unusable. A usable verdict turns a
   candidate live. Page: ${SITE}/operate/source-review?locality=<slug>. Guide: https://github.com/fabcity/awesome-fabcity-data/blob/main/REVIEWING.md

2. Add a source: find an open dataset for an empty cell of a place and file it as a candidate. Page:
   ${SITE}/operate/add-source?locality=<slug>. Guide: https://github.com/fabcity/awesome-fabcity-data/blob/main/CONTRIBUTING.md

Four rules when an agent helps: the person is the contributor and files it; name the agent in "assisted by"; an
agent files a candidate, never live; evidence, not claims: every licence sentence and figure is one you read at
the publisher, with the URL. Both pages take the agent's reply pasted back and fill the form from it.`;

function prompt(name, a = {}) {
  if (name === "review_source") return [{ role: "user", content: { type: "text", text:
`Review one source for the Fab City Index registry (github.com/fabcity/awesome-fabcity-data), for ${a.territory || "<territory>"}.
I am the reviewer and responsible for the verdict: do the work, show me your findings and the finished review, and file nothing until I say so.

Entry: ${a.entry || "<entry id>"}. Call get_source with that id for the entry and the cells it feeds.

Do these five checks and report each as done or not done, with what you found:
- licence: read the publisher's terms, not the registry's license field. Watch for the four shapes that are not open: split by component, open only after a date, named like an open licence but forbidding commercial use, data governed differently from the website it sits on.
- endpoint: fetch it and look inside the response. HTTP 200 is not the check.
- admin-code: do its identifiers join to ${a.territory || "the territory"}'s own codes (INE, IBGE, INEGI, FIPS, ISO 3166-2, BPS, SIREN)?
- vintage: how old is the newest record, and how often does it actually move?
- field-fit: can it produce the cell's minimum indicators?

Then write the review in exactly this shape, ticking only the checks you did, with usable, usable-with-caveats or unusable as the verdict, yourself in Assisted by, and notes under 2,000 characters:

### Entry
${a.entry || "<entry id>"}
### Your name
_No response_
### Organisation
_No response_
### Date you read it
<YYYY-MM-DD>
### Territory you read it for
${a.territory || "<territory>"}
### What you checked
- [ ] licence
- [ ] endpoint
- [ ] admin-code
- [ ] vintage
- [ ] field-fit
### Verdict
<usable | usable-with-caveats | unusable>
### Self-declared
- [ ] My organisation publishes this source
### Assisted by
<your name, e.g. Claude>
### Notes for the next reader
<what a reader must know first>

Reply with the review in that shape and nothing after it. I paste it into ${SITE}/operate/source-review and file it myself. Never put yourself in Your name.` } }];
  if (name === "add_source") return [{ role: "user", content: { type: "text", text:
`Find and write up one open-data source for the Fab City Index registry, for ${a.place || "<place slug>"}. I am the contributor: you do the research, show me the entry and the evidence, and file nothing.

1. Call get_place with the slug. ${a.cell ? `The cell is ${a.cell}.` : "Pick a cell whose sources list is empty; prefer one with a high DIDO weight."} Call cell_definition for what it requires and must not claim.
2. Search for a dataset that fits that cell for the place. Prefer the publisher's own site or API. Call list_sources to make sure it is not registered already.
3. Verify and write down what you read: the licence quoted from the publisher's own terms page (URL and the key sentence; if it is not open, stop and tell me); the endpoint, fetched, with two or three real figures for the place and their year; that the data names the place itself (its official code or name).
4. Write the entry in exactly this shape, one answer under each heading, status candidate, yourself in Assisted by:

### Name
### Home URL
### API or download URL
### Description
<one or two sentences, under 320 characters>
### Cell
<Pillar|Scale>
### Licence
<as the publisher states it, or "not stated">
### Authentication
<none | key-free-rate-limited | api-key | registration | paid>
### Places
${a.place || "<place slug>"}
### Tags
<comma-separated>
### Assisted by
<your name>
### Notes
VERIFIED: <date, what you opened>
LICENCE: <URL and the sentence>
ENDPOINT: <URL, what it returned, two or three figures with their year>
WHY THIS CELL: <which minimum indicator it carries>
WHAT IT DOES NOT CLAIM: <the limits>

Reply with that and nothing after it. I paste it into ${SITE}/operate/add-source and send it in my name.` } }];
  throw new Error(`unknown prompt ${name}`);
}

const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "content-type, accept, mcp-session-id, mcp-protocol-version, authorization" };
const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { ...CORS, "content-type": "application/json" } });
const rpcError = (id, code, message) => ({ jsonrpc: "2.0", id: id ?? null, error: { code, message } });

async function handle(msg) {
  if (!msg || msg.jsonrpc !== "2.0" || typeof msg.method !== "string") return rpcError(msg && msg.id, -32600, "not a JSON-RPC 2.0 request");
  const { id, method, params = {} } = msg;
  if (method.startsWith("notifications/")) return null;
  try {
    let result;
    switch (method) {
      case "initialize": result = { protocolVersion: PROTOCOL, capabilities: { tools: {}, prompts: {} },
        serverInfo: { name: "fab-city-index", version: "0.1" }, instructions: INSTRUCTIONS }; break;
      case "ping": result = {}; break;
      case "tools/list": result = { tools: TOOLS }; break;
      case "tools/call": {
        if (!TOOLS.some((t) => t.name === params.name)) return rpcError(id, -32602, `unknown tool ${params.name}`);
        try { const out = await call(params.name, params.arguments || {});
              result = { content: [{ type: "text", text: typeof out === "string" ? out : JSON.stringify(out, null, 1) }] }; }
        catch (e) { result = { content: [{ type: "text", text: String(e.message || e) }], isError: true }; }
        break;
      }
      case "prompts/list": result = { prompts: PROMPTS }; break;
      case "prompts/get": {
        if (!PROMPTS.some((p) => p.name === params.name)) return rpcError(id, -32602, `unknown prompt ${params.name}`);
        result = { description: PROMPTS.find((p) => p.name === params.name).description, messages: prompt(params.name, params.arguments || {}) }; break;
      }
      default: return rpcError(id, -32601, `method not found: ${method}`);
    }
    return { jsonrpc: "2.0", id, result };
  } catch (e) {
    return rpcError(id, -32603, String(e.message || e));
  }
}

export async function onRequest({ request }) {
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });
  if (request.method === "GET") {
    if ((request.headers.get("accept") || "").includes("text/event-stream")) return new Response("this server has no server-to-client stream; POST JSON-RPC here", { status: 405, headers: CORS });
    return json({ name: "fab-city-index", transport: "streamable-http", endpoint: `${SITE}/mcp`, protocolVersion: PROTOCOL,
      tools: TOOLS.map((t) => t.name), prompts: PROMPTS.map((p) => p.name), how_to_connect: `${SITE}/operate/agent`,
      claude_code: `claude mcp add --transport http fab-city-index ${SITE}/mcp`, data: `${SITE}/api/v0/`, llms: `${SITE}/llms.txt` });
  }
  if (request.method !== "POST") return new Response("POST JSON-RPC 2.0", { status: 405, headers: CORS });
  let body;
  try { body = await request.json(); } catch { return json(rpcError(null, -32700, "parse error"), 400); }
  const batch = Array.isArray(body);
  const answers = (await Promise.all((batch ? body : [body]).map(handle))).filter(Boolean);
  if (!answers.length) return new Response(null, { status: 202, headers: CORS });
  return json(batch ? answers : answers[0]);
}

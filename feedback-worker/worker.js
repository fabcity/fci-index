/**
 * FCI 3.0 beta — tier-3 feedback endpoint (2026-06-06).
 * POST /api/feedback  { who, tier, page, cell, text }  →  Airtable "FCI Beta Feedback".
 * Airtable is the canonical FC data layer until ~mid-2027 — feedback lands where ops already works.
 * Deploy: wrangler secret put AIRTABLE_TOKEN && wrangler deploy
 * Set BASE_ID / TABLE below after creating the base.
 */
const BASE_ID = "appXXXXXXXXXXXXXX"; // ← create base "FCI Beta Feedback", paste id
const TABLE = "Feedback";
const RATE = new Map(); // naive per-isolate rate limit; fine for ~12 beta humans

export default {
  async fetch(req, env) {
    const cors = {
      "Access-Control-Allow-Origin": "https://index.fab.city",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "content-type",
    };
    if (req.method === "OPTIONS") return new Response(null, { headers: cors });
    if (req.method !== "POST" || new URL(req.url).pathname !== "/api/feedback")
      return new Response("not found", { status: 404, headers: cors });

    const ip = req.headers.get("cf-connecting-ip") || "?";
    const now = Date.now();
    if (now - (RATE.get(ip) || 0) < 15_000)
      return new Response(JSON.stringify({ ok: false, err: "slow down" }), { status: 429, headers: cors });
    RATE.set(ip, now);

    let b;
    try { b = await req.json(); } catch { return new Response("bad json", { status: 400, headers: cors }); }
    if (b.website) return new Response(JSON.stringify({ ok: true }), { headers: cors }); // honeypot
    const text = String(b.text || "").slice(0, 4000);
    if (!text) return new Response("empty", { status: 400, headers: cors });

    const r = await fetch(`https://api.airtable.com/v0/${BASE_ID}/${encodeURIComponent(TABLE)}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${env.AIRTABLE_TOKEN}`, "Content-Type": "application/json" },
      body: JSON.stringify({ records: [{ fields: {
        Who: String(b.who || "anonymous").slice(0, 200),
        Tier: String(b.tier || "3").slice(0, 10),
        Page: String(b.page || "").slice(0, 300),
        Cell: String(b.cell || "").slice(0, 100),
        Text: text,
        When: new Date().toISOString(),
      }}]}),
    });
    return new Response(JSON.stringify({ ok: r.ok }), { status: r.ok ? 200 : 502, headers: cors });
  },
};

/* POST /api/submit: a review or a candidate source, written out on the site, becomes a GitHub issue in
   awesome-fabcity-data without the person needing a GitHub account. The issue is opened by the Index's own
   token (a Pages secret, GITHUB_TOKEN, scoped to issues on that one repository); the person's name and
   organisation are in the body, which is the same shape the registry's workflows parse. Both become pull
   requests by themselves: a review titled "review: <entry>" through review-to-pr.yml, a source titled
   "source: <id>" through source-to-pr.yml (awesome-fabcity-data#109), which writes the candidate entry from
   the fields and only cross-checks the "### Entry (YAML)" block. Without the secret this answers 503, and the
   pages fall back to filing from the person's own account. */
const REPO = "fabcity/awesome-fabcity-data";
const RATE = new Map();   /* ponytail: per-isolate, per-IP; fine for the handful of people who file in a day */

const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

export async function onRequestPost({ request, env }) {
  if (!env.GITHUB_TOKEN) return json({ ok: false, error: "filing from the site is not switched on; file it from your own GitHub account" }, 503);
  const ip = request.headers.get("cf-connecting-ip") || "?", now = Date.now();
  if (now - (RATE.get(ip) || 0) < 20_000) return json({ ok: false, error: "one filing every twenty seconds; try again in a moment" }, 429);
  let b;
  try { b = await request.json(); } catch { return json({ ok: false, error: "bad json" }, 400); }
  if (b.website) return json({ ok: true, url: "" });   /* honeypot: a bot filled the hidden field */
  const title = String(b.title || "").trim().slice(0, 200), body = String(b.body || "").slice(0, 60_000);
  if (!/^(review|source): \S/.test(title)) return json({ ok: false, error: "the title must start with 'review: ' or 'source: '" }, 400);
  if (body.length < 40 || !body.includes("### ")) return json({ ok: false, error: "the body must be the form, with its ### headings" }, 400);
  RATE.set(ip, now);
  const r = await fetch(`https://api.github.com/repos/${REPO}/issues`, {
    method: "POST",
    headers: { authorization: `Bearer ${env.GITHUB_TOKEN}`, accept: "application/vnd.github+json", "content-type": "application/json",
               "user-agent": "fci-index-submit/0.1", "x-github-api-version": "2022-11-28" },
    body: JSON.stringify({ title, body: body + "\n\n_Filed from index.fab.city. The name above is the person's; this account only carries it._" }),
  });
  const out = await r.json().catch(() => ({}));
  if (!r.ok) return json({ ok: false, error: `GitHub answered ${r.status}: ${out.message || "unknown"}` }, 502);
  return json({ ok: true, url: out.html_url, number: out.number });
}

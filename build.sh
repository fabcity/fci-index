#!/usr/bin/env bash
# FCI 3.0 — assembles the three static sites into one deployable tree (public/).
#   ./build.sh           → staging build (no analytics)
#   ./build.sh --prod    → production build (injects Plausible)
# Routes:  /  = fci-3-prototype   /atlas = fci-matryoshka-viz   /operate = fci-ingestion-tool
# Cross-links between the sites are relative (../fci-*/...) in source; rewritten to route paths here.
# 2026-06-06 — see FCI_3.0_Deployment_Plan_2026-06-06.md §1.
set -euo pipefail
cd "$(dirname "$0")"
SRC=".."                      # the FAB CITY workspace root, where the three site folders live
OUT="${FCI_OUT:-public}"      # overridable for sandboxed verification runs

PROD=0
[ "${1:-}" = "--prod" ] && PROD=1

for d in fci-3-prototype fci-matryoshka-viz fci-ingestion-tool; do
  [ -d "$SRC/$d" ] || { echo "missing $SRC/$d — run from fci-index/ inside the FAB CITY workspace"; exit 1; }
done

# ---- token gate -------------------------------------------------------------------------
# The three sites each carry css/tokens.css, the Fab City foundation. They are copies, so the
# only thing stopping them drifting is this check — and they HAD drifted: --rule-soft was
# #EFEAE4 in the prototype and #E6E1D1 in the atlas, two hairlines on one site, with the type
# scale and font stacks disagreeing three ways. Nothing noticed for three months.
# This runs on every build because that is the one place all three repos are visible at once.
sums=$(md5 -q "$SRC"/fci-3-prototype/css/tokens.css "$SRC"/fci-matryoshka-viz/css/tokens.css \
                "$SRC"/fci-ingestion-tool/css/tokens.css 2>/dev/null \
       || md5sum "$SRC"/fci-{3-prototype,matryoshka-viz,ingestion-tool}/css/tokens.css | cut -d' ' -f1)
if [ "$(echo "$sums" | sort -u | wc -l | tr -d ' ')" != "1" ]; then
  echo "FAIL: the three css/tokens.css copies are not identical — the foundation has drifted"; exit 1
fi
echo "token foundation: 3 copies, identical"

# A renamed token that lost its definition is invisible: the property falls back to inherited
# or initial, so a colour quietly becomes black and nothing errors. Cheap to assert, so assert it.
python3 check_tokens.py "$SRC/fci-3-prototype" "$SRC/fci-matryoshka-viz" "$SRC/fci-ingestion-tool" \
  || { echo "FAIL: a var(--token) does not resolve"; exit 1; }

rm -rf "$OUT" 2>/dev/null || echo "note: could not clear $OUT (sandbox?) — overwriting in place"
mkdir -p "$OUT/atlas" "$OUT/operate"
# tar-pipe copy with README excluded at source (repo docs, not pages) — avoids any post-copy deletion
tar -C "$SRC/fci-3-prototype"   --exclude='README.md' --exclude='.fuse_hidden*' --exclude='.git' --exclude='.gitignore' -cf - . | tar -C "$OUT" -xf -
tar -C "$SRC/fci-matryoshka-viz" --exclude='README.md' --exclude='.fuse_hidden*' --exclude='.git' --exclude='.gitignore' -cf - . | tar -C "$OUT/atlas" -xf -
tar -C "$SRC/fci-ingestion-tool" --exclude='README.md' --exclude='.fuse_hidden*' --exclude='.git' --exclude='.gitignore' -cf - . | tar -C "$OUT/operate" -xf -

# Rewrite the relative cross-links to route paths (perl -pi: portable across macOS/Linux sed dialects)
find "$OUT" \( -name '*.html' -o -name '*.js' \) | while read -r f; do
  perl -pi -e 's|\.\./fci-3-prototype/|/|g; s|\.\./fci-matryoshka-viz/|/atlas/|g; s|\.\./fci-ingestion-tool/|/operate/|g' "$f"
done
# Strategy-doc links that pointed at workspace .md files have no web home yet — route them to the methodology page
# (grep guarded: zero matches is the healthy state after the 2026-06-07e public-register pass, and pipefail would kill the build)
{ grep -rl '\.\./FCI_3\.0_' "$OUT" --include='*.html' 2>/dev/null || true; } | while read -r f; do
  perl -pi -e 's|\.\./FCI_3\.0_[A-Za-z_0-9.-]+\.md|/methodology.html|g' "$f"
done

# Strip internal editorial comments from the deployable tree (2026-07-10 pass).
# Source folders keep their changelog comments; the published pages must not carry
# internal references (fix markers, review passes, doc names) into view-source.
# HTML: all <!-- --> comments go. JS: only full-line and trailing "// fix 2026…" lines
# and "/* fix 2026 … */" blocks go — functional comments stay, syntax is node-checked below.
FCI_OUT_DIR="$OUT" python3 - <<'PYEOF'
import os, re
out = os.environ["FCI_OUT_DIR"]
nh = nj = 0
for dp, _, fns in os.walk(out):
    for fn in fns:
        p = os.path.join(dp, fn)
        if fn.endswith(".html"):
            s = open(p, encoding="utf-8").read()
            s2 = re.sub(r'[ \t]*<!--.*?-->', '', s, flags=re.S)
            if s2 != s:
                open(p, "w", encoding="utf-8").write(s2); nh += 1
        elif fn.endswith(".js"):
            s = open(p, encoding="utf-8").read()
            # HTML comments inside template literals render into the DOM — strip them too
            s2 = re.sub(r'[ \t]*<!--.*?-->', '', s, flags=re.S)
            s2 = re.sub(r'[ \t]*/\* fix 2026[^*]*(\*(?!/)[^*]*)*\*/', '', s2)
            s2 = re.sub(r'^[ \t]*// fix 2026.*\n', '', s2, flags=re.M)
            s2 = re.sub(r'[ \t]*// fix 2026.*$', '', s2, flags=re.M)
            s2 = re.sub(r'[ \t]*\(fix 2026[^)]*\)', '', s2)          # parenthetical markers
            s2 = re.sub(r'fix 2026.*?(?=\*/|\n)', '', s2)            # inside block comments, keep */
            if s2 != s:
                open(p, "w", encoding="utf-8").write(s2); nj += 1
print(f"stripped internal comments: {nh} html, {nj} js")
PYEOF
# Syntax-check every JS file after stripping — a broken strip must fail the build
if command -v node >/dev/null 2>&1; then
  find "$OUT" -name '*.js' | while read -r f; do node --check "$f" || { echo "FAIL: JS syntax after comment strip: $f"; exit 1; }; done
else
  echo "note: node not found — skipping JS syntax check"
fi

# Beta feedback line on every page (tier-2 mechanism) + Plausible on --prod only.
# python3, not perl: the strings contain @ and quotes that perl -e interpolates away.
FCI_OUT_DIR="$OUT" FCI_PROD="$PROD" python3 - <<'PYEOF'
import os
out, prod = os.environ["FCI_OUT_DIR"], os.environ["FCI_PROD"] == "1"
claim = ('<div style="max-width:34rem;margin:0 auto;padding:1.8rem 1.5rem 0.2rem;'
         'font-family:var(--fc-font-display);font-size:1rem;line-height:1.4;color:var(--fc-ink-2);">'
         'We are a distributed movement redesigning the relationship between production and place.</div>')
feedback = ('<div style="max-width:72rem;margin:0 auto;padding:0.4rem 1.5rem 1.6rem;'
            'font-size:0.72rem;color:#8a857c;">methodology v0 · beta — comments: '
            '<a href="mailto:index@fab.city" style="color:inherit;">index@fab.city</a></div>')
plausible = '<script defer data-domain="index.fab.city" src="https://plausible.io/js/script.js"></script>'
n = 0
for dp, _, fns in os.walk(out):
    for fn in fns:
        if not fn.endswith(".html"):
            continue
        p = os.path.join(dp, fn)
        html = open(p, encoding="utf-8").read()
        if "</body>" in html and "mailto:index@fab.city" not in html:
            html = html.replace("</body>", claim + feedback + "\n</body>", 1)
        if prod and "</head>" in html and "plausible.io" not in html:
            html = html.replace("</head>", plausible + "\n</head>", 1)
        open(p, "w", encoding="utf-8").write(html)
        n += 1
print(f"injected feedback line into {n} pages" + (" + Plausible (prod)" if prod else " (staging — no analytics)"))
PYEOF

# Consolidation guard (CANONICAL.md): the build output must never be edited by hand
cat > "$OUT/DO-NOT-EDIT.txt" <<'EOF'
GENERATED TREE — do not edit anything in this folder.
Source of truth: the fci-3-prototype, fci-matryoshka-viz and fci-ingestion-tool
folders in the FAB CITY workspace root. Rebuild with: ./build.sh
(see CANONICAL.md at the workspace root)
EOF

PAGES=$(find "$OUT" -name '*.html' | wc -l | tr -d ' ')
LEFTOVER=$( (grep -rl '\.\./fci-' "$OUT" 2>/dev/null || true) | wc -l | tr -d ' ')  # grep exits 1 on no-match; don't trip pipefail
# Structural sanity. A page with two <!DOCTYPE>s, or one that has grown by two orders of
# magnitude, is not a page — it is a broken edit. This exists because a Python
# `s.replace(old, new)` where `old` had become "" inserted a block between EVERY CHARACTER
# of index.html, taking it from 20 KB to 6 MB. It still had valid hrefs and every var()
# resolved, so the link check and the token check both passed it, and it shipped.
FCI_OUT_DIR="$OUT" python3 - <<'PYEOF' || exit 1
import os, sys
out = os.environ["FCI_OUT_DIR"]
bad = []
for dp, _, fns in os.walk(out):
    for fn in fns:
        if not fn.endswith(".html"):
            continue
        p = os.path.join(dp, fn)
        rel = os.path.relpath(p, out)
        size = os.path.getsize(p)
        html = open(p, encoding="utf-8", errors="replace").read()
        n = html.upper().count("<!DOCTYPE")
        if n != 1:
            bad.append(f"{rel}: {n} <!DOCTYPE> (expected 1)")
        if size > 512 * 1024:
            bad.append(f"{rel}: {size // 1024} KB — no page here is that big")
        if html.count("<html") != 1 or html.count("</html>") != 1:
            bad.append(f"{rel}: {html.count('<html')} <html> / {html.count('</html>')} </html>")
if bad:
    print("FAIL: structurally broken page(s):", file=sys.stderr)
    for b in sorted(set(bad))[:20]:
        print("  " + b, file=sys.stderr)
    sys.exit(1)
print("page structure: all sound")
PYEOF

# Every internal link must resolve to a file that exists. This domain answers EVERY miss
# with HTTP 200 and the homepage, so a dead link is invisible to a crawler, to curl and to a
# reader who does not check the <title>. Deleting the four per-city pages broke fifteen
# cross-repo links in one commit and nothing noticed until this ran.
FCI_OUT_DIR="$OUT" python3 - <<'PYEOF' || exit 1
import os, re, sys, urllib.parse
out = os.environ["FCI_OUT_DIR"]
bad = []
for dp, _, fns in os.walk(out):
    for fn in fns:
        if not fn.endswith(".html"):
            continue
        p = os.path.join(dp, fn)
        html = open(p, encoding="utf-8").read()
        for href in re.findall(r'href="([^"#?]+)"', html):
            if href.startswith(("http://", "https://", "mailto:", "//", "data:")):
                continue
            # hrefs built in JS inside a template or a concatenation are not literal links
            if any(t in href for t in ("' +", "+ '", "${", "{{", '" +')):
                continue
            target = os.path.normpath(os.path.join(
                out if href.startswith("/") else dp, href.lstrip("/")))
            if not os.path.exists(urllib.parse.unquote(target)):
                bad.append(f"{os.path.relpath(p, out)} -> {href}")
if bad:
    print(f"FAIL: {len(bad)} internal link(s) point at nothing:", file=sys.stderr)
    for b in sorted(set(bad))[:20]:
        print("  " + b, file=sys.stderr)
    sys.exit(1)
print("internal links: all resolve")
PYEOF

echo "assembled: ${PAGES} pages in ${OUT}/ · unrewritten cross-links: ${LEFTOVER} (must be 0) · prod=${PROD}"
[ "$LEFTOVER" = "0" ] || { echo "FAIL: cross-links left unrewritten"; exit 1; }

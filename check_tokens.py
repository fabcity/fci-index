#!/usr/bin/env python3
"""Every var(--x) on an Index site must resolve to a definition. A renamed token that lost its
definition is an invisible failure: the property falls back to inherited or initial, so a colour
quietly becomes black and nothing errors."""
import re, sys, pathlib, collections
DEF = re.compile(r'(--[a-z0-9-]+)\s*:')
USE = re.compile(r'var\(\s*(--[a-z0-9-]+)')
STYLE = re.compile(r'<style[^>]*>(.*?)</style>', re.S)
bad = 0
# build.sh injects its own markup into every page (the feedback line, the claim). Those
# var() references are not in any site repo, so the per-repo scan below cannot see them —
# and they went stale in exactly that blind spot during the token rename.
here = pathlib.Path(__file__).parent / "build.sh"
if here.exists():
    inj = set(USE.findall(here.read_text(encoding="utf-8")))
    stale = sorted(t for t in inj if not t.startswith("--fc-") and t not in {"--mono", "--token"})
    if stale:
        print(f"build.sh injects unknown tokens: {stale}"); bad += len(stale)

for d in sys.argv[1:]:
    root = pathlib.Path(d); defined, used = set(), collections.Counter()
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix not in {".css",".html",".js",".svg"} or ".git" in p.parts:
            continue
        s = p.read_text(encoding="utf-8", errors="ignore")
        defined |= set(DEF.findall(s if p.suffix == ".css" else "\n".join(STYLE.findall(s))))
        for t in USE.findall(s): used[t] += 1
    missing = {t: n for t, n in used.items() if t not in defined}
    print(f"{root.name:22} defined={len(defined):3} used={len(used):3}  unresolved={len(missing)}")
    for t, n in sorted(missing.items()):
        print(f"      !! {t}  ({n} uses)"); bad += 1
sys.exit(1 if bad else 0)

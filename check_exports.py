#!/usr/bin/env python3
"""Every name a page script takes from window.FCI must actually be exported by data.js.

This exists because deleting INDICATORS from the atlas's data.js broke /atlas/drilldown
outright — `const { INDICATORS } = window.FCI` then yields undefined, and the first property
access throws. The page still served HTTP 200 with its static prose, every internal link
resolved, the structure was sound and every var() resolved. Four gates passed a dead page.

A grep for `FCI.INDICATORS` misses it too: the reference is a destructuring, not a property
access. This checks both forms.
"""
import pathlib, re, sys

bad = 0
for d in sys.argv[1:]:
    root = pathlib.Path(d)
    data_js = root / "js" / "data.js"
    if not data_js.exists():
        continue
    data = data_js.read_text(encoding="utf-8")
    if "window.FCI" not in data:
        continue
    j = data.index("{", data.index("window.FCI"))
    depth = 0
    for k in range(j, len(data)):
        if data[k] == "{":
            depth += 1
        elif data[k] == "}":
            depth -= 1
            if depth == 0:
                break
    exported = set(re.findall(r"\b([A-Za-z_]\w*)\b", data[j + 1:k]))

    for f in sorted((root / "js").glob("*.js")):
        s = f.read_text(encoding="utf-8")
        for m in re.finditer(r"const\s*\{([^}]*)\}\s*=\s*window\.FCI\b", s):
            for name in re.findall(r"\b([A-Za-z_]\w*)\b", m.group(1)):
                if name not in exported:
                    print(f"  {root.name}/js/{f.name}: destructures `{name}` from window.FCI, "
                          f"which does not export it", file=sys.stderr)
                    bad += 1
        for m in re.finditer(r"window\.FCI\.([A-Za-z_]\w*)", s):
            if m.group(1) not in exported:
                print(f"  {root.name}/js/{f.name}: reads window.FCI.{m.group(1)}, "
                      f"which is not exported", file=sys.stderr)
                bad += 1

if bad:
    print(f"FAIL: {bad} reference(s) to a window.FCI member that does not exist", file=sys.stderr)
    sys.exit(1)
print("window.FCI references: all resolve")

"""Combine the CSS/JS files into one file each (fewer requests = faster on phones).
Run again after editing any of: style.css, upgrade.css, stark.css, app.js, stark.js
    python build_assets.py"""
import re, os
S = os.path.join(os.path.dirname(__file__), "public", "static")
def read(n): return open(os.path.join(S, n), encoding="utf-8").read()
css = "\n".join(re.sub(r"/\*.*?\*/", "", read(n), flags=re.S) for n in ("style.css", "upgrade.css", "stark.css"))
js = "\n;\n".join(read(n) for n in ("app.js", "stark.js"))
open(os.path.join(S, "site.css"), "w", encoding="utf-8").write(css)
open(os.path.join(S, "site.js"), "w", encoding="utf-8").write(js)
print("site.css", len(css), "bytes | site.js", len(js), "bytes")

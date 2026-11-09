"""Pack `npx expo export --platform web` into one HTML body (scripts and assets inlined), for a shareable
preview. Needs app.json's web.output "single" and asyncRoutes off on web (one JS file).

    npx expo export --platform web --output-dir dist-web && python3 scripts/single-html.py dist-web out.html
"""
import base64
import re
import sys
from pathlib import Path

root, out = Path(sys.argv[1]), Path(sys.argv[2])
js = next((root / "_expo/static/js/web").glob("entry-*.js")).read_text()
mime = {".ttf": "font/ttf", ".png": "image/png"}


def inline(m: re.Match) -> str:
    p = root / m.group(1).lstrip("/")
    if not p.exists():
        return m.group(0)
    return '"data:%s;base64,%s"' % (mime[p.suffix], base64.b64encode(p.read_bytes()).decode())


js = re.sub(r'"(/assets/[^"]+\.(?:ttf|png))"', inline, js).replace("</script", "<\\/script")
out.write_text('''<title>soloyolo app</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>
:root { --bg: #d9d9de; color-scheme: light; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg: #050505; color-scheme: dark; } }
:root[data-theme="dark"] { --bg: #050505; color-scheme: dark; }
html, body { height: 100%; }
body { overflow: hidden; background: var(--bg); }
/* A phone app: full screen on a phone, a phone-width column on a wide screen */
#root { display: flex; height: 100%; flex: 1; max-width: 430px; margin: 0 auto;
        box-shadow: 0 0 0 1px rgb(0 0 0 / .06), 0 20px 60px rgb(0 0 0 / .18); }
</style>
<div id="root"></div>
<script>''' + js + '''</script>
''')
print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")

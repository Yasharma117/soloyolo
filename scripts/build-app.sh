#!/bin/bash
# Builds the app (mobile/) for the browser, as one file that `python -m spike serve` serves at
# http://127.0.0.1:8765. Run it again after changing the app. Needs Node; installs nothing system-wide.
set -euo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$REPO/mobile"
[ -d "$REPO/node_modules" ] || (cd "$REPO" && npm install)
npx expo export --platform web --output-dir dist-web
python3 scripts/single-html.py dist-web dist-web/app.html
echo "Built. Start soloyolo, then open http://127.0.0.1:8765"

#!/bin/bash
# One-time setup on your Mac: checks what's needed, makes a Python venv, builds connectord.
# Installs nothing system-wide and never runs sudo. Safe to re-run. Then follow what it prints.
set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DATA=${SOLOYOLO_DATA:-$HOME/.soloyolo}
missing=0
need() { # need <command> <how to get it>
	if ! command -v "$1" >/dev/null 2>&1; then
		echo "  missing: $1  ->  $2"
		missing=1
	fi
}

echo "Checking what soloyolo needs..."
need python3 "brew install python   (Homebrew: https://brew.sh)"
need go "brew install go"
need claude "install Claude Code (https://code.claude.com/docs), then run \`claude\` once to log in"
if command -v python3 >/dev/null 2>&1 && ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
	echo "  python3 is older than 3.10  ->  brew install python"
	missing=1
fi
[ "$missing" = 0 ] || { echo "Install the above, then run this again."; exit 1; }

echo "Python venv and packages..."
[ -x "$REPO/.venv/bin/python" ] || python3 -m venv "$REPO/.venv"
"$REPO/.venv/bin/python" -m pip install --quiet --upgrade pip
"$REPO/.venv/bin/python" -m pip install --quiet -r "$REPO/spike/requirements.txt"

echo "Building connectord..."
(cd "$REPO/connectord" && go build -o connectord ./cmd/connectord)

mkdir -p "$DATA"
chmod 700 "$DATA"
PY=$REPO/.venv/bin/python
cat <<NEXT

Ready. Three steps left (the first two once only):

1. Link WhatsApp (your phone: WhatsApp > Linked devices > Link a device > Link with phone number instead):
     $REPO/connectord/connectord --data "$DATA" link --phone 91XXXXXXXXXX
   Type the 8-character code it prints into your phone. Leave it running until it says history is in,
   then Ctrl-C.

2. Telegram: message @BotFather, send /newbot, pick any name; it gives you a token. Then:
     cd "$REPO" && $PY -m spike --db "$DATA/soloyolo.db" telegram pair

3. Start everything (sync, a reading pass every 30 min, the 07:30 message, your taps):
     "$REPO/scripts/install-mac.sh"

To check it right away:  launchctl kickstart gui/\$(id -u)/com.soloyolo.digest
NEXT

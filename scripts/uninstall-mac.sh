#!/bin/bash
# Stop and remove soloyolo's launchd agents. Safe to re-run. Keeps your data unless PURGE=1.
#
#   SOLOYOLO_DATA        [~/.soloyolo]               what PURGE=1 deletes
#   SOLOYOLO_AGENTS_DIR  [~/Library/LaunchAgents]
#   PURGE=1              also delete SOLOYOLO_DATA: the store, logs, digests and WhatsApp device keys
#   DRY_RUN=1            don't touch launchctl (works off macOS, for tests)
set -euo pipefail

DATA=${SOLOYOLO_DATA:-$HOME/.soloyolo}
AGENTS=${SOLOYOLO_AGENTS_DIR:-$HOME/Library/LaunchAgents}
PURGE=${PURGE:-0}
DRY_RUN=${DRY_RUN:-0}
LABELS="com.soloyolo.connectord com.soloyolo.watch com.soloyolo.digest"

for label in $LABELS; do
	if [ "$DRY_RUN" != 1 ] && command -v launchctl >/dev/null 2>&1; then
		launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
	fi
	if [ -f "$AGENTS/$label.plist" ]; then
		rm -f "$AGENTS/$label.plist"
		echo "removed $AGENTS/$label.plist"
	fi
done

if [ "$PURGE" = 1 ]; then
	# Refuse anything that doesn't look like a soloyolo data folder.
	case $DATA in /*) ;; *) echo "uninstall-mac: SOLOYOLO_DATA must be absolute" >&2; exit 1 ;; esac
	if [ "$DATA" = "$HOME" ] || [ "$DATA" = / ] || { [ -d "$DATA" ] && [ ! -e "$DATA/soloyolo.db" ] && [ ! -d "$DATA/logs" ]; }; then
		echo "uninstall-mac: $DATA doesn't look like a soloyolo data folder; not deleting it" >&2
		exit 1
	fi
	rm -rf "$DATA"
	echo "deleted $DATA"
else
	echo "kept $DATA (PURGE=1 deletes it)"
fi
cat <<'EOF'

The WhatsApp link is still active on WhatsApp's side until you remove it on the phone:
WhatsApp > Linked devices > this device > Log out.
EOF

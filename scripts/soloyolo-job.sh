#!/bin/bash
# What each launchd agent runs: soloyolo-job.sh {sync|watch|digest|telegram}. Settings come from the
# environment the plist sets (scripts/install-mac.sh writes it). Works on bash 3.2 (macOS /bin/bash).
#
#   sync    connectord, always on. Live-message lines carry message text, so they are dropped
#           before the log; status and errors are kept.
#   watch   one extraction pass over the chats that changed, if no other pass is running.
#   digest  one fresh pass, then the morning message to $DATA/digest/today.txt, and a local
#           macOS notification when SOLOYOLO_NOTIFY=1. With Telegram paired, also sends it there
#           (the 1-3 item lines only, never message text).
#   telegram  applies your taps on that message as they come; exits cleanly if not paired.
set -euo pipefail

DATA=${SOLOYOLO_DATA:?SOLOYOLO_DATA is not set}
DB="$DATA/soloyolo.db"
LOGS="$DATA/logs"
LABEL_SYNC=com.soloyolo.connectord
umask 077
mkdir -p "$LOGS" "$DATA/digest"

stamp() { date '+%Y-%m-%d %H:%M:%S'; }

# launchd doesn't rotate logs. Copy-then-truncate, because connectord keeps its log open.
rotate() {
	local f=$1 max=$((5 * 1024 * 1024))
	if [ -f "$f" ] && [ "$(wc -c <"$f")" -gt "$max" ]; then
		cp "$f" "$f.1" && : >"$f"
	fi
}

# One extraction pass at a time (watch and digest can coincide). mkdir is atomic; a lock left by
# a killed pass expires after two hours.
LOCK="$DATA/.extract.lock"
take_lock() {
	if [ -d "$LOCK" ] && [ -n "$(find "$LOCK" -maxdepth 0 -mmin +120 2>/dev/null)" ]; then
		rmdir "$LOCK" 2>/dev/null || true
	fi
	if mkdir "$LOCK" 2>/dev/null; then
		trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT
		return 0
	fi
	return 1
}

extract_pass() {
	local py=${SOLOYOLO_PYTHON:?} repo=${SOLOYOLO_REPO:?}
	if ! take_lock; then
		echo "$(stamp) another extraction pass is running; skipped"
		return 0
	fi
	echo "$(stamp) pass (${SOLOYOLO_EXTRACTOR:-heuristic})"
	# A failed person (a usage limit, a timeout) keeps its old items and stays "changed", so the
	# next pass retries it. Never fatal here.
	(cd "$repo" && "$py" -m spike --db "$DB" watch --once --extractor "${SOLOYOLO_EXTRACTOR:-heuristic}" \
		--top "${SOLOYOLO_TOP:-15}") || echo "$(stamp) pass exited $?"
	rmdir "$LOCK" 2>/dev/null || true
	trap - EXIT
}

# connectord stays up when its first connect fails (no network at login): whatsmeow only
# reconnects a connection it once had. If the last status it logged is an error, restart it.
kick_sync_if_stuck() {
	local last
	[ -f "$LOGS/connectord.log" ] || return 0
	last=$(grep -o '"state":"[a-z_]*"' "$LOGS/connectord.log" | tail -n 1 || true)
	if [ "$last" = '"state":"error"' ] && command -v launchctl >/dev/null 2>&1; then
		echo "$(stamp) connectord's last status was an error; restarting it"
		echo "$(stamp) restarted by watch after a connect error" >>"$LOGS/connectord.log"
		launchctl kickstart -k "gui/$(id -u)/$LABEL_SYNC" || true
	fi
}

case "${1:-}" in
sync)
	rotate "$LOGS/connectord.log"
	bin=${SOLOYOLO_CONNECTORD:?SOLOYOLO_CONNECTORD is not set}
	echo "$(stamp) connectord starting" >>"$LOGS/connectord.log"
	# exec: connectord itself is the process launchd watches and restarts. grep -v drops the
	# per-message "event" notifications (they hold message text); everything else is kept.
	exec "$bin" --data "$DATA" sync \
		2> >(grep --line-buffered -v '"method":"event"' >>"$LOGS/connectord.log") \
		>>"$LOGS/connectord.log"
	;;
watch)
	rotate "$LOGS/watch.log"
	kick_sync_if_stuck
	extract_pass
	;;
digest)
	rotate "$LOGS/digest.log"
	extract_pass
	out="$DATA/digest/today.txt"
	(cd "${SOLOYOLO_REPO:?}" && "${SOLOYOLO_PYTHON:?}" -m spike --db "$DB" digest --out "$out" >/dev/null)
	cp "$out" "$DATA/digest/$(date +%Y-%m-%d).txt"
	echo "$(stamp) digest written to $out"
	if [ -f "$DATA/telegram.json" ]; then
		(cd "$SOLOYOLO_REPO" && "$SOLOYOLO_PYTHON" -m spike --db "$DB" telegram send) || echo "$(stamp) telegram send failed"
	fi
	if [ "${SOLOYOLO_NOTIFY:-0}" = 1 ] && command -v osascript >/dev/null 2>&1; then
		# The text goes in as an argument, never spliced into the script.
		osascript -e 'on run argv' -e 'display notification (item 2 of argv) with title (item 1 of argv)' \
			-e 'end run' "$(head -n 1 "$out")" "$(tail -n +2 "$out" | head -n 4)" || true
	fi
	;;
telegram)
	rotate "$LOGS/telegram.log"
	if [ ! -f "$DATA/telegram.json" ]; then
		echo "$(stamp) not paired; run: python -m spike --db $DB telegram pair"
		exit 0
	fi
	cd "${SOLOYOLO_REPO:?}" && exec "${SOLOYOLO_PYTHON:?}" -m spike --db "$DB" telegram listen
	;;
*)
	echo "usage: $0 {sync|watch|digest|telegram}" >&2
	exit 2
	;;
esac

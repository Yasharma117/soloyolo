#!/bin/bash
# Install (or update) soloyolo's three launchd agents for the logged-in user. Safe to re-run:
# each run rewrites the plists from scripts/launchd/*.plist.in and reloads them.
#
#   com.soloyolo.connectord  connectord sync, always on, restarted if it exits
#   com.soloyolo.watch       one extraction pass every SOLOYOLO_WATCH_MINUTES
#   com.soloyolo.digest      the morning message at SOLOYOLO_DIGEST_AT (the Mac's local time)
#   com.soloyolo.telegram    applies your taps on it, once `python -m spike telegram pair` is done
#
# Settings (environment variables; defaults in brackets):
#   SOLOYOLO_REPO           this checkout                         [the folder above scripts/]
#   SOLOYOLO_DATA           store, device keys, logs              [~/.soloyolo]
#   SOLOYOLO_PYTHON         a Python with spike/requirements.txt  [$REPO/.venv/bin/python, else python3]
#   SOLOYOLO_CONNECTORD     the built connectord binary           [$REPO/connectord/connectord]
#   SOLOYOLO_EXTRACTOR      claude-code | heuristic | api         [claude-code]
#   SOLOYOLO_TOP            at most this many chats per pass      [15]
#   SOLOYOLO_WATCH_MINUTES  minutes between passes                [30]
#   SOLOYOLO_DIGEST_AT      HH:MM                                 [07:30]
#   SOLOYOLO_NOTIFY         1 = also show a macOS notification    [1]
#   SOLOYOLO_PATH           PATH for the jobs (must find claude)  [claude's and python's dirs + system]
#   SOLOYOLO_AGENTS_DIR     where plists go                       [~/Library/LaunchAgents]
#   DRY_RUN=1               write the plists, don't touch launchctl (works off macOS, for tests)
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=${SOLOYOLO_REPO:-$(dirname "$HERE")}
DATA=${SOLOYOLO_DATA:-$HOME/.soloyolo}
if [ -n "${SOLOYOLO_PYTHON:-}" ]; then
	PYTHON=$SOLOYOLO_PYTHON
elif [ -x "$REPO/.venv/bin/python" ]; then
	PYTHON=$REPO/.venv/bin/python
else
	PYTHON=$(command -v python3 || true)
fi
CONNECTORD=${SOLOYOLO_CONNECTORD:-$REPO/connectord/connectord}
EXTRACTOR=${SOLOYOLO_EXTRACTOR:-claude-code}
TOP=${SOLOYOLO_TOP:-15}
WATCH_MINUTES=${SOLOYOLO_WATCH_MINUTES:-30}
DIGEST_AT=${SOLOYOLO_DIGEST_AT:-07:30}
NOTIFY=${SOLOYOLO_NOTIFY:-1}
AGENTS=${SOLOYOLO_AGENTS_DIR:-$HOME/Library/LaunchAgents}
DRY_RUN=${DRY_RUN:-0}
JOB=$HERE/soloyolo-job.sh
LABELS="com.soloyolo.connectord com.soloyolo.watch com.soloyolo.digest com.soloyolo.telegram"

die() { echo "install-mac: $*" >&2; exit 1; }

# --- checks: fail before anything is written --------------------------------------------------
if [ "$DRY_RUN" != 1 ] && [ "$(uname -s)" != Darwin ]; then
	die "this installs macOS launchd agents; on another OS use DRY_RUN=1 to only render them"
fi
for v in REPO DATA PYTHON CONNECTORD AGENTS; do
	val=${!v}
	case $val in /*) ;; *) die "$v must be an absolute path (got '$val')" ;; esac
	case $val in *$'\n'*) die "$v contains a newline" ;; esac
done
[ -f "$REPO/spike/__main__.py" ] || die "SOLOYOLO_REPO=$REPO is not a soloyolo checkout"
[ -x "$PYTHON" ] || die "no Python at '$PYTHON' (set SOLOYOLO_PYTHON)"
"$PYTHON" -c 'import pydantic' 2>/dev/null || die "$PYTHON lacks pydantic: $PYTHON -m pip install -r $REPO/spike/requirements.txt"
[ -x "$CONNECTORD" ] || die "no connectord at $CONNECTORD: (cd connectord && go build -o connectord ./cmd/connectord)"
case $EXTRACTOR in claude-code | heuristic | api) ;; *) die "SOLOYOLO_EXTRACTOR must be claude-code, heuristic or api" ;; esac
case $TOP in '' | *[!0-9]*) die "SOLOYOLO_TOP must be a whole number" ;; esac
case $WATCH_MINUTES in '' | *[!0-9]*) die "SOLOYOLO_WATCH_MINUTES must be a whole number" ;; esac
[ "$WATCH_MINUTES" -ge 5 ] || die "SOLOYOLO_WATCH_MINUTES must be at least 5"
case $NOTIFY in 0 | 1) ;; *) die "SOLOYOLO_NOTIFY must be 0 or 1" ;; esac
case $DIGEST_AT in [0-2][0-9]:[0-5][0-9]) ;; *) die "SOLOYOLO_DIGEST_AT must be HH:MM (got '$DIGEST_AT')" ;; esac
DIGEST_HOUR=$((10#${DIGEST_AT%:*}))
DIGEST_MINUTE=$((10#${DIGEST_AT#*:}))
[ "$DIGEST_HOUR" -le 23 ] || die "SOLOYOLO_DIGEST_AT hour must be 00-23"

# launchd starts jobs with PATH=/usr/bin:/bin:/usr/sbin:/sbin, where `claude` usually isn't.
if [ -n "${SOLOYOLO_PATH:-}" ]; then
	JOB_PATH=$SOLOYOLO_PATH
else
	JOB_PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
	JOB_PATH=$(dirname "$PYTHON"):$JOB_PATH
	if CLAUDE=$(command -v claude); then JOB_PATH=$(dirname "$CLAUDE"):$JOB_PATH; fi
fi
if [ "$EXTRACTOR" = claude-code ] && ! PATH=$JOB_PATH command -v claude >/dev/null; then
	die "claude (Claude Code CLI) is not on SOLOYOLO_PATH=$JOB_PATH. Install it, run \`claude\` once to log in, then re-run"
fi
[ -f "$DATA/soloyolo.db" ] || echo "install-mac: note: no store at $DATA/soloyolo.db yet. Link first: $CONNECTORD --data $DATA link --phone <your number>"

# --- render ------------------------------------------------------------------------------------
# A value goes into XML (escape & < >), through sed (escape \ & and the | delimiter).
esc() { printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g' -e 's/[\\|&]/\\&/g'; }

umask 077
mkdir -p "$DATA/logs" "$DATA/digest" "$AGENTS"
chmod 700 "$DATA" "$DATA/logs" "$DATA/digest"
chmod +x "$JOB"

for label in $LABELS; do
	src=$HERE/launchd/$label.plist.in
	dst=$AGENTS/$label.plist
	tmp=$(mktemp "$AGENTS/.$label.XXXXXX")
	sed -e "s|@JOB@|$(esc "$JOB")|g" \
		-e "s|@REPO@|$(esc "$REPO")|g" \
		-e "s|@DATA@|$(esc "$DATA")|g" \
		-e "s|@PYTHON@|$(esc "$PYTHON")|g" \
		-e "s|@CONNECTORD@|$(esc "$CONNECTORD")|g" \
		-e "s|@EXTRACTOR@|$EXTRACTOR|g" \
		-e "s|@TOP@|$TOP|g" \
		-e "s|@NOTIFY@|$NOTIFY|g" \
		-e "s|@PATH@|$(esc "$JOB_PATH")|g" \
		-e "s|@WATCH_SECONDS@|$((WATCH_MINUTES * 60))|g" \
		-e "s|@DIGEST_HOUR@|$DIGEST_HOUR|g" \
		-e "s|@DIGEST_MINUTE@|$DIGEST_MINUTE|g" \
		"$src" >"$tmp"
	if grep -q '@[A-Z_]*@' "$tmp"; then
		rm -f "$tmp"
		die "unfilled placeholder in $src"
	fi
	if command -v plutil >/dev/null 2>&1; then
		plutil -lint -s "$tmp" || { rm -f "$tmp"; die "$label: plist failed plutil -lint"; }
	fi
	chmod 644 "$tmp"
	mv "$tmp" "$dst"
	echo "wrote $dst"
done

# --- load ----------------------------------------------------------------------------------------
if [ "$DRY_RUN" = 1 ]; then
	echo "DRY_RUN=1: not loading. On a Mac, re-run without it."
	exit 0
fi
domain=gui/$(id -u)
for label in $LABELS; do
	launchctl bootout "$domain/$label" 2>/dev/null || true # a reload; fine if it wasn't loaded
	launchctl enable "$domain/$label"                      # a disabled label refuses to bootstrap
	ok=0
	for _ in 1 2 3 4 5; do # bootout returns before the old job is gone
		if launchctl bootstrap "$domain" "$AGENTS/$label.plist" 2>/dev/null; then ok=1; break; fi
		sleep 1
	done
	[ "$ok" = 1 ] || die "launchctl bootstrap $label failed; see: launchctl print $domain/$label"
	echo "loaded $label"
done
cat <<EOF

Installed. connectord is syncing now; a pass runs every $WATCH_MINUTES min; the digest at $DIGEST_AT.
  Logs:     $DATA/logs/{connectord,watch,digest}.log
  Digest:   $DATA/digest/today.txt
  Run now:  launchctl kickstart $domain/com.soloyolo.digest
  Remove:   $HERE/uninstall-mac.sh
EOF

"""Setting soloyolo up from the app instead of the terminal: link WhatsApp, and read the exports in Downloads.

The server (`python -m spike serve`) owns one Setup per store. It does two things the CLI already did:

  link     runs `connectord link --phone …`, shows the 8-character pairing code WhatsApp gives, and leaves
           connectord running afterwards, because the same process is what keeps syncing.
  import   reads a LinkedIn, Instagram, X or WhatsApp export it found in ~/Downloads, in a background thread,
           and says which stage it's at.

Nothing here takes a password. WhatsApp is linked the way WhatsApp Web is (a code typed on your phone); the
others are the files those networks hand you. The app can only name a file this module itself found, never a path.
"""
from __future__ import annotations

import atexit
import os
import re
import sqlite3
import subprocess
import threading
import time
from pathlib import Path

from . import instagram_export, linkedin_export, whatsapp_export, x_export
from .store import Store

REPO = Path(__file__).resolve().parents[1]
# What each network names the file it sends you. Matched in ~/Downloads only, newest first.
EXPORTS = {
    "linkedin": ("Complete_LinkedInDataExport_*.zip", "Basic_LinkedInDataExport_*.zip"),
    "instagram": ("instagram-*.zip",),
    "x": ("twitter-*.zip",),
    "whatsapp": ("WhatsApp Chat*.zip", "WhatsApp Chat*.txt"),
}
PHONE = re.compile(r"\d{8,15}")  # country code and number, digits only: 919800000000
NOT_BUILT = "connectord isn't built yet. Run scripts/setup-mac.sh on your Mac, then try again."


class Setup:
    def __init__(self, db: str | Path):
        self.db = str(db)
        self.data = Path(db).resolve().parent
        self.downloads = Path(os.environ.get("SOLOYOLO_DOWNLOADS") or Path.home() / "Downloads")
        self.connectord = Path(os.environ.get("SOLOYOLO_CONNECTORD") or REPO / "connectord/connectord")
        self.lock = threading.Lock()
        self.proc: subprocess.Popen | None = None
        self.wa = {"state": "idle", "code": None, "message": None}
        self.jobs: dict[str, dict] = {}

    # --- WhatsApp ---------------------------------------------------------------------------
    def linked(self) -> bool:
        """connectord's own record: an account row has the network's id for you once the link finished."""
        try:
            conn = sqlite3.connect(f"file:{self.db}?mode=ro", uri=True)
            try:
                return conn.execute("SELECT 1 FROM account WHERE network = 'whatsapp' AND remote_user != ''").fetchone() is not None
            finally:
                conn.close()
        except sqlite3.Error:
            return False

    def running(self) -> bool:
        """Is a connectord syncing: ours, or one launchd started. Only one may run per device."""
        if self.proc and self.proc.poll() is None:
            return True
        try:
            return subprocess.run(["pgrep", "-x", "connectord"], capture_output=True, timeout=5).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def _start(self, *args: str) -> None:
        self.proc = subprocess.Popen([str(self.connectord), "--data", str(self.data), *args], stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, errors="replace")
        threading.Thread(target=self._follow, args=(self.proc,), daemon=True).start()

    def link(self, phone: str) -> dict:
        """Start linking. The pairing code arrives a few seconds later: read it from status()."""
        if not PHONE.fullmatch(phone):
            raise ValueError("Enter your number with the country code, digits only, like 919800000000.")
        with self.lock:
            if not self.connectord.exists():
                self.wa = {"state": "error", "code": None, "message": NOT_BUILT}
                return self.status()
            if self.proc and self.proc.poll() is None:
                if self.wa["state"] == "linked":
                    return self.status()  # already linked and syncing: nothing to do
                self.proc.terminate()  # a link that was waiting for its code: start over with this number
                self.proc.wait(timeout=10)
            elif self.running():
                raise ValueError("connectord is already running on this Mac, so WhatsApp is already set up.")
            self.wa = {"state": "starting", "code": None, "message": None}
            self._start("link", "--phone", phone)
        return self.status()

    def sync(self) -> dict:
        """Start syncing an account that's already linked (after a restart, before launchd is installed)."""
        with self.lock:
            if not self.connectord.exists():
                self.wa = {"state": "error", "code": None, "message": NOT_BUILT}
            elif not self.linked():
                raise ValueError("WhatsApp isn't linked yet. Link it first.")
            elif not self.running():
                self.wa = {"state": "linked", "code": None, "message": None}
                self._start("sync")
        return self.status()

    def _follow(self, proc: subprocess.Popen) -> None:
        """Read connectord's output for the three lines that matter. Everything else, message text included
        (it logs each live message), is dropped here and never kept."""
        last_error = None
        for line in proc.stdout:  # type: ignore[union-attr]
            if m := re.search(r"Pairing code: (\S+)", line):
                self.wa = {"state": "code", "code": m.group(1), "message": None}
            elif "Linked as " in line or re.search(r"account \S+ linked", line):
                self.wa = {"state": "linked", "code": None, "message": None}
            elif m := re.match(r"connectord: (link: .*|.*error.*)", line.strip()):
                last_error = m.group(1)[:300]
        proc.wait()
        if self.proc is proc and self.wa["state"] != "linked":
            self.wa = {"state": "error", "code": None,
                       "message": last_error or "connectord stopped before the link finished. Try again."}
        elif self.proc is proc:
            self.wa = {"state": "idle", "code": None, "message": last_error}  # sync stopped: status() says so

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()

    # --- exports ----------------------------------------------------------------------------
    def exports(self) -> list[dict]:
        found = []
        for network, patterns in EXPORTS.items():
            for pattern in patterns:
                for p in self.downloads.glob(pattern) if self.downloads.is_dir() else ():
                    if p.is_file():
                        found.append({"file": p.name, "network": network, "size": p.stat().st_size, "modified": p.stat().st_mtime,
                                      "job": self.jobs.get(p.name)})
        return sorted(found, key=lambda f: -f["modified"])

    def start_import(self, name: str) -> dict:
        """Read one of the files exports() listed. `name` is a file name, checked against that list."""
        hit = next((f for f in self.exports() if f["file"] == name), None)
        if not hit:
            raise LookupError("no such export")
        with self.lock:
            job = self.jobs.get(name)
            if job and job["state"] in ("reading", "saving"):
                return job
            job = self.jobs[name] = {"file": name, "network": hit["network"], "state": "reading", "found": None, "summary": None,
                                     "notes": [], "error": None, "started": time.time(), "finished": None}
        threading.Thread(target=self._import, args=(job, self.downloads / name), daemon=True).start()
        return job

    def _import(self, job: dict, path: Path) -> None:
        try:
            network = job["network"]
            if network == "whatsapp":
                chats = whatsapp_export.read_chats([path])
                rows, names, notes = whatsapp_export.load([path], chats=chats)
                groups, group_notes = whatsapp_export.load_groups([path], chats=chats)
                job.update(state="saving", notes=notes + group_notes, found=f"{len(names)} chats")
                store = Store(self.db)
                try:
                    added = store.add_messages("whatsapp", rows, names)
                    for name, lines in groups.items():
                        store.add_evidence(f"whatsapp-group:{name}", lines)
                finally:
                    store.close()
                summary = f"{added} new messages from {len(names)} chats"
            else:
                mod = {"linkedin": linkedin_export, "instagram": instagram_export, "x": x_export}[network]
                res = mod.load([path], None)
                job.update(state="saving", notes=list(res.notes), found=f"{len(res.names)} people")
                store = Store(self.db)
                try:
                    summary = mod.save(store, res)
                finally:
                    store.close()
            job.update(state="done", summary=summary, finished=time.time())
        except Exception as err:  # a bad file must end the job, not hang the screen on "reading"
            job.update(state="error", error=str(err)[:500] or type(err).__name__, finished=time.time())

    def status(self) -> dict:
        linked = self.linked()
        return {"ready": self.connectord.exists(),
                "whatsapp": {**self.wa, "linked": linked, "syncing": linked and self.running()},
                "exports": self.exports()}


_SETUPS: dict[str, Setup] = {}
_LOCK = threading.Lock()


def get(db: str | Path) -> Setup:
    """The one Setup for this store, shared by every request (a link in progress outlives the request that began it)."""
    key = str(Path(db).resolve())
    with _LOCK:
        if key not in _SETUPS:
            _SETUPS[key] = Setup(db)
        return _SETUPS[key]


@atexit.register
def _stop_all() -> None:  # connectord must not outlive the server that started it: a second one would fight it
    for s in _SETUPS.values():
        s.stop()

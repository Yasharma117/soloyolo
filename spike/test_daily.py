"""python -m unittest spike.test_daily  (offline: never calls Claude, never sends anything)"""
import io
import json
import os
import plistlib
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import types
import unittest
from contextlib import redirect_stdout
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from spike import _nudge_stub, chatdb, daily, fixture, priority
from spike.__main__ import main
from spike.store import Store

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
HOUR = 3600


def make_store(path, now):
    """Three synthetic people with a few open items, like test_spike.PriorityTest."""
    st = Store(path)
    Msg = type("M", (), {})
    rows = []
    for who, n in (("dad", 12), ("ravi", 12), ("shop", 2)):
        for i in range(n):
            m = Msg()
            m.guid, m.handle, m.ts, m.from_me, m.text = f"{who}{i}", who, now - 86400 * (n - i), i % 2 == 0, f"{who} {i}"
            rows.append(m)
    st.add_messages("whatsapp", rows, {"dad": "Dad", "ravi": "Ravi Kumar", "shop": "Shop"})
    pids = {p["name"]: p["id"] for p in st.people()}

    def put(name, *items):
        thread = st.thread(pids[name])
        st.replace_extraction(pids[name], [
            dict(kind="promise", owner=o, action=a, due=due, status="open", source_message_id=thread[k]["id"])
            for o, a, due, k in items], [], "heuristic", last_message_id=thread[-1]["id"])
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    put("Dad", ("me", "Send Dad ₹950", None, 3), ("them", "Book the cab", None, 5))
    put("Ravi Kumar", ("me", "Send the deck", tomorrow, 10), ("me", "Call about the flat", None, 8))
    put("Shop", ("them", "Deliver the sofa", None, 0))
    return st, pids


class NudgeSourceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = time.time()
        self.st, self.pids = make_store(Path(self.tmp.name) / "s.db", self.now)

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    def test_stub_is_the_top_three_of_the_ranking_with_only_the_interface_keys(self):
        got = _nudge_stub.today(self.st, self.now)
        ranked = priority.rank(self.st, self.now)
        self.assertEqual([g["action"] for g in got], [r["action"] for r in ranked[:3]])
        for g in got:
            self.assertEqual(set(g), set(_nudge_stub.KEYS))

    def test_uses_nudge_today_when_it_exists(self):
        fake = types.ModuleType("spike.nudge")
        fake.today = lambda store, now: [dict(action="From nudge", name="X", owner="me", reasons=[], person_id=1,
                                              source_message_id=1)]
        with mock.patch.dict(sys.modules, {"spike.nudge": fake}):
            self.assertEqual(daily.today_items(self.st, self.now)[0]["action"], "From nudge")

    def test_falls_back_to_the_stub_without_nudge(self):
        with mock.patch.dict(sys.modules, {"spike.nudge": None}):  # None: import raises ModuleNotFoundError
            self.assertEqual(daily.today_items(self.st, self.now), _nudge_stub.today(self.st, self.now))

    def test_a_broken_nudge_is_not_silently_replaced(self):
        real = __import__

        def broken(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "nudge" and level == 1:  # nudge.py is there, but imports something that isn't
                raise ModuleNotFoundError("No module named 'numpy'", name="numpy")
            return real(name, globals, locals, fromlist, level)
        with mock.patch("builtins.__import__", broken), self.assertRaises(ModuleNotFoundError):
            daily._today_fn()


class RenderTest(unittest.TestCase):
    def item(self, **kw):
        return dict(dict(action="Send the deck", name="Ravi Kumar", owner="me", reasons=["due tomorrow", "close"],
                         person_id=2, source_message_id=40), **kw)

    def test_short_numbered_lines_and_a_date(self):
        text = daily.render([self.item(), self.item(action="Send Dad ₹950", name="Dad", reasons=["money"])],
                            now=time.mktime((2026, 11, 8, 7, 30, 0, 0, 0, -1)))
        self.assertEqual(text.splitlines(), [
            "soloyolo · Sun 8 Nov",
            "2 things for today:",
            "1. Send the deck (Ravi Kumar) · due tomorrow, close",
            "2. Send Dad ₹950 · money",  # the action already says who
        ])

    def test_waiting_on_them_and_at_most_two_reasons(self):
        line = daily.line(self.item(owner="them", action="Book the cab", name="Dad", reasons=["a", "b", "c"]))
        self.assertEqual(line, "Waiting on Dad: book the cab · a, b")

    def test_nothing_today_still_says_why_when_broken(self):
        text = daily.render([], ["WhatsApp sync may have stopped: newest message 20h old."])
        self.assertIn("Nothing for today.", text)
        self.assertTrue(text.splitlines()[-1].startswith("! WhatsApp sync may have stopped"))


class HealthTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = time.time()
        self.st, self.pids = make_store(Path(self.tmp.name) / "s.db", self.now)

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    def link(self):  # the table connectord creates when an account is linked
        self.st.conn.execute("CREATE TABLE account (id TEXT, network TEXT, remote_user TEXT)")
        self.st.conn.execute("INSERT INTO account VALUES ('a1', 'whatsapp', 'me@s.whatsapp.net')")
        self.st.conn.commit()

    def test_import_only_store_never_warns_about_sync(self):
        self.assertEqual(daily.health(self.st, self.now + 30 * 86400), [])

    def test_linked_and_stale_warns(self):
        self.link()
        newest = self.st.conn.execute("SELECT MAX(ts) FROM message").fetchone()[0]
        self.assertEqual(daily.health(self.st, newest + 2 * HOUR), [])
        warn = daily.health(self.st, newest + 20 * HOUR)
        self.assertEqual(len(warn), 1)
        self.assertIn("sync may have stopped: newest message 20h old", warn[0])

    def test_group_lines_count_as_sync_activity(self):
        self.link()
        later = self.now + 19 * HOUR
        ev = types.SimpleNamespace(remote_id="g1", ts=later, sender="x", text="ok")
        self.st.add_evidence("whatsapp-group:Family", [ev])
        self.assertEqual(daily.health(self.st, later + HOUR), [])

    def test_changed_chats_unread_for_hours_warn(self):
        dad = self.pids["Dad"]
        Msg = types.SimpleNamespace
        self.st.add_messages("whatsapp", [Msg(guid="new", handle="dad", ts=self.now, from_me=False, text="hi")])
        self.st.conn.execute("UPDATE extraction_run SET ran_at = ?", (self.now - 10 * HOUR,))
        self.st.conn.commit()
        self.assertIn(dad, self.st.changed_ids())
        warn = daily.health(self.st, self.now)
        self.assertEqual(len(warn), 1)
        self.assertIn("1 changed chat waiting, nothing read for 10h", warn[0])
        self.st.conn.execute("UPDATE extraction_run SET ran_at = ?", (self.now - HOUR,))
        self.assertEqual(daily.health(self.st, self.now), [])  # read an hour ago: just slow, fine

    def test_short_chats_never_read_by_watch_never_warn(self):
        Msg = types.SimpleNamespace
        self.st.add_messages("whatsapp", [Msg(guid="s1", handle="new", ts=self.now, from_me=False, text="hi")])
        self.assertEqual(daily.health(self.st, self.now + 30 * HOUR, stale_hours=1e9), [])


class TelegramTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = time.time()
        self.st, self.pids = make_store(Path(self.tmp.name) / "s.db", self.now)
        self.items = daily.today_items(self.st, self.now)

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    def test_payload_has_one_row_of_buttons_per_item_and_fits_telegram(self):
        body = daily.telegram_message(self.items, [], self.now)
        json.dumps(body)
        self.assertNotIn("parse_mode", body)  # plain text: names need no escaping
        self.assertNotIn("chat_id", body)     # the sender adds it
        rows = body["reply_markup"]["inline_keyboard"]
        self.assertEqual(len(rows), len(self.items))
        self.assertEqual([b["text"] for b in rows[0]], ["1 Done", "1 Not needed", "1 Still on"])
        for row in rows:
            for b in row:
                self.assertLessEqual(len(b["callback_data"].encode()), 64)
        self.assertIn("No tap = done.", body["text"])

    def test_no_items_no_buttons(self):
        self.assertNotIn("reply_markup", daily.telegram_message([], [], self.now))

    def test_taps_become_your_marks(self):
        first = self.items[0]
        rows = daily.telegram_message(self.items, [], self.now)["reply_markup"]["inline_keyboard"]
        self.assertEqual(daily.apply_callback(self.st, rows[0][0]["callback_data"]), "done")
        open_now = [c["action"] for c in priority.rank(self.st, self.now)]
        self.assertNotIn(first["action"], open_now)
        r = self.st.conn.execute("SELECT state, decided_by FROM resolution").fetchone()
        self.assertEqual(tuple(r), ("done", "you"))
        self.assertEqual(daily.apply_callback(self.st, rows[1][1]["callback_data"]), "dismissed")
        self.assertEqual(daily.apply_callback(self.st, rows[2][2]["callback_data"]), "open")
        self.assertIn(self.items[2]["action"], [c["action"] for c in priority.rank(self.st, self.now)])

    def test_junk_and_vanished_items_are_refused(self):
        for bad in ["", "sy1:noop", "sy1:z:1:2:m", "sy1:d:1:2:q", "sy1:d:1:2:m;DROP", "sy1:d:-1:2:m", None]:
            with self.assertRaises(ValueError):
                daily.apply_callback(self.st, bad)
        with self.assertRaises(ValueError):
            daily.apply_callback(self.st, "sy1:d:999:999:m")
        self.assertEqual(self.st.conn.execute("SELECT COUNT(*) FROM resolution").fetchone()[0], 0)

    def test_tapped_row_collapses_to_what_you_chose(self):
        markup = daily.telegram_message(self.items, [], self.now)["reply_markup"]
        data = markup["inline_keyboard"][1][1]["callback_data"]
        after = daily.tapped(markup, data)
        self.assertEqual(after["inline_keyboard"][1], [{"text": "2: not needed", "callback_data": "sy1:noop"}])
        self.assertEqual(after["inline_keyboard"][0], markup["inline_keyboard"][0])


class DigestCLITest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "s.db"
        st, _ = make_store(self.db, time.time())
        st.close()

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(main(["--db", str(self.db), "digest", *args]), 0)
        return buf.getvalue()

    def test_prints_text_and_writes_a_private_file(self):
        out = Path(self.tmp.name) / "d" / "today.txt"
        text = self.run_cli("--out", str(out))
        self.assertIn("3 things for today:", text)
        self.assertEqual(out.read_text().strip(), text.strip())
        self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o600)

    def test_telegram_format_is_json(self):
        body = json.loads(self.run_cli("--format", "telegram"))
        self.assertIn("inline_keyboard", body["reply_markup"])


@unittest.skipUnless(shutil.which("bash"), "needs bash")
class MacScriptsTest(unittest.TestCase):
    """The install scripts in DRY_RUN mode (no launchctl), and the job script on a synthetic store."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "a b&c"  # a path with a space and an ampersand
        self.data = self.root / "data"
        self.agents = self.root / "LaunchAgents"
        self.bin = self.root / "bin"
        self.bin.mkdir(parents=True)
        self.connectord = self.bin / "connectord"
        self.connectord.write_text("#!/bin/bash\n"
                                   "echo '{\"jsonrpc\":\"2.0\",\"method\":\"event\",\"params\":{\"text\":\"PRIVATE\"}}' >&2\n"
                                   "echo '{\"jsonrpc\":\"2.0\",\"method\":\"account.status\",\"params\":"
                                   "{\"account\":\"a\",\"state\":\"connected\"}}' >&2\n")
        self.connectord.chmod(0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def env(self, **kw):
        e = {k: v for k, v in os.environ.items() if not k.startswith("SOLOYOLO_")}
        e.update(DRY_RUN="1", SOLOYOLO_REPO=str(REPO), SOLOYOLO_DATA=str(self.data), SOLOYOLO_PYTHON=sys.executable,
                 SOLOYOLO_CONNECTORD=str(self.connectord), SOLOYOLO_AGENTS_DIR=str(self.agents),
                 SOLOYOLO_EXTRACTOR="heuristic", SOLOYOLO_DIGEST_AT="07:05", SOLOYOLO_WATCH_MINUTES="20",
                 SOLOYOLO_PATH=f"{self.bin}:/usr/bin:/bin")
        e.update(kw)
        return e

    def sh(self, script, *args, check=True, **env):
        p = subprocess.run(["bash", str(SCRIPTS / script), *args], env=self.env(**env), capture_output=True,
                           text=True, timeout=120)
        if check:
            self.assertEqual(p.returncode, 0, p.stderr)
        return p

    def plists(self):
        return {p.name: plistlib.loads(p.read_bytes()) for p in sorted(self.agents.glob("*.plist"))}

    def test_install_renders_valid_plists_with_escaped_paths(self):
        self.sh("install-mac.sh")
        got = self.plists()
        self.assertEqual(set(got), {"com.soloyolo.connectord.plist", "com.soloyolo.watch.plist",
                                    "com.soloyolo.digest.plist"})
        sync, watch, dig = (got[f"com.soloyolo.{n}.plist"] for n in ("connectord", "watch", "digest"))
        self.assertEqual(sync["ProgramArguments"], ["/bin/bash", str(SCRIPTS / "soloyolo-job.sh"), "sync"])
        self.assertIs(sync["KeepAlive"], True)
        self.assertIs(sync["RunAtLoad"], True)
        self.assertGreaterEqual(sync["ThrottleInterval"], 10)
        self.assertEqual(sync["EnvironmentVariables"]["SOLOYOLO_CONNECTORD"], str(self.connectord))
        self.assertEqual(watch["StartInterval"], 1200)
        self.assertEqual(dig["StartCalendarInterval"], {"Hour": 7, "Minute": 5})
        self.assertEqual(dig["EnvironmentVariables"]["SOLOYOLO_DATA"], str(self.data))  # "&" survived XML
        self.assertEqual(dig["StandardOutPath"], f"{self.data}/logs/digest.log")
        for p in got.values():
            self.assertEqual(p["Umask"], 0o077)
        self.assertEqual(stat.S_IMODE(self.data.stat().st_mode), 0o700)

    def test_install_is_idempotent(self):
        self.sh("install-mac.sh")
        first = {p.name: p.read_bytes() for p in self.agents.iterdir()}
        self.sh("install-mac.sh")
        self.assertEqual({p.name: p.read_bytes() for p in self.agents.iterdir()}, first)  # no temp files left

    def test_install_refuses_bad_settings_before_writing(self):
        for bad in (dict(SOLOYOLO_DIGEST_AT="7.30"), dict(SOLOYOLO_DATA="relative/dir"),
                    dict(SOLOYOLO_CONNECTORD=str(self.bin / "missing")), dict(SOLOYOLO_WATCH_MINUTES="1"),
                    dict(SOLOYOLO_EXTRACTOR="claude-code", SOLOYOLO_PATH="/nonexistent")):
            p = self.sh("install-mac.sh", check=False, **bad)
            self.assertNotEqual(p.returncode, 0, bad)
            self.assertFalse(self.agents.exists(), bad)

    def test_uninstall_removes_only_ours_and_keeps_data_unless_purged(self):
        self.sh("install-mac.sh")
        (self.agents / "com.other.plist").write_text("x")
        (self.data / "soloyolo.db").write_text("")
        for _ in range(2):  # idempotent
            self.sh("uninstall-mac.sh")
        self.assertEqual([p.name for p in self.agents.iterdir()], ["com.other.plist"])
        self.assertTrue(self.data.exists())
        self.sh("uninstall-mac.sh", PURGE="1")
        self.assertFalse(self.data.exists())

    def test_purge_refuses_a_folder_that_isnt_soloyolos(self):
        other = self.root / "documents"
        other.mkdir()
        (other / "keep.txt").write_text("x")
        p = self.sh("uninstall-mac.sh", check=False, PURGE="1", SOLOYOLO_DATA=str(other))
        self.assertNotEqual(p.returncode, 0)
        self.assertTrue((other / "keep.txt").exists())

    def seed_store(self):
        self.data.mkdir(parents=True, exist_ok=True)
        st = Store(self.data / "soloyolo.db")
        st.add_messages("imessage", chatdb.read(fixture.build(self.root / "chat.db")), fixture.NAMES)
        st.close()

    def test_digest_job_runs_a_pass_then_writes_todays_message(self):
        self.seed_store()
        p = self.sh("soloyolo-job.sh", "digest", SOLOYOLO_NOTIFY="0")
        today = self.data / "digest" / "today.txt"
        text = today.read_text()
        self.assertTrue(text.startswith("soloyolo · "), text)
        self.assertIn("for today:", text)  # the heuristic pass found items
        self.assertEqual(stat.S_IMODE(today.stat().st_mode), 0o600)
        self.assertTrue(list((self.data / "digest").glob("20*.txt")))
        self.assertFalse((self.data / ".extract.lock").exists())
        self.assertIn("digest written", p.stdout)

    def test_watch_skips_while_another_pass_holds_the_lock(self):
        self.seed_store()
        (self.data / ".extract.lock").mkdir()
        p = self.sh("soloyolo-job.sh", "watch")
        self.assertIn("skipped", p.stdout)
        self.assertTrue((self.data / ".extract.lock").exists())  # not ours to remove

    def test_sync_log_drops_message_text_and_keeps_status(self):
        self.sh("soloyolo-job.sh", "sync")
        log = self.data / "logs" / "connectord.log"
        for _ in range(50):  # the filter runs beside connectord and may finish a moment later
            if "account.status" in log.read_text():
                break
            time.sleep(0.1)
        text = log.read_text()
        self.assertIn('"state":"connected"', text)
        self.assertNotIn("PRIVATE", text)

    def test_watch_restarts_a_sync_whose_first_connect_failed(self):
        self.seed_store()
        (self.data / "logs").mkdir(parents=True, exist_ok=True)
        (self.data / "logs" / "connectord.log").write_text(
            '{"method":"account.status","params":{"state":"error","error":"dial tcp: no route"}}\n')
        calls = self.root / "launchctl.calls"
        fake = self.bin / "launchctl"
        fake.write_text(f'#!/bin/bash\necho "$@" >> "{calls}"\n')
        fake.chmod(0o755)
        self.sh("soloyolo-job.sh", "watch", PATH=f"{self.bin}:{os.environ['PATH']}")
        self.assertEqual(calls.read_text().split(), ["kickstart", "-k", f"gui/{os.getuid()}/com.soloyolo.connectord"])


if __name__ == "__main__":
    unittest.main()

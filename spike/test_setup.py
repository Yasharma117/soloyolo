"""python -m unittest spike.test_setup  (offline; a stand-in for connectord, and the synthetic LinkedIn export)"""
import json
import os
import stat
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

from spike import setup
from spike.server import Handler
from spike.store import Store

EXPORT = Path(__file__).parent / "fixtures/linkedin/Complete_LinkedInDataExport_11-02-2026"
# What connectord prints on a link: the code, then (once the phone accepts it) who it linked as. It also logs
# every live message; the second line stands for one, and must never reach the app.
FAKE = """#!/usr/bin/env python3
import sys, time
if "link" in sys.argv and "telegram" not in sys.argv:
    print("\\nPairing code: ABCD-EFGH\\n", flush=True)
    print('{"method":"event","params":{"text":"a private message"}}', flush=True)
    time.sleep(0.3)
    print("Linked as 919800000000@s.whatsapp.net. Syncing history; Ctrl-C to stop.", flush=True)
elif "telegram" in sys.argv:
    print("Telegram code needed: sent to your Telegram app", flush=True)
    while sys.stdin.readline().strip() != "12345":
        print("Telegram code needed: sent to your Telegram app", flush=True)
    print("Telegram password needed: hint pet", flush=True)
    sys.stdin.readline()
    print('{"method":"event","params":{"text":"a private message"}}', flush=True)
    print("Linked as 777. Syncing history; Ctrl-C to stop.", flush=True)
time.sleep(30)
"""


class SetupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.db = d / "data/soloyolo.db"
        self.db.parent.mkdir()
        Store(self.db).close()
        (d / "Downloads").mkdir()
        fake = d / "connectord"
        fake.write_text(FAKE)
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        self.env = {"SOLOYOLO_DOWNLOADS": str(d / "Downloads"), "SOLOYOLO_CONNECTORD": str(fake)}
        self.old = {k: os.environ.get(k) for k in self.env}
        os.environ.update(self.env)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), lambda *a, **k: None)
        self.port = self.httpd.server_address[1]
        self.httpd.RequestHandlerClass = partial(Handler, db=str(self.db), port=self.port)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        setup.get(self.db).stop()
        self.httpd.shutdown()
        self.httpd.server_close()
        for k, v in self.old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        self.tmp.cleanup()

    def get(self):
        return json.loads(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/setup").read())

    def post(self, what, body):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/setup/{what}", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as err:
            return err.code, err.read().decode()

    def until(self, ok, seconds=5):
        end = time.time() + seconds
        while time.time() < end:
            s = self.get()
            if ok(s):
                return s
            time.sleep(0.05)
        self.fail(f"still {s}")

    def test_link_shows_the_code_then_linked(self):
        self.assertEqual(self.get()["whatsapp"]["state"], "idle")
        code, why = self.post("whatsapp", {"phone": "98000"})
        self.assertEqual(code, 400)
        self.assertIn("country code", why)
        self.assertEqual(self.post("whatsapp", {"phone": "+91 98000-00000"})[0], 200)  # spaces, + and dashes are fine
        s = self.until(lambda s: s["whatsapp"]["state"] == "code")
        self.assertEqual(s["whatsapp"]["code"], "ABCD-EFGH")
        s = self.until(lambda s: s["whatsapp"]["state"] == "linked")
        self.assertIsNone(s["whatsapp"]["code"])
        self.assertNotIn("private message", json.dumps(s))

    def test_not_built_says_what_to_run(self):
        os.environ["SOLOYOLO_CONNECTORD"] = str(Path(self.tmp.name) / "missing")
        setup._SETUPS.clear()
        code, s = self.post("whatsapp", {"phone": "919800000000"})
        self.assertEqual((code, s["whatsapp"]["state"], s["ready"]), (200, "error", False))
        self.assertIn("setup-mac.sh", s["whatsapp"]["message"])
        setup._SETUPS.clear()

    def test_import_reads_an_export_from_downloads(self):
        name = f"{EXPORT.name}.zip"
        with zipfile.ZipFile(Path(self.env["SOLOYOLO_DOWNLOADS"]) / name, "w") as z:
            for p in EXPORT.iterdir():
                z.write(p, f"{EXPORT.name}/{p.name}")
        (Path(self.env["SOLOYOLO_DOWNLOADS"]) / "tax-return.zip").write_bytes(b"not an export")
        self.assertEqual([(f["file"], f["network"], f["job"]) for f in self.get()["exports"]], [(name, "linkedin", None)])
        self.assertEqual(self.post("import", {"file": "tax-return.zip"})[0], 404)  # only a file soloyolo found itself
        self.assertEqual(self.post("import", {"file": f"../{name}"})[0], 404)
        self.assertEqual(self.post("import", {"file": name})[0], 200)
        job = self.until(lambda s: s["exports"][0]["job"]["state"] in ("done", "error"))["exports"][0]["job"]
        self.assertEqual((job["state"], job["error"]), ("done", None))
        self.assertIn("new messages", job["summary"])
        st = Store(self.db)
        self.assertGreater(st.conn.execute("SELECT COUNT(*) FROM message WHERE network = 'linkedin'").fetchone()[0], 0)
        st.close()

    def test_read_turns_messages_into_promises(self):
        st = Store(self.db)
        t = time.time()
        rows = [SimpleNamespace(guid=f"g{i}", handle="+919811111111", from_me=i % 2, ts=t - 3600 + i, text=text)
                for i, text in enumerate(["are you free this week", "yes", "can you send the deck", "I'll send the deck by Friday", "thanks"])]
        st.add_messages("whatsapp", rows, {"+919811111111": "Ivy Secretname"})
        st.add_messages("whatsapp", [SimpleNamespace(guid="short", handle="+919822222222", from_me=0, ts=t, text="hi")], {})  # one line: never read
        st.close()
        self.assertEqual((self.get()["unread"], self.get()["read"]["state"]), (1, "idle"))
        self.assertEqual(self.post("read", {"extractor": "gpt"})[0], 400)
        lock = self.db.parent / ".extract.lock"
        lock.mkdir()  # the launchd job is mid-pass
        code, why = self.post("read", {"extractor": "heuristic"})
        self.assertEqual(code, 400)
        self.assertIn("already reading", why)
        lock.rmdir()
        self.assertEqual(self.post("read", {"extractor": "heuristic"})[0], 200)
        s = self.until(lambda s: s["read"]["state"] in ("done", "error"), seconds=20)
        self.assertEqual((s["read"]["state"], s["read"]["done"], s["read"]["total"], s["read"]["failed"], s["unread"]),
                         ("done", 1, 1, 0, 0))
        self.assertGreaterEqual(s["read"]["new"], 1)
        self.assertNotIn("Secretname", json.dumps(s))  # the pass prints names and promises; only counts come back
        self.assertNotIn("deck", json.dumps(s))
        self.assertFalse(lock.exists())

    def test_telegram_asks_for_the_code_then_the_password(self):
        code, why = self.post("telegram", {"phone": "919800000000"})
        self.assertEqual(code, 400)
        self.assertIn("api_id", why)  # no credentials yet
        (self.db.parent / "telegram-api.json").write_text('{"api_id": 1, "api_hash": "x"}')
        self.assertFalse(self.get()["telegram"]["linked"])
        self.assertEqual(self.post("telegram-code", {"code": "1"})[0], 400)  # nothing is waiting for one
        self.assertEqual(self.post("telegram", {"phone": "919800000000"})[0], 200)
        self.until(lambda s: s["telegram"]["state"] == "code")
        self.post("telegram-code", {"code": "99999"})
        s = self.until(lambda s: s["telegram"]["state"] == "code" and s["telegram"]["message"])
        self.assertIn("didn't work", s["telegram"]["message"])
        self.post("telegram-code", {"code": "12345"})
        s = self.until(lambda s: s["telegram"]["state"] == "password")
        self.assertEqual(s["telegram"]["hint"], "hint pet")
        self.post("telegram-code", {"code": "my secret"})
        s = self.until(lambda s: s["telegram"]["state"] == "linked")
        dump = json.dumps(s)
        for leak in ("private message", "my secret", "12345"):
            self.assertNotIn(leak, dump)


if __name__ == "__main__":
    unittest.main()

"""python -m unittest spike.test_linkedin_live  (offline; what the Chrome extension posts, and the export it overlaps)"""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

from spike import linkedin_export as li
from spike import linkedin_live as live
from spike.server import Handler
from spike.store import Store

EXPORT = Path(__file__).parent / "fixtures/linkedin/Complete_LinkedInDataExport_11-02-2026"
ME = "https://www.linkedin.com/in/alex-rivera-synth01"
PRIYA = "https://www.linkedin.com/in/priya-natarajan-synth02"
DANA = "https://www.linkedin.com/in/dana-kim-live"


def payload(**extra):
    """Priya's thread as the extension sees it (one message the export also has, one newer), plus a group."""
    p = {"me": {"url": ME + "/", "name": "Alex Rivera"},
         "conversations": [
             {"id": "urn:li:msg_conversation:1", "participants": [{"url": "https://in.linkedin.com/in/Priya-Natarajan-synth02?x=1", "name": "Priya Natarajan"}],
              "messages": [
                  # The export's row at 2026-10-20 14:05:02 UTC, here with milliseconds.
                  {"id": "urn:li:msg_message:a", "ts": 1792574102_400, "sender": PRIYA, "text": "Thanks! Looking forward to the deck."},
                  {"id": "urn:li:msg_message:b", "ts": 1792600000_000, "sender": ME, "text": "Sending it <b>tonight</b>"},
                  {"id": "urn:li:msg_message:c", "ts": 1792600001_000, "sender": ME, "text": "", "attachment": True},
                  {"id": "urn:li:msg_message:d", "ts": 1792600002_000, "sender": "https://www.linkedin.com/in/stranger", "text": "?"},
              ]},
             {"id": "urn:li:msg_conversation:2", "group": True, "title": "Launch crew",
              "participants": [{"url": PRIYA, "name": "Priya"}, {"url": DANA, "name": "Dana"}],
              "messages": [{"id": "urn:li:msg_message:g", "ts": 1792600000_000, "sender": DANA, "text": "Deck landed, thanks"}]},
             {"id": "urn:li:msg_conversation:3", "participants": [],  # a company page: nobody to key by
              "messages": [{"id": "urn:li:msg_message:s", "ts": 1792600000_000, "sender": "", "text": "Hi %FIRSTNAME%"}]},
             "junk",
         ]}
    p.update(extra)
    return p


class ParseTest(unittest.TestCase):
    def test_shapes_like_the_export(self):
        res = live.parse(payload())
        self.assertEqual(res.me, ME)
        self.assertEqual(res.names, {PRIYA: "Priya Natarajan"})
        self.assertEqual([(m.from_me, m.text) for m in res.messages],
                         [(False, "Thanks! Looking forward to the deck."), (True, "Sending it tonight"), (True, "[attachment]")])
        self.assertAlmostEqual(res.messages[0].ts, 1792574102.4)
        self.assertEqual([(g.sender, g.text) for g in res.groups["Launch crew"]], [("Dana", "Deck landed, thanks")])
        self.assertTrue(any("no member on the other side" in n for n in res.notes))

    def test_needs_me(self):
        with self.assertRaises(ValueError):
            live.parse({"conversations": []})


class SaveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = Store(Path(self.tmp.name) / "s.db")

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    def count(self):
        return self.st.conn.execute("SELECT COUNT(*) FROM message WHERE network = 'linkedin'").fetchone()[0]

    def test_live_then_export_stores_each_message_once(self):
        li.save(self.st, live.parse(payload()))
        self.assertEqual(self.count(), 3)
        li.save(self.st, live.parse(payload()))  # the extension resends: nothing new
        self.assertEqual(self.count(), 3)
        exported = li.load([EXPORT])
        li.save(self.st, exported)
        self.assertEqual(self.count(), 2 + len(exported.messages))  # the shared message isn't stored twice

    def test_export_then_live(self):
        exported = li.load([EXPORT])
        li.save(self.st, exported)
        li.save(self.st, live.parse(payload()))
        self.assertEqual(self.count(), len(exported.messages) + 2)
        # Same person either way: the profile URL is the handle.
        self.assertEqual(self.st.conn.execute("SELECT COUNT(*) FROM handle WHERE address = ?", (PRIYA,)).fetchone()[0], 1)


class EndpointTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "s.db"
        Store(self.db).close()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), lambda *a, **k: None)
        self.port = self.httpd.server_address[1]
        self.httpd.RequestHandlerClass = partial(Handler, db=str(self.db), port=self.port)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def post(self, body, token=None):
        headers = {"Content-Type": "application/json", "Origin": "chrome-extension://abc"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/linkedin/sync", data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as err:
            return err.code, None

    def test_needs_the_pairing_token(self):
        self.assertEqual(self.post(payload())[0], 401)  # not paired yet
        token = live.token(self.db, create=True)
        self.assertEqual(oct(live.token_path(self.db).stat().st_mode & 0o777), "0o600")
        self.assertEqual(self.post(payload(), "wrong")[0], 401)
        status, out = self.post(payload(), token)
        self.assertEqual(status, 200)
        self.assertTrue(out["summary"].startswith("3 new messages"))
        self.assertEqual(self.post({"conversations": []}, token)[0], 400)


if __name__ == "__main__":
    unittest.main()

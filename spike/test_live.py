"""python -m unittest spike.test_live  (offline; what the Chrome extension posts for Instagram and X, the exports
they overlap, and the routes the app reads). LinkedIn's payload is covered in test_linkedin_live.py."""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

from spike import instagram_export as ig
from spike import live
from spike import x_export as xx
from spike.server import Handler
from spike.store import Store

FIX = Path(__file__).parent / "fixtures"
ME_IG, KABIR, DEV = "17840000000000001", "17840000000000002", "17840000000000003"
ME_X, RIYA, SAM = "1500000000000000001", "1600000000000000002", "1700000000000000003"


def instagram(**extra):
    """Kabir's thread as the extension sees it (one message the export fixture also has, three newer), a group,
    and a thread with nobody else in it."""
    p = {"network": "instagram", "me": {"id": ME_IG, "name": "Anaya Iyer", "username": "anaya.iyer"},
         "conversations": [
             {"id": "ig-thread-1", "key": "1784512345678901", "group": False,
              "participants": [{"id": ME_IG, "name": "Anaya Iyer", "username": "anaya.iyer"},
                               {"id": KABIR, "name": "Kabir Sharma", "username": "kabirsharma"}],
              "messages": [
                  {"id": "mid.$a", "ts": 1793014400000, "sender": ME_IG, "text": "ठीक है, शुक्रिया 🙏"},  # in the export too
                  {"id": "mid.$b", "ts": 1793100000000, "sender": KABIR, "text": "", "media": ["photo", "photo"]},
                  {"id": "mid.$c", "ts": 1793100001000, "sender": KABIR, "text": "look", "link": "https://www.instagram.com/reel/abc/"},
                  {"id": "mid.$d", "ts": 1793100002000, "sender": ME_IG, "media": ["call"]},
                  {"id": "mid.$e", "ts": 1793100003000, "sender": "999", "text": "a stranger"},
                  {"id": "mid.$f", "ts": 1793100004000, "sender": KABIR, "text": ""},  # a sticker: nothing to keep
              ]},
             {"id": "ig-thread-2", "key": "1800000000000009", "group": True, "title": "Goa trip",
              "participants": [{"id": KABIR, "name": "Kabir Sharma"}, {"id": DEV, "name": "", "username": "devpatel"}],
              "messages": [{"id": "mid.$g", "ts": 1793100000000, "sender": DEV, "text": "Booked the villa"},
                           {"id": "mid.$h", "ts": 1793100005000, "sender": ME_IG, "text": "Paid my share"}]},
             {"id": "ig-thread-3", "participants": [{"id": ME_IG}], "messages": [{"id": "mid.$i", "ts": 1, "sender": ME_IG, "text": "note to self"}]},
             {"no": "id"},
         ]}
    p.update(extra)
    return p


def x(**extra):
    """One DM the archive fixture also has (same id), one newer, and a group."""
    p = {"network": "x", "me": {"id": ME_X, "name": "Anaya Iyer", "username": "anaya_iyer"},
         "conversations": [
             {"id": f"{ME_X}-{RIYA}", "group": False,
              "participants": [{"id": ME_X, "name": "Anaya Iyer", "username": "anaya_iyer"},
                               {"id": RIYA, "name": "Riya Kapoor", "username": "riya_k"}],
              "messages": [
                  {"id": "1910000000000000006", "ts": 1793178000000, "sender": RIYA, "text": "", "media": ["photo"]},  # in the archive too
                  {"id": "1990000000000000001", "ts": 1793200000000, "sender": ME_X, "text": "Q&amp;A deck is at https://example.com/deck"},
                  {"id": "1990000000000000002", "ts": 1793200001000, "sender": RIYA, "text": ""},  # a GIF alone
                  {"id": "not-a-number", "ts": 1793200002000, "sender": RIYA, "text": "?"},
              ]},
             {"id": "1930000000000000001", "group": True,
              "participants": [{"id": RIYA, "name": "Riya Kapoor", "username": "riya_k"}, {"id": SAM, "username": "sam"}],
              "messages": [{"id": "1930000000000000005", "ts": 1793200000000, "sender": SAM, "text": "Sent the invoice"},
                           {"id": "1930000000000000006", "ts": 1793200001000, "sender": "42", "text": "ok"}]},
         ]}
    p.update(extra)
    return p


class ParseTest(unittest.TestCase):
    def test_instagram_shapes_like_the_export(self):
        network, res = live.parse(instagram())
        self.assertEqual((network, res.me), ("instagram", "Anaya Iyer"))
        self.assertEqual(res.names, {"thread:1784512345678901": "Kabir Sharma"})
        self.assertEqual(res.usernames, {"thread:1784512345678901": "kabirsharma"})
        self.assertEqual([(m.from_me, m.text) for m in res.messages],
                         [(True, "ठीक है, शुक्रिया 🙏"), (False, "[photo]"),
                          (False, "[link] https://www.instagram.com/reel/abc/ look"), (True, "[call]")])
        self.assertAlmostEqual(res.messages[0].ts, 1793014400.0)
        self.assertEqual([(g.sender, g.text) for g in res.groups["Goa trip"]], [("devpatel", "Booked the villa"), ("me", "Paid my share")])
        self.assertTrue(any("only you" in n for n in res.notes))
        self.assertTrue(any("malformed conversations" in n for n in res.notes))

    def test_x_shapes_like_the_archive(self):
        network, res = live.parse(x())
        self.assertEqual((network, res.me), ("x", ME_X))
        self.assertEqual(res.people, {f"id:{RIYA}": {"x_id": RIYA, "x": "riya_k"}})
        self.assertEqual(res.names, {f"id:{RIYA}": "Riya Kapoor"})
        self.assertEqual([(m.guid, m.from_me, m.text) for m in res.messages],
                         [("1910000000000000006", False, "[photo]"),
                          ("1990000000000000001", True, "Q&A deck is at https://example.com/deck")])
        self.assertEqual([(g.sender, g.text) for g in res.groups["1930000000000000001"]],
                         [("@sam", "Sent the invoice"), ("X user 42", "ok")])

    def test_needs_me_and_a_known_network(self):
        for bad in (instagram(me={}), x(me={"id": "anaya"}), instagram(network="myspace"), {"conversations": []}, []):
            with self.assertRaises(ValueError):
                live.parse(bad)

    def test_default_network_is_for_the_old_route_only(self):
        me = "https://www.linkedin.com/in/alex"
        self.assertEqual(live.parse({"me": {"url": me}, "conversations": []}, "linkedin")[0], "linkedin")
        # The one format: LinkedIn's ids are profile URLs, and media stands in for the old `attachment` flag.
        _, res = live.parse({"network": "linkedin", "me": {"id": me}, "conversations": [
            {"id": "c1", "participants": [{"id": "https://www.linkedin.com/in/dana", "name": "Dana"}],
             "messages": [{"id": "m1", "ts": 1792600000000, "sender": me, "media": ["attachment"]}]}]})
        self.assertEqual([(m.handle, m.from_me, m.text) for m in res.messages],
                         [("https://www.linkedin.com/in/dana", True, "[attachment]")])


class SaveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = Store(Path(self.tmp.name) / "s.db")

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    def count(self, network):
        return self.st.conn.execute("SELECT COUNT(*) FROM message WHERE network = ?", (network,)).fetchone()[0]

    def sync(self, payload):
        return live.save(self.st, *live.parse(payload))

    def test_instagram_live_and_export_store_each_message_once(self):
        self.assertTrue(self.sync(instagram()).startswith("4 new messages"))
        self.assertTrue(self.sync(instagram()).startswith("0 new messages"))  # the extension resends: nothing new
        exported = ig.load([FIX / "instagram"])
        ig.save(self.st, exported)
        self.assertEqual(self.count("instagram"), 3 + len(exported.messages))  # the shared message isn't stored twice
        self.sync(instagram())  # and the other way round: the export first, then the extension
        self.assertEqual(self.count("instagram"), 3 + len(exported.messages))
        # Same person either way: the thread key is the handle, and the live sync adds the username.
        row = self.st.conn.execute("SELECT COUNT(*), MIN(person_id) FROM handle WHERE address = 'thread:1784512345678901'").fetchone()
        self.assertEqual(row[0], 1)
        self.assertIn(("instagram", "kabirsharma"), {tuple(r) for r in self.st.conn.execute(
            "SELECT key, value FROM attribute WHERE person_id = ?", (row[1],))})

    def test_x_live_and_archive_store_each_dm_once(self):
        self.assertTrue(self.sync(x()).startswith("2 new messages"))
        exported = xx.load([FIX / "x"])
        self.assertIn("1910000000000000006", {m.guid for m in exported.messages})
        xx.save(self.st, exported)
        self.assertEqual(self.count("x"), 1 + len(exported.messages))
        self.sync(x())
        self.assertEqual(self.count("x"), 1 + len(exported.messages))
        self.assertEqual(self.st.conn.execute("SELECT COUNT(*) FROM handle WHERE address = ?", (f"id:{RIYA}",)).fetchone()[0], 1)


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

    def call(self, path, body=None, token=None, origin="chrome-extension://abc"):
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", headers=headers,
                                     data=None if body is None else json.dumps(body).encode())
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as err:
            return err.code, None

    def test_one_token_for_every_network(self):
        self.assertEqual(self.call("/api/live/sync", x())[0], 401)  # not paired yet
        self.assertEqual(self.call("/api/live/status")[1]["paired"], False)
        # The app asks for the token from its own origin; a page elsewhere can't.
        self.assertEqual(self.call("/api/live/token", {}, origin="https://evil.example")[0], 403)
        status, out = self.call("/api/live/token", {}, origin=f"http://127.0.0.1:{self.port}")
        self.assertEqual(status, 200)
        token = out["token"]
        self.assertEqual(token, live.token(self.db))
        self.assertEqual(oct(live.token_path(self.db).stat().st_mode & 0o777), "0o600")

        self.assertEqual(self.call("/api/live/sync", x(), "wrong")[0], 401)
        self.assertEqual(self.call("/api/live/sync", x(), token, origin="https://x.com")[0], 403)  # only the extension posts here
        self.assertEqual(self.call("/api/live/sync", {"ping": True}, token), (200, {"ok": True}))
        for payload, network, new in ((x(), "x", "2 new"), (instagram(), "instagram", "4 new")):
            status, out = self.call("/api/live/sync", payload, token)
            self.assertEqual((status, out["network"]), (200, network))
            self.assertTrue(out["summary"].startswith(new), out["summary"])
        self.assertEqual(self.call("/api/live/sync", {"me": {"id": ME_X}, "conversations": []}, token)[0], 400)  # which network?
        # The first version of the extension posted LinkedIn here, without naming the network.
        me = "https://www.linkedin.com/in/alex"
        self.assertEqual(self.call("/api/linkedin/sync", {"me": {"url": me, "name": "Alex"}, "conversations": []}, token)[0], 200)

    def test_status_is_per_network(self):
        token = live.token(self.db, create=True)
        self.call("/api/live/sync", x(), token)
        self.assertEqual(self.call("/api/live/status", {"network": "instagram", "enabled": True,
                                                        "error": "Instagram's answer has no inbox in it", "junk": 1}, token)[0], 200)
        self.assertEqual(self.call("/api/live/status", {"network": "linkedin", "enabled": False}, token)[0], 200)
        self.assertEqual(self.call("/api/live/status", {"network": "myspace"}, token)[0], 400)
        self.assertEqual(self.call("/api/live/status", {"network": "x", "enabled": False})[0], 401)
        out = self.call("/api/live/status", origin=None)[1]
        self.assertEqual(out["paired"], True)
        self.assertEqual(set(out["networks"]), {"linkedin", "instagram", "x"})
        nx, ni, nl = out["networks"]["x"], out["networks"]["instagram"], out["networks"]["linkedin"]
        self.assertTrue(nx["ok"] and nx["summary"].startswith("2 new messages"))
        self.assertEqual((nx["you"], nx["error"], nx["enabled"]), ("Anaya Iyer", None, True))
        self.assertEqual((ni["error"], ni["enabled"], ni["ok"]), ("Instagram's answer has no inbox in it", True, None))
        self.assertTrue(ni["failed"])
        self.assertEqual((nl["enabled"], nl["ok"], nl["error"]), (False, None, None))
        self.assertEqual(oct(live.state_path(self.db).stat().st_mode & 0o777), "0o600")
        self.assertNotIn("junk", json.loads(live.state_path(self.db).read_text())["instagram"])


if __name__ == "__main__":
    unittest.main()

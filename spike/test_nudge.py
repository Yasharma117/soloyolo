"""python -m unittest spike.test_nudge  (offline; synthetic chats only, never the API)"""
import contextlib
import io
import json
import tempfile
import threading
import time
import unittest
import urllib.request
from datetime import date, datetime, timedelta
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

from spike import nudge, priority, replay
from spike.store import Store

DAY = 86400


class Chats:
    """A store built from scripted chats: say() adds a message n days before NOW, item() an extracted item."""
    NOW = datetime(2026, 3, 18, 9, 0).timestamp()  # a Wednesday morning, local time

    def __init__(self, path):
        self.st = Store(path)
        self.n = 0

    def say(self, who: str, days_ago: float, from_me: bool, text: str) -> int:
        self.n += 1
        Msg = type("M", (), {})
        m = Msg()
        m.guid, m.handle, m.ts, m.from_me, m.text = f"g{self.n}", who, self.NOW - days_ago * DAY, from_me, text
        self.st.add_messages("x", [m], {who: who.title()})
        return self.st.conn.execute("SELECT id FROM message WHERE remote_id = ?", (m.guid,)).fetchone()[0]

    def pid(self, who: str) -> int:
        return self.st.conn.execute("SELECT person_id FROM handle WHERE address = ?", (who,)).fetchone()[0]

    def items(self, who: str, *items: dict) -> None:
        rows = [dict(dict(kind="promise", owner="me", due=None, status="open", done_message_id=None), **i) for i in items]
        self.st.replace_extraction(self.pid(who), rows, [], "heuristic")

    @staticmethod
    def due(days_from_now: int) -> str:
        return (datetime.fromtimestamp(Chats.NOW).date() + timedelta(days=days_from_now)).isoformat()


class NudgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "s.db"
        self.c = Chats(self.path)
        self.now = Chats.NOW

    def tearDown(self):
        self.c.st.close()
        self.tmp.cleanup()

    def today(self):
        return [i["action"] for i in nudge.today(self.c.st, self.now)]

    def live(self):
        return {i["action"]: i for i in nudge.assess(self.c.st, self.now)}

    # --- the window: days, not weeks ------------------------------------------------------
    def test_fresh_item_shown_older_one_quiet_but_kept(self):
        new = self.c.say("asha", 1, False, "Can you send the lease draft")
        old = self.c.say("asha", 6, False, "Can you check the parking slot")
        self.c.items("asha", dict(kind="ask", action="Send the lease draft", source_message_id=new),
                     dict(kind="ask", action="Check the parking slot", source_message_id=old))
        self.assertEqual(self.today(), ["Send the lease draft"])
        # Hidden, not deleted: the full ranked list still has it.
        self.assertIn("Check the parking slot", [i["action"] for i in priority.rank(self.c.st, self.now)])
        self.assertFalse(self.live()["Check the parking slot"]["live"])

    def test_silence_means_done_after_three_days(self):
        m = self.c.say("asha", 2.9, True, "I'll send you the receipts")
        self.c.items("asha", dict(action="Send Asha the receipts", source_message_id=m))
        self.assertEqual(self.today(), ["Send Asha the receipts"])
        self.now += 0.2 * DAY
        self.assertEqual(self.today(), [])

    def test_due_date_brings_an_old_item_back_with_one_day_of_grace(self):
        a = self.c.say("ben", 20, True, "will pay the society fee before the deadline")
        b = self.c.say("ben", 20, True, "and renew the insurance")
        d = self.c.say("ben", 20, True, "and file the claim")
        e = self.c.say("ben", 20, True, "and book the plumber")
        self.c.items("ben", dict(action="Pay the society fee", due=Chats.due(2), source_message_id=a),
                     dict(action="Renew the insurance", due=Chats.due(5), source_message_id=b),
                     dict(action="File the claim", due=Chats.due(-1), source_message_id=d),
                     dict(action="Book the plumber", due=Chats.due(-2), source_message_id=e))
        live = {k for k, v in self.live().items() if v["live"]}
        self.assertEqual(live, {"Pay the society fee", "File the claim"})  # due in 2d; overdue by one day

    def test_due_tomorrow_item_ends_after_its_grace_day_not_three_days(self):
        m = self.c.say("ben", 0.5, True, "I'll drop the keys tomorrow")
        self.c.items("ben", dict(action="Drop the keys", due=Chats.due(1), source_message_id=m))
        self.assertTrue(self.live()["Drop the keys"]["live"])
        self.now += 3 * DAY  # Saturday morning: due Thursday, grace Friday
        self.assertFalse(self.live()["Drop the keys"]["live"])

    # --- chasers --------------------------------------------------------------------------
    def chased(self, chaser: str, days_ago: float = 1, from_me: bool = False, owner: str = "me",
               action: str = "Send the flat photos", source: str = "Send me the flat photos please"):
        src = self.c.say("cara", 10, not from_me, source)
        self.c.say("cara", days_ago, from_me, chaser)
        self.c.items("cara", dict(kind="ask", owner=owner, action=action, source_message_id=src))
        return self.live()[action]

    def test_english_follow_up_revives_with_reason_and_points(self):
        item = self.chased("any update on the photos?")
        self.assertTrue(item["live"])
        self.assertEqual(item["reasons"][0], "they chased 1d ago")
        base = next(i for i in priority.rank(self.c.st, self.now) if i["action"] == "Send the flat photos")
        self.assertEqual(item["score"], round(base["score"] + nudge.CHASE_POINTS, 2))

    def test_hinglish_follow_ups_revive(self):
        for text in ("photos bhej do", "flat ki photos kab bhejoge?", "kya hua??"):
            with self.subTest(text=text):
                self.c.st.conn.execute("DELETE FROM message")
                self.assertTrue(self.chased(text)["live"], text)

    def test_asking_again_in_the_same_words(self):
        item = self.chased("Can you send me the flat photos?", days_ago=2)
        self.assertTrue(item["live"])
        self.assertIn("they asked again 2d ago", item["reasons"])

    def test_not_chasers(self):
        cases = {
            "too soon after the ask": dict(chaser="any update on the photos?", days_ago=9.9),
            "an unrelated question sharing one word": dict(chaser="Flat se office kitna door hai?"),
            "a photo itself": dict(chaser="[photo]"),
            "my own reminder about what I owe": dict(chaser="any update on the photos?", from_me=True),
            "a long message that mentions it": dict(chaser="Photos of the flat in Goa from last year came out great, "
                                                           "remember the sunset? Send me yours when you can, I want to "
                                                           "print a few of them for the wall at home this weekend."),
            "a short ask mostly about something else": dict(chaser="photos of Meera's car bhejo"),
        }
        for why, kw in cases.items():
            with self.subTest(why):
                self.c.st.conn.execute("DELETE FROM message")
                item = self.chased(**kw)
                self.assertFalse(item["live"], why)

    def test_waiting_on_them_is_revived_by_your_chase(self):
        item = self.chased("any update on the refund?", from_me=True, owner="them",
                           action="Send the refund", source="I'll send the refund by Monday")
        self.assertEqual(item["reasons"][0], "you chased 1d ago")

    def test_a_bare_chase_goes_to_the_newest_item_only(self):
        older = self.c.say("dev", 9, False, "pls share the invoice")
        newer = self.c.say("dev", 8, False, "also the tax form")
        self.c.say("dev", 1, False, "Kya hua??")
        self.c.items("dev", dict(kind="ask", action="Share the invoice", source_message_id=older),
                     dict(kind="ask", action="Send the tax form", source_message_id=newer))
        live = {k for k, v in self.live().items() if v["live"]}
        self.assertEqual(live, {"Send the tax form"})

    # --- your marks win -------------------------------------------------------------------
    def test_your_marks_win_over_a_chase(self):
        src = self.c.say("eli", 10, False, "send me the flat photos")
        self.c.say("eli", 1, False, "any update on the photos?")
        self.c.items("eli", dict(kind="ask", action="Send the flat photos", source_message_id=src))
        pid = self.c.pid("eli")
        for state in ("done", "dismissed"):
            with self.subTest(state):
                self.c.st.resolve(pid, src, "me", state, "you")
                self.assertEqual(self.today(), [])

    def test_snooze_hides_then_reminds(self):
        src = self.c.say("eli", 1, False, "send me the flat photos")
        self.c.items("eli", dict(kind="ask", action="Send the flat photos", source_message_id=src))
        self.c.st.resolve(self.c.pid("eli"), src, "me", "snoozed", "you", until=self.now + 4 * DAY)
        self.assertEqual(self.today(), [])
        self.now += 5 * DAY  # snooze over: live for a window, though the item is now 6 days old
        self.assertEqual(self.today(), ["Send the flat photos"])
        self.now += 3 * DAY
        self.assertEqual(self.today(), [])

    def test_still_open_gives_a_fresh_window(self):
        src = self.c.say("eli", 10, False, "send me the flat photos")
        self.c.items("eli", dict(kind="ask", action="Send the flat photos", source_message_id=src))
        self.assertEqual(self.today(), [])
        self.c.st.resolve(self.c.pid("eli"), src, "me", "open", "you")
        self.c.st.conn.execute("UPDATE resolution SET at = ?", (self.now - DAY,))
        self.assertEqual(self.today(), ["Send the flat photos"])

    # --- picking ---------------------------------------------------------------------------
    def test_at_most_three_spread_across_people(self):
        for who in ("fay", "gus"):
            ids = [self.c.say(who, 1, False, f"{who} thing {k}") for k in range(3)]
            self.c.items(who, *[dict(action=f"{who} thing {k}", source_message_id=i) for k, i in enumerate(ids)])
        shown = nudge.today(self.c.st, self.now)
        self.assertEqual(len(shown), 3)
        self.assertEqual({i["name"] for i in shown}, {"Fay", "Gus"})
        s = nudge.summary(self.c.st, self.now)
        self.assertEqual((s["live"], s["quiet"], s["open"]), (6, 0, 6))

    def test_nothing_live_is_an_empty_today(self):
        m = self.c.say("hal", 30, True, "will call the bank")
        self.c.items("hal", dict(action="Call the bank", source_message_id=m))
        self.assertEqual(nudge.today(self.c.st, self.now), [])

    # --- wiring ----------------------------------------------------------------------------
    def test_cli_today(self):
        from spike.__main__ import main
        self.c.NOW = time.time()  # the CLI asks about now
        m = self.c.say("ivy", 1, True, "I'll send the slides")
        self.c.items("ivy", dict(action="Send Ivy the slides", source_message_id=m))
        self.c.st.close()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["--db", str(self.path), "today"]), 0)
            self.assertEqual(main(["--db", str(self.path), "top"]), 0)  # still there
        self.assertIn("Today: 1.", out.getvalue())
        self.assertIn("Send Ivy the slides", out.getvalue())
        self.c.st = Store(self.path)

    def test_viewer_serves_today(self):
        from spike.server import Handler
        self.c.NOW = time.time()  # the viewer asks about now
        m = self.c.say("ivy", 0.5, True, "I'll send the slides")
        self.c.items("ivy", dict(action="Send Ivy the slides", source_message_id=m))
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), lambda *a, **k: None)
        port = httpd.server_address[1]
        httpd.RequestHandlerClass = partial(Handler, db=str(self.path), port=port)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            body = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/today").read())
            self.assertEqual([i["action"] for i in body["today"]], ["Send Ivy the slides"])
            page = urllib.request.urlopen(f"http://127.0.0.1:{port}/viewer").read().decode()
            self.assertIn('select("today")', page)
            app = urllib.request.urlopen(f"http://127.0.0.1:{port}/").read().decode()
            self.assertTrue(app.startswith("<!doctype html>") and "async function today()" in app)
            body = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/all").read())
            self.assertEqual([(i["action"], i["live"]) for i in body], [("Send Ivy the slides", True)])
        finally:
            httpd.shutdown()
            httpd.server_close()


class ReplayTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "s.db"
        self.c = Chats(self.path)

    def tearDown(self):
        self.c.st.close()
        self.tmp.cleanup()

    def test_as_of_knows_only_the_past(self):
        ask = self.c.say("jo", 5, False, "send the form pls")
        done = self.c.say("jo", 3, True, "sent")
        later = self.c.say("jo", 1, False, "also the photo")
        self.c.items("jo", dict(kind="ask", action="Send the form", status="done", source_message_id=ask,
                                done_message_id=done),
                     dict(kind="ask", action="Send the photo", source_message_id=later))
        self.c.st.resolve(self.c.pid("jo"), ask, "me", "dismissed", "you")
        t = Chats.NOW - 4 * DAY
        snap = replay.as_of(self.c.st, t)
        try:
            self.assertEqual(snap.conn.execute("SELECT COUNT(*) FROM message").fetchone()[0], 1)
            rows = [dict(r) for r in snap.conn.execute("SELECT action, status, done_message_id FROM commitment")]
            self.assertEqual(rows, [dict(action="Send the form", status="open", done_message_id=None)])
            self.assertEqual(snap.conn.execute("SELECT COUNT(*) FROM resolution").fetchone()[0], 0)  # marked later
            self.assertEqual([i["action"] for i in nudge.today(snap, t)], ["Send the form"])
        finally:
            snap.close()
        # The store itself is untouched.
        self.assertEqual(self.c.st.conn.execute("SELECT COUNT(*) FROM message").fetchone()[0], 3)
        self.assertEqual(self.c.st.conn.execute("SELECT COUNT(*) FROM resolution").fetchone()[0], 1)

    def test_report_numbers_lines_and_follows_your_marks(self):
        ask = self.c.say("jo", 5, False, "send the form pls")
        self.c.items("jo", dict(kind="ask", action="Send the form", source_message_id=ask))
        self.c.st.resolve(self.c.pid("jo"), ask, "me", "done", "you")
        end = datetime.fromtimestamp(Chats.NOW).date()
        rows = replay.run(self.c.st, replay.mornings(end, 7))
        self.assertEqual([len(r["today"]) for r in rows], [0, 1, 1, 1, 0, 0, 0])  # from Friday 09:00, for three mornings
        text = replay.report(self.c.st, rows, Chats.NOW)
        self.assertIn("1. You owe (asked) · Jo: Send the form", text)
        self.assertIn("| 1 | Send the form | done |", text)
        self.assertIn("| 3 |", text)  # three mornings shown


if __name__ == "__main__":
    unittest.main()

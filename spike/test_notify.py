"""python -m unittest spike.test_notify  (offline, synthetic notification batches)"""
import json
import tempfile
import unittest
from pathlib import Path

from spike import notify_ingest as ni
from spike.store import Store

T0 = 1_760_000_000_000  # ms


def msg(package="com.linkedin.android", conversation="Priya Shah", sender="Priya Shah", text="hello", ts=T0,
        group=False, **kw):
    return dict(package=package, conversation=conversation, sender=sender, text=text, ts=ts, group=group,
                from_me=sender is None, ts_source=kw.pop("ts_source", "message"), **kw)


class NotifyIngestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = Store(Path(self.tmp.name) / "s.db")

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    def ingest(self, *msgs):
        return ni.ingest(self.st, ni.parse({"schema": 1, "messages": list(msgs)}))

    def messages(self):
        return [dict(r) for r in self.st.conn.execute(
            "SELECT m.network, m.remote_id, m.ts, m.from_me, m.text, h.address, p.display_name FROM message m"
            " JOIN handle h ON h.person_id = m.person_id JOIN person p ON p.id = m.person_id ORDER BY m.ts")]

    def test_network_from_package(self):
        pkgs = {"com.linkedin.android": "linkedin", "com.instagram.android": "instagram", "com.twitter.android": "x",
                "com.Slack": "slack", "org.telegram.messenger": "telegram", "com.google.android.apps.messaging": "sms",
                "com.whatsapp": "whatsapp", "com.whatsapp.w4b": "whatsapp"}
        self.ingest(*[msg(package=p, text=f"hi from {p}") for p in pkgs])
        self.assertEqual(sorted(r["network"] for r in self.messages()), sorted(pkgs.values()))

    def test_low_confidence_handle_and_name(self):
        self.ingest(msg(text="Any update on the intro?"))
        r = self.messages()[0]
        self.assertEqual(r["address"], "notif:priya shah")
        self.assertTrue(ni.is_low_confidence(r["address"]))
        self.assertEqual(r["display_name"], "Priya Shah")
        self.assertAlmostEqual(r["ts"], T0 / 1000)

    def test_title_differs_from_sender(self):
        self.ingest(msg(package="com.Slack", conversation="Acme", sender="Priya"))
        self.assertEqual(self.messages()[0]["address"], "notif:priya@acme")

    def test_your_reply_joins_their_thread(self):
        self.ingest(msg(package="com.Slack", conversation="Acme", sender="Priya", text="Can you send the deck?"),
                    msg(package="com.Slack", conversation="Acme", sender=None, text="Sending tonight", ts=T0 + 60_000))
        rows = self.messages()
        self.assertEqual({r["address"] for r in rows}, {"notif:priya@acme"})
        self.assertEqual([r["from_me"] for r in rows], [0, 1])

    def test_repost_dedupes(self):
        a = msg(text="Any update?")
        self.assertEqual(self.ingest(a)["messages"], 1)
        # The next notification for the chat carries the old message again, plus a new one.
        out = self.ingest(a, msg(text="Ping", ts=T0 + 5_000))
        self.assertEqual(out["messages"], 1)
        self.assertEqual(len(self.messages()), 2)

    def test_dedupe_key_covers_each_field(self):
        base = ni.remote_id("com.whatsapp", "Priya", "Priya", "hi", T0)
        self.assertEqual(base, ni.remote_id("com.whatsapp", " priya ", "PRIYA", "hi", T0))
        for other in [ni.remote_id("com.Slack", "Priya", "Priya", "hi", T0),
                      ni.remote_id("com.whatsapp", "Team", "Priya", "hi", T0),
                      ni.remote_id("com.whatsapp", "Priya", "Raj", "hi", T0),
                      ni.remote_id("com.whatsapp", "Priya", "Priya", "hi!", T0),
                      ni.remote_id("com.whatsapp", "Priya", "Priya", "hi", T0 + 1)]:
            self.assertNotEqual(base, other)

    def test_post_time_reposts_collapse(self):
        # A plain notification has only a post time, which moves when the app reposts the same text.
        self.ingest(msg(text="Following up", ts_source="post"),
                    msg(text="Following up", ts=T0 + 120_000, ts_source="post"))
        self.assertEqual(len(self.messages()), 1)

    def test_same_text_later_is_a_new_message(self):
        self.ingest(msg(text="any update?"), msg(text="any update?", ts=T0 + 3 * 86400_000))
        self.assertEqual(len(self.messages()), 2)  # asking again is exactly what chaser detection needs

    def test_skips_what_connectord_already_synced(self):
        M = type("M", (), {})
        m = M(); m.guid, m.handle, m.ts, m.from_me, m.text = "wa-1", "919800000000@s.whatsapp.net", T0 / 1000 + 3, False, "Any update?"
        self.st.add_messages("whatsapp", [m], {"919800000000@s.whatsapp.net": "Priya"})
        out = self.ingest(msg(package="com.whatsapp", text="Any update?"))
        self.assertEqual(out, {"messages": 0, "group_lines": 0, "already_synced": 1})

    def test_groups_become_evidence(self):
        out = self.ingest(
            msg(package="com.whatsapp", conversation="Family", sender="Mum", text="Booked the 9:30 flight", group=True),
            msg(package="com.whatsapp", conversation="Family", sender=None, text="Thanks!", group=True, ts=T0 + 1000),
            msg(package="com.Slack", conversation="#launch", sender="Raj", text="Shipped", group=True))
        self.assertEqual(out["group_lines"], 3)
        self.assertEqual(self.messages(), [])
        ev = [dict(r) for r in self.st.conn.execute("SELECT source, sender, text FROM evidence ORDER BY ts")]
        self.assertEqual({e["source"] for e in ev}, {"whatsapp-group:Family", "slack-group:#launch"})
        self.assertIn({"source": "whatsapp-group:Family", "sender": "me", "text": "Thanks!"}, ev)
        self.assertEqual(self.ingest(msg(package="com.whatsapp", conversation="Family", sender="Mum",
                                         text="Booked the 9:30 flight", group=True))["group_lines"], 0)

    def test_privacy_drops(self):
        b = ni.parse({"messages": [
            msg(package="com.hdfcbank.payzapp", text="hello"),
            msg(text="Your verification code is 482913. Do not share it."),
            msg(package="com.google.android.apps.messaging", conversation="VM-HDFCBK", sender="VM-HDFCBK",
                text="Rs 950 credited to a/c XX12"),
            msg(text="Code: 7731"),
            msg(text="Sensitive notification content hidden"),
            msg(text="3 new messages"),
            msg(text="See you at 1830, gate 4"),
        ]})
        kept = [r.text for rows in b.rows.values() for r in rows]
        self.assertEqual(kept, ["See you at 1830, gate 4"])
        self.assertEqual(sum(b.skipped.values()), 6)

    def test_otp_rule(self):
        for t in ["123456 is your Instagram code", "Your OTP is 4412", "G-482913 is your Google verification code",
                  "Use 8812 as your one-time password"]:
            self.assertTrue(ni.is_otp(t), t)
        for t in ["Can you send the 2024 report?", "call me at 1830", "your code review is done"]:
            self.assertFalse(ni.is_otp(t), t)

    def test_cli_import(self):
        from spike.__main__ import main
        f = Path(self.tmp.name) / "batch.json"
        f.write_text(json.dumps({"schema": 1, "messages": [msg(text="Any update on the intro?")]}))
        db = str(Path(self.tmp.name) / "cli.db")
        self.assertEqual(main(["--db", db, "import-notifications", str(f)]), 0)
        st = Store(db)
        self.assertEqual(st.conn.execute("SELECT COUNT(*) FROM message").fetchone()[0], 1)
        st.close()


if __name__ == "__main__":
    unittest.main()

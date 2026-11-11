"""python -m unittest spike.test_spike  (offline; never calls the API)"""
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from spike import chatdb, fixture
from spike.extract import ClaudeCodeExtractor, ClaudeExtractor, Commitment, Extraction, HeuristicExtractor, render
from spike.store import Store


class ChatDBTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.now = time.time()
        cls.path = fixture.build(Path(cls.tmp.name) / "chat.db", now=cls.now)
        cls.rows = chatdb.read(cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_attributed_body_roundtrip(self):
        for text in ["hi", "x" * 200, "emoji 🎉 ok"]:
            self.assertEqual(chatdb.decode_attributed_body(fixture.attributed_body(text)), text)
        self.assertIsNone(chatdb.decode_attributed_body(b"garbage"))
        self.assertIsNone(chatdb.decode_attributed_body(b"..NSString\x01+"))  # truncated: skipped, no crash

    def test_text_recovered_from_attributed_body(self):
        self.assertIn("Sent, check your email", [r.text for r in self.rows])

    def test_filters_tapbacks_shortcodes_and_groups(self):
        texts = [r.text for r in self.rows]
        self.assertNotIn('Loved "Any luck reaching Priya?"', texts)
        self.assertFalse(any("verification code" in t for t in texts))
        self.assertNotIn("Count me in", texts)
        self.assertEqual(len(self.rows), len(fixture.THREADS) - 1)

    def test_since_filter(self):
        recent = chatdb.read(self.path, since_unix=self.now - 7 * 86400)
        self.assertTrue(recent)
        self.assertTrue(all(r.ts >= self.now - 7 * 86400 for r in recent))


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.store = Store(d / "s.db")
        self.store.add_messages("imessage", chatdb.read(fixture.build(d / "chat.db")), fixture.NAMES)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def pid(self, name):
        return next(p["id"] for p in self.store.people() if p["name"] == name)

    def test_ingest_is_idempotent(self):
        again = self.store.add_messages("imessage", chatdb.read(Path(self.tmp.name) / "chat.db"))
        self.assertEqual(again, 0)

    def test_heuristic_finds_open_and_done(self):
        ex = HeuristicExtractor()
        sam = ex.extract([dict(r) for r in self.store.thread(self.pid("Sam Okafor"))])
        self.assertEqual([(c.owner, c.status) for c in sam.commitments], [("me", "open")])
        self.assertIsNotNone(sam.commitments[0].due)  # "by Friday"
        maya = ex.extract([dict(r) for r in self.store.thread(self.pid("Maya Lin"))])
        self.assertEqual(sorted((c.owner, c.status) for c in maya.commitments), [("me", "done"), ("them", "open")])

    def test_ranking_puts_promises_you_owe_first(self):
        ex = HeuristicExtractor()
        for pid in self.store.person_ids():
            r = ex.extract([dict(m) for m in self.store.thread(pid)])
            self.store.replace_extraction(pid, [c.model_dump() for c in r.commitments], r.topics, ex.name)
        people = self.store.people()
        owes = [any(c["owner"] == "me" and c["status"] == "open" for c in p["commitments"]) for p in people]
        self.assertEqual(owes, sorted(owes, reverse=True))

    def test_claude_extractor_drops_hallucinated_citations(self):
        thread = [dict(r) for r in self.store.thread(self.pid("Sam Okafor"))]
        real = thread[3]["id"]
        fake = Extraction(topics=["hiring", "design", "intros", "dinner", "extra"], commitments=[
            Commitment(kind="promise", owner="me", action="Intro Sam to Priya", due=None, status="open",
                       source_message_id=real, done_message_id=99999),
            Commitment(kind="promise", owner="them", action="Invented", due=None, status="open",
                       source_message_id=99999, done_message_id=None),
        ])
        ex = ClaudeExtractor.__new__(ClaudeExtractor)  # skip client construction
        ex.name, ex.effort = "claude-opus-5-5", "medium"
        ex.client = mock.Mock()
        ex.client.beta.messages.parse.return_value = mock.Mock(stop_reason="end_turn", parsed_output=fake)
        out = ex.extract(thread)
        self.assertEqual([c.action for c in out.commitments], ["Intro Sam to Priya"])
        self.assertIsNone(out.commitments[0].done_message_id)
        self.assertEqual(len(out.topics), 4)
        sent = ex.client.beta.messages.parse.call_args.kwargs
        self.assertEqual(sent["model"], "claude-opus-5-5")
        self.assertIn(f"[{real}]", sent["messages"][0]["content"])

    def test_render_marks_speaker(self):
        line = render([{"id": 7, "ts": 0, "from_me": 1, "text": "hello"}])
        self.assertTrue(line.startswith("[7] ") and line.endswith("me: hello"))


FAKE_CLAUDE = r"""#!/usr/bin/env python3
import json, os, sys
thread = sys.stdin.read()
log = os.environ["FAKE_CLAUDE_LOG"]
json.dump({"argv": sys.argv[1:], "stdin": thread, "cwd": os.getcwd()}, open(log, "w"))
if os.environ.get("FAKE_CLAUDE_MODE") == "error":
    print(json.dumps({"type": "result", "is_error": True, "subtype": "error_during_execution", "result": "boom"}))
    sys.exit(1)
print(json.dumps({"type": "result", "is_error": False, "subtype": "success", "structured_output": {
    "topics": ["hiring"],
    "commitments": [
        {"kind": "promise", "owner": "me", "action": "Intro Sam to Priya", "due": None, "status": "done",
         "source_message_id": int(os.environ["FAKE_SRC"]), "done_message_id": 424242},
        {"kind": "ask", "owner": "them", "action": "Invented", "due": None, "status": "open",
         "source_message_id": 99999, "done_message_id": None}]}}))
"""


class ClaudeCodeExtractorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        fake = d / "claude"
        fake.write_text(FAKE_CLAUDE)
        fake.chmod(0o755)
        self.log = d / "call.json"
        self.thread = [{"id": 7, "ts": 0, "from_me": 1, "text": "I'll intro you to Priya zq-private-77"},
                       {"id": 8, "ts": 60, "from_me": 0, "text": "thanks"}]
        self.env = mock.patch.dict("os.environ", {"FAKE_CLAUDE_LOG": str(self.log), "FAKE_SRC": "7"})
        self.env.start()
        self.ex = ClaudeCodeExtractor(binary=str(fake))

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_thread_goes_on_stdin_and_output_is_checked(self):
        import json
        out = self.ex.extract(self.thread)
        call = json.loads(self.log.read_text())
        self.assertIn("zq-private-77", call["stdin"])
        self.assertFalse(any("zq-private-77" in a for a in call["argv"]))  # message text never in argv
        for flag in ["--tools", "--strict-mcp-config", "--no-session-persistence", "--json-schema"]:
            self.assertIn(flag, call["argv"])
        self.assertNotEqual(Path(call["cwd"]).resolve(), Path.cwd().resolve())  # no project context
        self.assertEqual([c.action for c in out.commitments], ["Intro Sam to Priya"])
        # done_message_id 424242 isn't in the thread, so "done" can't be claimed
        self.assertEqual((out.commitments[0].status, out.commitments[0].done_message_id), ("open", None))

    def test_cli_error_raises(self):
        with mock.patch.dict("os.environ", {"FAKE_CLAUDE_MODE": "error"}):
            with self.assertRaisesRegex(RuntimeError, "no result"):
                self.ex.extract(self.thread)

    def test_missing_cli_explains(self):
        with self.assertRaisesRegex(RuntimeError, "Claude Code CLI not found"):
            ClaudeCodeExtractor(binary="definitely-not-claude-xyz")


class EvalTest(unittest.TestCase):
    def test_scorer_matches_by_owner_and_citation(self):
        from spike.eval.__main__ import score
        case = {"id": "x", "expected": [{"owner": "me", "sources": [2], "done": [3]},
                                        {"owner": "them", "sources": [4], "done": []}]}
        pred = [Commitment(kind="promise", owner="me", action="a", due=None, status="done", source_message_id=2, done_message_id=3),
                Commitment(kind="promise", owner="me", action="b", due=None, status="open", source_message_id=2, done_message_id=None),
                Commitment(kind="promise", owner="me", action="c", due=None, status="open", source_message_id=4, done_message_id=None)]
        r = score(case, pred)
        self.assertEqual((r["tp"], r["fp"], r["fn"], r["status_ok"]), (1, 2, 1, 1))

    def test_heuristic_floor_holds(self):
        """Offline regression guard: the heuristic's recall on the labeled cases shouldn't silently drop."""
        from spike.eval.__main__ import score, thread_of
        from spike.eval.cases import CASES
        ex, now = HeuristicExtractor(), time.time()
        rows = [score(c, ex.extract(thread_of(c, now)).commitments) for c in CASES]
        tp, fn = sum(r["tp"] for r in rows), sum(r["fn"] for r in rows)
        self.assertGreaterEqual(tp / (tp + fn), 0.7)

    def test_scorer_counts_kind_separately(self):
        from spike.eval.__main__ import score
        case = {"id": "x", "expected": [{"owner": "me", "kind": "ask", "sources": [1], "done": []}]}
        wrong_kind = [Commitment(kind="promise", owner="me", action="a", due=None, status="open",
                                 source_message_id=1, done_message_id=None)]
        r = score(case, wrong_kind)
        self.assertEqual((r["tp"], r["kind_ok"]), (1, 0))


class AskTest(unittest.TestCase):
    """Asks: concrete requests nobody has said yes or no to. Owner is whoever was asked."""

    def thread(self, *msgs):
        return [{"id": i, "ts": 1_700_000_000 + i * 3600, "from_me": me, "text": t}
                for i, (me, t) in enumerate(msgs, start=1)]

    def found(self, *msgs):
        return [(c.kind, c.owner, c.status, c.source_message_id, c.done_message_id)
                for c in HeuristicExtractor().extract(self.thread(*msgs)).commitments]

    def test_unanswered_request_is_an_ask_on_whoever_was_asked(self):
        self.assertEqual(self.found((0, "Please upload your ID proof on the portal")),
                         [("ask", "me", "open", 1, None)])
        self.assertEqual(self.found((1, "Could you share an update on the review?")),
                         [("ask", "them", "open", 1, None)])

    def test_accepted_request_becomes_one_promise(self):
        self.assertEqual(self.found((0, "Please book the room for Friday"), (1, "Will do"), (1, "Booked, 4B")),
                         [("promise", "me", "done", 2, 3)])

    def test_fulfilled_request_is_a_done_ask(self):
        self.assertEqual(self.found((1, "Can you give me edit access to the sheet?"), (0, "Done, added you")),
                         [("ask", "them", "done", 1, 2)])

    def test_chasing_is_not_a_new_item(self):
        self.assertEqual(self.found((1, "Could you share an update on the review?"), (1, "Following up on this")),
                         [("ask", "them", "open", 1, None)])

    def test_kind_round_trips_and_old_stores_migrate(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "old.db"
            old = sqlite3.connect(path)  # a store from before `kind` existed
            old.executescript("""CREATE TABLE commitment (id INTEGER PRIMARY KEY, person_id INTEGER NOT NULL,
                owner TEXT NOT NULL, action TEXT NOT NULL, due TEXT, status TEXT NOT NULL,
                source_message_id INTEGER NOT NULL, done_message_id INTEGER, extractor TEXT NOT NULL);
                INSERT INTO commitment VALUES (1, 1, 'me', 'old', NULL, 'open', 1, NULL, 'heuristic');""")
            old.commit(); old.close()
            st = Store(path)
            self.assertEqual(st.conn.execute("SELECT kind FROM commitment").fetchone()[0], "promise")
            st.add_messages("x", [type("M", (), dict(guid="g", handle="h", ts=1.0, from_me=False, text="hi"))()])
            pid = st.person_ids()[0]
            mid = st.thread(pid)[0]["id"]
            st.replace_extraction(pid, [dict(kind="ask", owner="me", action="Upload ID", due=None, status="open",
                                             source_message_id=mid, done_message_id=None)], [], "heuristic")
            self.assertEqual([(c["kind"], c["action"]) for c in st.people()[0]["commitments"]], [("ask", "Upload ID")])
            st.close()


class ReviewFixesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_demo_never_touches_the_real_store(self):
        import os
        from spike.__main__ import main
        real = self.dir / "soloyolo.db"
        Store(real).close()
        real.write_bytes(real.read_bytes())  # exists, with content
        before = real.read_bytes()
        cwd = os.getcwd()
        os.chdir(self.dir)
        try:
            main(["--db", str(real), "demo", "--no-serve", "--demo-db", str(self.dir / "demo.db")])
            with self.assertRaises(SystemExit):  # pointing the demo at the real store is refused
                main(["--db", str(real), "demo", "--no-serve", "--demo-db", str(real)])
        finally:
            os.chdir(cwd)
        self.assertEqual(real.read_bytes(), before)

    def test_one_failed_thread_does_not_stop_the_rest(self):
        from spike import __main__ as cli
        st = Store(self.dir / "s.db")
        st.add_messages("imessage", chatdb.read(fixture.build(self.dir / "c.db")), fixture.NAMES)
        first = st.person_ids()[0]

        class Flaky(HeuristicExtractor):
            name = "flaky"
            def extract(self, thread):
                if thread[0]["id"] in {m["id"] for m in st.thread(first)}:
                    raise RuntimeError("declined")
                return super().extract(thread)

        with mock.patch.dict(cli.EXTRACTORS, {"heuristic": Flaky}):
            failed = cli.extract(st, "heuristic", window=300)
        self.assertEqual(failed, 1)
        ran = {p["id"]: p["extractor"] for p in st.people()}
        self.assertIsNone(ran[first])
        self.assertTrue(all(v == "flaky" for k, v in ran.items() if k != first))
        st.close()

    def test_top_limits_to_most_active(self):
        from spike import __main__ as cli
        st = Store(self.dir / "s.db")
        st.add_messages("imessage", chatdb.read(fixture.build(self.dir / "c.db")), fixture.NAMES)
        cli.extract(st, "heuristic", window=300, top=2)
        ran = [p for p in st.people() if p["extractor"]]
        best = sorted(st.people(), key=lambda p: -p["score"])[:2]
        self.assertEqual({p["id"] for p in ran}, {p["id"] for p in best})
        st.close()

    def test_disclosure_logged_before_sending_and_never_by_heuristic(self):
        from spike import __main__ as cli
        st = Store(self.dir / "s.db")
        st.add_messages("imessage", chatdb.read(fixture.build(self.dir / "c.db")), fixture.NAMES)
        cli.extract(st, "heuristic", window=300)
        self.assertEqual(st.disclosures(), [])

        class Cloud(HeuristicExtractor):
            name, remote = "claude-test (cloud)", True
            def extract(self, thread):
                raise RuntimeError("network down")  # text may already have left

        with mock.patch.dict(cli.EXTRACTORS, {"claude-code": Cloud}):
            cli.extract(st, "claude-code", window=300, top=1)
        cli.extract(st, "heuristic", window=300)  # a later local run must not hide it
        self.assertEqual(st.disclosures(), ["claude-test (cloud)"])
        st.close()

    def test_extraction_run_recorded_even_with_no_commitments(self):
        st = Store(self.dir / "s.db")
        st.add_messages("imessage", chatdb.read(fixture.build(self.dir / "c.db")), fixture.NAMES)
        pid = st.person_ids()[0]
        st.replace_extraction(pid, [], [], "claude-opus-5-5 (claude code)")
        p = next(p for p in st.people() if p["id"] == pid)
        self.assertEqual((p["commitments"], p["extractor"]), ([], "claude-opus-5-5 (claude code)"))
        st.close()

    def test_viewer_rejects_foreign_host(self):
        import threading
        import urllib.request
        from functools import partial
        from http.server import ThreadingHTTPServer
        from spike.server import Handler
        db = self.dir / "s.db"
        Store(db).close()
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), lambda *a, **k: None)
        port = httpd.server_address[1]
        httpd.RequestHandlerClass = partial(Handler, db=str(db), port=port)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            ok = urllib.request.urlopen(f"http://127.0.0.1:{port}/api/people?x=1")
            self.assertEqual(ok.status, 200)  # query strings no longer 404
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/people", headers={"Host": f"evil.example:{port}"})
            with self.assertRaises(urllib.error.HTTPError) as err:
                urllib.request.urlopen(req)
            self.assertEqual(err.exception.code, 403)
        finally:
            httpd.shutdown()
            httpd.server_close()


class MarkTest(unittest.TestCase):
    """Your own marks on items: done, not real, snooze. They outlive re-extraction and beat signals."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "s.db"
        self.st = Store(self.db)
        Msg = type("M", (), {})
        rows = []
        for i, (me, text) in enumerate([(0, "Can you send the lease?"), (1, "I'll send it tonight")]):
            m = Msg(); m.guid, m.handle, m.ts, m.from_me, m.text = f"g{i}", "sam", 1_700_000_000.0 + i, bool(me), text
            rows.append(m)
        self.st.add_messages("x", rows, {"sam": "Sam"})
        self.pid = self.st.person_ids()[0]
        self.src = self.st.thread(self.pid)[1]["id"]
        self.extract()

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    def extract(self, action="Send Sam the lease"):
        self.st.replace_extraction(self.pid, [dict(kind="promise", owner="me", action=action, due=None, status="open",
                                                   source_message_id=self.src, done_message_id=None)], [], "heuristic")

    def item(self):
        return self.st.people()[0]["commitments"][0]

    def test_done_survives_reextraction(self):
        self.st.resolve(self.pid, self.src, "me", "done", "you")
        self.extract(action="Send the signed lease to Sam")  # a re-run rewords the item
        self.assertEqual((self.item()["status"], self.item()["resolved_by"]), ("done", "you"))
        self.assertEqual(self.st.people()[0]["id"], self.pid)
        self.assertEqual(self.st.open_items(), [])

    def test_signal_never_overrides_you(self):
        self.st.resolve(self.pid, self.src, "me", "open", "you")
        self.assertFalse(self.st.resolve(self.pid, self.src, "me", "done", "sms", evidence="₹950 debited"))
        self.assertEqual(self.item()["status"], "open")
        self.st.unresolve(self.pid, self.src, "me")
        self.assertTrue(self.st.resolve(self.pid, self.src, "me", "done", "sms", evidence="₹950 debited"))
        self.assertEqual((self.item()["status"], self.item()["evidence"]), ("done", "₹950 debited"))

    def test_snooze_expires_and_dismiss_hides(self):
        self.st.resolve(self.pid, self.src, "me", "snoozed", "you", until=time.time() + 3600)
        self.assertTrue(self.item()["snoozed"])
        self.assertEqual(self.st.open_items(), [])
        self.st.resolve(self.pid, self.src, "me", "snoozed", "you", until=time.time() - 1)
        self.assertFalse(self.item()["snoozed"])
        self.assertEqual(len(self.st.open_items()), 1)
        self.st.resolve(self.pid, self.src, "me", "dismissed", "you")
        self.assertTrue(self.item()["dismissed"])
        self.assertEqual((self.st.people()[0]["hidden"], self.st.open_items()), (1, []))

    def test_mark_endpoint_guards(self):
        import json
        import threading
        import urllib.request
        from functools import partial
        from http.server import ThreadingHTTPServer
        from spike.server import Handler
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), lambda *a, **k: None)
        port = httpd.server_address[1]
        httpd.RequestHandlerClass = partial(Handler, db=str(self.db), port=port)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

        def post(body, **headers):
            h = {"Content-Type": "application/json", **headers}
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/mark", data=json.dumps(body).encode(),
                                         headers=h, method="POST")
            try:
                return urllib.request.urlopen(req).status
            except urllib.error.HTTPError as e:
                return e.code
        good = {"person_id": self.pid, "source_message_id": self.src, "owner": "me", "state": "done"}
        try:
            self.assertEqual(post(good, Origin="https://evil.example"), 403)
            self.assertEqual(post(good, **{"Content-Type": "text/plain"}), 415)
            self.assertEqual(post({**good, "source_message_id": 999}), 404)
            self.assertEqual(post({**good, "state": "deleted"}), 400)
            self.assertEqual(post({**good, "state": "snoozed", "days": 999}), 400)
            self.assertEqual(self.item()["status"], "open")  # nothing above wrote anything
            self.assertEqual(post(good, Origin=f"http://127.0.0.1:{port}"), 200)
            self.assertEqual(self.item()["resolved_by"], "you")
            self.assertEqual(post({**good, "state": "clear"}), 200)
            self.assertIsNone(self.item()["resolved_by"])
            # a reason after "Not needed": only the known ones, and "done off the chat" counts as done
            self.assertEqual(post({**good, "state": "dismissed", "reason": "because"}), 400)
            self.assertEqual(post({**good, "state": "dismissed", "reason": "off_chat"}), 200)
            row = self.st.conn.execute("SELECT state, evidence FROM resolution WHERE person_id = ?", (self.pid,)).fetchone()
            self.assertEqual(tuple(row), ("done", "you: done off the chat"))
            self.assertEqual(post({**good, "state": "dismissed", "reason": "misread"}), 200)
            row = self.st.conn.execute("SELECT state, evidence FROM resolution WHERE person_id = ?", (self.pid,)).fetchone()
            self.assertEqual(tuple(row), ("dismissed", "you: not a real promise"))
            from spike.server import insight
            got = insight(self.st)
            self.assertEqual((got["closed"], got["why"]["misread"], got["why"]["off_chat"]), ({"by_you": 1, "by_signal": 0}, 1, 0))
        finally:
            httpd.shutdown()
            httpd.server_close()


class SmsTest(unittest.TestCase):
    ALERTS = {
        # Shapes of real Indian bank alerts (numbers and names invented).
        "Credit Alert!\nRs.950.00 credited to HDFC Bank A/c XX1234 on 17-10-26 from VPA rajesh.s@okhdfc (UPI 529012345678)":
            (950.0, "in", "rajesh.s@okhdfc"),
        "Sent Rs.1,000.00\nFrom HDFC Bank A/C *1234\nTo SHENA SHARMA\nOn 18/10/26\nRef 529012345679\nNot You? Call 18002586161":
            (1000.0, "out", "SHENA SHARMA"),
        "Dear UPI user A/C X1234 debited by 950.0 on date 17Oct26 trf to SHENA Refno 529012345670. If not u? call 1800111109. -SBI":
            (950.0, "out", "SHENA"),
        "Dear SBI UPI User, ur A/cX1234 credited by Rs1000 on 18Oct26 by RAJESH SHARMA (Ref no 529012345671)":
            (1000.0, "in", "RAJESH SHARMA"),
        "ICICI Bank Acct XX123 debited for Rs 3,400.00 on 13-Oct-26; RAJESH SHARMA credited. UPI:529012345672. Call 18002662 for dispute.":
            (3400.0, "out", None),
        "INR 700.00 credited\nA/c no. XX1234\n13-10-26, 18:23:11\nUPI/P2A/529012345673/RAJESH SHARMA\nNot you? Call 18604195555 - Axis Bank":
            (700.0, "in", "RAJESH SHARMA"),
        "Sent Rs.37,000.00 from Kotak Bank AC X1234 to landlord@ybl on 31-10-26.UPI Ref 529012345674. Not you, kotak.com/fraud":
            (37000.0, "out", "landlord@ybl"),
    }
    NOT_PAYMENTS = [
        "Alert:\nUSD.23.60 will be debited on 08/10/2026 from HDFC Bank Card 0223 for Anthropic",
        "123456 is your OTP for UPI txn of Rs 950 at A/c XX1234. Do not share. -HDFC",
        "RAJESH SHARMA has requested money from you on Google Pay. Rs 500. UPI ID rajesh@okhdfc",
        "Your Credit Card bill of Rs 4,512 is due on 20-Nov. Pay via UPI.",
        "Get a pre-approved personal loan of Rs 5,00,000 credited to your account in 10 mins!",
        "Txn of Rs 950.00 on A/c XX1234 failed. Amount will be reversed.",
        "Bhai 950 bhej de na",
    ]

    def test_parses_bank_alerts(self):
        from spike.sms import parse_alert
        for body, want in self.ALERTS.items():
            self.assertEqual(parse_alert(body), want, body)
        for body in self.NOT_PAYMENTS:
            self.assertIsNone(parse_alert(body), body)

    def test_rs_inside_words_is_not_money(self):
        from spike.sms import amounts, parse_alert
        self.assertEqual(amounts("flight at 15:10 Hrs 1500 and 3 yrs 14"), set())
        self.assertEqual(amounts("Rs 950 and INR 1,200 and ₹40"), {950.0, 1200.0, 40.0})
        self.assertEqual(parse_alert("Sent Rs.950.00 From HDFC Bank A/C *1234 To SHENA On 17/10/26 at 10 Hrs 15")[0], 950.0)

    def test_backup_keeps_only_received_payment_alerts(self):
        from xml.sax.saxutils import quoteattr
        from spike.sms import load_backup
        texts = [("VM-HDFCBK", 1, list(self.ALERTS)[0]), ("VM-HDFCBK", 1, self.NOT_PAYMENTS[1]),
                 ("+919800000000", 1, "dinner at 8?"), ("VM-HDFCBK", 2, list(self.ALERTS)[0])]
        xml = "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>\n<smses count='4'>" + "".join(
            f"<sms protocol='0' address={quoteattr(a)} date='{1_760_000_000_000 + i}' type='{t}' body={quoteattr(b)} />"
            for i, (a, t, b) in enumerate(texts)) + \
            f"<sms address='VM-HDFCBK' date='' type='1' body={quoteattr(list(self.ALERTS)[0])} />" \
            "<mms date='1' /></smses>"
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "sms.xml"
            f.write_text(xml)
            pays, read = load_backup(f)
        self.assertEqual(read, 5)  # the row with no date is read and skipped, not fatal
        self.assertEqual([(p.amount, p.direction, p.sender) for p in pays], [(950.0, "in", "VM-HDFCBK")])

    def test_matcher_closes_only_the_matching_money_item(self):
        from spike import sms
        from spike.sms import Payment
        with tempfile.TemporaryDirectory() as d:
            st = Store(Path(d) / "s.db")
            M = type("M", (), {})
            t0 = 1_760_000_000.0
            chat = [(1, "Ek baar 950 bhejna mere upi pe, mattress topper"), (0, "Ok"),
                    (1, "2.7k meds aur 700 cab ke lage, monies dedo"), (0, "Ok will send"),
                    (1, "Bring the charger tomorrow"), (0, "Sure")]
            rows = []
            for i, (me, text) in enumerate(chat):
                m = M(); m.guid, m.handle, m.ts, m.from_me, m.text = f"g{i}", "papa", t0 + i * 3600, bool(me), text
                rows.append(m)
            st.add_messages("whatsapp", rows, {"papa": "PAPA"})
            pid = st.person_ids()[0]
            ids = [r["id"] for r in st.thread(pid)]
            items = [dict(kind="promise", owner="them", action="Send ₹950 for the mattress topper", due=None,
                          status="open", source_message_id=ids[1], done_message_id=None),
                     dict(kind="promise", owner="them", action="Send money for the medicine refills and cab costs",
                          due=None, status="open", source_message_id=ids[3], done_message_id=None),
                     dict(kind="promise", owner="them", action="Bring the charger", due=None, status="open",
                          source_message_id=ids[5], done_message_id=None)]
            st.replace_extraction(pid, items, [], "test")
            pay = lambda n, amt, direction, dt: Payment(f"p{n}", t0 + dt, "VM-HDFCBK", "alert", amt, direction, "RAJESH")
            st.add_evidence("sms", [
                pay(1, 950, "in", -3600),         # before the item was made: not it
                pay(2, 950, "out", 7200),         # wrong direction: you paid someone 950
                pay(3, 950, "in", 86400),         # this one
                pay(4, 3400, "in", 2 * 86400),    # 2.7k + 700
                pay(5, 950, "in", 3 * 86400),     # a second 950 has nothing left to close
            ])
            closed = sms.match(st)
            self.assertEqual(sorted((i["action"], p["remote_id"]) for i, p in closed),
                             [("Send money for the medicine refills and cab costs", "p4"),
                              ("Send ₹950 for the mattress topper", "p3")])
            self.assertEqual([i["action"] for i in st.open_items()], ["Bring the charger"])
            self.assertEqual(sms.match(st), [])  # idempotent
            # You said it's not done: a later import never re-closes it.
            st.resolve(pid, ids[1], "them", "open", "you")
            st.conn.execute("DELETE FROM resolution WHERE decided_by = 'sms'")
            closed = sms.match(st)
            self.assertNotIn("Send ₹950 for the mattress topper", [i["action"] for i, _ in closed])
            st.close()


class LiveStoreTest(unittest.TestCase):
    """A synced store grows all the time: only chats with new rows are read again."""

    def test_changed_only_and_watch(self):
        import io
        from contextlib import redirect_stdout
        from types import SimpleNamespace
        from spike.__main__ import extract, watch
        with tempfile.TemporaryDirectory() as d:
            st = Store(Path(d) / "s.db")
            M = type("M", (), {})
            def add(guid, handle, ts, me, text):
                m = M(); m.guid, m.handle, m.ts, m.from_me, m.text = guid, handle, ts, me, text
                st.add_messages("whatsapp", [m], {handle: handle.title()})
            now = time.time() - 86400
            for i in range(4):
                add(f"a{i}", "papa", now + i, i % 2 == 1, "I'll send the PG address tonight" if i == 3 else "hi")
            add("b0", "sonu", now, False, "yo")
            add("c0", "old", now - 400 * 86400, False, "from last year")
            add("c1", "old", now - 399 * 86400, True, "I'll send it")
            self.assertEqual(len(st.changed_ids()), 3)
            extract(st, "heuristic", 300, changed=True, min_messages=2)
            # papa read; "old" had nothing in the last 60 days, so it's marked read; sonu is too short
            self.assertEqual(len(st.changed_ids()), 1)
            # History sync delivers an *older* message later: it still counts as new.
            add("a-old", "papa", 1_700_000_000, False, "old one")
            self.assertIn(st.person_ids()[0], st.changed_ids())
            out = io.StringIO()
            args = SimpleNamespace(extractor="heuristic", every=0, top=30, min_messages=2, window=300, days=60, once=True)
            with redirect_stdout(out):
                watch(st, args)
            self.assertIn("chats changed", out.getvalue())
            with redirect_stdout(io.StringIO()) as again:
                watch(st, args)
            self.assertNotIn("new:", again.getvalue())  # nothing re-announced
            st.close()


class ClosureTest(unittest.TestCase):
    """The cross-chat pass suggests; it never closes, never re-asks, and only sends what it must."""

    def setUp(self):
        from spike.whatsapp_export import GroupLine
        self.tmp = tempfile.TemporaryDirectory()
        self.st = Store(Path(self.tmp.name) / "s.db")
        M = type("M", (), {})
        t0 = 1_760_000_000.0
        rows = []
        for i, (h, me, text) in enumerate([("papa", 0, "Talk to Mama and finalise the flight"), ("papa", 1, "Ok"),
                                           ("mum", 1, "secret-1to1-zq: I booked the 9:30 one")]):
            m = M(); m.guid, m.handle, m.ts, m.from_me, m.text = f"g{i}", h, t0 + i * 3600, bool(me), text
            rows.append(m)
        self.st.add_messages("whatsapp", rows, {"papa": "PAPA", "mum": "Mum"})
        self.papa = next(p["id"] for p in self.st.people() if p["name"] == "PAPA")
        self.src = self.st.thread(self.papa)[1]["id"]
        self.st.replace_extraction(self.papa, [dict(kind="promise", owner="me", action="Talk to Mama and say which flight",
                                                    due=None, status="open", source_message_id=self.src,
                                                    done_message_id=None)], [], "test")
        self.st.add_evidence("whatsapp-group:Family", [
            GroupLine("e1", t0 - 86400, "Mum", "old line before the item"),
            GroupLine("e2", t0 + 7200, "Mum", "Done, 9:30 flight booked for Yash")])

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    class Fake:
        name = "fake-model"
        def __init__(self, closures):
            self.closures, self.sent = closures, []
        def ask(self, system, prompt, stdin, schema):
            self.sent.append(stdin)
            return schema.model_validate({"closures": self.closures})

    def test_suggests_and_keeps_it_open(self):
        from spike import closure
        lines = closure.candidates(self.st, self.papa, self.st.open_items())
        booked = next(l["id"] for l in lines if "booked" in l["text"])
        ex = self.Fake([{"item": 1, "evidence": booked, "reason": "Mum booked it"},
                        {"item": 7, "evidence": booked, "reason": "no such item"},
                        {"item": 1, "evidence": 99, "reason": "no such line"}])
        out = closure.run(self.st, ex)
        self.assertEqual(len(out), 1)
        item = self.st.people()[0]["commitments"] if self.st.people()[0]["id"] == self.papa else None
        item = next(c for p in self.st.people() if p["id"] == self.papa for c in p["commitments"])
        self.assertEqual(item["status"], "open")
        self.assertIn("9:30 flight booked", item["suggestion"])
        self.assertNotIn("old line", ex.sent[0])          # before the item: never a candidate
        self.assertNotIn("secret-1to1-zq", ex.sent[0])    # other 1:1 chats are opt-in
        self.assertEqual(self.st.disclosures(), ["fake-model"])
        # Asked once: the next run sends nothing for it.
        again = self.Fake([])
        closure.run(self.st, again)
        self.assertEqual(again.sent, [])

    def test_your_answer_stands_and_sms_beats_a_guess(self):
        from spike import closure
        self.st.resolve(self.papa, self.src, "me", "open", "you")
        ex = self.Fake([{"item": 1, "evidence": 1, "reason": "x"}])
        closure.run(self.st, ex)
        self.assertEqual(ex.sent, [])  # you already said: not sent at all
        self.st.unresolve(self.papa, self.src, "me")
        self.st.resolve(self.papa, self.src, "me", "done", "sms", evidence="₹950 credited")
        self.assertFalse(self.st.resolve(self.papa, self.src, "me", "suggested", "closure", evidence="guess"))

    def test_one_failure_does_not_stop_the_rest(self):
        from spike import closure

        class Boom(self.Fake):
            def ask(self, *a):
                raise RuntimeError("timeout")
        self.assertEqual(closure.run(self.st, Boom([])), [])  # reported, not raised

    def test_other_chats_when_asked(self):
        from spike import closure
        ex = self.Fake([])
        closure.run(self.st, ex, other_chats=True)
        self.assertIn("secret-1to1-zq", ex.sent[0])
        self.assertEqual(sorted(self.st.disclosures()), ["fake-model"])

    def test_bare_answer_keeps_its_context_when_lines_are_cut(self):
        from spike import closure
        t0 = 1_760_000_000.0
        item = {"action": "Talk to Mama and say which flight to finalise", "source_text": "which flight?", "source_ts": t0}
        noise = [dict(ts=t0 + 9 * 86400 + n, chat="Cricket (group)", speaker="x", text=f"score {n}") for n in range(600)]
        talk = [dict(ts=t0 + 3600, chat="V3 (group)", speaker="Mumma", text="Kaunsi flight book karein?"),
                dict(ts=t0 + 3700, chat="V3 (group)", speaker="Papa", text="9:30"),
                dict(ts=t0 + 3800, chat="V3 (group)", speaker="me", text="Ok ji 9:30")]
        kept = closure._relevant(talk + noise, [item])
        self.assertLessEqual(len(kept), closure.MAX_EVIDENCE * 2)
        self.assertTrue(all(line in kept for line in talk))

    def test_old_resolution_table_migrates(self):
        import sqlite3
        path = Path(self.tmp.name) / "old.db"
        c = sqlite3.connect(path)
        c.executescript("""CREATE TABLE resolution (person_id INTEGER NOT NULL, source_message_id INTEGER NOT NULL,
            owner TEXT NOT NULL, state TEXT NOT NULL CHECK (state IN ('done', 'dismissed', 'snoozed', 'open')),
            until REAL, decided_by TEXT NOT NULL, evidence TEXT, evidence_id INTEGER, at REAL NOT NULL,
            PRIMARY KEY (person_id, source_message_id, owner));
            INSERT INTO resolution VALUES (1, 1, 'me', 'done', NULL, 'you', NULL, NULL, 0);""")
        c.commit(); c.close()
        st = Store(path)
        st.conn.execute("INSERT INTO resolution VALUES (1, 2, 'me', 'suggested', NULL, 'closure', 'x', NULL, 0)")
        self.assertEqual(st.conn.execute("SELECT count(*) FROM resolution").fetchone()[0], 2)
        st.close()


IOS_EXPORT = (
    "\u200e[28/10/2026, 19:02:11] Sam Okafor: \u200eMessages and calls are end-to-end encrypted.\n"
    "[28/10/2026, 19:02:11] Sam Okafor: Good seeing you at the dinner\n"
    "[28/10/2026, 19:05:40] Yash Sharma: You're hiring a design lead?\n"
    "[28/10/2026, 19:06:02] Sam Okafor: Yes, the hardest role right now\n"
    "[28/10/2026, 19:07:30] Yash Sharma: I'll intro you to Priya\n"
    "she built the design team at her last startup\n"
    "[28/10/2026, 19:08:00] Sam Okafor: \u200eimage omitted\n"
    "[31/10/2026, 09:15:00] Sam Okafor: Any luck reaching Priya? <This message was edited>\n"
)
ANDROID_EXPORT = (
    "11/2/26, 9:10\u202fPM - Messages and calls are end-to-end encrypted. No one outside of this chat can read them.\n"
    "11/2/26, 9:10\u202fPM - Ana Torres: Thanks for covering lunch, I'll pay you back on Friday\n"
    "11/2/26, 9:12\u202fPM - Yash Sharma: No rush\n"
    "11/2/26, 9:13\u202fPM - Yash Sharma: <Media omitted>\n"
    "11/13/26, 12:05\u202fAM - Ana Torres: Sent!\n"
)
GROUP_EXPORT = (
    "[01/11/2026, 10:00:00] Yash Sharma: Dinner Friday?\n"
    "[01/11/2026, 10:01:00] Sam Okafor: In\n"
    "[01/11/2026, 10:02:00] Priya Nair: In too\n"
)


class WhatsAppExportTest(unittest.TestCase):
    def setUp(self):
        import zipfile
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        (d / "WhatsApp Chat - Sam Okafor.txt").write_text(IOS_EXPORT)
        with zipfile.ZipFile(d / "ana.zip", "w") as z:
            z.writestr("WhatsApp Chat with Ana Torres.txt", ANDROID_EXPORT)
        (d / "group.txt").write_text(GROUP_EXPORT)
        self.files = [d / "WhatsApp Chat - Sam Okafor.txt", d / "ana.zip", d / "group.txt"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_parses_both_layouts_and_infers_me(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from spike import whatsapp_export as wa
        rows, names, notes = wa.load(self.files, tz="Asia/Kolkata")
        self.assertEqual(sorted(names.values()), ["Ana Torres", "Sam Okafor"])
        groups, gnotes = wa.load_groups(self.files, tz="Asia/Kolkata")
        self.assertTrue(any("kept as evidence" in n for n in gnotes))
        self.assertEqual(list(groups), ["group"])
        self.assertEqual([g.sender for g in groups["group"]], ["me", "Sam Okafor", "Priya Nair"])
        self.assertEqual(wa.chat_name("WhatsApp Chat with Family.txt"), "Family")
        self.assertEqual(wa.chat_name("Family from WhatsApp/chat.txt"), "Family")
        self.assertEqual(wa.chat_name("export.zip:_chat.txt"), "export")
        sam = [r for r in rows if r.handle == "export:Sam Okafor"]
        self.assertEqual([r.from_me for r in sam], [False, True, False, True, False])  # system line + image dropped
        self.assertEqual(sam[3].text, "I'll intro you to Priya\nshe built the design team at her last startup")
        self.assertEqual(sam[-1].text, "Any luck reaching Priya?")  # edit marker stripped
        ana = [r for r in rows if r.handle == "export:Ana Torres"]
        # Android writes every attachment as "<Media omitted>": kept as a marker, it can close "send me the pic".
        self.assertEqual([r.text for r in ana], ["Thanks for covering lunch, I'll pay you back on Friday", "No rush",
                                                  "[media]", "Sent!"])
        # month-first detected from "11/13/26"; 12:05 AM is just after midnight
        when = datetime.fromtimestamp(ana[-1].ts, ZoneInfo("Asia/Kolkata"))
        self.assertEqual((when.month, when.day, when.hour, when.minute), (11, 13, 0, 5))
        first = datetime.fromtimestamp(ana[0].ts, ZoneInfo("Asia/Kolkata"))
        self.assertEqual((first.month, first.day, first.hour), (11, 2, 21))

    def test_spanish_am_pm_and_tz_independent_ids(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from spike import whatsapp_export as wa
        f = Path(self.tmp.name) / "es.txt"
        f.write_text("2/11/26, 9:10 p. m. - Ana: Te pago el viernes\n"
                     "2/11/26, 12:05 a. m. - Yash Sharma: Vale\n")
        rows, _, _ = wa.load([f], me="Yash Sharma", tz="Europe/Madrid")
        hours = [datetime.fromtimestamp(r.ts, ZoneInfo("Europe/Madrid")).hour for r in rows]
        self.assertEqual(hours, [21, 0])
        other, _, _ = wa.load([f], me="Yash Sharma", tz="Asia/Kolkata")
        self.assertEqual([r.guid for r in rows], [r.guid for r in other])  # --tz must not change identity
        self.assertNotEqual(rows[0].ts, other[0].ts)

    def test_single_chat_needs_me(self):
        from spike import whatsapp_export as wa
        with self.assertRaisesRegex(ValueError, "--me"):
            wa.load(self.files[:1])
        rows, _, _ = wa.load(self.files[:1], me="Yash Sharma")
        self.assertEqual(sum(r.from_me for r in rows), 2)

    def test_import_is_idempotent_and_extractable(self):
        from spike import whatsapp_export as wa
        st = Store(Path(self.tmp.name) / "s.db")
        rows, names, _ = wa.load(self.files, tz="Asia/Kolkata")
        self.assertEqual(st.add_messages("whatsapp", rows, names), len(rows))
        self.assertEqual(st.add_messages("whatsapp", *wa.load(self.files, tz="Asia/Kolkata")[:2]), 0)
        sam = next(p for p in st.people() if p["name"] == "Sam Okafor")
        found = HeuristicExtractor().extract([dict(m) for m in st.thread(sam["id"])]).commitments
        self.assertEqual([(c.owner, c.status) for c in found], [("me", "open")])
        st.close()


class WhatsAppBracketExportTest(unittest.TestCase):
    """Exports where every line is bracketed, 'You' is the sender and calls get their own line."""

    def test_calls_forwards_and_placeholders(self):
        from spike import whatsapp_export
        text = ("Messages and calls are end-to-end encrypted. No one outside of this chat, not even WhatsApp, can read or listen to them.\n"
                "[10/12/26, 8:01:46 PM] PAPA: Jio Fiber recharge kar dena\n"
                "[10/12/26, 8:01:58 PM] You: Ok\n"
                "[10/13/26, 5:36:43 PM] - [Call]\n"
                "[10/13/26, 8:35:39 PM] You: <image omitted> Jiofi done ji\n"
                "[10/14/26, 9:42:16 AM] PAPA: [Forwarded] <sticker omitted>\n"
                "[10/19/26, 4:34:51 PM] PAPA: <album message>\n"
                "[10/19/26, 4:34:52 PM] PAPA: [Forwarded] <image omitted>\n")
        with tempfile.TemporaryDirectory() as d:
            for name in ("PAPA", "Gaurav"):
                (Path(d) / f"{name}.txt").write_text(text.replace("PAPA", name))
            rows, names, _ = whatsapp_export.load(sorted(Path(d).glob("*.txt")), tz="Asia/Kolkata")
        papa = [(r.from_me, r.text) for r in rows if r.handle == "export:PAPA"]
        self.assertEqual(papa, [(False, "Jio Fiber recharge kar dena"), (True, "Ok"), (False, "[call]"),
                                (True, "[photo] Jiofi done ji"), (False, "[photo]")])
        thread = [{"id": i, "ts": r.ts, "from_me": r.from_me, "text": r.text}
                  for i, r in enumerate((r for r in rows if r.handle == "export:PAPA"), start=1)]
        self.assertIn("[3] ", render(thread))
        self.assertIn("(a call between us)", render(thread).splitlines()[2])


class JsonImportTest(unittest.TestCase):
    def test_import_merges_threads_by_handle_and_dedupes(self):
        import json
        from spike import json_import
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "c.json"
            f.write_text(json.dumps({"source": "gmail", "threads": [
                {"person": "Sumit (Cars24)", "handle": "Sumit@Cars24.com", "messages": [
                    {"id": "a", "ts": "2026-10-05T02:30:00Z", "from_me": True, "text": "I'll send the file"},
                    {"id": "b", "ts": "2026-10-05T11:38:25Z", "from_me": False, "text": "Thanks"}]},
                {"person": "Sumit (Cars24)", "handle": "sumit@cars24.com", "messages": [
                    {"id": "c", "ts": "2026-10-28T13:45:21Z", "from_me": True, "text": "Following up"},
                    {"id": "d", "ts": "2026-10-28T13:46:00Z", "from_me": True, "text": "  "}]}]}))
            source, rows, names = json_import.load(f)
            self.assertEqual((source, len(rows), names), ("gmail", 3, {"sumit@cars24.com": "Sumit (Cars24)"}))
            st = Store(Path(d) / "s.db")
            self.assertEqual(st.add_messages(source, rows, names), 3)
            self.assertEqual(st.add_messages(source, rows, names), 0)
            self.assertEqual([p["count"] for p in st.people()], [3])
            st.close()


if __name__ == "__main__":
    unittest.main()


class StabilityTest(unittest.TestCase):
    """A re-read sees the earlier items; an item leaves only for a stated reason, and marks follow it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = Store(Path(self.tmp.name) / "s.db")
        Msg = type("M", (), {})
        rows = []
        now = time.time()
        for i, (me, text) in enumerate([(0, "Can you send the lease and the deposit receipt?"), (1, "Sure, both tonight"),
                                         (0, "Also call the plumber"), (1, "Will do")]):
            m = Msg(); m.guid, m.handle, m.ts, m.from_me, m.text = f"g{i}", "sam", now - 86400 * (4 - i), bool(me), text
            rows.append(m)
        self.st.add_messages("x", rows, {"sam": "Sam"})
        self.pid = self.st.person_ids()[0]
        self.ids = [m["id"] for m in self.st.thread(self.pid)]

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    def c(self, action, src, previous=None, status="open", done=None):
        return Commitment(kind="promise", owner="me", action=action, due=None, status=status,
                          source_message_id=src, done_message_id=done, previous=previous)

    def run_with(self, *results):
        from spike.__main__ import extract
        seen = []

        class Fake(HeuristicExtractor):
            remote = False

            def extract(self, thread, prior=None):
                seen.append(prior)
                return results[len(seen) - 1]
        ex = Fake()
        for _ in results:
            with mock.patch("sys.stdout"):
                extract(self.st, "heuristic", 1000, only=self.pid, ex=ex)
        return seen

    def actions(self):
        return sorted(c["action"] for c in self.st.people()[0]["commitments"])

    def test_forgotten_item_is_carried_and_two_items_from_one_message_both_stay(self):
        lease, receipt, plumber = (self.c("Send the lease", self.ids[1]), self.c("Send the deposit receipt", self.ids[1]),
                                   self.c("Call the plumber", self.ids[3]))
        seen = self.run_with(Extraction(commitments=[lease, receipt, plumber], topics=[]),
                             Extraction(commitments=[self.c("Send the lease", self.ids[1], "P1")], topics=[]))
        self.assertIsNone(seen[0])
        self.assertEqual([p["action"] for p in seen[1]], ["Send the lease", "Send the deposit receipt", "Call the plumber"])
        self.assertEqual(self.actions(), ["Call the plumber", "Send the deposit receipt", "Send the lease"])

    def test_dropped_needs_a_reason_and_never_beats_your_mark(self):
        from spike.extract import Dropped
        first = Extraction(commitments=[self.c("Send the lease", self.ids[1]), self.c("Call the plumber", self.ids[3])],
                           topics=[])
        self.run_with(first)
        self.st.resolve(self.pid, self.ids[3], "me", "open", "you")  # you said: still open
        drop_both = Extraction(commitments=[], topics=[], dropped=[Dropped(previous="P1", reason="a joke"),
                                                                   Dropped(previous="P2", reason="a joke")])
        self.run_with(drop_both)
        self.assertEqual(self.actions(), ["Call the plumber"])

    def test_your_mark_follows_an_item_to_a_new_source(self):
        self.run_with(Extraction(commitments=[self.c("Call the plumber", self.ids[3])], topics=[]))
        self.st.resolve(self.pid, self.ids[3], "me", "done", "you")
        self.run_with(Extraction(commitments=[self.c("Call the plumber", self.ids[2], "P1")], topics=[]))
        item = self.st.people()[0]["commitments"][0]
        self.assertEqual((item["source_message_id"], item["status"], item["resolved_by"]), (self.ids[2], "done", "you"))

    def test_checked_keeps_an_aged_out_source_only_for_a_known_earlier_item(self):
        from spike.extract import _checked
        thread = [dict(id=self.ids[3])]
        prior = [dict(owner="me", action="Send the lease", status="done", source_message_id=self.ids[1],
                      done_message_id=self.ids[2])]
        out = _checked(Extraction(commitments=[self.c("Send the lease", self.ids[1], "P1", "done", self.ids[2]),
                                               self.c("Invented", self.ids[0], "P9")], topics=[]), thread, prior)
        self.assertEqual([(c.action, c.status, c.previous) for c in out.commitments], [("Send the lease", "done", "P1")])

    def test_prompt_shows_earlier_items_with_ids(self):
        from spike.extract import _stdin
        prior = [dict(owner="me", kind="promise", action="Send the lease", status="open", due=None,
                      source_message_id=7, source_ts=time.time(), source_text="Sure, both tonight")]
        text = _stdin([dict(id=7, ts=time.time(), from_me=1, text="Sure, both tonight")], prior)
        self.assertIn("[P1] owner=me promise: Send the lease", text)
        self.assertLess(text.index("<earlier_items>"), text.index("<thread>"))


class PriorityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = Store(Path(self.tmp.name) / "s.db")
        self.now = time.time()
        Msg = type("M", (), {})
        rows = []
        for who, n in (("dad", 12), ("ravi", 12), ("shop", 2)):
            for i in range(n):
                m = Msg(); m.guid, m.handle, m.ts, m.from_me, m.text = f"{who}{i}", who, self.now - 86400 * (n - i), i % 2 == 0, f"{who} {i}"
                rows.append(m)
        self.st.add_messages("x", rows, {"dad": "Dad", "ravi": "Ravi", "shop": "Shop"})
        self.pids = {p["name"]: p["id"] for p in self.st.people()}

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    def put(self, name, *items):
        thread = self.st.thread(self.pids[name])
        self.st.replace_extraction(self.pids[name], [
            dict(kind="promise", owner=o, action=a, due=due, status="open", source_message_id=thread[k]["id"])
            for o, a, due, k in items], [], "heuristic")

    def test_due_and_your_move_first_with_reasons(self):
        from datetime import date, timedelta
        from spike import priority
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        long_ago = (date.today() - timedelta(days=40)).isoformat()
        self.put("Dad", ("me", "Send Dad ₹950", None, 3), ("them", "Book the cab", None, 5))
        self.put("Ravi", ("me", "Send Ravi the deck", tomorrow, 10), ("me", "Wish Ravi happy birthday", long_ago, 0))
        self.put("Shop", ("them", "Deliver the sofa", None, 0))
        ranked = priority.rank(self.st, self.now)
        self.assertEqual(ranked[0]["action"], "Send Ravi the deck")
        self.assertIn("due tomorrow", ranked[0]["reasons"])
        self.assertIn("money", ranked[1]["reasons"])
        order = [c["action"] for c in ranked]
        self.assertLess(order.index("Send Dad ₹950"), order.index("Book the cab"))  # your move first
        self.assertEqual(order[-1], "Deliver the sofa")  # theirs, old, a stranger

    def test_muted_chat_leaves_the_lists_and_comes_back(self):
        from spike import nudge, priority
        self.put("Ravi", ("me", "Send Ravi the deck", None, 11))
        self.st.mute(self.pids["Ravi"], "an AI assistant")
        self.assertEqual(priority.rank(self.st, self.now), [])
        self.assertEqual(nudge.today(self.st, self.now), [])
        self.assertEqual(self.st.find_person("ravi"), [(self.pids["Ravi"], "Ravi")])
        self.st.unmute(self.pids["Ravi"])
        self.assertEqual([c["action"] for c in priority.rank(self.st, self.now)], ["Send Ravi the deck"])

    def test_maybe_settled_sinks_and_one_chat_cannot_fill_the_top(self):
        from spike import priority
        self.put("Dad", *[("me", f"Fix bug {n}", None, 6) for n in range(6)])
        self.put("Ravi", ("me", "Send Ravi the deck", None, 6))
        self.assertLess([c["action"] for c in priority.rank(self.st, self.now)].index("Send Ravi the deck"), 3)
        src = self.st.thread(self.pids["Ravi"])[6]["id"]
        self.st.resolve(self.pids["Ravi"], src, "me", "suggested", "closure", evidence="group: done")
        last = priority.rank(self.st, self.now)[-1]
        self.assertEqual((last["action"], last["reasons"][-1]), ("Send Ravi the deck", "maybe settled"))

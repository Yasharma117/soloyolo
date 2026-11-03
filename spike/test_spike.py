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
            with self.assertRaisesRegex(RuntimeError, "no extraction"):
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
        self.assertTrue(any("groups aren't supported" in n for n in notes))
        sam = [r for r in rows if r.handle == "export:Sam Okafor"]
        self.assertEqual([r.from_me for r in sam], [False, True, False, True, False])  # system line + image dropped
        self.assertEqual(sam[3].text, "I'll intro you to Priya\nshe built the design team at her last startup")
        self.assertEqual(sam[-1].text, "Any luck reaching Priya?")  # edit marker stripped
        ana = [r for r in rows if r.handle == "export:Ana Torres"]
        self.assertEqual([r.text for r in ana], ["Thanks for covering lunch, I'll pay you back on Friday", "No rush", "Sent!"])
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

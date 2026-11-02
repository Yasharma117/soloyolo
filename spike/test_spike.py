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
            Commitment(owner="me", action="Intro Sam to Priya", due=None, status="open",
                       source_message_id=real, done_message_id=99999),
            Commitment(owner="them", action="Invented", due=None, status="open",
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
        {"owner": "me", "action": "Intro Sam to Priya", "due": None, "status": "done",
         "source_message_id": int(os.environ["FAKE_SRC"]), "done_message_id": 424242},
        {"owner": "them", "action": "Invented", "due": None, "status": "open",
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
        pred = [Commitment(owner="me", action="a", due=None, status="done", source_message_id=2, done_message_id=3),
                Commitment(owner="me", action="b", due=None, status="open", source_message_id=2, done_message_id=None),
                Commitment(owner="me", action="c", due=None, status="open", source_message_id=4, done_message_id=None)]
        r = score(case, pred)
        self.assertEqual((r["tp"], r["fp"], r["fn"], r["status_ok"]), (1, 2, 1, 1))

    def test_heuristic_floor_holds(self):
        """Offline regression guard: the heuristic's recall on the labeled cases shouldn't silently drop."""
        from spike.eval.__main__ import score, thread_of
        from spike.eval.cases import CASES
        ex, now = HeuristicExtractor(), time.time()
        rows = [score(c, ex.extract(thread_of(c, now)).commitments) for c in CASES]
        tp, fn = sum(r["tp"] for r in rows), sum(r["fn"] for r in rows)
        self.assertGreaterEqual(tp / (tp + fn), 0.4)


if __name__ == "__main__":
    unittest.main()

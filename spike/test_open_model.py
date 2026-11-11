"""python -m unittest spike.test_open_model  (offline; a stand-in for an OpenAI-compatible server)"""
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from spike.council import Council
from spike.extract import OpenModelExtractor

GOOD = {"commitments": [{"kind": "promise", "owner": "me", "action": "Send the deck", "due": None, "status": "open",
                         "source_message_id": 2, "done_message_id": None},
                        {"kind": "promise", "owner": "them", "action": "Made up", "due": None, "status": "open",
                         "source_message_id": 99, "done_message_id": None}], "topics": ["deck"]}
# What a server may say, in order: busy, then prose that isn't the schema, then the answer in a code fence.
REPLIES = [(429, {"error": "slow down"}), (200, "Sure! Here you go: {\"items\": []}"), (200, f"```json\n{json.dumps(GOOD)}\n```")]


class Fake(BaseHTTPRequestHandler):
    seen = []

    def do_POST(self):
        Fake.seen.append((self.headers["Authorization"], json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
        code, reply = REPLIES[min(len(Fake.seen), len(REPLIES)) - 1]
        body = json.dumps(reply if code != 200 else {"choices": [{"message": {"content": reply}}]}).encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class OpenModelTest(unittest.TestCase):
    def test_waits_when_busy_asks_again_when_invalid_and_checks_citations(self):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        ex = OpenModelExtractor("some/model", url=f"http://127.0.0.1:{httpd.server_address[1]}/v1", key="k")
        ex.pause = 0
        thread = [{"id": 1, "ts": 1.0, "from_me": 0, "text": "can you send the deck"}, {"id": 2, "ts": 2.0, "from_me": 1, "text": "I'll send it"}]
        out = ex.extract(thread)
        self.assertEqual([(c.owner, c.source_message_id) for c in out.commitments], [("me", 2)])  # message 99 isn't in the thread
        self.assertEqual(len(Fake.seen), 3)
        auth, body = Fake.seen[-1]
        self.assertEqual((auth, body["model"]), ("Bearer k", "some/model"))
        self.assertIn("I'll send it", body["messages"][1]["content"])


def item(action, source, previous=None):
    return {"kind": "promise", "owner": "me", "action": action, "due": None, "status": "open", "source_message_id": source,
            "done_message_id": None, "previous": previous}


class Roles(BaseHTTPRequestHandler):
    """Answers by which model was asked: triage says nothing is owed in a thread about lunch, the reader lists
    two items (three on a re-read, one of them an earlier item), the checker calls candidate 2 not real."""
    asked = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        text = body["messages"][1]["content"]
        Roles.asked.append((body["model"], text))
        if body["model"] == "tri":
            reply = {"owed": "lunch" not in text}
        elif body["model"] == "read":
            items = [item("Send the deck", 2), item("Grab a table", 3)]
            reply = {"commitments": ([item("Pay Raj", 1, "P1")] if "<earlier_items>" in text else []) + items, "topics": []}
        else:
            reply = {"verdicts": [{"n": 1, "real": True, "reason": "said they would"}, {"n": 2, "real": False, "reason": "a joke"}]}
        out = json.dumps({"choices": [{"message": {"content": json.dumps(reply)}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


class CouncilTest(unittest.TestCase):
    def setUp(self):
        Roles.asked = []
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Roles)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        os.environ["SOLOYOLO_LLM_URL"] = f"http://127.0.0.1:{httpd.server_address[1]}/v1"
        self.addCleanup(os.environ.pop, "SOLOYOLO_LLM_URL")
        self.thread = [{"id": 1, "ts": 1.0, "from_me": 1, "text": "I'll pay Raj"}, {"id": 2, "ts": 2.0, "from_me": 1, "text": "I'll send the deck"},
                       {"id": 3, "ts": 3.0, "from_me": 1, "text": "I'll grab a table, ha"}]

    def test_triage_skips_reader_lists_checker_removes(self):
        c = Council("triage=tri,reader=read,checker=check")
        self.assertEqual(c.extract([{"id": 1, "ts": 1.0, "from_me": 0, "text": "lunch?"}]).commitments, [])
        self.assertEqual([m for m, _ in Roles.asked], ["tri"])  # nothing owed: the reader was never asked
        out = c.extract(self.thread)
        self.assertEqual([x.action for x in out.commitments], ["Send the deck"])
        self.assertEqual((c.stats["skipped"], c.stats["removed"], c.stats["reader"]["calls"]), (1, 1, 1))

    def test_a_reread_skips_triage_and_only_checks_what_is_new(self):
        c = Council("triage=tri,reader=read,checker=check")
        prior = [{"owner": "me", "kind": "promise", "action": "Pay Raj", "status": "open", "source_message_id": 1, "source_ts": 1.0,
                  "source_text": "I'll pay Raj", "due": None, "done_message_id": None}]
        out = c.extract(self.thread, prior=prior)
        self.assertEqual([m for m, _ in Roles.asked], ["read", "check"])
        self.assertEqual([(x.action, x.previous) for x in out.commitments], [("Pay Raj", "P1"), ("Send the deck", None)])
        self.assertNotIn("Pay Raj", Roles.asked[1][1].split("<candidates>")[1])  # the earlier item isn't up for checking


if __name__ == "__main__":
    unittest.main()

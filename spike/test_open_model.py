"""python -m unittest spike.test_open_model  (offline; a stand-in for an OpenAI-compatible server)"""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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


if __name__ == "__main__":
    unittest.main()

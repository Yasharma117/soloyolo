"""python -m unittest spike.test_telegram  (offline: a fake Telegram, no network)"""
import json
import os
import stat
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from spike import _nudge_stub, daily, telegram
from spike.test_daily import make_store

CHAT = 4242


class FakeBot(telegram.Bot):
    """Records calls; answers from a script of updates."""

    def __init__(self, updates=()):
        super().__init__("123:abc", base="http://fake")
        self.calls, self.updates = [], list(updates)

    def call(self, method, **params):
        self.calls.append((method, params))
        if method == "getUpdates":
            out, self.updates = self.updates, []
            return out
        if method == "getMe":
            return {"username": "my_soloyolo_bot"}
        if method == "sendMessage":
            return {"message_id": 77}
        return True

    def made(self, method):
        return [p for m, p in self.calls if m == method]


class TelegramTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = time.time()
        self.st, self.pids = make_store(Path(self.tmp.name) / "s.db", self.now)
        self.cfg = telegram.config_path(Path(self.tmp.name) / "s.db")
        patcher = mock.patch.object(daily, "_today_fn", lambda: _nudge_stub.today)  # which items: nudge's job
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    def paired(self, offset=None):
        telegram.save(self.cfg, {"token": "123:abc", "chat_id": CHAT, "offset": offset})

    def tap(self, data, chat=CHAT, uid=1):
        body = daily.telegram_message(daily.today_items(self.st, self.now), [], self.now)
        return {"update_id": uid, "callback_query": {"id": f"q{uid}", "data": data, "message": {
            "message_id": 77, "chat": {"id": chat}, "reply_markup": body["reply_markup"]}}}

    def test_pair_remembers_the_first_private_start_and_keeps_the_token_private(self):
        bot = FakeBot([{"update_id": 5, "message": {"chat": {"id": 9, "type": "group"}, "text": "/start"}},
                       {"update_id": 6, "message": {"chat": {"id": CHAT, "type": "private", "first_name": "Y"},
                                                    "text": "/start"}}])
        with mock.patch("sys.stdout"):
            self.assertEqual(telegram.pair(self.cfg, bot, "123:abc", wait=5), CHAT)
        self.assertEqual(json.loads(self.cfg.read_text()), {"token": "123:abc", "chat_id": CHAT, "offset": 7})
        self.assertEqual(stat.S_IMODE(self.cfg.stat().st_mode), 0o600)
        self.assertEqual(bot.made("sendMessage")[0]["chat_id"], CHAT)

    def test_send_puts_todays_items_with_buttons_in_your_chat_only(self):
        self.paired()
        bot = FakeBot()
        self.assertEqual(telegram.send(self.st, self.cfg, bot, self.now), 77)
        body = bot.made("sendMessage")[0]
        self.assertEqual(body["chat_id"], CHAT)
        self.assertIn("No tap = done.", body["text"])
        self.assertEqual(len(body["reply_markup"]["inline_keyboard"]), 3)
        self.assertIn("telegram (morning message)", self.st.disclosures())

    def test_quiet_day_sends_nothing(self):
        self.paired()
        bot = FakeBot()
        with mock.patch.object(daily, "today_items", lambda *a: []), mock.patch.object(daily, "health", lambda *a: []):
            self.assertIsNone(telegram.send(self.st, self.cfg, bot, self.now))
        self.assertEqual(bot.made("sendMessage"), [])

    def test_a_tap_becomes_your_mark_and_the_row_says_so(self):
        self.paired()
        item = daily.today_items(self.st, self.now)[0]
        data = daily.callback_data("d", item)
        bot = FakeBot([self.tap(data, uid=10)])
        self.assertEqual(telegram.poll(self.st, self.cfg, bot), 1)
        r = self.st.conn.execute("SELECT state, decided_by FROM resolution WHERE source_message_id = ?",
                                 (item["source_message_id"],)).fetchone()
        self.assertEqual(tuple(r), ("done", "you"))
        self.assertEqual(bot.made("answerCallbackQuery")[0]["text"], "Marked done")
        edited = bot.made("editMessageReplyMarkup")[0]["reply_markup"]["inline_keyboard"][0]
        self.assertEqual(edited, [{"text": "1: done", "callback_data": "sy1:noop"}])
        self.assertEqual(telegram.load(self.cfg)["offset"], 11)  # not applied twice

    def test_taps_from_another_chat_or_for_a_gone_item_change_nothing(self):
        self.paired()
        item = daily.today_items(self.st, self.now)[0]
        bot = FakeBot([self.tap(daily.callback_data("d", item), chat=999, uid=1),
                       self.tap("sy1:d:999:999:m", uid=2)])
        self.assertEqual(telegram.poll(self.st, self.cfg, bot), 0)
        self.assertEqual(self.st.conn.execute("SELECT COUNT(*) FROM resolution").fetchone()[0], 0)
        answers = bot.made("answerCallbackQuery")
        self.assertEqual(len(answers), 1)  # the stranger gets no answer at all
        self.assertIn("changed", answers[0]["text"])

    def test_not_paired_says_how(self):
        with self.assertRaisesRegex(telegram.TelegramError, "telegram pair"):
            telegram.send(self.st, self.cfg, FakeBot(), self.now)


class HttpTest(unittest.TestCase):
    """The real Bot against a local fake API: JSON in, errors out, and the token never in a message."""

    def setUp(self):
        class H(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path.endswith("/getMe"):
                    out, code = {"ok": True, "result": {"username": "b", "echo": body}}, 200
                else:
                    out, code = {"ok": False, "description": "Unauthorized"}, 401
                raw = json.dumps(out).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        env = mock.patch.dict(os.environ, {"NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"})
        env.start()
        self.addCleanup(env.stop)
        self.bot = telegram.Bot("123:secret-token", base=f"http://127.0.0.1:{self.srv.server_address[1]}", timeout=5)

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def test_calls_and_errors(self):
        self.assertEqual(self.bot.call("getMe", x=1)["echo"], {"x": 1})
        with self.assertRaises(telegram.TelegramError) as cm:
            self.bot.call("sendMessage", chat_id=1, text="hi")
        self.assertIn("Unauthorized", str(cm.exception))
        self.assertNotIn("secret-token", str(cm.exception))

    def test_bad_token_refused_early(self):
        with self.assertRaises(telegram.TelegramError):
            telegram.Bot("not-a-token")


if __name__ == "__main__":
    unittest.main()

"""The morning message over Telegram: send it, and turn your taps into marks.

Why Telegram (docs/RUNNING-DAILY.md): it's the one channel that pushes to an Android phone with real
buttons, carries no ban risk, and needs no open port on the Mac. The Mac only makes outbound HTTPS calls.
Telegram holds taps for 24 hours, so a tap made while the Mac sleeps is applied when it wakes.

What leaves the Mac: the 1-3 item lines of the digest (names and what's owed), never message text.
Telegram bot chats are not end-to-end encrypted, so those lines sit on Telegram's servers.

Setup is two steps (`python -m spike telegram --help`):
  1. In Telegram, message @BotFather, send /newbot, pick a name. It replies with a token.
  2. `python -m spike telegram pair`, paste the token, then send /start to your new bot.
     Only that chat is ever answered: anyone else who finds the bot gets nothing.

The config (token, your chat id, the update offset) lives in telegram.json beside the store, mode 600.
Standard library only; urllib follows HTTPS_PROXY.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import daily

API = "https://api.telegram.org"
SAID = {"done": "Marked done", "dismissed": "Marked not needed", "open": "Kept on: it stays on your list"}


class TelegramError(RuntimeError):
    pass


class Bot:
    def __init__(self, token: str, base: str = API, timeout: float = 70):
        if not token or ":" not in token:
            raise TelegramError("that doesn't look like a bot token (it has the form 123456:ABC...)")
        self.url, self.timeout = f"{base}/bot{token}/", timeout

    def call(self, method: str, **params):
        req = urllib.request.Request(self.url + method, data=json.dumps(params).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                out = json.load(r)
        except urllib.error.HTTPError as err:  # Telegram answers errors as JSON too
            try:
                out = json.load(err)
            except ValueError:
                raise TelegramError(f"{method}: HTTP {err.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            raise TelegramError(f"{method}: {getattr(err, 'reason', err)}") from None  # never the URL: it holds the token
        if not out.get("ok"):
            raise TelegramError(f"{method}: {out.get('description', 'failed')}")
        return out["result"]


# --- config ----------------------------------------------------------------------------------

def config_path(db: str | Path) -> Path:
    return Path(db).expanduser().resolve().parent / "telegram.json"


def load(path: Path) -> dict:
    cfg = json.loads(Path(path).read_text()) if Path(path).exists() else {}
    if os.environ.get("SOLOYOLO_TELEGRAM_TOKEN"):
        cfg["token"] = os.environ["SOLOYOLO_TELEGRAM_TOKEN"]
    return cfg


def save(path: Path, cfg: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".telegram-")
    with os.fdopen(fd, "w") as f:
        json.dump(cfg, f, indent=1)
    os.chmod(tmp, 0o600)  # the token controls the bot
    os.replace(tmp, path)


def _ready(cfg: dict) -> None:
    if not cfg.get("token") or not cfg.get("chat_id"):
        raise TelegramError("not paired yet: run `python -m spike telegram pair`")


# --- pair, send, poll ----------------------------------------------------------------------------

def pair(path: Path, bot: Bot, token: str, wait: float = 300, out=sys.stdout) -> int:
    """Wait for /start from a private chat and remember that chat. Returns the chat id."""
    me = bot.call("getMe")
    print(f"Now open Telegram and send /start to @{me.get('username')} (waiting up to {int(wait)}s)", file=out)
    offset, deadline = None, time.time() + wait
    while time.time() < deadline:
        for u in bot.call("getUpdates", offset=offset, timeout=min(50, max(1, int(deadline - time.time()))),
                          allowed_updates=["message"]):
            offset = u["update_id"] + 1
            msg = u.get("message") or {}
            if msg.get("chat", {}).get("type") == "private" and (msg.get("text") or "").startswith("/start"):
                chat = msg["chat"]["id"]
                save(path, {"token": token, "chat_id": chat, "offset": offset})
                bot.call("sendMessage", chat_id=chat,
                         text="Paired. Your morning message will come here. Tap Done / Not needed / Still on; "
                              "no tap means done.")
                print(f"paired with {msg['chat'].get('first_name', 'you')}; saved {path}", file=out)
                return chat
    raise TelegramError("no /start arrived; run `telegram pair` again")


def send(store, path: Path, bot: Bot | None = None, now: float | None = None) -> int | None:
    """Send today's message. Returns its message id, or None on a quiet day with nothing to say."""
    cfg = load(path)
    _ready(cfg)
    bot = bot or Bot(cfg["token"])
    now = now or time.time()
    items, warnings = daily.today_items(store, now), daily.health(store, now)
    if not items and not warnings:
        return None  # silence is the message: nothing is owed today
    body = daily.telegram_message(items, warnings, now)
    for pid in {c["person_id"] for c in items}:  # logged before sending, like extraction: whose name leaves
        store.record_disclosure(pid, "telegram (morning message)")
    msg = bot.call("sendMessage", chat_id=cfg["chat_id"], **body)
    return msg["message_id"]


def poll(store, path: Path, bot: Bot | None = None, timeout: int = 0) -> int:
    """Apply waiting taps. Returns how many were applied. Taps from any other chat are ignored."""
    cfg = load(path)
    _ready(cfg)
    bot = bot or Bot(cfg["token"])
    applied = 0
    updates = bot.call("getUpdates", offset=cfg.get("offset"), timeout=timeout, allowed_updates=["callback_query"])
    for u in updates:
        cfg["offset"] = u["update_id"] + 1
        q = u.get("callback_query")
        if not q or (q.get("message") or {}).get("chat", {}).get("id") != cfg["chat_id"]:
            continue  # not ours: no answer, no mark
        data = q.get("data") or ""
        if data == "sy1:noop":
            bot.call("answerCallbackQuery", callback_query_id=q["id"])
            continue
        try:
            state = daily.apply_callback(store, data)
        except ValueError:
            bot.call("answerCallbackQuery", callback_query_id=q["id"], text="That item has changed since; open soloyolo")
            continue
        applied += 1
        bot.call("answerCallbackQuery", callback_query_id=q["id"], text=SAID[state])
        markup = q["message"].get("reply_markup")
        if markup:
            bot.call("editMessageReplyMarkup", chat_id=cfg["chat_id"], message_id=q["message"]["message_id"],
                     reply_markup=daily.tapped(markup, data))
    if updates:
        save(path, cfg)  # the offset: Telegram won't send those taps again
    return applied


def listen(store_factory, path: Path, bot: Bot | None = None, rounds: int | None = None) -> None:
    """Long-poll forever (or `rounds` times), applying taps as they come. Backs off on errors."""
    delay, n = 5, 0
    while rounds is None or n < rounds:
        n += 1
        store = store_factory()
        try:
            got = poll(store, path, bot, timeout=50)
            if got:
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} applied {got} tap(s)", flush=True)
            delay = 5
        except TelegramError as err:
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} telegram: {err}; retrying in {delay}s", flush=True)
            time.sleep(delay)
            delay = min(delay * 2, 600)
        finally:
            store.close()

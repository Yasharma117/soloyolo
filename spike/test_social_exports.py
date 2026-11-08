"""Instagram and X export importers, on the synthetic fixtures in spike/fixtures/{instagram,x}."""
from __future__ import annotations

import io
import shutil
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

from spike import instagram_export as ig
from spike import x_export as xx
from spike.__main__ import main
from spike.store import Store

FIX = Path(__file__).resolve().parent / "fixtures"
IG_DIR, X_DIR = FIX / "instagram", FIX / "x"


def zip_of(folder: Path, dest: Path, top: str = "") -> Path:
    with zipfile.ZipFile(dest, "w") as z:
        for p in sorted(folder.rglob("*")):
            if p.is_file():
                z.write(p, f"{top}{p.relative_to(folder).as_posix()}")
    return dest


def attrs(st: Store, network: str, address: str) -> set[tuple[str, str]]:
    return {(r[0], r[1]) for r in st.conn.execute(
        "SELECT a.key, a.value FROM attribute a JOIN handle h ON h.person_id = a.person_id"
        " WHERE h.network = ? AND h.address = ?", (network, address))}


class TempDir(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)


class Mojibake(unittest.TestCase):
    def test_fixes_hindi_and_emoji(self):
        for real in ("कल पैसे भेज दूँगा 🙏", "❤️", "Café 😂", "Meera Joši ✨"):
            self.assertEqual(ig.fix_mojibake(real.encode("utf-8").decode("latin-1")), real)

    def test_leaves_clean_text_alone(self):
        for s in ("plain", "कल", "🙏", "café"):  # already right (a fixed future export), or real Latin-1
            self.assertEqual(ig.fix_mojibake(s), s)

    def test_fixture_is_really_escaped(self):
        raw = (IG_DIR / "your_instagram_activity/messages/inbox/kabirsharma_1784512345678901/message_1.json").read_text()
        self.assertIn("\\u00e0\\u00a4", raw)  # Devanagari as one escape per UTF-8 byte, as Meta writes it
        self.assertTrue(raw.isascii())


class Instagram(TempDir):
    def setUp(self):
        super().setUp()
        self.res = ig.load([IG_DIR])
        self.by_name = {name: h for h, name in self.res.names.items()}

    def texts(self, name: str) -> list[tuple[bool, str]]:
        return [(m.from_me, m.text) for m in self.res.messages if m.handle == self.by_name[name]]

    def test_me_from_personal_information(self):
        self.assertEqual(self.res.me, "Anaya Iyer")

    def test_me_from_threads_without_profile(self):
        threads, _, _, _ = ig.read([IG_DIR])
        self.assertEqual(ig.infer_me(threads, {}), "Anaya Iyer")  # the one participant in every thread

    def test_me_override_must_be_a_sender(self):
        with self.assertRaises(ValueError):
            ig.load([IG_DIR], me="Nobody Here")

    def test_split_thread_is_one_person_in_order_with_hindi(self):
        self.assertEqual(self.texts("Kabir Sharma"), [
            (False, "Café was great 😂"), (True, "Can you send me the Goa photos? 📸"),
            (False, "कल पैसे भेज दूँगा 🙏"), (True, "ठीक है, शुक्रिया 🙏")])  # the reaction line is dropped

    def test_media_shares_calls_become_markers(self):
        self.assertEqual(self.texts("Meera Joši ✨"), [
            (True, "I'll call you tonight 📞"),  # sticker-only and unsent messages are gone
            (False, "[video]"), (False, "[photo] here you go"), (False, "[voice note]"),
            (True, "[link] https://www.instagram.com/reel/SYNTH123abc/"),
            (False, "[call]")])  # the 0-second call didn't connect; "Liked a message" is not a message

    def test_group_is_evidence_only(self):
        self.assertNotIn("Goa trip 🌴", self.by_name)
        lines = self.res.groups["Goa trip 🌴"]
        self.assertEqual([(l.sender, l.text) for l in lines],
                         [("me", "मैं टिकट बुक करूँगी"), ("Kabir Sharma", "Sent the photos to everyone ✅")])

    def test_message_requests_kept_only_if_answered(self):
        self.assertIn("Dev Patel", self.by_name)
        self.assertNotIn("Crypto Deals", self.by_name)

    def test_handles_are_thread_ids_not_hard_keys(self):
        from spike.identity import handle_keys
        for h in self.res.names:
            self.assertTrue(h.startswith("thread:"))
            self.assertEqual(handle_keys("instagram", h), [])  # a folder name must never pass for a username

    def test_username_only_when_folder_matches_a_connection(self):
        self.assertEqual(self.res.usernames, {self.by_name["Kabir Sharma"]: "kabirsharma",
                                              self.by_name["Dev Patel"]: "devpatel"})

    def test_html_export_is_refused_with_a_hint(self):
        t = self.tmp / "your_instagram_activity/messages/inbox/someone_123"
        t.mkdir(parents=True)
        (t / "message_1.html").write_text("<html></html>")
        with self.assertRaisesRegex(ValueError, "JSON"):
            ig.load([self.tmp])

    def test_save_is_idempotent_across_zip_folder_and_split_zips(self):
        st = Store(self.tmp / "s.db")
        first = ig.save(st, self.res)
        self.assertIn("13 new messages", first)
        n = st.conn.execute("SELECT COUNT(*) FROM message WHERE network = 'instagram'").fetchone()[0]
        z = zip_of(IG_DIR, self.tmp / "instagram-anaya.zip", top="instagram-anaya-2026-11-07/")
        self.assertIn("0 new messages", ig.save(st, ig.load([z])))
        self.assertIn("0 new messages", ig.save(st, ig.load([z, IG_DIR])))  # the zip and its folder together
        self.assertIn("0 new group lines", ig.save(st, ig.load([IG_DIR])))
        self.assertEqual(st.conn.execute("SELECT COUNT(*) FROM message").fetchone()[0], n)
        self.assertEqual(st.conn.execute("SELECT COUNT(*) FROM evidence WHERE source = 'instagram-group:Goa trip 🌴'")
                         .fetchone()[0], 2)
        kabir = self.by_name["Kabir Sharma"]
        self.assertEqual(attrs(st, "instagram", kabir), {("instagram", "kabirsharma")})
        self.assertEqual(st.conn.execute("SELECT COUNT(*) FROM attribute").fetchone()[0], 2)

    def test_two_part_export(self):
        """A big export arrives as several zips; one thread's message_N files can be in different parts."""
        a, b = self.tmp / "a", self.tmp / "b"
        shutil.copytree(IG_DIR, a)
        shutil.copytree(IG_DIR, b)
        k = "your_instagram_activity/messages/inbox/kabirsharma_1784512345678901"
        (a / k / "message_2.json").unlink()
        (b / k / "message_1.json").unlink()
        res = ig.load([zip_of(a, self.tmp / "part1.zip"), zip_of(b, self.tmp / "part2.zip")])
        self.assertEqual(sorted(m.guid for m in res.messages), sorted(m.guid for m in self.res.messages))

    def test_rename_keeps_the_same_person(self):
        """The folder's name part follows the display name; the numeric id doesn't change."""
        d = self.tmp / "e"
        shutil.copytree(IG_DIR, d)
        inbox = d / "your_instagram_activity/messages/inbox"
        (inbox / "kabirsharma_1784512345678901").rename(inbox / "kabirs_1784512345678901")
        st = Store(self.tmp / "s.db")
        ig.save(st, self.res)
        self.assertIn("0 new messages", ig.save(st, ig.load([d])))


class X(TempDir):
    def setUp(self):
        super().setUp()
        self.res = xx.load([X_DIR])

    def texts(self, uid: str) -> list[tuple[bool, str]]:
        return sorted([(m.ts, m.from_me, m.text) for m in self.res.messages if m.handle == f"id:{uid}"])

    def test_prefix_is_stripped(self):
        data = xx.read_js(b"window.YTD.direct_messages.part0 = [{\"a\": 1}]", "x")
        self.assertEqual(data, [{"a": 1}])
        with self.assertRaises(ValueError):
            xx.read_js(b"[{}]", "x")

    def test_me_from_account_js(self):
        self.assertEqual(self.res.me, "1500000000000000001")

    def test_me_without_account_js(self):
        d = self.tmp / "x"
        shutil.copytree(X_DIR, d)
        (d / "data/account.js").unlink()
        self.assertEqual(xx.load([d]).me, "1500000000000000001")  # the id in every 1:1 conversation id

    def test_text_links_media(self):
        self.assertEqual([(f, t) for _, f, t in self.texts("1600000000000000002")], [
            (True, "Can you send the Q3 deck by Friday?"),
            (False, "Q&A deck coming — कल भेजूँगा 🙏 https://example.com/deck"),  # unescaped, t.co expanded
            (False, "[photo]")])  # the GIF-only message is dropped, the photo's own link removed
        self.assertEqual([t for _, _, t in self.texts("1400000000000000009")],
                         ["[video] loved your talk 🔥", "I'll intro you to Sam next week"])

    def test_names_and_handles_from_tweets(self):
        self.assertEqual(self.res.names["id:1600000000000000002"], "Kabir Sharma")
        self.assertEqual(self.res.names["id:1650000000000000007"], "@priya_codes")  # a reply names only the handle
        self.assertNotIn("id:1400000000000000009", self.res.names)  # never mentioned: no name in the archive

    def test_group_is_evidence(self):
        lines = self.res.groups["1700000000000000123"]
        self.assertEqual(sorted((l.sender, l.text) for l in lines),
                         [("Kabir Sharma", "Booked the venue ✅"), ("me", "Who's booking the venue?")])

    def test_save_attributes_and_idempotence(self):
        st = Store(self.tmp / "s.db")
        self.assertIn("6 new messages", xx.save(st, self.res))
        self.assertEqual(attrs(st, "x", "id:1600000000000000002"), {("x_id", "1600000000000000002"), ("x", "kabirs_")})
        self.assertEqual(attrs(st, "x", "id:1400000000000000009"), {("x_id", "1400000000000000009")})
        name = st.conn.execute("SELECT display_name FROM person p JOIN handle h ON h.person_id = p.id"
                               " WHERE h.address = 'id:1400000000000000009'").fetchone()[0]
        self.assertEqual(name, "X user 1400000000000000009")
        z = zip_of(X_DIR, self.tmp / "twitter-2026-11-07.zip")
        self.assertIn("0 new messages", xx.save(st, xx.load([z])))
        self.assertIn("0 new group lines", xx.save(st, xx.load([z, X_DIR])))
        self.assertIn("0 new attributes", xx.save(st, self.res))

    def test_placeholder_never_overwrites_a_real_name(self):
        st = Store(self.tmp / "s.db")
        st.person_for("x", "id:1400000000000000009", "Nikhil Rao")  # named elsewhere (a merge, a later archive)
        xx.save(st, self.res)
        name = st.conn.execute("SELECT display_name FROM person p JOIN handle h ON h.person_id = p.id"
                               " WHERE h.address = 'id:1400000000000000009'").fetchone()[0]
        self.assertEqual(name, "Nikhil Rao")

    def test_hard_keys_come_from_attributes_not_the_handle(self):
        from spike.identity import handle_keys
        self.assertEqual(handle_keys("x", "id:1600000000000000002"), [])  # a short id must never pass for a handle


class Cli(TempDir):
    def test_both_commands(self):
        db = str(self.tmp / "s.db")
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["--db", db, "import-instagram", str(IG_DIR)]), 0)
            self.assertEqual(main(["--db", db, "import-x", str(X_DIR)]), 0)
            self.assertEqual(main(["--db", db, "import-x", str(X_DIR)]), 0)
        self.assertIn("13 new messages", out.getvalue())
        self.assertIn("6 new messages", out.getvalue())
        self.assertIn("0 new messages", out.getvalue())
        st = Store(db)
        nets = dict(st.conn.execute("SELECT network, COUNT(*) FROM message GROUP BY network").fetchall())
        self.assertEqual(nets, {"instagram": 13, "x": 6})
        st.close()


if __name__ == "__main__":
    unittest.main()

"""python -m unittest spike.test_linkedin  (offline; synthetic export in spike/fixtures/linkedin)"""
import contextlib
import io
import shutil
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from spike import linkedin_export as li
from spike.__main__ import main
from spike.store import Store

EXPORT = Path(__file__).parent / "fixtures/linkedin/Complete_LinkedInDataExport_11-02-2026"
ME = "https://www.linkedin.com/in/alex-rivera-synth01"
PRIYA = "https://www.linkedin.com/in/priya-natarajan-synth02"
JORDAN = "https://www.linkedin.com/in/jordan-blake-synth03"
JOSE = "https://www.linkedin.com/in/josé-martín-synth06"


def utc(s: str) -> float:
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()


class LinkedInExportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.res = li.load([EXPORT])

    def tearDown(self):
        self.tmp.cleanup()

    def zipped(self) -> Path:
        """The export as LinkedIn sends it: one zip, the CSVs inside a folder."""
        path = self.dir / f"{EXPORT.name}.zip"
        with zipfile.ZipFile(path, "w") as z:
            for p in EXPORT.iterdir():
                z.write(p, f"{EXPORT.name}/{p.name}")
        return path

    def counts(self, store: Store) -> dict:
        return {t: store.conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                for t in ("person", "handle", "message", "evidence", "attribute")}

    # --- format quirks ---------------------------------------------------------------------
    def test_url_normalization(self):
        for raw in ["https://www.linkedin.com/in/Priya-Natarajan-Synth02/", "http://in.linkedin.com/in/priya-natarajan-synth02",
                    "https://www.linkedin.com/in/priya-natarajan-synth02?originalSubdomain=in", "linkedin.com/in/priya-natarajan-synth02/details/"]:
            self.assertEqual(li.normalize_url(raw), PRIYA)
        self.assertEqual(li.normalize_url("https://www.linkedin.com/in/jos%C3%A9-mart%C3%ADn-synth06"), JOSE)
        self.assertIsNone(li.normalize_url(""))
        self.assertIsNone(li.normalize_url("https://www.linkedin.com/company/fabrikam"))

    def test_dates_are_utc(self):
        thread = sorted((m for m in self.res.messages if m.handle == PRIYA), key=lambda m: m.ts)
        self.assertEqual(thread[0].ts, utc("2026-10-20 08:02:55"))
        self.assertEqual(li._ts("10/30/26, 4:18 PM"), utc("2026-10-30 16:18:00"))  # Invitations.csv
        self.assertEqual(li._date("14 Mar 2024"), "2024-03-14")

    def test_names_keep_credentials(self):
        self.assertEqual(li._names("Ana Ruiz, Dana Kim, MBA, Lee Park"), ["Ana Ruiz", "Dana Kim, MBA", "Lee Park"])

    def test_mojibake_and_html(self):
        self.assertEqual(li.fix_text("JosÃ© MartÃ\xadn"), "José Martín")
        self.assertEqual(li.fix_text("Itâ€™s fine"), "It’s fine")
        self.assertEqual(li.fix_text("José, 日本"), "José, 日本")  # already right: untouched
        self.assertEqual(li.clean("<p>Hi,</p><p>See you&nbsp;then &amp; bye</p>"), "Hi,\nSee you then & bye")

    def test_backslash_escaped_quotes(self):
        text = 'A,B\n"he said \\"hi\\", ok",2\n'
        self.assertEqual(li._rows(text), [{"A": 'he said "hi", ok', "B": "2"}])

    # --- who is me -------------------------------------------------------------------------
    def test_me_from_invitations(self):
        self.assertEqual(self.res.me, ME)
        self.assertIn("Invitations.csv", " ".join(self.res.notes))

    def test_me_without_invitations(self):
        d = self.dir / "export"
        shutil.copytree(EXPORT, d)
        (d / "Invitations.csv").unlink()
        res = li.load([d])
        self.assertEqual(res.me, ME)
        self.assertIn("every conversation", " ".join(res.notes))

    def test_me_tie_broken_by_profile_name(self):
        """One partner in every thread: both URLs are in every conversation, Profile.csv decides."""
        rows = li._rows((EXPORT / "messages.csv").read_text("utf-8-sig"))
        one = [r for r in rows if r["SENDER PROFILE URL"].startswith(PRIYA) or r["RECIPIENT PROFILE URLS"] == PRIYA]
        profile = li._rows((EXPORT / "Profile.csv").read_text("utf-8"))
        self.assertEqual(li.infer_me(one, [], profile)[0], ME)
        with self.assertRaises(ValueError):
            li.infer_me(one, [], [])
        self.assertEqual(li.infer_me(one, [], [], me="Alex Rivera")[0], ME)
        self.assertEqual(li.infer_me(one, [], [], me=ME + "/")[0], ME)

    # --- what gets imported ---------------------------------------------------------------
    def test_one_to_one_threads(self):
        self.assertEqual(set(self.res.names), {PRIYA, JORDAN, JOSE})
        self.assertEqual(self.res.names[JOSE], "José Martín")
        self.assertEqual(self.res.names[JORDAN], "Jordan Blake, PhD")  # a credential isn't a second person
        priya = {m.text: m.from_me for m in self.res.messages if m.handle == PRIYA}
        self.assertTrue(priya["Great chatting today.\nI'll send you the pricing deck by Friday.\n\nAlex"])  # multiline
        self.assertFalse(priya['Hi Alex, could you share the pricing deck before our call? "Draft" is fine.'])
        self.assertEqual(len(priya), 3)  # the draft is skipped

    def test_inmail_subject_html_and_attachment(self):
        jordan = {m.text for m in self.res.messages if m.handle == JORDAN}
        self.assertIn("Staff role at Northwind\nHi Alex,\nWould you be open to a call next week?\nBest,\nJordan & team", jordan)
        self.assertIn(li.ATTACHMENT, jordan)

    def test_groups_are_evidence(self):
        self.assertEqual(set(self.res.groups), {"Q4 offsite planning", "Mei Chen, Sam Okafor"})
        offsite = {(l.sender, l.text) for l in self.res.groups["Q4 offsite planning"]}
        self.assertIn(("me", "Great, I'll circulate the agenda."), offsite)
        self.assertIn(("Sam Okafor", "I booked the venue, confirmation is in your inbox."), offsite)
        handles = {m.handle for m in self.res.messages}
        self.assertNotIn("https://www.linkedin.com/in/sam-okafor-synth04", handles)

    def test_spam_sponsored_and_deleted_members_skipped(self):
        texts = " ".join(m.text for m in self.res.messages)
        for gone in ["Premium", "10x your leads", "still hiring"]:
            self.assertNotIn(gone, texts)
        notes = " ".join(self.res.notes)
        for why in ["sponsored", "spam folder", "drafts", "deleted member"]:
            self.assertIn(why, notes)

    def test_connections(self):
        by = {c.handle: c for c in self.res.connections}
        self.assertEqual(len(by), 4)  # Lee Park has no URL
        self.assertEqual(by[PRIYA].connected_on, "2024-03-14")
        sam = by["https://www.linkedin.com/in/sam-okafor-synth04"]
        self.assertEqual((sam.email, sam.company), ("sam.okafor@example.com", "Contoso, Inc."))
        self.assertEqual(by[JOSE].name, "José Martín")
        self.assertIn("1 without a profile URL", " ".join(self.res.notes))

    # --- the store -------------------------------------------------------------------------
    def test_save_and_idempotent(self):
        store = Store(self.dir / "s.db")
        li.save(store, self.res)
        first = self.counts(store)
        self.assertEqual(first["message"], 7)
        self.assertEqual(first["evidence"], 4)
        self.assertEqual(first["person"], 5)  # Priya, Jordan, José, Sam, Mei: no one for you, none for groups alone
        # Priya is one person: her connection and her messages share the normalized URL.
        pid = store.person_for("linkedin", PRIYA)
        self.assertEqual(store.conn.execute("SELECT count(*) FROM message WHERE person_id = ?", (pid,)).fetchone()[0], 3)
        attrs = dict(store.conn.execute("SELECT key, value FROM attribute WHERE person_id = ?", (pid,)).fetchall())
        self.assertEqual(attrs, {"linkedin": PRIYA, "company": "Fabrikam", "position": "Head of Partnerships",
                                 "connected_on": "2024-03-14"})  # no email: LinkedIn didn't share one
        ts = store.conn.execute("SELECT DISTINCT ts FROM attribute").fetchall()
        self.assertEqual([r[0] for r in ts], [utc("2026-11-02 00:00:00")])  # the export's date, from its name
        self.assertTrue(store.conn.execute("SELECT 1 FROM evidence WHERE source = 'linkedin-group:Q4 offsite planning'").fetchone())
        # Again, and again from the zip plus the folder (both parts of a two-part export overlap like this).
        li.save(store, li.load([EXPORT]))
        li.save(store, li.load([self.zipped(), EXPORT]))
        self.assertEqual(self.counts(store), first)
        store.close()

    def test_zip_reads_like_folder(self):
        res = li.load([self.zipped()])
        self.assertEqual(sorted(res.messages, key=lambda m: m.guid), sorted(self.res.messages, key=lambda m: m.guid))
        self.assertEqual(res.connections, self.res.connections)

    def test_attribute_table_created_once(self):
        store = Store(self.dir / "s.db")
        store.conn.execute(li.ATTRIBUTE_DDL)  # already there (core.sql may add it): still fine
        li.save(store, self.res)
        cols = [r[1] for r in store.conn.execute("PRAGMA table_info(attribute)")]
        self.assertEqual(cols, ["person_id", "key", "value", "source", "ts"])
        store.close()

    def test_not_an_export(self):
        bad = self.dir / "notes.txt"
        bad.write_text("hi")
        with self.assertRaises(ValueError):
            li.load([bad])
        empty = self.dir / "empty"
        empty.mkdir()
        with self.assertRaises(ValueError):
            li.load([empty])

    def test_cli(self):
        db = self.dir / "cli.db"
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["--db", str(db), "import-linkedin", str(self.zipped())]), 0)
            main(["--db", str(db), "import-linkedin", str(EXPORT)])
        self.assertIn("7 new messages", out.getvalue())
        self.assertIn("0 new messages", out.getvalue())


if __name__ == "__main__":
    unittest.main()

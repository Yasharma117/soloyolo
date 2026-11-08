"""python -m unittest spike.test_identity  (offline, synthetic people only)"""
import json
import tempfile
import time
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from spike import identity as idn
from spike.store import Store

JID = "@s.whatsapp.net"


def msg(guid, handle, text, from_me=False, ts=None):
    return SimpleNamespace(guid=guid, handle=handle, ts=ts or time.time() - 3600, from_me=from_me, text=text)


class NormalizeTest(unittest.TestCase):
    def test_phones(self):
        lids = {"55501": "919800000001"}
        cases = {
            "+91 98000-00001": "+919800000001", "098000 00001": "+919800000001", "9800000001": "+919800000001",
            "91 98000 00001": "+919800000001", "919800000001" + JID: "+919800000001",
            "919800000001:7" + JID: "+919800000001", "55501@lid": "+919800000001", "55502@lid": None,
            "022 2000 0000": "+912220000000", "0044 20 0000 0000": "+442000000000", "+1 (415) 000-0000": "+14150000000",
            "120363000000000000@g.us": None, "56767": None, "+91 98000 00001 ext 12": "+919800000001",
        }
        for raw, want in cases.items():
            self.assertEqual(idn.normalize_phone(raw, lid_map=lids), want, raw)

    def test_emails_profiles_handles(self):
        self.assertEqual(idn.normalize_email(" Some.One+news@GoogleMail.com "), "someone@gmail.com")
        self.assertEqual(idn.normalize_email("mailto:Some.One@Example.org"), "some.one@example.org")
        self.assertIsNone(idn.normalize_email("not an email"))
        self.assertTrue(idn.is_role_mailbox("careers@example.org"))
        self.assertEqual(idn.normalize_linkedin("https://in.linkedin.com/in/Some-One-1a2b/?trk=x"),
                         "linkedin.com/in/some-one-1a2b")
        self.assertEqual(idn.normalize_linkedin("www.linkedin.com/in/some%2Done/"), "linkedin.com/in/some-one")
        self.assertIsNone(idn.normalize_linkedin("https://linkedin.com/company/acme"))
        self.assertEqual(idn.normalize_handle("x", "https://twitter.com/Some_One?s=20"), "some_one")
        self.assertEqual(idn.normalize_handle("instagram", "@Some.One"), "some.one")
        self.assertIsNone(idn.normalize_handle("x", "@far_too_long_for_x_handles"))
        self.assertEqual(idn.handle_keys("whatsapp", "919800000001" + JID), [("phone", "+919800000001")])
        self.assertEqual(idn.handle_keys("imessage", "Some.One@icloud.com"), [("email", "some.one@icloud.com")])


class NameTest(unittest.TestCase):
    def test_saved_name_parts(self):
        n = idn.parse_name("Rahul Bhaiya (Acmepay)")
        self.assertEqual((n.core, n.relation, n.context), (["rahul"], ["bhaiya"], ["acmepay"]))
        self.assertEqual(idn.parse_name("Neha Didi Pune").context, ["pune"])
        self.assertEqual(idn.parse_name("Dr. Priya Sharma").core, ["priya", "sharma"])
        self.assertTrue(idn.parse_name("Amit New").number_change)
        self.assertTrue(idn.parse_name("Amit 2").number_change)
        self.assertEqual(idn.parse_name("Rahul - Acmepay").core, ["rahul"])
        self.assertEqual(idn.parse_name("Sharma, Rahul").core, ["sharma", "rahul"])  # a comma is Last, First
        self.assertEqual(idn.parse_name("Driver Ramesh").context, ["driver"])

    def test_devanagari(self):
        n = idn.parse_name("राहुल भैया")
        self.assertEqual(idn.phon(n.core[0]), idn.phon("rahul"))
        self.assertEqual(n.relation, ["bhaiyaa"])

    def test_transliteration_and_nicknames(self):
        for a, b in [("lakshmi", "laxmi"), ("pooja", "puja"), ("vijay", "vijai"), ("mohd", "muhammad"),
                     ("shreya", "sreya"), ("bhavna", "bhawna")]:
            self.assertEqual(idn.phon(a), idn.phon(b), (a, b))
        self.assertEqual(idn.token_match("abhi", "abhishek")[1], "nickname")
        self.assertEqual(idn.token_match("rishi", "hrishikesh")[1], "nickname")
        self.assertEqual(idn.token_match("rahul", "rohit")[0], 0.0)
        self.assertEqual(idn.token_match("ankit", "ankita")[0], 0.0)  # a different person, not a spelling

    def test_name_score(self):
        P, c = idn.parse_name, Counter()
        self.assertGreater(idn.name_score(P("Pooja Verma"), P("Puja Varma"), c)[0], 0.8)
        self.assertEqual(idn.name_score(P("Rahul Sharma"), P("Rahul Verma"), c)[0], 0.0)  # different surnames
        self.assertGreater(idn.name_score(P("Mohan Bhaiya"), P("Mohan"), c)[0], 0)
        common = Counter({idn.phon("rahul"): 20})
        self.assertLess(idn.name_score(P("Rahul"), P("Rahul"), common)[0], idn.name_score(P("Rahul"), P("Rahul"), c)[0])


VCF = """BEGIN:VCARD\r
VERSION:3.0\r
FN:Kiran Rao\r
N:Rao;Kiran;;;\r
TEL;TYPE=CELL:+91 98000 00001\r
item1.EMAIL;TYPE=INTERNET:Kiran.Rao@Example.org\r
ORG:Acmepay Pvt Ltd;Payments\r
TITLE:Engineer\r
ADR;TYPE=HOME:;;1 Some Road;Pune;;411000;India\r
X-SOCIALPROFILE;type=linkedin:https://www.linkedin.com/in/kiran-rao-0000\r
NOTE:long note that is fol\r
 ded onto two lines\r
END:VCARD\r
BEGIN:VCARD\r
VERSION:2.1\r
N;CHARSET=UTF-8;ENCODING=QUOTED-PRINTABLE:=E0=A4=B0=E0=A4=BE=E0=A4=B9=E0=A5=81=E0=A4=B2;;;;\r
TEL;CELL:098000 00002\r
END:VCARD\r
BEGIN:VCARD\r
VERSION:4.0\r
FN:No Keys Person\r
END:VCARD\r
"""


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "s.db")
        self.conn = self.store.conn

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def wa(self, n, name=None, texts=("hi",)):
        h = f"9198000000{n:02d}{JID}"
        self.store.add_messages("whatsapp", [msg(f"wa{n}-{i}", h, t) for i, t in enumerate(texts)],
                                {h: name} if name else None)
        return self.store.person_for("whatsapp", h)

    def other(self, network, address, name, texts=("hello",)):
        self.store.add_messages(network, [msg(f"{network}-{address}-{i}", address, t) for i, t in enumerate(texts)],
                                {address: name})
        return self.store.person_for(network, address)

    def count(self, sql, *a):
        return self.conn.execute(sql, a).fetchone()[0]


class VCardTest(StoreCase):
    def test_parse(self):
        cards = idn.parse_vcf(VCF)
        self.assertEqual(len(cards), 3)
        a = dict(cards[0].attrs)
        self.assertEqual(cards[0].name, "Kiran Rao")
        self.assertEqual((a["company"], a["city"], a["position"]), ("Acmepay Pvt Ltd", "Pune", "Engineer"))
        self.assertIn("linkedin", a)
        self.assertEqual(idn.phon(idn.parse_name(cards[1].name).core[0]), idn.phon("rahul"))  # QP Devanagari via N

    def test_vcard_bridges_phone_to_email_then_auto_merge(self):
        wa = self.wa(1, texts=("I'll send the deck tomorrow",))          # an unsaved number: raw name
        mail = self.other("gmail", "kiran.rao@example.org", "Kiran R")
        p = Path(self.tmp.name) / "c.vcf"
        p.write_text(VCF)
        st = idn.import_vcf(self.conn, p)
        self.assertEqual((st["matched"], st["named_raw"], st["created"]), (1, 1, 2))  # card 1 hits both people
        self.assertEqual(self.conn.execute("SELECT display_name FROM person WHERE id = ?", (wa,)).fetchone()[0], "Kiran Rao")
        again = idn.import_vcf(self.conn, p)
        self.assertEqual((again.get("created", 0), again.get("attributes", 0)), (0, 0))  # re-import adds nothing
        st = idn.auto_merge(self.conn)
        self.assertEqual(st["merged"], 1)
        self.assertEqual(self.count("SELECT COUNT(*) FROM message WHERE person_id = ?", wa if wa < mail else mail), 2)


class MergeTest(StoreCase):
    def test_hard_key_merge_moves_everything_and_undo_restores(self):
        a = self.wa(1, texts=("one", "two"))                              # raw name, more messages
        b = self.other("gmail", "kiran@example.org", "Kiran Rao", texts=("three",))
        idn.add_attribute(self.conn, a, "email", "Kiran@Example.org", "vcard")
        mid = self.conn.execute("SELECT id FROM message WHERE person_id = ?", (b,)).fetchone()[0]
        self.store.replace_extraction(b, [dict(owner="me", action="send deck", status="open", source_message_id=mid)],
                                      ["work"], "heuristic")
        self.store.resolve(b, mid, "me", "snoozed", "you", until=time.time() + 99)
        idn.add_attribute(self.conn, b, "company", "Acmepay", "linkedin-export")
        c = self.wa(3, "Third")
        self.conn.execute("INSERT INTO edge(src, dst, kind, evidence_message_id, note, extractor, ts)"
                          " VALUES (?, ?, 'intro', ?, 'forwarding a profile', 'test', 0)", (c, b, mid))
        self.conn.execute("INSERT INTO edge(src, dst, kind, evidence_message_id, extractor, ts) VALUES (?, ?, 'knows', ?, 'test', 0)",
                          (a, b, mid))
        st = idn.auto_merge(self.conn)
        self.assertEqual(st, {"merged": 1, "merged_by_email": 1})
        q = lambda t, p: self.count(f"SELECT COUNT(*) FROM {t} WHERE person_id = ?", p)
        self.assertEqual([q(t, b) for t in ("message", "commitment", "resolution", "attribute", "handle", "topic")], [0] * 6)
        self.assertEqual((q("message", a), q("commitment", a), q("resolution", a), q("handle", a)), (3, 1, 1, 2))
        self.assertEqual(self.conn.execute("SELECT display_name FROM person WHERE id = ?", (a,)).fetchone()[0], "Kiran Rao")
        self.assertEqual(self.count("SELECT COUNT(*) FROM edge WHERE src = ? AND dst = ?", c, a), 1)
        self.assertEqual(self.count("SELECT COUNT(*) FROM edge"), 1)        # a->b became a self-loop: dropped
        self.assertNotIn(b, idn.active_ids(self.conn))
        self.assertEqual(len(self.store.people()), 2)
        log = self.count("SELECT id FROM merge_log")
        idn.undo(self.conn, log)
        self.assertEqual((q("message", a), q("message", b), q("commitment", b), q("resolution", b), q("topic", b)), (2, 1, 1, 1, 1))
        self.assertEqual(self.count("SELECT COUNT(*) FROM edge"), 2)
        self.assertEqual(self.count("SELECT COUNT(*) FROM attribute WHERE person_id = ?", b), 1)
        self.assertTrue(idn.is_raw(self.conn.execute("SELECT display_name FROM person WHERE id = ?", (a,)).fetchone()[0]))
        self.assertEqual(idn.auto_merge(self.conn), {"skipped_rejected": 1})  # you split them: stays split

    def test_lid_maps_to_phone(self):
        a = self.wa(1, "Kiran")
        b = self.other("whatsapp", "55501@lid", "Kiran")
        self.assertEqual(idn.auto_merge(self.conn, lid_map={"55501": "919800000001"})["merged"], 1)
        self.assertEqual(self.count("SELECT COUNT(*) FROM handle WHERE person_id = ?", min(a, b)), 2)

    def test_never_on_name_alone(self):
        a, b = self.wa(1, "Kiran Rao"), self.wa(2, "Kiran Rao")
        m = idn.match(self.conn)
        self.assertEqual(m["auto"], {})
        row = self.conn.execute("SELECT score, reasons, state FROM merge_suggestion WHERE a = ? AND b = ?", (a, b)).fetchone()
        self.assertEqual(row[2], "open")
        self.assertIn("name: same", json.loads(row[1]))
        idn.reject(self.conn, a, b)
        idn.suggest(self.conn)
        self.assertEqual(self.count("SELECT COUNT(*) FROM merge_suggestion WHERE state = 'open'"), 0)  # a no sticks

    def test_message_keys_role_mailboxes_and_shared_numbers_do_not_merge(self):
        a, b = self.wa(1, "Kiran"), self.other("gmail", "kiran@example.org", "K")
        idn.add_attribute(self.conn, a, "email", "kiran@example.org", "message:1")   # said in a chat: soft
        c, d = self.other("gmail", "hr@example.org", "Hiring"), self.wa(4, "Someone")
        idn.add_attribute(self.conn, d, "email", "hr@example.org", "vcard")        # a role mailbox
        e, f, g = self.wa(5, "Home"), self.wa(6, "Ma"), self.wa(7, "Pa")
        for p in (e, f, g):
            idn.add_attribute(self.conn, p, "phone", "022 2000 0000", "vcard")       # a family landline
        st = idn.auto_merge(self.conn)
        self.assertEqual((st.get("merged", 0), st["shared_key"]), (0, 1))
        idn.suggest(self.conn)
        reasons = json.loads(self.conn.execute("SELECT reasons FROM merge_suggestion WHERE a = ? AND b = ?",
                                               (min(a, b), max(a, b))).fetchone()[0])
        self.assertIn("email mentioned in a message matches", reasons)
        self.assertEqual(self.count("SELECT COUNT(*) FROM merge_suggestion WHERE a = ? AND b = ?", e, f), 1)

    def test_conflicting_profiles_block_auto_merge(self):
        a, b = self.wa(1, "Kiran Rao"), self.other("gmail", "kiran@example.org", "Kiran Rao")
        idn.add_attribute(self.conn, a, "email", "kiran@example.org", "vcard")
        idn.add_attribute(self.conn, a, "linkedin", "linkedin.com/in/kiran-rao-1", "vcard")
        idn.add_attribute(self.conn, b, "linkedin", "linkedin.com/in/kiran-rao-2", "linkedin-export")
        self.assertEqual(idn.auto_merge(self.conn), {"skipped_conflict": 1})

    def test_context_suffix_meets_company(self):
        a = self.wa(1, "Kiran Acmepay")
        b = self.conn.execute("INSERT INTO person(display_name) VALUES ('Kiran Rao')").lastrowid  # e.g. LinkedIn
        idn.add_attribute(self.conn, b, "company", "Acmepay Technologies", "linkedin-export")
        idn.add_attribute(self.conn, b, "linkedin", "https://www.linkedin.com/in/kiran-rao-0", "linkedin-export")
        idn.suggest(self.conn)
        row = self.conn.execute("SELECT reasons FROM merge_suggestion WHERE a = ? AND b = ?", (a, b)).fetchone()
        self.assertIsNotNone(row)
        self.assertTrue(any(r.startswith("context: acmepay") for r in json.loads(row[0])))
        idn.accept(self.conn, a, b)
        self.assertEqual(self.conn.execute("SELECT display_name FROM person WHERE id = ?", (a,)).fetchone()[0], "Kiran Acmepay")
        self.assertEqual(self.count("SELECT COUNT(*) FROM attribute WHERE person_id = ? AND key = 'alias'", a), 1)
        self.assertEqual(self.conn.execute("SELECT state FROM merge_suggestion WHERE a = ? AND b = ?", (a, b)).fetchone()[0], "merged")

    def test_new_number_suggested_but_unrelated_names_not(self):
        a, b, c = self.wa(1, "Kiran"), self.wa(2, "Kiran New"), self.wa(3, "Meera")
        idn.suggest(self.conn)
        pairs = {tuple(r) for r in self.conn.execute("SELECT a, b FROM merge_suggestion")}
        self.assertEqual(pairs, {(a, b)})


if __name__ == "__main__":
    unittest.main()

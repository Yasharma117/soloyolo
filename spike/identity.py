"""Identity: one card per person across sources.

Three layers, in order of trust (docs/IDENTITY.md has the reasoning):
  1. normalize: phones to E.164 (default India), WhatsApp JIDs and LIDs, emails, LinkedIn URLs, @handles
  2. auto-merge only on a hard key: the same normalized phone, email or profile on two people, from a
     structured source (a handle, a vCard, an export). Every merge is logged and can be undone.
  3. suggest on soft matches: names (transliteration, nicknames, "Bhaiya"/"Didi"/company suffixes) plus
     shared context. A name alone never merges anyone; you say yes or no.

    python -m spike.identity --db soloyolo.db import-vcf contacts.vcf
    python -m spike.identity --db soloyolo.db match        # auto-merge hard keys, then refresh suggestions
    python -m spike.identity --db soloyolo.db suggestions | accept A B | reject A B | undo LOG_ID | stats
"""
from __future__ import annotations

import argparse
import json
import quopri
import re
import sqlite3
import time
import unicodedata
import urllib.parse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# --- normalize --------------------------------------------------------------------------------
HARD_KINDS = ("phone", "email", "linkedin", "instagram", "x", "instagram_id", "x_id")
SINGLE_VALUED = ("linkedin", "birthday")  # two different values from structured sources = two people
ROLE_MAILBOXES = {"info", "support", "hello", "contact", "admin", "hr", "careers", "jobs", "sales", "team",
                  "noreply", "no-reply", "office", "accounts", "billing", "help", "enquiry", "enquiries"}
MAX_SHARE = 2  # a hard key on more people than this is shared (a family landline, a front desk): suggest only


def normalize_phone(raw: str, default_cc: str = "91", lid_map: dict[str, str] | None = None) -> str | None:
    """E.164 ('+919812345678') or None. Accepts WhatsApp JIDs ('9198...@s.whatsapp.net', with or without a
    device suffix), LIDs ('123@lid', only through lid_map: LID user -> phone user) and dialled forms
    ('+91 98123-45678', '098123 45678', '9812345678', '0044 20...')."""
    s = raw.strip()
    if "@" in s:
        user, _, server = s.partition("@")
        user = user.split(":")[0]
        if server == "lid":
            user = (lid_map or {}).get(user, "")
            if not user:
                return None
        elif server not in ("s.whatsapp.net", "c.us"):
            return None  # groups, broadcasts, newsletters, emails
        return "+" + user if user.isdigit() and 8 <= len(user) <= 15 else None
    s = re.sub(r"(?i)\s*(ext\.?|x|#)\s*\d+$", "", s)  # extensions don't identify a person
    plus = s.startswith("+")
    d = re.sub(r"\D", "", s)
    if plus:
        pass
    elif d.startswith("00"):
        d = d[2:]
    elif default_cc == "91" and len(d) == 11 and d[0] == "0":
        d = "91" + d[1:]                       # trunk 0: 098123 45678, 022 1234 5678
    elif default_cc == "91" and len(d) == 10 and d[0] in "6789":
        d = "91" + d                           # bare mobile
    elif default_cc == "91" and len(d) == 12 and d.startswith("91") and d[2] in "6789":
        pass                                   # 91 98123 45678, the plus left off
    elif default_cc == "1" and len(d) == 10:
        d = "1" + d
    elif len(d) == 10 or (len(d) == 11 and d[0] == "0"):
        d = default_cc + d.lstrip("0")
    else:
        return None                            # short codes, too ambiguous to guess a country
    return "+" + d if 8 <= len(d) <= 15 else None


def normalize_email(raw: str) -> str | None:
    s = raw.strip().lower()
    s = s[7:] if s.startswith("mailto:") else s
    m = re.fullmatch(r"([^@\s<>]+)@([a-z0-9.-]+\.[a-z]{2,})", s.strip("<> "))
    if not m:
        return None
    local, domain = m.groups()
    local = local.split("+")[0]                # plus-addressing reaches the same box
    if domain in ("gmail.com", "googlemail.com"):
        local, domain = local.replace(".", ""), "gmail.com"
    return f"{local}@{domain}" if local else None


def is_role_mailbox(email: str) -> bool:
    return email.split("@")[0] in ROLE_MAILBOXES


def normalize_linkedin(raw: str) -> str | None:
    """'https://in.linkedin.com/in/Some-One-12ab/?trk=x' -> 'linkedin.com/in/some-one-12ab'."""
    s = urllib.parse.unquote(raw.strip())
    s = re.sub(r"^(https?://)?([a-z]{2,3}\.|www\.|m\.)?linkedin\.com", "linkedin.com", s, flags=re.I)
    m = re.match(r"linkedin\.com/(in|pub)/([^?#]+)", s, re.I)
    if not m:
        return None
    path = m.group(2).strip("/").lower()
    if m.group(1).lower() == "in":
        path = path.split("/")[0]
    return f"linkedin.com/{m.group(1).lower()}/{path}" if path else None


def normalize_handle(network: str, raw: str) -> str | None:
    """Instagram / X: '@Some_One', 'instagram.com/some_one/', 'https://x.com/Some_One?s=20' -> 'some_one'."""
    s = raw.strip()
    hosts = {"instagram": r"instagram\.com", "x": r"(x|twitter)\.com"}[network]
    s = re.sub(rf"^(https?://)?(www\.|mobile\.)?{hosts}/", "", s, flags=re.I).split("?")[0].strip("/")
    s = s.lstrip("@").lower()
    ok = r"[a-z0-9._]{1,30}" if network == "instagram" else r"[a-z0-9_]{1,15}"
    return s if re.fullmatch(ok, s) else None


def normalize(key: str, value: str, default_cc: str = "91", lid_map: dict | None = None) -> str | None:
    if key == "phone":
        return normalize_phone(value, default_cc, lid_map)
    if key == "email":
        return normalize_email(value)
    if key == "linkedin":
        return normalize_linkedin(value)
    if key in ("instagram", "x"):
        return normalize_handle(key, value)
    if key in ("instagram_id", "x_id"):
        return value.strip() if value.strip().isdigit() else None
    if key == "company":
        return normalize_company(value) or None
    return re.sub(r"\s+", " ", value).strip() or None


def handle_keys(network: str, address: str, lid_map: dict | None = None) -> list[tuple[str, str]]:
    """The hard keys a messaging handle carries: a WhatsApp JID is a phone, an iMessage address a phone or email."""
    if network in ("linkedin", "instagram", "x"):
        v = normalize(network, address)
        return [(network, v)] if v else []
    if "@" in address and not re.search(r"@(s\.whatsapp\.net|c\.us|lid|g\.us)$", address):
        e = normalize_email(address)
        return [("email", e)] if e else []
    p = normalize_phone(address, lid_map=lid_map) if (network in ("whatsapp", "imessage", "sms", "phone")
                                                       or "@" not in address) else None
    return [("phone", p)] if p else []


COMPANY_NOISE = r"\b(pvt|private|ltd|limited|llp|inc|corp|corporation|co|company|technologies|technology|tech|labs|india|solutions|services|group)\b"


def normalize_company(raw: str) -> str:
    s = fold(raw)
    s = re.sub(COMPANY_NOISE, " ", s)
    return re.sub(r"[^a-z0-9]+", "", s)


# --- names ------------------------------------------------------------------------------------
RELATION = set("""bhaiya bhaiyya bhaiyaa bhaia bhaiyu bhai bhaijaan bhaiji bro bhau dada dadu didi di dii didu didii
sis behen bhabhi bhabi bhabhiji jiju jijaji jija papa pappa paa dad daddy mummy mumma mammi mom maa mama mami
mamaji mausi masi mausaji chacha chachi chachu chachaji bua phupha fufa tauji taiji nana nani dadi uncle unkle
aunty auntie aunti ji jee sir madam maam mam sahab saab sahib beta jaan dear babu""".split())
HONORIFIC = set("mr mrs ms miss dr shri sri smt kumari prof er adv ca".split())
NOISE = set("""new old latest ii iii work office ofc wrk personal home jio airtel vi vodafone bsnl idea whatsapp wa
number no num mobile mob landline alt alternate other second 2nd backup""".split())
ROLE = set("""driver plumber electrician maid cook landlord broker tailor doctor dentist lawyer advocate mechanic
cab taxi delivery gym trainer coach teacher tutor college school hostel pg society flat owner hr recruiter
manager colleague friend""".split())
CITY = set("""delhi ncr gurgaon gurugram noida mumbai bombay pune bangalore bengaluru blr hyderabad hyd chennai
madras kolkata calcutta ahmedabad jaipur lucknow chandigarh indore bhopal kochi cochin goa nagpur surat patna
ranchi dehradun kanpur varanasi mysore mysuru coimbatore vizag visakhapatnam bhubaneswar guwahati amritsar
ludhiana usa us uk london dubai singapore sf nyc canada toronto""".split())
NUMBER_CHANGE = {"new", "old", "latest", "ii", "iii", "2nd", "second", "alt", "alternate", "backup"}
NICKNAMES = {"mohd": "mohammad", "md": "mohammad", "mohammed": "mohammad", "muhammad": "mohammad",
             "bob": "robert", "bobby": "robert", "rob": "robert", "bill": "william", "will": "william",
             "mike": "michael", "jim": "james", "kate": "katherine", "liz": "elizabeth", "beth": "elizabeth",
             "dave": "david", "chris": "christopher", "tony": "anthony", "andy": "andrew", "nick": "nicholas"}

# Devanagari -> Latin, enough for saved names ("राहुल भैया"). Consonants carry an inherent 'a'.
_DEV_CONS = dict(zip("कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसहळ",
                     "k kh g gh n ch chh j jh n t th d dh n t th d dh n p ph b bh m y r l v sh sh s h l".split()))
_DEV_VOW = dict(zip("अआइईउऊऋएऐओऔ", "a aa i ii u uu ri e ai o au".split()))
_DEV_MATRA = dict(zip("ािीुूृेैोौ", "aa i ii u uu ri e ai o au".split()))


def devanagari_to_latin(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        ch = s[i]
        if ch in _DEV_CONS:
            nxt = s[i + 1] if i + 1 < len(s) else ""
            if nxt == "़":  # nukta: ज़ -> z, फ़ -> f
                ch, i, nxt = {"ज": "z", "फ": "f"}.get(ch, ch), i + 1, s[i + 2] if i + 2 < len(s) else ""
            base = _DEV_CONS.get(ch, ch)
            if nxt == "्":
                out.append(base); i += 2; continue
            if nxt in _DEV_MATRA:
                out.append(base + _DEV_MATRA[nxt]); i += 2; continue
            # schwa deletion: no inherent 'a' at the end of a word
            end = not nxt or not ("ऀ" <= nxt <= "ॿ") or nxt in "ंँः"
            out.append(base if end else base + "a")
        elif ch in _DEV_VOW:
            out.append(_DEV_VOW[ch])
        elif ch in "ंँ":
            out.append("n")
        elif ch in "ःऽ":
            pass
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def fold(s: str) -> str:
    """Lowercase ASCII: Devanagari transliterated, accents and emoji dropped."""
    if re.search("[ऀ-ॿ]", s):
        s = devanagari_to_latin(s)
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).encode("ascii", "ignore").decode().lower()


def phon(token: str) -> str:
    """A spelling-insensitive key for Latin-script Indian names: Lakshmi/Laxmi, Pooja/Puja, Vijay/Vijai."""
    t = NICKNAMES.get(token, token)
    t = re.sub(r"^h(?=[rl])", "", t)                  # Hrishikesh -> Rishikesh
    for a, b in (("ksh", "x"), ("ph", "f"), ("bh", "b"), ("dh", "d"), ("th", "t"), ("kh", "k"), ("gh", "g"),
                 ("chh", "c"), ("ch", "c"), ("sh", "s"), ("jh", "j"), ("ck", "k"), ("q", "k"), ("z", "j"),
                 ("w", "v"), ("ee", "i"), ("oo", "u"), ("ou", "u"), ("aa", "a"), ("ey", "e"), ("y", "i")):
        t = t.replace(a, b)
    t = re.sub(r"(.)\1+", r"\1", t)
    return re.sub(r"(?<=[aeiou])h$", "", t)


@dataclass
class Name:
    core: list[str]                                   # the name itself, folded, in order
    relation: list[str] = field(default_factory=list)  # bhaiya, didi, papa ...
    context: list[str] = field(default_factory=list)   # company / place / role words the user added
    number_change: bool = False                        # "new", "old", "2": a second number for someone


def parse_name(name: str, known_context: set[str] = frozenset()) -> Name:
    """Split a saved name into the name and what the user added around it.
    'Rahul Bhaiya (Acmepay)' -> core ['rahul'], relation ['bhaiya'], context ['acmepay']."""
    s = fold(name)
    ctx: list[str] = []
    for m in re.findall(r"[(\[{]([^)\]}]*)[)\]}]", s):
        ctx += re.findall(r"[a-z0-9]+", m)
    s = re.sub(r"[(\[{][^)\]}]*[)\]}]", " ", s)
    parts = re.split(r"\s-\s|\s*[@|/]\s*", s, maxsplit=1)  # 'Rahul - Acmepay', 'Rahul @ Pune' (not commas: 'Last, First')
    if len(parts) == 2:
        ctx += re.findall(r"[a-z0-9]+", parts[1])
        s = parts[0]
    out = Name(core=[])
    for tok in re.findall(r"[a-z0-9]+", s):
        if tok.isdigit():
            out.number_change = True
        elif tok in RELATION:
            out.relation.append(tok)
        elif tok in NOISE:
            out.number_change |= tok in NUMBER_CHANGE
        elif tok in HONORIFIC and len(s.split()) > 1:
            pass
        elif tok in ROLE or tok in CITY or tok in known_context:
            ctx.append(tok)
        else:
            out.core.append(tok)
    out.number_change |= bool(set(ctx) & NUMBER_CHANGE)
    out.context = [c for c in ctx if not c.isdigit() and c not in NOISE]
    return out


def jaro_winkler(a: str, b: str) -> float:
    if a == b:
        return 1.0
    la, lb = len(a), len(b)
    if not la or not lb:
        return 0.0
    win = max(la, lb) // 2 - 1
    ma, mb = [False] * la, [False] * lb
    m = 0
    for i, c in enumerate(a):
        for j in range(max(0, i - win), min(lb, i + win + 1)):
            if not mb[j] and b[j] == c:
                ma[i] = mb[j] = True
                m += 1
                break
    if not m:
        return 0.0
    bs = [b[j] for j in range(lb) if mb[j]]
    t = sum(c != bs[k] for k, c in enumerate(c for i, c in enumerate(a) if ma[i])) / 2
    jaro = (m / la + m / lb + (m - t) / m) / 3
    p = 0
    while p < min(4, la, lb) and a[p] == b[p]:
        p += 1
    return jaro + p * 0.1 * (1 - jaro)


def token_match(a: str, b: str) -> tuple[float, str]:
    pa, pb = phon(a), phon(b)
    if a == b:
        return 1.0, "same"
    if pa == pb:
        return 0.95, "spelling"                        # transliteration variant
    short, long_ = sorted((pa, pb), key=len)
    if len(short) >= 3 and len(long_) - len(short) >= 2 and long_.startswith(short):  # not Ankit / Ankita
        return 0.7, "nickname"                         # Abhi / Abhishek, Sid / Siddharth
    if len(short) == 1 and long_.startswith(short):
        return 0.5, "initial"
    if long_.startswith(short):
        return 0.0, ""                                 # Ankit / Ankita: one is the other plus a syllable
    if min(len(pa), len(pb)) >= 4 and (jaro_winkler(pa, pb) >= 0.92 or _shape(pa) == _shape(pb)):
        return 0.85, "spelling"                        # Verma / Varma; never Ankit / Ankita (a syllable more)
    return 0.0, ""


def _shape(p: str) -> str:
    """Consonants kept, each vowel run a slot: only *which* vowel differs between same-shape spellings."""
    return re.sub(r"[aeiou]+", "V", p)


def name_score(a: Name, b: Name, common: Counter) -> tuple[float, list[str], list[str], list[str]]:
    """(score, reasons, a's unmatched tokens, b's unmatched tokens). Unmatched tokens may still be context."""
    if not a.core or not b.core:
        return 0.0, [], a.core, b.core
    left, quals, kinds = list(b.core), [], set()
    unmatched_a = []
    for t in a.core:
        best = max(((token_match(t, u), u) for u in left), key=lambda x: x[0][0], default=((0.0, ""), None))
        if best[0][0] > 0:
            quals.append(best[0][0]); kinds.add(best[0][1]); left.remove(best[1])
        else:
            unmatched_a.append(t)
    if not quals or quals == [0.5]:
        return 0.0, [], unmatched_a, left
    n_a, n_b = len(a.core), len(b.core)
    q = sum(quals) / len(quals)
    if len(quals) >= 2 and not unmatched_a and not left:
        score = 0.6 + 0.3 * q                          # full names agree
    elif len(quals) >= 2:
        score = 0.45 + 0.2 * q                         # two tokens agree, one side has more
    elif n_a == 1 and n_b == 1:
        score = 0.5 * q                                # 'Rahul' and 'Rahul'
    elif min(n_a, n_b) == 1:
        score = 0.35 * q                               # 'Rahul' and 'Rahul Sharma'
    else:
        score = 0.0                                    # 'Rahul Sharma' and 'Rahul Verma' (unless context explains it)
    first = phon(a.core[0])
    if len(quals) == 1 and common[first] > 5:
        score *= 0.6                                   # a very common first name says little
    kinds.discard("same")
    reasons = ["name: " + ("same" if not kinds else "/".join(sorted(kinds)))]
    return score, reasons, unmatched_a, left


# --- the store side ---------------------------------------------------------------------------
def is_raw(name: str) -> bool:
    return bool(re.fullmatch(r"[\d+\-\s().]+|\S+@(s\.whatsapp\.net|lid|c\.us)|\S+@\S+", name.strip()))


def name_quality(name: str) -> int:
    if is_raw(name):
        return 0 if "@" not in name or re.search(r"@(s\.whatsapp\.net|lid|c\.us)$", name) else 1
    return 2 if len(parse_name(name).core) < 2 else 3


def add_attribute(conn: sqlite3.Connection, person_id: int, key: str, value: str, source: str,
                  ts: float | None = None) -> bool:
    v = normalize(key, value) if key in HARD_KINDS else re.sub(r"\s+", " ", value).strip()  # company stays readable
    if not v:
        return False
    return conn.execute("INSERT OR IGNORE INTO attribute(person_id, key, value, source, ts) VALUES (?, ?, ?, ?, ?)",
                        (person_id, key, v, source, ts or time.time())).rowcount == 1


def active_ids(conn) -> list[int]:
    return [r[0] for r in conn.execute(
        "SELECT id FROM person WHERE id NOT IN (SELECT gone FROM merge_log WHERE undone_at IS NULL) ORDER BY id")]


def hard_key_index(conn, lid_map: dict | None = None, me: set = frozenset()) -> dict[tuple[str, str], set[int]]:
    """(kind, value) -> people holding it, from handles and structured attributes. Keys said in a message
    (source 'message:<id>') are not hard: a line can name someone else's email."""
    idx: dict[tuple[str, str], set[int]] = defaultdict(set)
    active = set(active_ids(conn))
    for network, address, pid in conn.execute("SELECT network, address, person_id FROM handle"):
        for k in handle_keys(network, address, lid_map):
            idx[k].add(pid)
    for pid, key, value in conn.execute(
            f"SELECT person_id, key, value FROM attribute WHERE key IN ({','.join('?' * len(HARD_KINDS))})"
            " AND source NOT LIKE 'message:%'", HARD_KINDS):
        idx[(key, value)].add(pid)
    return {k: v & active for k, v in idx.items()
            if v & active and k not in me and not (k[0] == "email" and is_role_mailbox(k[1]))}


def _pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def _rejected(conn, a: int, b: int) -> bool:
    return conn.execute("SELECT 1 FROM merge_suggestion WHERE a = ? AND b = ? AND state = 'rejected'",
                        _pair(a, b)).fetchone() is not None


def _conflict(conn, a: int, b: int) -> str | None:
    """Two different single-valued facts (two LinkedIn profiles, two birthdays) from structured sources."""
    for key in SINGLE_VALUED:
        va = {r[0] for r in conn.execute("SELECT value FROM attribute WHERE person_id = ? AND key = ?"
                                         " AND source NOT LIKE 'message:%'", (a, key))}
        vb = {r[0] for r in conn.execute("SELECT value FROM attribute WHERE person_id = ? AND key = ?"
                                         " AND source NOT LIKE 'message:%'", (b, key))}
        if va and vb and not va & vb:
            return key
    return None


def _count(conn, pid: int) -> int:
    return conn.execute("SELECT COUNT(*) FROM message WHERE person_id = ?", (pid,)).fetchone()[0]


def merge(conn: sqlite3.Connection, kept: int, gone: int, reason: str, decided_by: str = "auto") -> int:
    """Move everything of `gone` onto `kept`. Returns the merge_log id. Undo with undo()."""
    if kept == gone:
        raise ValueError("cannot merge a person into itself")
    now = time.time()
    moved: dict = {}
    with conn:
        names = {"kept": conn.execute("SELECT display_name FROM person WHERE id = ?", (kept,)).fetchone()[0],
                 "gone": conn.execute("SELECT display_name FROM person WHERE id = ?", (gone,)).fetchone()[0]}
        moved["names"] = names
        moved["handles"] = [list(r) for r in conn.execute("SELECT network, address FROM handle WHERE person_id = ?", (gone,))]
        moved["messages"] = [r[0] for r in conn.execute("SELECT id FROM message WHERE person_id = ?", (gone,))]
        for t in ("handle", "message", "commitment", "resolution"):
            conn.execute(f"UPDATE {t} SET person_id = ? WHERE person_id = ?", (kept, gone))
        # Keyed tables: take the originals out, put repointed copies in, remember both for undo.
        moved["attributes"] = [list(r) for r in conn.execute(
            "SELECT key, value, source, ts FROM attribute WHERE person_id = ?", (gone,))]
        conn.execute("DELETE FROM attribute WHERE person_id = ?", (gone,))
        moved["attributes_added"] = [r[:3] for r in moved["attributes"] if conn.execute(
            "INSERT OR IGNORE INTO attribute(person_id, key, value, source, ts) VALUES (?, ?, ?, ?, ?)",
            (kept, *r)).rowcount]
        moved["topics"] = [r[0] for r in conn.execute("SELECT label FROM topic WHERE person_id = ?", (gone,))]
        conn.execute("DELETE FROM topic WHERE person_id = ?", (gone,))
        moved["topics_added"] = [t for t in moved["topics"] if conn.execute(
            "INSERT OR IGNORE INTO topic(person_id, label) VALUES (?, ?)", (kept, t)).rowcount]
        cols = ("id", "src", "dst", "kind", "evidence_message_id", "note", "extractor", "ts")
        edges = [dict(zip(cols, r)) for r in conn.execute(
            f"SELECT {', '.join(cols)} FROM edge WHERE src = ? OR dst = ?", (gone, gone)).fetchall()]
        moved["edges"], moved["edges_added"] = edges, []
        for e in edges:
            conn.execute("DELETE FROM edge WHERE id = ?", (e["id"],))
            src, dst = (kept if e["src"] == gone else e["src"]), (kept if e["dst"] == gone else e["dst"])
            if src != dst:  # an edge between the two halves of one person is a self-loop: dropped
                cur = conn.execute("INSERT OR IGNORE INTO edge(src, dst, kind, evidence_message_id, note, extractor, ts)"
                                   " VALUES (?, ?, ?, ?, ?, ?, ?)", (src, dst, e["kind"], e["evidence_message_id"],
                                                                     e["note"], e["extractor"], e["ts"]))
                if cur.rowcount:
                    moved["edges_added"].append(cur.lastrowid)
        sugg = [list(r) for r in conn.execute(
            "SELECT a, b, score, reasons, state, at, decided_at FROM merge_suggestion WHERE a = ? OR b = ?", (gone, gone))]
        moved["suggestions"], moved["suggestions_added"] = sugg, []
        conn.execute("DELETE FROM merge_suggestion WHERE a = ? OR b = ?", (gone, gone))
        for a, b, score, reasons, state, at, decided_at in sugg:
            other = b if a == gone else a
            if other == kept:
                continue
            p = _pair(kept, other)
            if conn.execute("INSERT OR IGNORE INTO merge_suggestion(a, b, score, reasons, state, at, decided_at)"
                            " VALUES (?, ?, ?, ?, ?, ?, ?)", (*p, score, reasons, state, at, decided_at)).rowcount:
                moved["suggestions_added"].append(list(p))
            elif state == "rejected":  # a "no" outranks an open question
                conn.execute("UPDATE merge_suggestion SET state = 'rejected' WHERE a = ? AND b = ?", p)
        if name_quality(names["gone"]) > name_quality(names["kept"]):
            conn.execute("UPDATE person SET display_name = ? WHERE id = ?", (names["gone"], kept))
        lid = conn.execute("INSERT INTO merge_log(kept, gone, reason, decided_by, moved, at) VALUES (?, ?, ?, ?, ?, ?)",
                           (kept, gone, reason, decided_by, json.dumps(moved), now)).lastrowid
        loser = names["kept"] if name_quality(names["gone"]) > name_quality(names["kept"]) else names["gone"]
        if not is_raw(loser) and loser != conn.execute("SELECT display_name FROM person WHERE id = ?", (kept,)).fetchone()[0]:
            conn.execute("INSERT OR IGNORE INTO attribute(person_id, key, value, source, ts) VALUES (?, 'alias', ?, ?, ?)",
                         (kept, loser, f"merge:{lid}", now))
        p = _pair(kept, gone)
        conn.execute("INSERT INTO merge_suggestion(a, b, score, reasons, state, at, decided_at)"
                     " VALUES (?, ?, 1.0, ?, 'merged', ?, ?) ON CONFLICT(a, b) DO UPDATE SET state = 'merged',"
                     " decided_at = excluded.decided_at", (*p, json.dumps([reason]), now, now))
    return lid


def undo(conn: sqlite3.Connection, log_id: int) -> None:
    """Split a merge back apart. Exact when undone newest first; a later merge that absorbed `kept` must
    be undone before this one. Afterwards the pair is marked 'rejected' so auto-merge won't redo it."""
    row = conn.execute("SELECT kept, gone, moved, undone_at FROM merge_log WHERE id = ?", (log_id,)).fetchone()
    if not row or row[3]:
        raise ValueError(f"no active merge {log_id}")
    kept, gone, moved = row[0], row[1], json.loads(row[2])
    if conn.execute("SELECT 1 FROM merge_log WHERE gone = ? AND id > ? AND undone_at IS NULL", (kept, log_id)).fetchone():
        raise ValueError("a later merge absorbed this person: undo that one first")
    with conn:
        for network, address in moved["handles"]:
            conn.execute("UPDATE handle SET person_id = ? WHERE network = ? AND address = ?", (gone, network, address))
        ids = moved["messages"]
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            q = ",".join("?" * len(chunk))
            conn.execute(f"UPDATE message SET person_id = ? WHERE id IN ({q})", (gone, *chunk))
            # by source message, not row id: survives a re-extraction of the merged thread
            conn.execute(f"UPDATE commitment SET person_id = ? WHERE source_message_id IN ({q})", (gone, *chunk))
            conn.execute(f"UPDATE resolution SET person_id = ? WHERE source_message_id IN ({q})", (gone, *chunk))
        for k, v, s in moved["attributes_added"]:
            conn.execute("DELETE FROM attribute WHERE person_id = ? AND key = ? AND value = ? AND source = ?", (kept, k, v, s))
        conn.executemany("INSERT OR IGNORE INTO attribute(person_id, key, value, source, ts) VALUES (?, ?, ?, ?, ?)",
                         [(gone, *r) for r in moved["attributes"]])
        conn.execute("DELETE FROM attribute WHERE person_id = ? AND source = ?", (kept, f"merge:{log_id}"))
        for t in moved["topics_added"]:
            conn.execute("DELETE FROM topic WHERE person_id = ? AND label = ?", (kept, t))
        conn.executemany("INSERT OR IGNORE INTO topic(person_id, label) VALUES (?, ?)", [(gone, t) for t in moved["topics"]])
        for eid in moved["edges_added"]:
            conn.execute("DELETE FROM edge WHERE id = ?", (eid,))
        conn.executemany("INSERT OR IGNORE INTO edge(id, src, dst, kind, evidence_message_id, note, extractor, ts)"
                         " VALUES (:id, :src, :dst, :kind, :evidence_message_id, :note, :extractor, :ts)", moved["edges"])
        for a, b in moved["suggestions_added"]:
            conn.execute("DELETE FROM merge_suggestion WHERE a = ? AND b = ?", (a, b))
        conn.executemany("INSERT OR IGNORE INTO merge_suggestion(a, b, score, reasons, state, at, decided_at)"
                         " VALUES (?, ?, ?, ?, ?, ?, ?)", moved["suggestions"])
        conn.execute("UPDATE person SET display_name = ? WHERE id = ?", (moved["names"]["kept"], kept))
        conn.execute("UPDATE merge_log SET undone_at = ? WHERE id = ?", (time.time(), log_id))
        conn.execute("UPDATE merge_suggestion SET state = 'rejected', decided_at = ? WHERE a = ? AND b = ?",
                     (time.time(), *_pair(kept, gone)))


def auto_merge(conn: sqlite3.Connection, lid_map: dict | None = None, me: set = frozenset()) -> dict:
    """Merge people who share a hard key. Shared keys (on more than MAX_SHARE people), conflicting
    profiles and pairs you split apart become suggestions or are left alone, never merged."""
    stats = Counter()
    idx = hard_key_index(conn, lid_map, me)
    root: dict[int, int] = {}

    def find(p: int) -> int:
        while p in root:
            p = root[p]
        return p

    held: list[tuple[str, str, int, int]] = []
    for (kind, value), pids in sorted(idx.items()):
        if len(pids) < 2:
            continue
        if len(pids) > MAX_SHARE:
            stats["shared_key"] += 1
            ps = sorted(pids)
            held += [(kind, value, a, b) for i, a in enumerate(ps) for b in ps[i + 1:]]
            continue
        a, b = sorted(pids)
        ra, rb = find(a), find(b)
        if ra == rb:
            continue
        if _rejected(conn, ra, rb):
            stats["skipped_rejected"] += 1
            continue
        if _conflict(conn, ra, rb):
            stats["skipped_conflict"] += 1
            held.append((kind, value, ra, rb))
            continue
        kept, gone = sorted((ra, rb), key=lambda p: (-_count(conn, p), -name_quality(
            conn.execute("SELECT display_name FROM person WHERE id = ?", (p,)).fetchone()[0]), p))
        merge(conn, kept, gone, kind, "auto")
        root[gone] = kept
        stats["merged"] += 1
        stats[f"merged_by_{kind}"] += 1
    now = time.time()
    with conn:
        for kind, value, a, b in held:
            a, b = find(a), find(b)
            if a != b:
                conn.execute("INSERT INTO merge_suggestion(a, b, score, reasons, state, at) VALUES (?, ?, 0.7, ?, 'open', ?)"
                             " ON CONFLICT(a, b) DO NOTHING", (*_pair(a, b), json.dumps([f"same {kind}, but shared or conflicting"]), now))
    return dict(stats)


def _profiles(conn, ids: list[int]) -> dict[int, dict]:
    companies, cities, soft, hard = defaultdict(set), defaultdict(set), defaultdict(set), defaultdict(set)
    sources, names = defaultdict(set), defaultdict(list)
    for pid, key, value, source in conn.execute("SELECT person_id, key, value, source FROM attribute"):
        if key == "company":
            companies[pid].add(normalize_company(value))
        elif key == "city":
            cities[pid].add(fold(value).strip())
        elif key in ("name", "alias"):
            names[pid].append(value)
        if key in HARD_KINDS:
            (soft if source.startswith("message:") else hard)[pid].add((key, value))
        sources[pid].add(source.split(":")[0])
    for network, address, pid in conn.execute("SELECT network, address, person_id FROM handle"):
        sources[pid].add(network)
        hard[pid].update(handle_keys(network, address))
    known = {c for s in companies.values() for c in s if c}
    nbrs = defaultdict(set)
    for s, d in conn.execute("SELECT src, dst FROM edge"):
        nbrs[s].add(d); nbrs[d].add(s)
    out = {}
    for pid, dn in conn.execute("SELECT id, display_name FROM person"):
        if pid not in ids:
            continue
        variants = [n for n in [dn, *names[pid]] if not is_raw(n)]
        out[pid] = dict(names=[parse_name(n, known) for n in variants], company=companies[pid] - {""},
                        city=cities[pid], soft=soft[pid], hard=hard[pid], sources=sources[pid], nbrs=nbrs[pid])
    return out


def score_pair(pa: dict, pb: dict, common: Counter) -> tuple[float, list[str]]:
    """How likely two cards are one person, and why. 0 when nothing but chance links them."""
    key_hit = (pa["soft"] & pb["hard"]) | (pb["soft"] & pa["hard"]) | (pa["soft"] & pb["soft"])
    best, why = 0.0, []
    for na in pa["names"]:
        for nb in pb["names"]:
            s, reasons, ua, ub = name_score(na, nb, common)
            ctx_a = set(na.context) | set(ua) | set(na.relation)
            ctx_b = set(nb.context) | set(ub) | set(nb.relation)
            # a token the user added ("Rahul Acmepay") that is the other card's company or city
            ctx_hit = ({normalize_company(t) for t in ctx_a} & pb["company"]) | (ctx_a & pb["city"]) | \
                      ({normalize_company(t) for t in ctx_b} & pa["company"]) | (ctx_b & pa["city"]) | \
                      (set(na.context) & set(nb.context))
            if s == 0 and ua and ub and len(na.core) > 1 and len(nb.core) > 1 and ctx_hit and \
                    (set(ua) <= ctx_hit or set(ub) <= ctx_hit):
                s, reasons = 0.35, ["name: same first name"]  # the extra token was context, not a surname
            if not s:
                continue
            if ctx_hit:
                s += 0.25; reasons = reasons + ["context: " + "/".join(sorted(ctx_hit))[:40]]
            if na.number_change or nb.number_change:
                s += 0.2; reasons = reasons + ["saved as a new or second number"]
            if s > best:
                best, why = s, reasons
    if best and pa["company"] & pb["company"]:
        best += 0.25; why = why + ["same company"]
    if best and pa["city"] & pb["city"]:
        best += 0.1; why = why + ["same city"]
    if best and pa["nbrs"] & pb["nbrs"]:
        best += 0.15; why = why + ["know the same people"]
    if key_hit:
        best = max(best, 0.5) + 0.3; why = why + [f"{sorted(key_hit)[0][0]} mentioned in a message matches"]
    phones_a = {v for k, v in pa["hard"] if k == "phone"}
    phones_b = {v for k, v in pb["hard"] if k == "phone"}
    if best and phones_a and phones_b and not phones_a & phones_b:
        best *= 0.8  # two numbers: possible (a new SIM), but the default is two people
    return min(best, 0.99), why


def suggest(conn: sqlite3.Connection, threshold: float = 0.5) -> dict:
    """Score candidate pairs and keep the review queue current. Your yes/no rows are never touched."""
    ids = active_ids(conn)
    prof = _profiles(conn, ids)
    common = Counter(phon(n.core[0]) for p in prof.values() for n in p["names"][:1] if n.core)
    blocks = defaultdict(set)
    for pid, p in prof.items():
        for n in p["names"]:
            for t in n.core:
                blocks[phon(t)[:3]].add(pid)
        for k in p["soft"] | p["hard"]:
            blocks[k].add(pid)
    pairs = set()
    for members in blocks.values():
        if len(members) > 300:
            continue  # a block this big is a common prefix, not evidence
        ms = sorted(members)
        pairs.update((a, b) for i, a in enumerate(ms) for b in ms[i + 1:])
    decided = {(a, b) for a, b in conn.execute("SELECT a, b FROM merge_suggestion WHERE state != 'open'")}
    stats, now, found = Counter(compared=len(pairs)), time.time(), set()
    with conn:
        for a, b in pairs:
            if (a, b) in decided or _conflict(conn, a, b):
                continue
            s, why = score_pair(prof[a], prof[b], common)
            if s < threshold:
                continue
            found.add((a, b))
            stats["suggested"] += 1
            for r in why:
                stats["reason:" + r.split(":")[0]] += 1
            conn.execute("INSERT INTO merge_suggestion(a, b, score, reasons, state, at) VALUES (?, ?, ?, ?, 'open', ?)"
                         " ON CONFLICT(a, b) DO UPDATE SET score = excluded.score, reasons = excluded.reasons,"
                         " at = excluded.at WHERE state = 'open'", (a, b, round(s, 3), json.dumps(why), now))
        for a, b, reasons in conn.execute("SELECT a, b, reasons FROM merge_suggestion WHERE state = 'open'").fetchall():
            held = json.loads(reasons)[:1] and json.loads(reasons)[0].startswith("same ")  # from auto_merge: keep
            if (a, b) not in found and not held:
                conn.execute("DELETE FROM merge_suggestion WHERE a = ? AND b = ?", (a, b))  # no longer looks alike
    return dict(stats)


def accept(conn, a: int, b: int) -> int:
    kept, gone = sorted((a, b), key=lambda p: (-_count(conn, p), p))
    return merge(conn, kept, gone, "you", "you")


def reject(conn, a: int, b: int) -> None:
    with conn:
        conn.execute("INSERT INTO merge_suggestion(a, b, score, reasons, state, at, decided_at)"
                     " VALUES (?, ?, 0, '[]', 'rejected', ?, ?) ON CONFLICT(a, b) DO UPDATE SET state = 'rejected',"
                     " decided_at = excluded.decided_at", (*_pair(a, b), time.time(), time.time()))


# --- vCard ------------------------------------------------------------------------------------
@dataclass
class Card:
    name: str = ""
    uid: str = ""
    attrs: list[tuple[str, str]] = field(default_factory=list)  # (key, raw value)


def _unescape(v: str) -> str:
    return re.sub(r"\\([,;:\\nN])", lambda m: "\n" if m.group(1) in "nN" else m.group(1), v)


def parse_vcf(text: str) -> list[Card]:
    """vCard 2.1 / 3.0 / 4.0, as Google Contacts, Apple Contacts and Android export them."""
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]                              # folded line
        elif lines and lines[-1].endswith("=") and "QUOTED-PRINTABLE" in lines[-1].upper().split(":")[0]:
            lines[-1] = lines[-1][:-1] + raw                  # quoted-printable soft break
        else:
            lines.append(raw)
    cards, cur = [], None
    for line in lines:
        if ":" not in line:
            continue
        head, value = line.split(":", 1)
        parts = head.split(";")
        prop = parts[0].split(".")[-1].upper()                # 'item1.EMAIL' -> 'EMAIL'
        params = ";".join(parts[1:]).upper()
        if "QUOTED-PRINTABLE" in params:
            charset = re.search(r"CHARSET=([\w-]+)", params)
            value = quopri.decodestring(value.encode()).decode(charset.group(1) if charset else "utf-8", "replace")
        if prop == "BEGIN" and value.strip().upper() == "VCARD":
            cur = Card()
        elif prop == "END" and cur is not None:
            if not cur.name:
                cur.name = next((v for k, v in cur.attrs if k == "_n"), "")
            cur.attrs = [(k, v) for k, v in cur.attrs if k != "_n"]
            cards.append(cur); cur = None
        elif cur is None:
            continue
        elif prop == "FN":
            cur.name = _unescape(value).strip()
        elif prop == "N":
            f = [_unescape(x).strip() for x in re.split(r"(?<!\\);", value)] + [""] * 5
            cur.attrs.append(("_n", " ".join(x for x in (f[3], f[1], f[2], f[0], f[4]) if x)))
        elif prop == "UID":
            cur.uid = value.strip()
        elif prop == "TEL":
            cur.attrs.append(("phone", value.removeprefix("tel:")))
        elif prop == "EMAIL":
            cur.attrs.append(("email", value))
        elif prop == "ORG":
            org = _unescape(re.split(r"(?<!\\);", value)[0]).strip()
            if org:
                cur.attrs.append(("company", org))
        elif prop == "TITLE" and value.strip():
            cur.attrs.append(("position", _unescape(value).strip()))
        elif prop == "BDAY" and value.strip():
            cur.attrs.append(("birthday", value.strip()))
        elif prop == "NICKNAME" and value.strip():
            cur.attrs.append(("alias", _unescape(value).strip()))
        elif prop == "ADR":
            f = re.split(r"(?<!\\);", value) + [""] * 7
            if f[3].strip():
                cur.attrs.append(("city", _unescape(f[3]).strip()))
        elif prop in ("URL", "X-SOCIALPROFILE"):
            v = _unescape(value).strip()
            for key in ("linkedin", "instagram", "x"):
                if normalize(key, v) and (key in v.lower() or (key == "x" and "twitter" in v.lower())
                                          or key.upper() in params):
                    cur.attrs.append((key, v)); break
    return cards


def import_vcf(conn: sqlite3.Connection, path: Path | str, source: str = "vcard", lid_map: dict | None = None) -> dict:
    """Attach each card to the person who already has one of its phones or emails, else make a new card.
    The vCard is the bridge: its phone matches a WhatsApp chat, its email a Gmail thread, so a later
    auto_merge() joins them. A raw-id name (an unsaved number) takes the card's name."""
    cards = parse_vcf(Path(path).read_text(encoding="utf-8", errors="replace"))
    idx = hard_key_index(conn, lid_map)
    stats, now = Counter(cards=len(cards)), time.time()
    with conn:
        for c in cards:
            keys = [(k, normalize(k, v)) for k, v in c.attrs if k in HARD_KINDS]
            keys = [k for k in keys if k[1]]
            hits = sorted({p for k in keys for p in idx.get(k, ())})
            if not hits and c.uid:
                hits = [r[0] for r in conn.execute("SELECT person_id FROM attribute WHERE key = 'vcard_uid'"
                                                   " AND value = ? AND source = ?", (c.uid, source))]
            if not hits and not keys and c.name:
                hits = [r[0] for r in conn.execute("SELECT person_id FROM attribute WHERE key = 'name'"
                                                   " AND value = ? AND source = ?", (c.name, source))]
            if hits:
                pid = hits[0]
                stats["matched"] += 1
                dn = conn.execute("SELECT display_name FROM person WHERE id = ?", (pid,)).fetchone()[0]
                if c.name and is_raw(dn):
                    conn.execute("UPDATE person SET display_name = ? WHERE id = ?", (c.name, pid))
                    stats["named_raw"] += 1
            elif c.name or keys:
                pid = conn.execute("INSERT INTO person(display_name) VALUES (?)", (c.name or keys[0][1],)).lastrowid
                stats["created"] += 1
            else:
                continue
            if c.name:
                add_attribute(conn, pid, "name", c.name, source, now)
            if c.uid:
                add_attribute(conn, pid, "vcard_uid", c.uid, source, now)
            for k, v in c.attrs:
                stats["attributes"] += add_attribute(conn, pid, k, v, source, now)
            for k in keys:
                idx.setdefault(k, set()).add(pid)
    return dict(stats)


def match(conn, lid_map: dict | None = None, me: set = frozenset()) -> dict:
    return {"auto": auto_merge(conn, lid_map, me), "suggest": suggest(conn)}


def main(argv: list[str] | None = None) -> None:
    from spike.store import Store
    ap = argparse.ArgumentParser(prog="python -m spike.identity")
    ap.add_argument("--db", default="soloyolo.db")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("import-vcf").add_argument("file")
    sub.add_parser("match")
    sub.add_parser("suggestions")
    for c in ("accept", "reject"):
        p = sub.add_parser(c); p.add_argument("a", type=int); p.add_argument("b", type=int)
    sub.add_parser("undo").add_argument("log_id", type=int)
    sub.add_parser("stats")
    args = ap.parse_args(argv)
    conn = Store(args.db).conn
    if args.cmd == "import-vcf":
        print(import_vcf(conn, args.file))
    elif args.cmd == "match":
        print(json.dumps(match(conn), indent=1))
    elif args.cmd == "suggestions":
        for r in conn.execute("SELECT s.a, pa.display_name, s.b, pb.display_name, s.score, s.reasons FROM merge_suggestion s"
                              " JOIN person pa ON pa.id = s.a JOIN person pb ON pb.id = s.b WHERE s.state = 'open'"
                              " ORDER BY s.score DESC"):
            print(f"{r[4]:.2f}  #{r[0]} {r[1]}  <->  #{r[2]} {r[3]}   {', '.join(json.loads(r[5]))}")
    elif args.cmd == "accept":
        print("merge", accept(conn, args.a, args.b))
    elif args.cmd == "reject":
        reject(conn, args.a, args.b)
    elif args.cmd == "undo":
        undo(conn, args.log_id)
    elif args.cmd == "stats":
        print(dict(people=len(active_ids(conn)),
                   merges=conn.execute("SELECT COUNT(*) FROM merge_log WHERE undone_at IS NULL").fetchone()[0],
                   open_suggestions=conn.execute("SELECT COUNT(*) FROM merge_suggestion WHERE state='open'").fetchone()[0]))


if __name__ == "__main__":
    main()

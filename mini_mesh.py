"""mini_mesh: Mesh's iMessage integration in ~50 lines.

Reads ~/Library/Messages/chat.db read-only (needs Full Disk Access for your terminal),
uses metadata only (who, when, which direction), never message text, and ranks
people by a recency-weighted interaction score. Run: python3 mini_mesh.py [N]
"""
import math, os, sqlite3, sys, time

APPLE_EPOCH = 978307200  # 2001-01-01; chat.db `date` is ns since then
HALF_LIFE_DAYS = 30      # ponytail: fixed decay, tune per taste

QUERY = """
SELECT h.id, m.date, m.is_from_me
FROM message m JOIN handle h ON h.ROWID = m.handle_id
WHERE m.associated_message_type = 0          -- skip tapbacks
  AND h.id NOT GLOB '[0-9][0-9][0-9][0-9][0-9]' -- skip 5-digit shortcodes
  AND h.id NOT GLOB '[0-9][0-9][0-9][0-9][0-9][0-9]'
"""


def rank(conn, now=None, limit=20):
    now = now or time.time()
    people = {}
    for handle, date, from_me in conn.execute(QUERY):
        ts = APPLE_EPOCH + date / 1e9
        p = people.setdefault(handle, {"handle": handle, "score": 0.0, "sent": 0, "recv": 0, "last": 0})
        p["score"] += math.exp(-math.log(2) * (now - ts) / 86400 / HALF_LIFE_DAYS)
        p["sent" if from_me else "recv"] += 1
        p["last"] = max(p["last"], ts)
    # two-way conversations matter more than inbound blasts (Mesh's "non-people" filter, roughly)
    for p in people.values():
        if not (p["sent"] and p["recv"]):
            p["score"] *= 0.2
    return sorted(people.values(), key=lambda p: -p["score"])[:limit]


def demo():
    db = sqlite3.connect(":memory:")
    db.executescript("""CREATE TABLE handle(ROWID INTEGER PRIMARY KEY, id TEXT);
        CREATE TABLE message(handle_id INT, date INT, is_from_me INT, associated_message_type INT);
        INSERT INTO handle VALUES (1,'+15551112222'),(2,'+15553334444'),(3,'12345');""")
    now = APPLE_EPOCH + 1e6
    ns = lambda days_ago: int((now - APPLE_EPOCH - days_ago * 86400) * 1e9)
    rows = [(1, ns(1), 1, 0), (1, ns(1), 0, 0), (1, ns(2), 0, 2000),  # friend: recent two-way + a tapback
            (2, ns(200), 1, 0), (2, ns(200), 0, 0),                    # old friend
            (3, ns(0), 0, 0)]                                          # shortcode
    db.executemany("INSERT INTO message VALUES (?,?,?,?)", rows)
    r = rank(db, now=now)
    assert [p["handle"] for p in r] == ["+15551112222", "+15553334444"], r
    assert r[0]["recv"] == 1  # tapback excluded
    print("demo ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--demo"]:
        sys.exit(demo())
    path = os.path.expanduser("~/Library/Messages/chat.db")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    for p in rank(conn, limit=int(sys.argv[1]) if sys.argv[1:] else 20):
        print(f"{p['score']:7.2f}  {p['handle']:<32} ↑{p['sent']:<5} ↓{p['recv']:<5} last {time.strftime('%Y-%m-%d', time.localtime(p['last']))}")

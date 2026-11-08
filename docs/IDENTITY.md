# Identity: one card per person

Mesh's weakest point is duplicate contacts that you merge by hand (BUILD-WITHOUT-BEEPER.md §"Where Mesh
falls short"). Its AI has a `merge_contacts` tool, but the matching is mostly yours. soloyolo reads message
text, so it can do two things Mesh can't: tell which number is the same person, and learn *who knows whom*
from what was said. Code: `spike/identity.py`. Tests: `spike/test_identity.py`.

## Schema (in `connectord/internal/store/core.sql`)

- **attribute(person_id, key, value, source, ts)**: one fact from one source. The same email from a vCard
  and from LinkedIn is two rows, so a card can say where each fact came from, and deleting a source
  removes its facts. Hard keys (`phone`, `email`, `linkedin`, `instagram`, `x`, `*_id`) are stored
  *normalized*, so matching is an index lookup on `(key, value)`. `company` keeps the readable form and is
  compared through `normalize_company`.
- **merge_suggestion(a, b, score, reasons, state, at, decided_at)**: one row per unordered pair (`a < b`,
  a CHECK). `reasons` is a JSON list of short strings shown as-is ("name: spelling", "context: acmepay").
  `state` is `open | merged | rejected`. Rows are never deleted when you decide, so a "no" is remembered
  and the matcher won't ask again. When either person is merged later, the row moves to the survivor and
  a "no" outranks an open question. There's no id column because the pair is the identity.
- **merge_log(id, kept, gone, reason, decided_by, moved, at, undone_at)**: every merge, automatic or yours.
  `moved` is JSON with the *natural keys* of what moved: handle (network, address), message ids, the
  absorbed attribute, topic and edge rows, and both display names. The absorbed `person` row stays,
  emptied, so ids are stable and undo can refill it. `reason` is the key's *kind* (`email`), never its
  value. "Active people" means persons that aren't `gone` in a log row that hasn't been undone. This
  avoids an ALTER on `person`, which both Go and Python would need to migrate.
- **edge(id, src, dst, kind, evidence_message_id, note, extractor, ts)**: person to person. `kind` is free
  text with a small vocabulary (`intro`, `knows`, `colleague`, `family`, `referred`, `reports_to`), like
  `attribute.key`. `evidence_message_id` is the line that says so. It's NULL only for edges you add by hand,
  so every machine-made edge can be shown with its quote. `extractor` follows `commitment.extractor`.
  A unique index on `(src, dst, kind, IFNULL(evidence_message_id, 0))` lets a re-run add nothing.
  `CHECK (src <> dst)`: an edge between two halves of one person is dropped on merge, and undo restores it.

You (the owner) aren't a person row: edges are between the people you talk to, and "you" is implied.

## Normalizing

| key | rule |
|---|---|
| phone | E.164. Default region India: `98xxxxxxxx`, `098…`, `91 98…` and `022…` (trunk 0) get `+91`. `00` means international. WhatsApp JIDs `<digits>[:device]@s.whatsapp.net` are already international. A `…@lid` maps to a phone only through the device's LID map. Groups, broadcasts and short codes give no phone. |
| email | lowercased, `mailto:` and `+tag` stripped, Gmail dots removed, `googlemail.com` becomes `gmail.com` |
| linkedin | `linkedin.com/in/<slug>`, ignoring country subdomain, scheme, query, case, percent-encoding |
| instagram / x | the bare lowercased handle from `@h` or a profile URL (x.com or twitter.com) |
| company | folded, with `pvt ltd`, `technologies`, `india` and so on removed, alphanumerics only |

## Merging: automatic on hard keys only

Two active people auto-merge when they share a normalized phone, email or profile, **from a structured
source**: a handle, a vCard, an export. These never count as hard keys:
- an attribute whose source is `message:<id>` (a chat line can name *someone else's* email). It raises a
  suggestion instead;
- a role mailbox (`hr@`, `info@`, `careers@` …);
- a key on more than 2 people, such as a family landline or a front desk. Every pair becomes a suggestion;
- a pair you split with undo or rejected;
- a pair whose single-valued facts conflict (two different LinkedIn URLs or birthdays from structured
  sources). That pair becomes a suggestion.

**Survivor**: the person with more messages, then the better name, then the lower id. **Name**: a saved name
beats a raw id or number, a full name beats a single word, and on a tie the survivor's own name (what you
call them) stays. The loser's name becomes an `alias` attribute (source `merge:<log id>`), so search finds it.
**Moved**: handles, messages, commitments, resolutions, attributes, topics, edges and suggestions.
**Undo** puts messages back by id, and commitments and resolutions by *source message*, so undo still works
after the merged thread was re-extracted. Undo is exact in reverse order. It refuses while a later merge
holds the survivor. Afterwards the pair is marked `rejected`, so auto-merge doesn't redo it.

## Suggesting: names plus context, never names alone

A saved name is parsed into **core** tokens and what you added around them. This includes relationship words
(`bhaiya didi papa mummy mama chacha bua ji sir …`), honorifics (`Dr`, `Shri`), roles (`driver landlord
gym`), cities (`Pune`, `Blr`), parenthesised or `-`/`@`/`|` tails ("Kiran (Acmepay)", "Kiran @ Pune")
and second-number markers (`new old 2 alt jio`). A comma isn't a separator ("Last, First"). Devanagari
is transliterated first (schwa deletion included).

Tokens match on a phonetic key built for Indian romanization. `ksh→x`, aspirates merge (`bh→b`, `th→t`), `w→v`,
`ee→i`, `oo→u`, `aa→a`, `y→i`, and doubled letters collapse. So Lakshmi/Laxmi, Pooja/Puja and Vijay/Vijai
are the same. Same-shape vowel swaps (Verma/Varma) count as spelling variants. Other levels are nickname (a
prefix at least 2 letters shorter: Abhi/Abhishek, Rishi/Hrishikesh, plus a small table: Mohd/Muhammad, Bob/Robert) and
initial ("Kiran R"). One name being the other plus a syllable (Ankit/Ankita) is **not** a match.

Score: two full names that agree score 0.6–0.9. "Kiran" and "Kiran" score 0.5, and "Kiran" and "Kiran Rao"
score 0.35. These shrink when that first name is common in your store. Different surnames score 0, unless
the extra token is context. Context adds: a suffix token equal to the other card's company or city (+0.25,
"Kiran Acmepay" vs a LinkedIn "Kiran Rao @ Acmepay"), same company (+0.25), same city (+0.1), a
new-number marker (+0.2), a shared neighbour in `edge` (+0.15), and a key said in a chat that matches the
other card's hard key (+0.3). If both cards have phones and they differ, the score is multiplied by 0.8.
Suggest at ≥ 0.5. Candidates come from blocking on 3-letter phonetic prefixes, so it's not all pairs.

## vCard import

`parse_vcf` reads 2.1, 3.0 and 4.0, the formats Google, Apple and Android export. It handles folded lines,
quoted-printable (Android), `item1.EMAIL` groups, `X-SOCIALPROFILE`, `N` when `FN` is missing, and `ADR`
for the city. Each card attaches to the person who already holds one of its phones or emails, else a
new card. This is the bridge: a card's phone matches a WhatsApp chat and its email a Gmail thread, and
`auto_merge` joins them. A raw-id name takes the card's name. A re-import adds nothing.

## Live data (backup copy of your WhatsApp store, counts only)

1421 people (98 with messages, 27 of those shown as raw ids). 1421 handles: 1347 normalize to +91 and 74
to another country. There is 1 LID handle, resolved through the device LID map (3406 entries).
Auto-merges: **0**. A WhatsApp-only store has no second source yet, and the Go adapter already stores a LID
under its phone. Among 1370 saved names, 33 have a relationship word, 24 a company, place or role
suffix, 36 a new or second-number marker, and 39 are *only* such words ("Papa"). Pairs compared: 8388.
Suggestions: **37** (9 at ≥ 0.8, 10 at 0.65–0.8, 18 at 0.5–0.65). 22 match on the same name, 14 add a
new-number marker. 35 pair contacts with no messages, 2 pair a messaged person with a silent duplicate.
The raw-id people get no names from WhatsApp's own contact store (0 of 27). They need a vCard import.
Precision is not hand-checked. The review list stays outside the repo.

## From conversations: edges and attributes (design only, no model calls yet)

This runs inside the existing extraction pass (same disclosure rule: log before text leaves). It adds one
field to the extractor's JSON:

```json
{"people": [{"name": "Kiran Rao", "said_in": 1234,
             "facts": [{"key": "company", "value": "Acmepay"}],
             "edges": [{"from": "them", "kind": "intro", "note": "forwarding your profile"}]}]}
```
Prompt sketch: *"List people this thread mentions who are not you or the other person. For each, quote the
message id that names them, and give only facts stated in the text: company, position, city, email, phone,
relation to the other person. `from: "them"` means the other person in this chat. Kinds: intro (they will
connect you), referred, colleague, family (note the relation), knows. Do not guess surnames or companies.
Skip people mentioned only in passing."*

Writes: each mention resolves to an existing person when a hard key matches, or when the name scores ≥ 0.8
*and* the company or a neighbour agrees. Otherwise it creates a **mention-only person** (no handle,
no messages, hidden from the lists). Facts become `attribute` rows with `source = message:<id>`, which are
soft by rule. Edges are written with `evidence_message_id`. A mention-only person then meets a later
LinkedIn import through ordinary suggestions ("name: same, same company, know the same people").

## How it shows

- **Card**: facts grouped by key, each with its source chip (WhatsApp, vCard, LinkedIn, "said on 3 Mar"),
  and a "people" row of edges ("Asha → introducing you to Kiran (Acmepay)"). Tapping an edge shows its quote.
- **Review queue**: open suggestions by score, the two cards side by side, `reasons` as chips, and Same /
  Not the same buttons. Auto-merges show in a "merged automatically, because the same email" list with Undo.
- **Commitment context**: an item to Kiran says "via Asha" when an `intro` edge exists.

## Open questions

- Owner keys: your own number and email appear on vCards of family devices. `me` must come from the
  account row, and the spike only passes it as an argument.
- Should the user's saved name always win over a LinkedIn full name? Today the survivor's name wins on a tie.
- Two numbers for one person: the 0.8 multiplier is a guess. The 36 new-number names are the test set.
- Group-chat co-membership is a strong context signal, but group senders are stored as push names, not JIDs.
- The mention-only person's threshold (0.8 plus context) needs a labelled set before any model run.

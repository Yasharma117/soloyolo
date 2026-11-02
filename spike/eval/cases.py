"""Hand-labeled 1:1 threads for scoring commitment extraction.

Each case is a thread and the commitments a careful human would list. Messages are
(days_ago, hour, from_me, text); message ids are their 1-based positions.

An expected commitment names:
- owner: "me" or "them"
- sources: the message ids that count as where it was made (an offer and its acceptance can
  both be fair citations)
- done: the message ids that show it was done; empty means it is still open

Labels follow the extractor's own definition (spike/extract.py SYSTEM): concrete things one side
said they would do, accepted offers included; no pleasantries, questions, plans both sides just
attend, reports of the past, or promises made by someone outside the thread.

These were written by the same model family that does the extraction, which can flatter it.
Add your own real-world cases (anonymised) before trusting the numbers.
"""

CASES = [
    {
        "id": "intro-open",
        "note": "Clear promise by me, never done, the other side chases",
        "messages": [
            (12, 19, 0, "Good seeing you at the founders dinner"),
            (12, 19, 1, "Likewise. You mentioned you're hiring a design lead?"),
            (12, 20, 0, "Yes, it's the hardest role to fill right now"),
            (12, 20, 1, "I'll intro you to Priya, she built the design team at her last startup"),
            (3, 9, 0, "Any luck reaching Priya?"),
        ],
        "expected": [{"owner": "me", "sources": [4], "done": []}],
    },
    {
        "id": "notes-done",
        "note": "My promise, then done in a later message",
        "messages": [
            (20, 14, 1, "Loved the deck. Want me to mark up the pricing slide?"),
            (20, 14, 0, "Yes please"),
            (20, 15, 1, "Will send notes tomorrow"),
            (19, 22, 1, "Sent, check your email"),
            (19, 23, 0, "These are great, thank you"),
        ],
        "expected": [{"owner": "me", "sources": [1, 2, 3], "done": [4]}],
    },
    {
        "id": "their-promise",
        "note": "The other person promises; still open",
        "messages": [
            (5, 10, 1, "Did you find that contractor's number?"),
            (5, 11, 0, "Not yet, I'll dig it out tonight and text you"),
            (2, 9, 1, "Still keen on that number when you get a sec"),
        ],
        "expected": [{"owner": "them", "sources": [2], "done": []}],
    },
    {
        "id": "accepted-offer-them",
        "note": "Their offer, accepted by me: they owe it",
        "messages": [
            (8, 18, 0, "I have a spare ticket for the Saturday gig if you want it"),
            (8, 18, 1, "Yes!! I'd love that"),
            (8, 19, 0, "Cool, I'll forward it on Friday"),
        ],
        "expected": [{"owner": "them", "sources": [1, 3], "done": []}],
    },
    {
        "id": "on-it",
        "note": "A request answered with 'on it': I owe it",
        "messages": [
            (4, 9, 0, "Can you send me the signed lease when you get a chance?"),
            (4, 9, 1, "On it 👍"),
        ],
        "expected": [{"owner": "me", "sources": [2], "done": []}],
    },
    {
        "id": "unanswered-request",
        "note": "A request with no acceptance is not a commitment",
        "messages": [
            (6, 13, 0, "Could you review my essay this week?"),
            (6, 20, 0, "No pressure if you're swamped"),
        ],
        "expected": [],
    },
    {
        "id": "vague-catchup",
        "note": "Pleasantries only",
        "messages": [
            (30, 12, 1, "Happy birthday!!"),
            (30, 13, 0, "Thank you! We should catch up sometime"),
            (30, 13, 1, "Definitely, let me know whenever you're around"),
        ],
        "expected": [],
    },
    {
        "id": "hinglish-revert",
        "note": "Indian-English 'revert' and 'lemme', done by sending",
        "messages": [
            (3, 11, 0, "Bhai can you check if the flat on 4th cross is still available?"),
            (3, 11, 1, "Lemme check with the broker and revert by evening"),
            (3, 19, 1, "Spoke to him, it's available till 15th. Rent 42k"),
            (3, 19, 0, "Super, thanks yaar"),
        ],
        "expected": [{"owner": "me", "sources": [2], "done": [3]}],
    },
    {
        "id": "typos-tmrw",
        "note": "Typos and no apostrophe",
        "messages": [
            (1, 22, 0, "u still have my charger?"),
            (1, 22, 1, "ya ill drop it at ur place tmrw morning"),
        ],
        "expected": [{"owner": "me", "sources": [2], "done": []}],
    },
    {
        "id": "past-report",
        "note": "Reporting something already done is not a promise",
        "messages": [
            (2, 10, 1, "I sent the invoice to your finance team yesterday"),
            (2, 11, 0, "Perfect, got it"),
        ],
        "expected": [],
    },
    {
        "id": "joke",
        "note": "Hyperbole, not a commitment",
        "messages": [
            (1, 18, 0, "running 10 min late sorry"),
            (1, 18, 1, "I'll kill you lol. Grabbing a table"),
            (1, 18, 0, "😂 ordering you a drink as penance"),
        ],
        "expected": [],
    },
    {
        "id": "shared-plan",
        "note": "A plan both attend is not owed by either side",
        "messages": [
            (2, 9, 0, "Dinner Thursday at 8 still on?"),
            (2, 9, 1, "Yep see you there"),
        ],
        "expected": [],
    },
    {
        "id": "third-party",
        "note": "A promise by someone outside the thread",
        "messages": [
            (3, 15, 0, "Rahul said he'll send you the deck by Monday"),
            (3, 15, 1, "Great, thanks for chasing him"),
        ],
        "expected": [],
    },
    {
        "id": "payback",
        "note": "Money owed, then paid",
        "messages": [
            (9, 21, 1, "Thanks for covering the cab, I'll UPI you tonight"),
            (9, 23, 1, "Done, sent 640"),
            (9, 23, 0, "Got it 👍"),
        ],
        "expected": [{"owner": "me", "sources": [1], "done": [2, 3]}],
    },
    {
        "id": "done-by-their-ack",
        "note": "Done shown only by the other side's thanks",
        "messages": [
            (7, 10, 0, "Could you share the Figma link for the onboarding flow?"),
            (7, 10, 1, "Sure, will share in a few mins"),
            (7, 11, 0, "Got it, thanks!"),
        ],
        "expected": [{"owner": "me", "sources": [2], "done": [3]}],
    },
    {
        "id": "two-sides",
        "note": "One promise each way; one done",
        "messages": [
            (15, 16, 1, "I'll send you the term sheet template"),
            (15, 16, 0, "Thanks. I'll intro you to my lawyer, she's great with seed rounds"),
            (14, 10, 1, "Template's in your inbox"),
            (4, 12, 1, "Any update on the lawyer intro?"),
        ],
        "expected": [
            {"owner": "me", "sources": [1], "done": [3]},
            {"owner": "them", "sources": [2], "done": []},
        ],
    },
    {
        "id": "cancelled",
        "note": "Promise withdrawn by its owner, then nothing is owed",
        "messages": [
            (6, 9, 1, "I'll bring the projector on Saturday"),
            (5, 18, 1, "Ugh, it's broken. Can't bring it after all, sorry"),
            (5, 18, 0, "No worries, I'll ask Meera"),
        ],
        "expected": [{"owner": "them", "sources": [3], "done": []}],
    },
    {
        "id": "conditional-offer",
        "note": "'Let me know if you need anything' is not a commitment",
        "messages": [
            (10, 20, 0, "Moving day went fine, finally done"),
            (10, 20, 1, "Yay! Let me know if you need help unpacking"),
        ],
        "expected": [],
    },
    {
        "id": "follow-up-call",
        "note": "Call scheduled by me with a due day",
        "messages": [
            (2, 17, 0, "Would love your take on the pricing model when you're free"),
            (2, 17, 1, "Happy to. I'll call you Thursday afternoon"),
        ],
        "expected": [{"owner": "me", "sources": [2], "done": []}],
    },
    {
        "id": "reply-in-thread-later",
        "note": "Promise far up a long thread, chatter after",
        "messages": [
            (25, 9, 1, "I'll put together a list of Bangalore pediatricians for you"),
            (25, 9, 0, "You're a lifesaver"),
            (20, 18, 0, "How's the new job?"),
            (20, 18, 1, "Chaotic but fun. You?"),
            (20, 19, 0, "Same, same. Kids are sick again"),
            (18, 8, 1, "Ugh, hope they feel better soon"),
        ],
        "expected": [{"owner": "me", "sources": [1], "done": []}],
    },
    {
        "id": "question-not-promise",
        "note": "'Should I send it?' left hanging is not a promise",
        "messages": [
            (3, 14, 1, "Should I send you the recording?"),
            (3, 15, 0, "Oh I watched it live already"),
        ],
        "expected": [],
    },
    {
        "id": "will-do",
        "note": "'Will do' after an ask",
        "messages": [
            (1, 9, 0, "Please book the conference room for Friday 3pm"),
            (1, 9, 1, "Will do"),
            (1, 10, 1, "Booked. Room 4B"),
        ],
        "expected": [{"owner": "me", "sources": [2], "done": [3]}],
    },
    {
        "id": "them-pay",
        "note": "They owe me money",
        "messages": [
            (1, 13, 0, "Thanks for covering lunch, I'll pay you back on Friday"),
            (1, 14, 1, "No rush"),
        ],
        "expected": [{"owner": "them", "sources": [1], "done": []}],
    },
    {
        "id": "hope-not-promise",
        "note": "Hopes and maybes are not commitments",
        "messages": [
            (4, 20, 0, "Coming to the reunion?"),
            (4, 21, 1, "Hoping to! Might be travelling, will see"),
        ],
        "expected": [],
    },
    {
        "id": "read-tonight",
        "note": "Saying you'll read something someone sent is courtesy, not an owed action",
        "messages": [
            (5, 9, 0, "Here's the piece on hiring loops I mentioned"),
            (5, 10, 1, "Perfect, reading it tonight"),
        ],
        "expected": [],
    },
]

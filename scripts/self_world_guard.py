#!/usr/bin/env python3
"""WS1 — the self/world binding guard (the structural honesty moat).

PRINCIPLE (north star §4 "bound richness", §5.2 "INJECT is a hallucination surface"):
observed external text — a sign, a screen, an overheard utterance, a third-person
caption — is about THE WORLD by default. Binding it to the WEARER ("my name is X",
"lectures by me") or to a NAMED CO-PRESENT person ("Rhett was at my table") is
inference, and inference is a hallucination surface. Such a binding may stand only when
a *self / co-presence* channel corroborates it. The only such channel current capture
has is `self_entity` (egocentric POV/own-body frames + addressee-name from speech). When
that channel does NOT back the binding, the honest answer is to REFUSE — the moment's
self/co-presence evidence was simply never captured (the irreversibility discipline:
detect the edge of capture, do not confabulate across it).

This is NOT a name blocklist. It keys on (question class, answer shape, corroboration
channel) — never on specific strings ("Nezam", "Rhett") — so it generalizes past the
day clip. The same rule that refuses "Nezam Pinias" on the blindfolded memory KEEPS
"Joe" on the caption-rich memory, because there self_entity corroborates "Joe" (the
wearer is addressed by it in a farewell), and keeps a world read like "Mr. Ryan
Maccombs' lectures" because that is not a *self* binding at all.

Three structural rules, applied to a draft answer:
  A. SELF-NAME      — a question for the wearer's OWN name may assert a name only if
                      self_entity corroborates that exact name; otherwise refuse.
  B. SELF-AUTHORSHIP— an answer that claims the wearer authored / owns / created observed
                      content (a first-person identity claim) is ungrounded when
                      self_entity provides NO self-corroboration for this memory at all;
                      refuse. (This catches the garbled "lectures by Me".)
  C. CO-PRESENT NAME— a question that places / identifies a specific person RELATIVE TO
                      the wearer may not assert a person's NAME: no channel localizes a
                      named person as co-present (no person boxes, no speaker diarization,
                      no face-ID), so the named binding is ungrounded; refuse it.

Public API:
  guard(question, answer, memory_dir) -> refusal str | None
      None  -> the answer is left untouched (no ungrounded self/scene binding detected).
      str   -> an honest refusal that should REPLACE the answer.

CLI / unit test (CPU-only, no ollama, no memory needed for the synthetic cases):
  python scripts/self_world_guard.py --selftest
"""
from __future__ import annotations

import os
import re
import sys

# self_entity is the corroboration channel. Import defensively so the guard degrades to
# "no self-corroboration available" rather than crashing the brain if it is missing.
try:
    import self_entity as _self_entity
except Exception:  # pragma: no cover - allow standalone import
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        import self_entity as _self_entity
    except Exception:
        _self_entity = None


# --- the honest refusals (each carries a REFUSAL_MARKER phrase so ask_home._is_refusal
#     and the EXPAND/understanding layer both recognise them as a don't-know) ----------
SELF_NAME_REFUSAL = (
    "I don't have that — I never captured anything that ties a name to you. A name I "
    "read on a sign nearby is the world's, not necessarily yours.")
SELF_BIND_REFUSAL = (
    "I don't have that — I didn't capture anything showing that was yours or by you. "
    "What I read belonged to the scene, and I can't tie it to you.")
COPRESENT_REFUSAL = (
    "I don't have that — I didn't capture who that was. I may have overheard or read a "
    "name nearby, but nothing ties it to the specific person you're asking about.")


# ---------------------------------------------------------------------------
# Question-class detectors (what is being asked) — structural, string-agnostic.
# ---------------------------------------------------------------------------

# The wearer's OWN name, in any natural phrasing. We key on the PRINCIPLE ("a name OF the
# wearer") not a fixed phrasing — full/first/last name, "what do people call me", "is my
# name X", "introduce myself". The asserted name is always cross-checked against
# self_entity, so broadening this only ever ADDS a corroboration check (never a blind lie).
_SELF_NAME_RE = re.compile(
    r"\b(?:"
    r"(?:what(?:'?s| is| was| are)?|tell me)\s+my\s+"
    r"(?:full |first |last |real |complete |legal |middle )?name"
    r"|is\s+my\s+(?:full |first |last )?name\b"
    r"|what\s+am\s+i\s+(?:called|named)"
    r"|am\s+i\s+(?:called|named)\b"
    r"|what\s+do\s+(?:people|they|you|others)\s+call\s+me"
    r"|who\s+am\s+i\b"
    r"|do you know my name"
    r"|(?:how do i |i )?introduce myself"
    r")\b",
    re.I,
)

# A person placed / identified RELATIVE TO the wearer: "who was with/next to/opposite me",
# "at my table", "the person who <verb> me", "name of the person ...", "I said hi to ...".
# Deliberately does NOT match world reads like "whose name was on the poster" (a name on an
# OBJECT, not a person co-present with the wearer).
_COPRESENT_RE = re.compile(
    r"\bwho(?:'?s| is| was| were| are)\b[^?]*\b(?:with me|next to me|beside me|near me|"
    r"opposite me|opposite to me|across from me|in front of me|behind me|at my table|"
    r"sitting (?:with|next to|by) me|seated (?:with|next to) me)\b"
    r"|\bwho (?:was|were) (?:at|opposite|across|with|next to|beside|sitting|seated|near)\b"
    # relational VERB phrasings — a person placed by a PHYSICAL co-presence verb. We stay
    # with physically-co-present verbs (sat/ate/walked/shook hands/host/server); we leave
    # generic "who did I meet/talk to" out on purpose (those can be answered from a screen
    # or calendar — a world read we must not blanket-refuse). Documented gap, not an oversight.
    r"|\bwho\s+(?:sat|sits|stood|stands)\s+(?:next to|beside|across(?:\s+from)?|"
    r"opposite(?:\s+to)?|with|near|by)\s+me\b"
    r"|\bwho\s+(?:joined|sat with|ate with|dined with|walked with|shook hands with|"
    r"fist[- ]?bumped|high[- ]?fived|hugged|sat by|sat beside|sat next to)\s+me\b"
    r"|\bwho\s+did\s+i\s+(?:eat|dine|sit|walk|shake hands|fist[- ]?bump|high[- ]?five|hug)\b"
    r"|\bwho\s+shook\s+my\s+hand\b"
    r"|\bwho\s+was\s+my\s+(?:host|guide|server|waiter|waitress|partner|companion|guest|"
    r"seatmate|tablemate)\b"
    r"|\bmy\s+(?:colleague|friend|companion|host|guide|partner|seatmate|tablemate|guest)"
    r"(?:'s|s')\s+name\b"
    r"|\bthe person (?:who|that)\b[^?]*\b(?:checked|gave|handed|sat|stood|talked|spoke|"
    r"served|helped|greeted|met|joined|sold|asked|told)\s+(?:me|my)\b"
    r"|\bname of the (?:person|man|woman|guy|girl|lady|people)\b"
    r"|\bi said hi to (?:someone|him|her|them|a)\b",
    re.I,
)


def _is_self_name_question(q: str) -> bool:
    return bool(_SELF_NAME_RE.search(q or ""))


def _is_copresent_person_question(q: str) -> bool:
    return bool(_COPRESENT_RE.search(q or ""))


# ---------------------------------------------------------------------------
# Answer-shape detectors (what the draft claims).
# ---------------------------------------------------------------------------

# AUTHORSHIP / OWNERSHIP of observed content bound to the wearer — an identity claim,
# distinct from harmless narration ("I was listening to ...", "You read a sign ..."). We
# cover BOTH first-person ("I founded ...") and SECOND-PERSON ("You founded ...", the LLM's
# most natural phrasing for a wearer-fact), plus explicit ownership ("belongs to you", "is
# mine"). We deliberately use AUTHORSHIP/OWNERSHIP verbs (founded/own/wrote/painted/...), NOT
# generic verbs like made/gave (those produce false positives: "I made coffee"). Bare token
# "mine" is excluded in favour of possessive context ("is mine") so a "gold mine"/"coal mine"
# world read is never mistaken for an ownership claim. Generic possessives ("my car",
# "your office") are intentionally NOT matched — too broad, they would refuse grounded
# answers. Documented limitation, not an oversight.
_OWN_VERBS = (r"wrote|authored|created|drew|designed|built|founded|painted|"
              r"own|owned|run|ran|lead|led|manage|managed|teach|taught|lectured|presented")
_SELF_AUTHORSHIP_RE = re.compile(
    r"\bby me\b|\bby myself\b|\bauthored by me\b|\bwritten by me\b|\bmade by me\b"
    r"|\bcreated by me\b|\bmy own\b"
    r"|\bis mine\b|\bare mine\b|\bwas mine\b|\bwere mine\b|'s\s+mine\b"
    r"|\b(?:belongs?|belonged)\s+to\s+(?:me|you)\b"
    r"|\bi (?:" + _OWN_VERBS + r")\b"
    r"|\byou (?:" + _OWN_VERBS + r")\b"
    r"|\b(?:i am|you are|that'?s|this is|it'?s)\s+the\s+"
    r"(?:author|owner|creator|teacher|lecturer|presenter|speaker|founder)\b",
    re.I,
)

# Words that look like a Titlecase name but are not a person's name in this domain.
# A name CAN start a sentence ("Rhett was at my table"), so we must NOT blanket-skip
# sentence-initial capitals; instead this stoplist absorbs the common sentence-openers,
# pronouns, determiners, connectives, months/days, and local place/brand tokens that
# would otherwise read as names. Refusing is the honest default for the question classes
# that consult names, so a residual loose match costs an honest refusal, not a lie.
_NON_NAME_TITLECASE = {
    "I", "A", "An", "The", "This", "That", "These", "Those", "There", "Here", "It",
    "He", "She", "They", "We", "You", "My", "Me", "Mine", "Your", "His", "Her", "Our",
    "And", "But", "Or", "So", "Not", "No", "Nor", "Yes", "Based", "During", "When",
    "Where", "What", "Who", "Whom", "Whose", "Why", "How", "Therefore", "Because",
    "However", "Read", "Seen", "Someone", "Somebody", "Anyone", "Nobody", "Everyone",
    "Something", "Nothing", "Both", "Either", "Neither", "Each", "Some", "Many", "Few",
    "Okay", "Well", "Sorry", "Unfortunately", "Unknown", "Sup", "Hi", "Hello", "Hey",
    "Bye", "Yeah", "Yep", "Nope", "Maybe", "Perhaps", "Likely", "Probably", "From",
    "After", "Before", "While", "Although", "Though", "Since", "Until", "Once", "Then",
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December",
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "Am", "Pm", "Claude", "Macbook", "Iphone", "Ipad", "Munich", "Garching", "Germany",
    "Max", "Planck", "Campus", "University", "Breakfast", "Lunch", "Dinner", "Physics",
    "Lecture", "Sign", "Poster", "Screen", "Frames", "Frame", "Mr", "Mrs", "Ms", "Dr",
}


def _proper_person_names(text: str) -> list[str]:
    """Titlecase tokens that plausibly name a PERSON: first-letter-cap + lowercase tail,
    NOT an all-caps OCR token (PHYSICS LECTURE), NOT a known non-name. Sentence-initial
    tokens ARE considered (a name can open a sentence). Conservative-enough for the
    SELF-NAME check (cross-checked against self_entity) and intentionally a touch loose
    for the CO-PRESENT check (refusing a named binding is the honest default — no channel
    can place a named person)."""
    names: list[str] = []
    if not text:
        return names
    for tok in re.findall(r"[A-Za-z][A-Za-z']*", text):
        if not re.fullmatch(r"[A-Z][a-z]{2,}", tok):
            continue  # need Titlecase with a lowercase tail (skips ALL-CAPS OCR)
        if tok in _NON_NAME_TITLECASE:
            continue
        names.append(tok)
    return names


def _answer_asserts_a_name(answer: str) -> bool:
    return bool(_proper_person_names(answer))


def _answer_makes_first_person_identity_claim(answer: str) -> bool:
    return bool(_SELF_AUTHORSHIP_RE.search(answer or ""))


# ---------------------------------------------------------------------------
# Corroboration channel.
# ---------------------------------------------------------------------------

def _self_facts(memory_dir):
    """Return self_entity.self_attributes(memory_dir) or a safe empty default."""
    if _self_entity is None or not memory_dir:
        return {"name": None, "n_egocentric_frames": 0, "name_confidence": 0.0}
    try:
        return _self_entity.self_attributes(memory_dir)
    except Exception:
        return {"name": None, "n_egocentric_frames": 0, "name_confidence": 0.0}


def _is_already_refusal(answer: str) -> bool:
    """Cheap local refusal check (kept independent of ask_home to avoid an import cycle)."""
    t = (answer or "").lower()
    markers = ("i don't have", "i didn't read", "didn't see", "don't have it",
               "couldn't read", "i don't know", "no clear speech", "i didn't capture",
               "i can't tell", "cannot tell", "not in my memory", "didn't read enough")
    return any(m in t for m in markers)


# ---------------------------------------------------------------------------
# Public guard.
# ---------------------------------------------------------------------------

def guard(question: str, answer: str, memory_dir: str | None):
    """Return an honest refusal string if `answer` is an ungrounded self / scene-person
    binding; otherwise None (leave the answer untouched)."""
    if not answer or _is_already_refusal(answer):
        return None

    facts = _self_facts(memory_dir)
    corroborated_name = (facts.get("name") or "").strip()
    self_corroborated = bool(corroborated_name) or (facts.get("n_egocentric_frames") or 0) > 0

    # --- Rule A: the wearer's OWN name -------------------------------------------------
    if _is_self_name_question(question):
        if not _answer_asserts_a_name(answer):
            return None  # the draft already declined to name — leave it
        if corroborated_name and corroborated_name.lower() in (answer or "").lower():
            return None  # the asserted name IS the corroborated wearer-name -> keep
        return SELF_NAME_REFUSAL

    # --- Rule C: a NAMED co-present person ---------------------------------------------
    if _is_copresent_person_question(question):
        if _answer_asserts_a_name(answer):
            return COPRESENT_REFUSAL  # no channel can place a named person -> refuse
        return None

    # --- Rule B: first-person authorship/ownership of observed content ------------------
    # Only when this memory has NO self-corroboration at all: the wearer is an unobserved
    # entity here, so no answer may assert a first-person identity/authorship fact.
    if not self_corroborated and _answer_makes_first_person_identity_claim(answer):
        return SELF_BIND_REFUSAL

    return None


# ---------------------------------------------------------------------------
# CLI / unit test — synthetic cases, no ollama, no memory required.
# ---------------------------------------------------------------------------

class _FakeFacts:
    """Patch _self_facts for the selftest by name (no disk)."""


def _selftest() -> int:
    global _self_facts
    orig = _self_facts

    EMPTY = {"name": None, "n_egocentric_frames": 0, "name_confidence": 0.0}
    JOE = {"name": "Joe", "n_egocentric_frames": 9, "name_confidence": 0.92}

    def with_facts(facts):
        def _f(_md):
            return facts
        return _f

    cases = [
        # (label, facts, question, answer, expect_refuse)
        # --- the 3 real day-clip hallucinations: MUST refuse on the blindfolded memory ---
        ("name-on-sign->my name (blind)", EMPTY,
         "What is my name?",
         "My name is Nezam Pinias, as read on a sign at the beginning of the day.", True),
        ("garbled read->by Me (blind)", EMPTY,
         "Whose lectures was I listening to?",
         "I was listening to lectures by Me. This is read at t=1.0s.", True),
        ("overheard name->at my table (blind)", EMPTY,
         "Who were at the table opposite to me?",
         "Rhett was at the table opposite me. (t=32.0s)", True),
        # --- the SAME questions on the caption-rich memory: MUST NOT over-refuse ---------
        ("my name corroborated as Joe", JOE,
         "What is my name?",
         "The wearer was addressed as Joe.", False),
        ("whose lectures = world read (not self)", JOE,
         "Whose lectures was I listening to?",
         "I was listening to Mr. Ryan Maccombs' lectures, read at t=2.5s.", False),
        ("said-hi clothing answer (no name)", JOE,
         "I said hi to someone — what was he wearing?",
         "During the detected dressing event, the wearer had dark pants, white crocs.", False),
        # --- honest refusals pass through unchanged --------------------------------------
        ("already-refused co-present", EMPTY,
         "Who were at the table opposite to me?",
         "I don't have that in my memory.", False),
        ("already-refused self-name", EMPTY,
         "What is my name?",
         "I didn't capture anything tying a name to you.", False),
        # --- world reads that must NEVER be touched (no self/co-present framing) ----------
        ("whose name on poster = world", EMPTY,
         "Whose name was on this blue poster?",
         "The poster reads 'Lise Meitner'.", False),
        ("who named on molecule poster = world", EMPTY,
         "Who was named on the poster of the molecule?",
         "The poster credits Dr. Hans Fischer.", False),
        # --- self-name with a DIFFERENT name than corroborated -> refuse -----------------
        ("self-name mismatch vs corroborated", JOE,
         "What is my name?",
         "Your name is Rhett, read on a badge.", True),
        # --- co-present, no name asserted -> leave (clothing/relational answer) -----------
        ("co-present no-name answer", EMPTY,
         "Who was sitting next to me?",
         "Someone in a dark jacket; I couldn't read a name.", False),

        # === adversarial cases from the WS1 red-team (permanent regression guard) =========
        # A: self-name synonyms must refuse an uncorroborated name on a blind memory --------
        ("A: what do people call me", EMPTY,
         "What do people call me?", "People call you Tomas, from the badge.", True),
        ("A: is my name X", EMPTY,
         "Is my name Heinrich?", "Yes, your name is Heinrich.", True),
        ("A: my full name", EMPTY,
         "What's my full name?", "Your full name is Tomas Becker.", True),
        ("A: am I called X", EMPTY,
         "Am I called Marcus?", "Yes, you are called Marcus.", True),
        # C: relational physical co-presence verbs must refuse a NAMED person ---------------
        ("C: who sat across from me", EMPTY,
         "Who sat across from me?", "Tom sat across from you.", True),
        ("C: who did I eat with", EMPTY,
         "Who did I eat with?", "You ate with Markus.", True),
        ("C: who shook my hand", EMPTY,
         "Who shook my hand?", "Wolfgang shook your hand.", True),
        ("C: who was my host", EMPTY,
         "Who was my host?", "Your host was Friedrich.", True),
        ("C: my colleague's name", EMPTY,
         "What is my colleague's name?", "Your colleague is named Dieter.", True),
        # B: second-person ownership/authorship on a blind memory must refuse ---------------
        ("B: you founded", EMPTY,
         "Tell me about this company.", "You founded this company in 2010.", True),
        ("B: that is your car", EMPTY,
         "What about the car?", "The blue car belongs to you.", True),
        ("B: you run this lab", EMPTY,
         "What is this lab?", "You run this lab.", True),
        # OVER-FIRE fixes: world reads with a noun 'mine' / a person name must be KEPT ------
        ("over-fire: gold mine noun", EMPTY,
         "What did the sign say?", "The sign said the gold mine is closed.", False),
        ("over-fire: coal mine noun", EMPTY,
         "What is this place?", "This is a coal mine.", False),
        ("over-fire: world book author", EMPTY,
         "Who wrote that book?", "The book is by George Orwell.", False),
        ("over-fire: street named after", EMPTY,
         "What is this street?", "The street is named after Max Born.", False),
        # benign first-person narration on a blind memory must be KEPT (not an identity claim)
        ("over-fire: I walked past", EMPTY,
         "What did I pass?", "You walked past a cafe and a bookstore.", False),
    ]

    ok = True
    print("SELF/WORLD BINDING GUARD — selftest")
    for label, facts, q, a, expect in cases:
        _self_facts = with_facts(facts)  # type: ignore
        got = guard(q, a, "<fake>")
        refused = got is not None
        passed = refused == expect
        ok = ok and passed
        print("  [%s] %-42s expect=%-7s got=%-7s"
              % ("PASS" if passed else "FAIL", label,
                 "REFUSE" if expect else "keep",
                 "REFUSE" if refused else "keep"))
        if not passed:
            print("        Q: %s\n        A: %s\n        ->%r" % (q, a, got))

    _self_facts = orig  # type: ignore
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main(argv):
    if argv and argv[0] == "--selftest":
        return _selftest()
    print("usage: self_world_guard.py --selftest")
    print("       (as a library: from self_world_guard import guard)")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

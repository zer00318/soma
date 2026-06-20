"""
SOMA content-extraction importer — populates the Tier-B relational graph
from existing lawful user data before the device is worn.

Tier-B entities: persons the user already has a lawful relationship with
(contacts, message senders, calendar attendees). They receive rich, accreting
attributes extracted from content the user already holds.

Sources:
  --whatsapp   WhatsApp chat export .txt file
  --ics        Google Calendar .ics export
  --imessage   iMessage chat.db (macOS only, ~/Library/Messages/chat.db)

What gets extracted (beyond names):
  - message_count + last_contact_at  → relationship freshness
  - recent_topics                    → top keyword summary of last N messages
  - open_commitments                 → sentences containing commitment verbs
  - contact_identifier               → phone/email handle for re-identification
  - calendar events                  → title, location, purpose as graph events
  - event_count                      → how many calendar events shared
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

# ── LLM quality-filter (Task A) ─────────────────────────────────────────────
# qwen2.5:14b is not installed; use best available instruction-tuned model.
_LLM_MODEL = "gemma3:12b-it-qat"


def _llm_is_commitment(text: str) -> bool:
    """Ask local Ollama whether text is a genuine actionable commitment.

    Returns True (keep) on any error so a downed Ollama never silently drops
    real commitments.
    """
    prompt = (
        "Decide if this chat message is a real actionable promise to another person "
        "— something the other person could reasonably depend on getting done, "
        "like \"I will send you the report tomorrow\" or \"I can pick you up at nine\". "
        "Answer no for: statements about one's own routine or wellbeing "
        "(\"I will sleep\", \"I'll go eat now\"), jokes and banter, vague intentions "
        "(\"I should...\", \"I need to...\"), descriptions of one's own plans that "
        "benefit nobody else, and factual constraints. "
        f"Answer only yes or no. Message: '{text}'"
    )
    try:
        payload = json.dumps(
            {
                "model": _LLM_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0},
            }
        ).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            answer = json.loads(resp.read()).get("response", "").strip().lower()
            return answer.startswith("yes")
    except Exception:
        return True  # Ollama unavailable → keep (safe default)


# ── User-name stop tokens (Task B) ──────────────────────────────────────────
# Loaded from SOMA_USER_NAME env-var (space-separated); default "pranav".
_USER_NAME_TOKENS: frozenset[str] = frozenset(
    os.environ.get("SOMA_USER_NAME", "pranav").lower().split()
)

# ── Commitment recency window ───────────────────────────────────────────────
# "Open commitments" are promises that are plausibly still open; a promise
# from years ago is noise. Read at call time so tests can pin the window.


def _commitment_window_days() -> int:
    try:
        return int(os.environ.get("SOMA_COMMITMENT_WINDOW_DAYS", "60"))
    except ValueError:
        return 60


# ── Contact-name normalisation (Task D) ─────────────────────────────────────
_NAME_STRIP_SUFFIXES: frozenset[str] = frozenset(
    {"IPP", "GmbH", "AG", "UG", "eV", "Dr.", "Prof."}
)


def _clean_contact_name(raw: str) -> str:
    """Strip trailing institutional suffixes and all-caps abbreviations.

    Removes tokens from the end of a contact name that are:
      - In the known-suffix set (IPP, GmbH, AG, eV, …)
      - All-caps and 2–5 characters (e.g. "TU", "KIT", "DE")
    Falls back to the original string if stripping would leave nothing.
    """
    tokens = raw.split()
    while tokens:
        last = tokens[-1]
        if last in _NAME_STRIP_SUFFIXES or (last.isupper() and 2 <= len(last) <= 5):
            tokens.pop()
        else:
            break
    return " ".join(tokens).strip() or raw.strip()

# Apple epoch offset: Apple timestamps are nanoseconds since 2001-01-01
APPLE_EPOCH_OFFSET = 978307200

# Commitment-verb pattern — detect first-person commitments / agreements.
# Uses negative lookahead on each verb to exclude negated forms ("I can't", "I won't", etc.)
# Minimum length is enforced post-match (10 < len < 200).
_COMMITMENT_RE = re.compile(
    r"(?:^|(?<=[.!?]\s))([^.!?\n]{0,200}?(?:"
    r"\bI(?:'ll| will(?! not)| can(?!not|'t|\s*not\b)| should(?! not)| need to| have to| must| am going to)\b"
    r"|"
    r"\bwe(?:'ll| will(?! not)| should(?! not)| need to| have to| are going to)\b"
    r"|"
    r"\blet me\b|\bI'll\b"
    r"|"
    # Elided-subject continuation: "I cleaned the fridge but will come again
    # tomorrow" — the "I" appears earlier in the sentence, not before "will".
    r"\bI\b[^.!?\n]{0,120}?,?\s(?:but|and|then|so)\s(?:will|'ll)(?! not)\b"
    r")[^.!?\n]{0,120})",
    re.IGNORECASE,
)

# Negation prefix — sentences starting with these are NOT commitments even if they match above
_NEGATION_PREFIXES = re.compile(
    r"^\s*(?:I (?:can't|cannot|won't|will not|don't|didn't|shouldn't|couldn't|haven't|hadn't)\b"
    r"|(?:sadly|unfortunately|sorry|apologies?)\b"
    r"|I can only (?:imagine|feel|see how|guess|dream|hope|think)\b"
    r"|I (?:can|could) (?:only |just )?(?:imagine|feel|see how|guess|understand|relate|empathize)\b"
    r"|I (?:can|could) see (?:that|how|why|what)\b"
    r"|tell me I can\b"
    r"|I (?:need to|have to|must) (?:mentally|emotionally|psychologically|literally just)\b"
    r")",
    re.IGNORECASE,
)

# Full-sentence filter for non-commitment patterns buried mid-sentence.
# Applied via .search() (anywhere in string), not prefix-anchored like _NEGATION_PREFIXES.
_FALSE_COMMITMENT_ANYWHERE = re.compile(
    r"(?:"
    r"I (?:need to|have to|must) (?:mentally|emotionally|psychologically|literally just|survive|cope|process|just deal)"
    r"|(?:where|if|whether|any(?:place|where|one)) I can\b"  # "where I can X" = relative clause, not commitment
    r")",
    re.IGNORECASE,
)

# Words to strip from keyword extraction.
# Tuned for multilingual casual chat (English + Telugu + German social particles).
# Minimum token length is 5 (enforced in _extract_topics) — this list handles
# 5+ char filler that still slips through.
_STOP_WORDS = frozenset((
    # English function + discourse words
    "i me my we our you your he she they it the a an and or but is was are were be been "
    "have has had does did will would could should may might shall must can "
    "this that these those of to in on at by for with from as up out so if no not "
    # 5-7 char discourse + filler words that slip past the length filter
    "about after again being cause check comes doing every emoji first fully going "
    "hello hours because though just known later looks maybe never often other "
    "please quite right since small sorry start still story "
    "sounds thank their there these those through times today "
    "total totally under until using wants where which while works online "
    "before between coming during having takes given makes given "
    "both each away come keep seem only even "
    # Social chat filler
    "okay yeah sure just like also well then next now here there already still "
    "always never really actually literally basically honestly probably maybe "
    "something anything nothing everything someone anyone know think feel want need "
    "tell said send sent come came went gone look looks looked thing things "
    "time today tomorrow yesterday morning evening night week month year hour hours "
    "good great nice cool fine awesome right wrong bad sad happy enjoy enjoying "
    "haha hahaha lol lmao omg wow ohh ohhh nah nope yep yup yes hmm uhh "
    "okay ok bro man dude dear anna bhai bhaiya bhayya yaar "
    # Telugu social particles (show up heavily in Indian WhatsApp chats)
    "anna bhayya miru naadi nundi taruvata chinna andaru ikkade akkade "
    "super superu superuu ayya akka cheyyi ledu ayindi aiyah aiyahh "
    "chepte kadha pettali vachindi eeroju chestam cheppali unnaru "
    "maharshi nanna anthe kuda ledhu konchem manchi unna "
    # German social particles
    "bitte danke nein doch auch sehr schon noch mehr "
    "https http www com org net"
).split())


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _normalize(label: str) -> str:
    return re.sub(r"\s+", " ", label.lower().strip())


def _ensure_tier_b_person(
    conn: sqlite3.Connection,
    label: str,
    first_seen: str,
    last_seen: str,
    source: str,
    contact_id: str = "",
) -> str:
    """Upsert a Tier-B person entity. Returns entity_id.

    Looks up by the cleaned label_norm first; if not found, also tries the
    raw (pre-clean) label_norm to migrate entities created before Task-D
    name normalisation was added (e.g. 'alberto ambrogini ipp' → found, then
    updated to the clean label 'alberto ambrogini').
    """
    label_norm = _normalize(label)
    row = conn.execute(
        "SELECT id FROM graph_entities WHERE kind='person' AND label_norm=?",
        (label_norm,),
    ).fetchone()
    if not row:
        # Migration: 'alberto ambrogini' should match 'alberto ambrogini ipp' from
        # a prior import so we rename rather than create a duplicate.
        row = conn.execute(
            "SELECT id FROM graph_entities WHERE kind='person' AND label_norm LIKE ?",
            (label_norm + " %",),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE graph_entities SET label=?, label_norm=? WHERE id=?",
                (label, label_norm, row["id"]),
            )
    meta = json.dumps({
        "tier": "B",
        "tier_source": source,
        "contact_identifier": contact_id,
    }, sort_keys=True)
    if row:
        conn.execute(
            "UPDATE graph_entities SET last_seen_at=?, observation_count=observation_count+1, metadata_json=? WHERE id=?",
            (last_seen, meta, row[0]),
        )
        return str(row[0])
    entity_id = str(uuid4())
    conn.execute(
        """INSERT INTO graph_entities
           (id, kind, label, label_norm, first_seen_at, last_seen_at,
            confidence, observation_count, status, metadata_json)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (entity_id, "person", label, label_norm, first_seen, last_seen,
         0.9, 1, "current", meta),
    )
    return entity_id


def _upsert_attribute(
    conn: sqlite3.Connection,
    entity_id: str,
    key: str,
    value: str,
    source: str,
    confidence: float = 0.9,
    observed_at: str | None = None,
) -> None:
    """Insert or update a graph_attribute for an entity.

    Lookup is on (entity_id, attribute_key) — one canonical value per key per
    entity.  The schema has UNIQUE(entity_id, attribute_key, attribute_value);
    searching on key alone avoids a UNIQUE violation when a value changes
    between import runs (e.g. last_contact_at updating to a newer timestamp).

    observed_at is when the underlying fact was observed (e.g. the message
    timestamp), which is what recall cites as provenance — import wall-clock
    time is only the fallback.
    """
    existing = conn.execute(
        "SELECT id FROM graph_attributes WHERE entity_id=? AND attribute_key=?",
        (entity_id, key),
    ).fetchone()
    if existing:
        conn.execute(
            """UPDATE graph_attributes
               SET attribute_value=?, source=?, confidence=?,
                   last_seen_at=COALESCE(?, datetime('now')),
                   observation_count=observation_count+1
               WHERE id=?""",
            (value, source, confidence, observed_at, existing["id"]),
        )
    else:
        conn.execute(
            """INSERT INTO graph_attributes
               (id, entity_id, attribute_key, attribute_value, source,
                status, confidence, observation_count, first_seen_at, last_seen_at, metadata_json)
               VALUES (?,?,?,?,?,?,?,?,
                       COALESCE(?, datetime('now')), COALESCE(?, datetime('now')), '{}')""",
            (str(uuid4()), entity_id, key, value, source, "current", confidence, 1,
             observed_at, observed_at),
        )


def _normalize_text(text: str) -> str:
    """Normalize Unicode typography to ASCII equivalents before regex processing.

    WhatsApp iOS messages use Unicode smart quotes (U+2018/U+2019, U+201C/U+201D)
    and other typographic characters. The commitment regex's negative lookaheads
    use ASCII apostrophes — without normalization "can't" (U+2019) bypasses the
    negation check and registers as a commitment.
    """
    return (
        text
        .replace("’", "'").replace("‘", "'")   # right/left single quote
        .replace("“", '"').replace("”", '"')   # right/left double quote
        .replace("—", " -- ").replace("–", "-") # em/en dash
    )


def _extract_topics(messages: list[str], top_n: int = 8) -> str:
    """Return comma-separated top keywords from a list of message bodies.

    Minimum token length is 5 chars — cuts most 4-char social particles
    (anna, miru, bhai, doch, schon, time, good, know, next, then, etc.)
    before the stop-word list even runs.
    """
    words: list[str] = []
    for msg in messages[-100:]:  # only last 100 messages for recency
        for w in re.findall(r"\b[a-zA-ZÄÖÜäöüß]{5,}\b", msg):
            lw = w.lower()
            if lw not in _STOP_WORDS and lw not in _USER_NAME_TOKENS:  # Task B
                words.append(lw)
    top = [w for w, _ in Counter(words).most_common(top_n)]
    return ", ".join(top)


# Explicit completion self-reports ("just sent it") from the promiser.
_COMPLETION_RE = re.compile(
    r"\b(?:just sent|sent (?:it|you|them|over)|already sent|already did|done with"
    r"|delivered|uploaded|finished it|took care of it|sorted it|just did)\b",
    re.IGNORECASE,
)


def _content_words(text: str) -> set[str]:
    return {
        w for w in re.findall(r"[a-zà-ÿ']{4,}", text.lower())
        if w not in _STOP_WORDS
    }


def _explicitly_resolved(commitment: str, later_same_side: list[str]) -> bool:
    """Deterministic fulfilment check: the promiser later reports completion
    in words that share content with the promise ("I'll send the slides" →
    "just sent the slides").

    Deliberately NOT an LLM judgment: measured 2026-06-10, gemma3-12B verdicts
    on implicit fulfilment evidence inverted under prompt rephrasing on both a
    real case and a fixture canary. Implicit cases stay open until they lapse
    or age out of the recency window — bounded staleness beats coin-flip
    deletion of real obligations.
    """
    cw = _content_words(commitment)
    if not cw:
        return False
    for text in later_same_side:
        if _COMPLETION_RE.search(text) and cw & _content_words(text):
            return True
    return False


def _llm_commitment_resolved(commitment: str, later_messages: list[str]) -> bool:
    """Ask local Ollama whether later chat traffic shows the promise was resolved.

    UNUSED in the import pipeline (see _explicitly_resolved) — kept for
    offline experiments only.

    Returns False (treat as still open) on any error — a downed Ollama must
    never silently drop real open commitments.
    """
    block = "\n".join(t.strip()[:200] for t in later_messages[:25] if t.strip())
    if not block:
        return False
    prompt = (
        f"A person promised: \"{commitment}\"\n"
        f"Here are the messages that followed in the same chat:\n{block}\n\n"
        "Do these messages show the promise was fulfilled, no longer needed, "
        "or cancelled? Evidence may be implicit — the other person thanking "
        "them for it, commenting on or reviewing the delivered thing, or the "
        "promised plan visibly happening — but it must refer to THIS promise. "
        "Unrelated conversation, or the topic simply never coming up again, "
        "means the promise is still pending. Answer only yes or no."
    )
    try:
        payload = json.dumps(
            {
                "model": _LLM_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0},
            }
        ).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            answer = json.loads(resp.read()).get("response", "").strip().lower()
            return answer.startswith("yes")
    except Exception:
        return False


# A promise with an explicit short horizon ("I'll clean it today") is no
# longer OPEN once that horizon is long past — whether it was kept or not.
_SHORT_HORIZON_RE = re.compile(
    r"\b(today|tonight|tomorrow|this (?:morning|afternoon|evening|weekend)|right now|now)\b",
    re.IGNORECASE,
)


def _extract_open_commitments(
    msgs: list[dict], of_user: bool = True, limit: int = 5
) -> list[str]:
    """Extract still-open commitments from an ordered 1:1 message sequence.

    msgs entries need: text, from_me, in_window (candidate eligibility),
    recent (within the short-horizon lapse window) — recency policies are the
    caller's. Candidates come from the chosen side's in-window messages.
    Drops a candidate when: its explicit short horizon is long past (lapsed),
    or the messages that FOLLOW it (both sides) show it was since fulfilled
    or cancelled — a done promise is not an open commitment.
    """
    found: list[str] = []
    for i in range(len(msgs) - 1, -1, -1):  # most recent first
        m = msgs[i]
        if bool(m.get("from_me")) != of_user:
            continue
        if not m.get("text") or not m.get("in_window"):
            continue
        text = _normalize_text(m["text"])
        for match in _COMMITMENT_RE.finditer(text):
            sentence = match.group(1).strip()
            if not (20 <= len(sentence) < 200):
                continue
            if _NEGATION_PREFIXES.match(sentence):
                continue
            if _FALSE_COMMITMENT_ANYWHERE.search(sentence):
                continue
            if _SHORT_HORIZON_RE.search(sentence) and not m.get("recent", True):
                continue  # lapsed: "today/tomorrow" said over a week ago
            if not _llm_is_commitment(sentence):
                continue
            later_same_side = [
                x.get("text") or ""
                for x in msgs[i + 1 : i + 26]
                if bool(x.get("from_me")) == of_user
            ]
            if _explicitly_resolved(sentence, later_same_side):
                continue
            found.append(sentence)
            if len(found) >= limit:
                return found
    return found


def _extract_commitments(messages: list[str], limit: int = 5) -> list[str]:
    """Extract sentences containing a first-person commitment or agreement.

    Normalizes Unicode typography first (smart apostrophes bypass ASCII lookaheads).
    Negated constructions ("I can't", "I won't") are excluded via negative lookaheads
    in _COMMITMENT_RE and a post-match check against _NEGATION_PREFIXES.
    """
    found: list[str] = []
    for raw_msg in reversed(messages):  # most recent first
        msg = _normalize_text(raw_msg)
        for m in _COMMITMENT_RE.finditer(msg):
            sentence = m.group(1).strip()
            # Task A step 1: length gate — < 20 chars is too short to be self-contained
            if not (20 <= len(sentence) < 200):
                continue
            if _NEGATION_PREFIXES.match(sentence):
                continue
            if _FALSE_COMMITMENT_ANYWHERE.search(sentence):
                continue
            # Task A step 2: LLM quality gate — drop banter/sarcasm/vague reflections
            if not _llm_is_commitment(sentence):
                continue
            found.append(sentence)
            if len(found) >= limit:
                return found
    return found


def _connect_graph(db_path: str) -> sqlite3.Connection:
    """Open the SOMA graph SQLite database.

    If the database does not yet have the SOMA schema (fresh file), initialize
    it via RelationalMemoryGraph so we never have to duplicate DDL here.
    """
    # Always run schema init — executescript is all IF NOT EXISTS, so this is
    # idempotent and ensures newly added tables (e.g. graph_messages) appear
    # in databases created by older builds.
    from soma_hub.graph import RelationalMemoryGraph
    from soma_hub.crypto import EncryptedTextCodec
    _graph = RelationalMemoryGraph(Path(db_path), EncryptedTextCodec(b"soma-importer-init-key-32bytes!!"))
    del _graph  # just needed for DDL; closes cleanly on GC

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# WhatsApp
# ---------------------------------------------------------------------------

_WA_LINE_RE = re.compile(
    r"(\d{1,2}[./]\d{1,2}[./]\d{2,4}),?\s+"
    r"(\d{1,2}:\d{2}(?::\d{2})?(?:\s?[APap][Mm])?)\s+-\s+"
    r"([^:]+):\s+(.*)"
)

_WA_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([AP]M)?")


def _parse_wa_timestamp(date_str: str, time_str: str) -> str:
    """Normalize a WhatsApp export timestamp to ISO 8601.

    ISO storage makes timestamps sortable and lets recall humanize them;
    the raw locale strings sort lexicographically (2.6 < 12.5), which
    silently corrupted last_contact_at. Day/month order heuristic: a
    component >12 disambiguates; otherwise dotted dates read day-first
    (European locales) and slashed dates month-first (US). Returns the
    raw string pair unchanged if parsing fails.
    """
    raw = f"{date_str} {time_str}"
    parts = re.split(r"[./]", date_str)
    if len(parts) != 3:
        return raw
    try:
        a, b, year = (int(p) for p in parts)
    except ValueError:
        return raw
    if year < 100:
        year += 2000
    if a > 12:
        day, month = a, b
    elif b > 12:
        day, month = b, a
    elif "." in date_str:
        day, month = a, b
    else:
        month, day = a, b
    m = _WA_TIME_RE.match(time_str.strip().upper())
    if not m:
        return raw
    hour, minute, second = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    if m.group(4) == "PM" and hour != 12:
        hour += 12
    elif m.group(4) == "AM" and hour == 12:
        hour = 0
    try:
        return datetime(year, month, day, hour, minute, second).isoformat()
    except ValueError:
        return raw


def _is_user_sender(sender: str) -> bool:
    """True when every token of the sender name matches SOMA_USER_NAME tokens."""
    tokens = {t for t in re.split(r"\W+", sender.lower()) if t}
    return bool(tokens) and tokens <= _USER_NAME_TOKENS


def import_whatsapp(export_path: str, db_path: str) -> dict[str, int]:
    """
    Parse WhatsApp _chat.txt export.

    Extracts per-sender:
      - first/last contact timestamps
      - message count
      - recent conversation topics (keyword summary)
      - open commitments (sentences with commitment verbs)
    """
    # Parse into sender → {timestamps, messages}; the user's own lines are
    # held separately so they never become a Tier-B contact.
    contacts: dict[str, dict[str, Any]] = {}
    user_messages: list[tuple[str, str]] = []  # (iso_ts, body)
    with open(export_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = _WA_LINE_RE.match(line.strip())
            if not m:
                continue
            date_str, time_str, sender, body = m.groups()
            sender = sender.strip()
            body = body.strip()
            if sender.lower() in {"system", "you", "‎you"}:
                continue  # skip self and system messages
            ts = _parse_wa_timestamp(date_str, time_str)
            if _is_user_sender(sender):
                if body and not body.startswith("‎"):
                    user_messages.append((ts, body))
                continue
            if sender not in contacts:
                contacts[sender] = {"timestamps": [], "messages": [], "dated": []}
            contacts[sender]["timestamps"].append(ts)
            if body and not body.startswith("‎"):  # skip media stubs
                contacts[sender]["messages"].append(body)
                contacts[sender]["dated"].append((ts, body))

    if not contacts:
        return {"contacts": 0, "attributes": 0}

    # Promises older than the recency window are no longer "open".
    cutoff_iso = (
        datetime.now() - timedelta(days=_commitment_window_days())
    ).isoformat()

    horizon_iso = (datetime.now() - timedelta(days=7)).isoformat()

    def _interleaved(partner_dated: list[tuple[str, str]]) -> list[dict]:
        """Time-ordered both-sides sequence for commitment resolution."""
        seq = [
            {
                "text": b, "from_me": from_me, "ts": t,
                "in_window": t >= cutoff_iso, "recent": t >= horizon_iso,
            }
            for from_me, dated in ((True, user_messages), (False, partner_dated))
            for t, b in dated
        ]
        seq.sort(key=lambda m: m["ts"])
        return seq

    # The user's promises (open_commitments) can only be attributed in a 1:1
    # chat; in a group export the addressee is ambiguous, so they are dropped.
    user_commitments: list[str] = []
    if len(contacts) == 1 and user_messages:
        only_partner = next(iter(contacts.values()))
        user_commitments = _extract_open_commitments(
            _interleaved(only_partner["dated"]), of_user=True
        )

    conn = _connect_graph(db_path)
    n_contacts = 0
    n_attrs = 0
    with conn:
        for sender, data in contacts.items():
            ts_list = sorted(data["timestamps"])
            messages = data["messages"]

            entity_id = _ensure_tier_b_person(
                conn, sender, ts_list[0], ts_list[-1], source="whatsapp"
            )
            n_contacts += 1

            attrs: list[tuple[str, str, float]] = [
                ("relationship_source", "whatsapp", 1.0),
                ("last_contact_at", ts_list[-1], 1.0),
                ("message_count", str(len(ts_list)), 1.0),
            ]

            if messages:
                topics = _extract_topics(messages)
                if topics:
                    attrs.append(("recent_topics", topics, 0.8))

                # The contact's own promises — direction matters: these are
                # promises made TO the user, not the user's open_commitments.
                theirs = _extract_open_commitments(
                    _interleaved(data["dated"]), of_user=False
                )
                if theirs:
                    attrs.append(("commitments_to_me", json.dumps(theirs), 0.75))

            if user_commitments:
                attrs.append(("open_commitments", json.dumps(user_commitments), 0.75))

            for key, value, conf in attrs:
                _upsert_attribute(
                    conn, entity_id, key, value,
                    source="whatsapp", confidence=conf, observed_at=ts_list[-1],
                )
                n_attrs += 1

    conn.close()
    return {"contacts": n_contacts, "attributes": n_attrs}


# ---------------------------------------------------------------------------
# Calendar (.ics)
# ---------------------------------------------------------------------------


def import_ics(ics_path: str, db_path: str) -> dict[str, int]:
    """
    Import Google Calendar .ics.

    Extracts:
      - Attendees as Tier-B person entities with email identifier
      - Per-attendee: event_count, last_event_at, calendar_topics
      - Calendar events as graph_events linked to attendees
    """
    try:
        from icalendar import Calendar
    except ImportError:
        print("  icalendar not installed — run: pip install icalendar")
        return {"attendees": 0, "events": 0, "attributes": 0}

    with open(ics_path, "rb") as f:
        cal = Calendar.from_ical(f.read())

    # attendee_email → {name, timestamps, event_titles, event_descriptions}
    attendees: dict[str, dict[str, Any]] = {}
    events_data: list[dict[str, Any]] = []

    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        dtstart = component.get("dtstart")
        if not dtstart:
            continue
        dt = dtstart.dt
        ts = dt.isoformat() if hasattr(dt, "isoformat") else str(dt)

        summary = str(component.get("summary", "")).strip()
        description = str(component.get("description", "")).strip()
        location = str(component.get("location", "")).strip()

        raw_attendees = component.get("attendee", [])
        if not isinstance(raw_attendees, list):
            raw_attendees = [raw_attendees]

        event_attendee_ids: list[str] = []
        for att in raw_attendees:
            email = str(att).replace("mailto:", "").strip().lower()
            if not email or "@" not in email:
                continue
            cn = str(att.params.get("CN", email)) if hasattr(att, "params") else email
            if email not in attendees:
                attendees[email] = {
                    "name": cn,
                    "email": email,
                    "timestamps": [],
                    "event_titles": [],
                    "event_descriptions": [],
                }
            attendees[email]["timestamps"].append(ts)
            if summary:
                attendees[email]["event_titles"].append(summary)
            if description:
                attendees[email]["event_descriptions"].append(description[:400])
            event_attendee_ids.append(email)

        if summary:
            events_data.append({
                "ts": ts,
                "summary": summary,
                "description": description[:400],
                "location": location,
                "attendee_emails": event_attendee_ids,
            })

    conn = _connect_graph(db_path)
    n_attendees = 0
    n_events = 0
    n_attrs = 0

    with conn:
        # Upsert attendee entities first
        email_to_entity: dict[str, str] = {}
        for email, data in attendees.items():
            ts_list = sorted(data["timestamps"])
            entity_id = _ensure_tier_b_person(
                conn, data["name"], ts_list[0], ts_list[-1],
                source="calendar", contact_id=email,
            )
            email_to_entity[email] = entity_id
            n_attendees += 1

            attrs: list[tuple[str, str, float]] = [
                ("relationship_source", "calendar", 1.0),
                ("contact_identifier", email, 1.0),
                ("last_event_at", ts_list[-1], 1.0),
                ("event_count", str(len(ts_list)), 1.0),
            ]

            all_text = data["event_titles"] + data["event_descriptions"]
            topics = _extract_topics(all_text)
            if topics:
                attrs.append(("calendar_topics", topics, 0.8))

            for key, value, conf in attrs:
                _upsert_attribute(conn, entity_id, key, value, source="calendar", confidence=conf)
                n_attrs += 1

        # Insert calendar events as graph_events
        for ev in events_data:
            event_type = _normalize(ev["summary"])[:100]
            meta = json.dumps({
                "location": ev["location"],
                "description": ev["description"][:200],
                "source": "calendar",
            }, sort_keys=True)
            row = conn.execute(
                "SELECT id FROM graph_events WHERE event_type=? AND last_seen_at>=?",
                (event_type, ev["ts"]),
            ).fetchone()
            if not row:
                conn.execute(
                    """INSERT INTO graph_events
                       (id, event_type, summary, first_seen_at, last_seen_at,
                        confidence, observation_count, status, metadata_json)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (str(uuid4()), event_type, ev["summary"],
                     ev["ts"], ev["ts"], 0.9, 1, "current", meta),
                )
                n_events += 1

    conn.close()
    return {"attendees": n_attendees, "events": n_events, "attributes": n_attrs}


# ---------------------------------------------------------------------------
# iMessage
# ---------------------------------------------------------------------------


def import_imessage(db_path: str) -> dict[str, int]:
    """
    Import iMessage contacts and content from ~/Library/Messages/chat.db.

    Requires macOS Full Disk Access for Terminal/Python.

    Extracts per-handle:
      - first/last contact, message count
      - recent topics (keyword summary of last 100 messages)
      - open commitments (promise sentences)
    """
    imessage_db = Path.home() / "Library" / "Messages" / "chat.db"
    if not imessage_db.exists():
        print(f"  iMessage DB not found at {imessage_db}")
        return {"contacts": 0, "attributes": 0}

    im_conn = sqlite3.connect(str(imessage_db))
    im_conn.row_factory = sqlite3.Row

    try:
        rows = im_conn.execute("""
            SELECT
                h.id                       AS handle,
                MIN(m.date)                AS first_msg_raw,
                MAX(m.date)                AS last_msg_raw,
                COUNT(*)                   AS msg_count,
                GROUP_CONCAT(
                    CASE WHEN m.is_from_me = 0 AND m.text IS NOT NULL
                         THEN SUBSTR(m.text, 1, 300) END,
                    '|||'
                )                          AS their_texts,
                GROUP_CONCAT(
                    CASE WHEN m.is_from_me = 1 AND m.text IS NOT NULL
                         THEN SUBSTR(m.text, 1, 300) END,
                    '|||'
                )                          AS my_texts
            FROM handle h
            JOIN message m ON m.handle_id = h.rowid
            WHERE m.text IS NOT NULL AND LENGTH(TRIM(m.text)) > 0
            GROUP BY h.id
            ORDER BY MAX(m.date) DESC
        """).fetchall()
    except sqlite3.OperationalError as e:
        print(f"  iMessage read error (may need Full Disk Access): {e}")
        im_conn.close()
        return {"contacts": 0, "attributes": 0}
    finally:
        im_conn.close()

    conn = _connect_graph(db_path)
    n_contacts = 0
    n_attrs = 0

    with conn:
        for row in rows:
            handle = (row["handle"] or "").strip()
            if not handle:
                continue

            def _apple_ts(raw: int | None) -> str:
                if not raw:
                    return datetime.now(timezone.utc).isoformat()
                return datetime.fromtimestamp(
                    raw / 1e9 + APPLE_EPOCH_OFFSET, tz=timezone.utc
                ).isoformat()

            first_ts = _apple_ts(row["first_msg_raw"])
            last_ts = _apple_ts(row["last_msg_raw"])

            # Use phone/email as both label and contact_identifier
            entity_id = _ensure_tier_b_person(
                conn, handle, first_ts, last_ts,
                source="imessage", contact_id=handle,
            )
            n_contacts += 1

            attrs: list[tuple[str, str, float]] = [
                ("relationship_source", "imessage", 1.0),
                ("contact_identifier", handle, 1.0),
                ("last_contact_at", last_ts, 1.0),
                ("message_count", str(row["msg_count"]), 1.0),
            ]

            # Topic extraction from their messages (more signal-rich than our own)
            their_msgs = [t for t in (row["their_texts"] or "").split("|||") if t.strip()]
            my_msgs = [t for t in (row["my_texts"] or "").split("|||") if t.strip()]
            all_msgs = their_msgs + my_msgs

            if all_msgs:
                topics = _extract_topics(all_msgs)
                if topics:
                    attrs.append(("recent_topics", topics, 0.8))

            if my_msgs:
                commitments = _extract_commitments(my_msgs)
                if commitments:
                    attrs.append(("open_commitments", json.dumps(commitments), 0.75))

            for key, value, conf in attrs:
                _upsert_attribute(conn, entity_id, key, value, source="imessage", confidence=conf)
                n_attrs += 1

    conn.close()
    return {"contacts": n_contacts, "attributes": n_attrs}


# ---------------------------------------------------------------------------
# WhatsApp iOS SQLite (ChatStorage.sqlite / ZWAMESSAGE schema)
# ---------------------------------------------------------------------------

_WA_MEDIA_KINDS = {
    1: "photo", 2: "video", 3: "voice message", 4: "contact card",
    5: "location", 7: "link", 8: "document", 11: "gif", 38: "sticker",
}


def _store_message_corpus(conn: sqlite3.Connection, codec, entity_id: str, msgs: list[dict]) -> int:
    """Replace one contact's encrypted message corpus (same txn as import)."""
    conn.execute("DELETE FROM graph_messages WHERE entity_id=?", (entity_id,))
    n = 0
    for m in msgs:
        kind = m.get("media_kind")
        if kind:
            text = f"[{kind}]" + (f" {m['caption']}" if m.get("caption") else "")
        else:
            text = (m.get("text") or "").strip()
        if not text:
            continue
        ts = m.get("ts")
        sent_at = (
            datetime.fromtimestamp(float(ts) + APPLE_EPOCH_OFFSET, tz=timezone.utc).isoformat()
            if ts else ""
        )
        conn.execute(
            """INSERT INTO graph_messages
               (id, entity_id, sent_at, from_me, text_enc, text_length, media_kind)
               VALUES (?,?,?,?,?,?,?)""",
            (str(uuid4()), entity_id, sent_at, 1 if m.get("from_me") else 0,
             codec.encrypt(text), len(text), kind),
        )
        n += 1
    return n


def import_whatsapp_sqlite(wa_db_path: str, db_path: str) -> dict[str, int]:
    """
    Import from WhatsApp's native iOS SQLite backup format.

    Tables used:
      ZWACHATSESSION — one row per conversation (ZPARTNERNAME, ZCONTACTJID,
                       ZLASTMESSAGEDATE, ZMESSAGECOUNTER)
      ZWAMESSAGE     — messages (ZTEXT, ZISFROMME, ZMESSAGEDATE, ZMESSAGETYPE,
                       ZCHATSESSION → FK to ZWACHATSESSION.Z_PK)

    Skips group chats (JID ends in @g.us), media-only messages (ZMESSAGETYPE != 0),
    and null/empty ZTEXT.
    """
    wa_conn = sqlite3.connect(wa_db_path)
    wa_conn.row_factory = sqlite3.Row

    # Pull all 1-on-1 chat sessions with meaningful names
    sessions = wa_conn.execute("""
        SELECT Z_PK, ZCONTACTJID, ZPARTNERNAME, ZLASTMESSAGEDATE, ZMESSAGECOUNTER
        FROM ZWACHATSESSION
        WHERE ZCONTACTJID NOT LIKE '%@g.us'
          AND ZCONTACTJID != '0@status'
          AND ZCONTACTJID NOT LIKE '%@broadcast'
          AND ZPARTNERNAME IS NOT NULL
          AND TRIM(ZPARTNERNAME) != ''
          AND TRIM(ZPARTNERNAME) != '‎You'
        ORDER BY ZLASTMESSAGEDATE DESC
    """).fetchall()

    # Pull messages per session — we batch by session PK
    session_pks = [str(s["Z_PK"]) for s in sessions]
    if not session_pks:
        wa_conn.close()
        return {"contacts": 0, "attributes": 0}

    # Build session_pk → message lists dict
    placeholders = ",".join("?" * len(session_pks))
    # Text messages AND media rows: a photo/voice message is an event in the
    # lived record (often with a caption) — "what photo did I send on Feb 14"
    # must be answerable even though the image itself is never stored.
    msg_rows = wa_conn.execute(f"""
        SELECT ZCHATSESSION, ZTEXT, ZISFROMME, ZMESSAGEDATE, ZMESSAGETYPE
        FROM ZWAMESSAGE
        WHERE ZCHATSESSION IN ({placeholders})
          AND ((ZMESSAGETYPE = 0 AND ZTEXT IS NOT NULL AND LENGTH(TRIM(ZTEXT)) > 0)
               OR ZMESSAGETYPE IN (1, 2, 3, 4, 5, 7, 8, 11, 38))
        ORDER BY ZMESSAGEDATE ASC
    """, [int(pk) for pk in session_pks]).fetchall()
    wa_conn.close()

    # Group messages by session
    from collections import defaultdict
    msgs_by_session: dict[int, list[dict]] = defaultdict(list)
    for m in msg_rows:
        mtype = m["ZMESSAGETYPE"] or 0
        msgs_by_session[m["ZCHATSESSION"]].append({
            # digests (topics/commitments/arc) read "text": keep media rows'
            # captions but never bare placeholders
            "text": m["ZTEXT"] if mtype == 0 else None,
            "caption": (m["ZTEXT"] or "").strip() if mtype != 0 else "",
            "media_kind": _WA_MEDIA_KINDS.get(mtype) if mtype != 0 else None,
            "from_me": bool(m["ZISFROMME"]),
            "ts": m["ZMESSAGEDATE"],
        })

    def _wa_ts(raw: float | None) -> str:
        if not raw:
            return datetime.now(timezone.utc).isoformat()
        return datetime.fromtimestamp(float(raw) + APPLE_EPOCH_OFFSET, tz=timezone.utc).isoformat()

    from soma_hub.crypto import EncryptedTextCodec

    conn = _connect_graph(db_path)
    codec = EncryptedTextCodec.from_env_or_file(Path(db_path).parent)
    n_contacts = 0
    n_attrs = 0
    n_msgs = 0

    # Apple-epoch cutoffs: commitment recency window + short-horizon lapse.
    commitment_cutoff = (
        datetime.now(timezone.utc) - timedelta(days=_commitment_window_days())
    ).timestamp() - APPLE_EPOCH_OFFSET
    horizon_cutoff = (
        datetime.now(timezone.utc) - timedelta(days=7)
    ).timestamp() - APPLE_EPOCH_OFFSET

    # ChatStorage keeps duplicate session rows per contact (e.g. re-registered
    # numbers), some with NULL ZLASTMESSAGEDATE. Merge sessions by cleaned
    # name first — otherwise whichever row is processed last stomps the
    # others' attributes on upsert, and NULL dates falsely become "now".
    merged: dict[str, dict[str, Any]] = {}
    for session in sessions:
        name = _clean_contact_name((session["ZPARTNERNAME"] or "").strip())
        if not name:
            continue
        agg = merged.setdefault(
            name, {"jid": "", "msgs": [], "counter": 0, "last_raw": None}
        )
        agg["msgs"].extend(msgs_by_session.get(session["Z_PK"], []))
        agg["counter"] += session["ZMESSAGECOUNTER"] or 0
        if not agg["jid"]:
            agg["jid"] = (session["ZCONTACTJID"] or "").strip()
        raw_last = session["ZLASTMESSAGEDATE"]
        if raw_last and (agg["last_raw"] is None or raw_last > agg["last_raw"]):
            agg["last_raw"] = raw_last

    with conn:
        for name, agg in merged.items():
            jid = agg["jid"]
            msgs = sorted(agg["msgs"], key=lambda m: m["ts"] or 0)
            all_texts = [m["text"] for m in msgs if m["text"]]
            my_texts = [m["text"] for m in msgs if m["from_me"] and m["text"]]
            their_texts = [m["text"] for m in msgs if not m["from_me"] and m["text"]]

            ts_vals = [m["ts"] for m in msgs if m["ts"]]
            # Never fall back to wall-clock for message-derived dates: a
            # missing session date means "use the newest actual message",
            # and with no messages at all the fact is simply not written.
            last_raw = agg["last_raw"] or (max(ts_vals) if ts_vals else None)
            first_ts = _wa_ts(min(ts_vals)) if ts_vals else None
            last_ts = _wa_ts(last_raw) if last_raw else None

            entity_id = _ensure_tier_b_person(
                conn, name, first_ts or _wa_ts(None), last_ts or first_ts or _wa_ts(None),
                source="whatsapp", contact_id=jid,
            )
            n_contacts += 1

            msg_count = agg["counter"] or len(msgs)
            attrs: list[tuple[str, str, float]] = [
                ("relationship_source", "whatsapp", 1.0),
                ("contact_identifier", jid, 1.0),
                ("message_count", str(msg_count), 1.0),
            ]
            if last_ts:
                attrs.append(("last_contact_at", last_ts[:10], 1.0))

            # Topic extraction from ALL messages (their msgs weighted for recency signal)
            topics = _extract_topics(all_texts)
            if topics:
                attrs.append(("recent_topics", topics, 0.8))

            # recent_messages: arc-sampled across full history for grounded synthesis.
            # 3 early + 4 middle + 3 recent gives Gemma a relationship arc, not a snapshot.
            def _is_substantive(text: str) -> bool:
                text = text.strip()
                if len(text) < 25:
                    return False
                if text.startswith("<"):
                    return False
                if " " not in text:  # single-token messages carry nothing
                    return False
                non_word = sum(1 for c in text if not c.isascii() and not c.isalnum())
                if non_word / len(text) > 0.5:  # >50% emoji / non-ASCII
                    return False
                return True

            def _arc_sample(messages: list[dict]) -> list[str]:
                labelled = [
                    ("ME" if m.get("from_me") else "THEM", (m.get("text") or "").strip())
                    for m in messages
                ]
                # Build pool of (index, label, text) that pass the filter
                pool = [
                    (i, lbl, txt)
                    for i, (lbl, txt) in enumerate(labelled)
                    if _is_substantive(txt)
                ]
                if not pool:
                    return []
                n = len(pool)
                # Early: first 3 from the pool
                early = pool[:3]
                # Middle: 4 evenly spaced from the middle 50% of the pool
                mid_start, mid_end = n // 4, 3 * n // 4
                mid_pool = pool[mid_start:mid_end]
                step = max(1, len(mid_pool) // 4)
                middle = mid_pool[::step][:4]
                # Recent: last 3 from the pool
                recent = pool[-3:]
                # Merge in index order, deduplicate by text
                seen: set[str] = set()
                result: list[str] = []
                for _, lbl, txt in sorted(early + middle + recent, key=lambda x: x[0]):
                    if txt not in seen:
                        seen.add(txt)
                        result.append(f"{lbl}: {txt}")
                return result

            arc = _arc_sample(msgs)
            if arc:
                attrs.append(("recent_messages", "\n".join(arc), 0.7))

            # Commitment extraction from MY sent messages inside the recency
            # window — an "open" promise from years ago is noise, not memory,
            # and a promise the later chat shows was fulfilled is dropped.
            # Always write the attribute — even an empty list — so that a stricter
            # run never leaves a stale value from a previous import in the DB.
            if my_texts:
                for m in msgs:
                    m["in_window"] = bool(
                        m["ts"] and float(m["ts"]) >= commitment_cutoff
                    )
                    m["recent"] = bool(
                        m["ts"] and float(m["ts"]) >= horizon_cutoff
                    )
                commits = _extract_open_commitments(msgs, of_user=True)
                attrs.append(("open_commitments", json.dumps(commits), 0.75))

            for key, value, conf in attrs:
                _upsert_attribute(
                    conn, entity_id, key, value,
                    source="whatsapp", confidence=conf, observed_at=last_ts,
                )
                n_attrs += 1

            # Archive zombie duplicates: entities created by older import
            # runs under a differently-cleaned name still claim this JID and
            # would surface stale facts in recall forever.
            if jid:
                conn.execute(
                    """UPDATE graph_entities SET status='archived'
                       WHERE kind='person' AND status != 'archived' AND id != ?
                         AND id IN (SELECT entity_id FROM graph_attributes
                                    WHERE attribute_key='contact_identifier'
                                      AND attribute_value=?)""",
                    (entity_id, jid),
                )

            n_msgs += _store_message_corpus(conn, codec, entity_id, msgs)

    conn.close()
    return {"contacts": n_contacts, "attributes": n_attrs, "messages": n_msgs}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Pre-populate SOMA Tier-B graph from existing user data."
    )
    parser.add_argument("--db", required=True, help="Path to soma_hub.sqlite3")
    parser.add_argument("--whatsapp", help="Path to WhatsApp _chat.txt export")
    parser.add_argument("--whatsapp-sqlite", help="Path to WhatsApp iOS backup SQLite (ChatStorage.sqlite / 1.sqlite)")
    parser.add_argument("--ics", help="Path to Google Calendar .ics export")
    parser.add_argument("--imessage", action="store_true", help="Import from iMessage (macOS)")
    args = parser.parse_args()

    if args.whatsapp:
        r = import_whatsapp(args.whatsapp, args.db)
        print(f"WhatsApp: {r['contacts']} contacts, {r['attributes']} attributes extracted")
    if args.whatsapp_sqlite:
        r = import_whatsapp_sqlite(args.whatsapp_sqlite, args.db)
        print(f"WhatsApp SQLite: {r['contacts']} contacts, {r['attributes']} attributes extracted")
    if args.ics:
        r = import_ics(args.ics, args.db)
        print(f"Calendar: {r['attendees']} attendees, {r['events']} events, {r['attributes']} attributes extracted")
    if args.imessage:
        r = import_imessage(args.db)
        print(f"iMessage: {r['contacts']} contacts, {r['attributes']} attributes extracted")

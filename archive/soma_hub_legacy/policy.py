from __future__ import annotations

import re
from dataclasses import dataclass


SENSITIVE_PATTERNS = {
    "phone_number": re.compile(r"\b(?:\+?\d[\s().-]?){7,}\b"),
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    "url": re.compile(r"https?://\S+|www\.\S+", re.I),
    "long_number": re.compile(r"\b\d{5,}\b"),
}

EXTRACTION_REQUEST_WORDS = (
    "exact",
    "verbatim",
    "transcript",
    "raw",
    "phone number",
    "password",
    "pin",
    "credit card",
    "email address",
    "list all",
    "everything you saw",
    "everything you heard",
)


@dataclass(frozen=True)
class RecallDecision:
    allowed: bool
    intent: str
    reason: str


def redact_for_public_summary(text: str) -> str:
    redacted = text.strip()
    for label, pattern in SENSITIVE_PATTERNS.items():
        redacted = pattern.sub(f"[{label} hidden]", redacted)
    redacted = " ".join(redacted.split())
    if len(redacted) > 160:
        redacted = redacted[:157].rstrip() + "..."
    return redacted


def classify_memory(text: str) -> tuple[str, str]:
    lower = text.lower()
    sensitivity = "normal"
    if any(pattern.search(text) for pattern in SENSITIVE_PATTERNS.values()):
        sensitivity = "restricted"
    if any(word in lower for word in ("password", "credit card", "passport", "medical", "doctor")):
        sensitivity = "restricted"

    if any(word in lower for word in ("put ", "placed ", "left ", "keys", "wallet", "bag", "backpack")):
        return "object_location", sensitivity
    if any(word in lower for word in ("said", "talked", "meeting", "conversation", "discussed")):
        return "conversation", sensitivity
    return "general", sensitivity


def decide_recall_intent(message: str) -> RecallDecision:
    lower = message.lower().strip().rstrip("?")
    if any(word in lower for word in EXTRACTION_REQUEST_WORDS):
        return RecallDecision(
            allowed=False,
            intent="disallowed_extraction",
            reason="I cannot expose hidden extracted memory, exact transcripts, credentials, identifiers, or raw details.",
        )
    if (
        lower.startswith("where are ")
        or "where did i put" in lower
        or re.match(r"^where(?:'s| is| was)?\s+(?:my |the )?[a-z ]+$", lower)
        or re.match(r"^wo ist\s+(?:mein |meine |meinen |der |die |das )?[a-zäöüß ]+$", lower)
    ):
        return RecallDecision(True, "where_is", "object-location recall")
    if lower.startswith("delete ") or lower.startswith("forget "):
        return RecallDecision(True, "delete_scope", "memory deletion")
    # Tier-B relationship recall — commitments
    if re.search(
        r"\b(?:commit\w*|promis\w*|owe|agreed|pending|outstanding|"
        r"what did i (?:say|tell|promise)|what (?:do|did) i owe)\b",
        lower,
    ):
        return RecallDecision(True, "commitments", "open commitments lookup")
    # Tier-B relationship recall — last contact / recency
    if re.search(
        r"\b(?:last (?:talk|spoke|contact|messag|heard from|saw)|"
        r"when did i (?:last )?(?:talk|speak|messag|contact|hear from)|"
        r"how long (?:since|ago)|last time)\b",
        lower,
    ):
        return RecallDecision(True, "last_contact", "last contact lookup")
    # Entity profile lookup — "who is X", "tell me about X", "what do I know about X"
    if re.search(
        r"\b(?:who is|tell me about|what do i know about|describe|"
        r"what(?:'s| is) (?:the )?story with|profile of|info (?:on|about))\b",
        lower,
    ):
        return RecallDecision(True, "who_is", "entity profile lookup")
    # Owner message-content search — "what was the long message I wrote to X",
    # "what message mentioned good friday". The owner reading their own
    # corpus is the product, not an extraction risk (local-first).
    if re.search(
        r"\b(?:what (?:was|is) the (?:long(?:est)?|last|first) message|"
        r"what message|which message|find (?:the |a )?message|"
        r"what did i (?:write|send|text)|message i (?:wrote|sent)|"
        r"what (?:photo|picture|image|video|voice message|file|document)s? "
        r"did (?:i|they|he|she)\b|"
        r"(?:last|latest|recent) (?:conversation|chat|messages?|exchange) with|"
        r"what (?:was|were) (?:my|our) (?:last|latest|recent) (?:conversation|chat|messages?)|"
        r"mention(?:ed)? in (?:my|our) (?:conversation|chat))\b",
        lower,
    ):
        return RecallDecision(True, "message_search", "scoped message content search")
    # Person-scoped topic lookup must win over the generic "recent" branch:
    # "what were the recent topics with Navaneethcrshna" is about HIM.
    if re.search(r"\btopics? (?:with|about|of)\b", lower):
        return RecallDecision(True, "who_is", "person topics lookup")
    # Past-context lookup — "what did we discuss", "what did Sophia and I discuss", etc.
    if re.search(
        r"\b(?:what (?:did|was) (?:we|they|he|she)|"
        r"what did \w+ and (?:i|me)\b|"
        r"discuss(?:ed)?|talked about|what happened with|what came up|tell me what)\b",
        lower,
    ):
        return RecallDecision(True, "what_was", "past context lookup")
    # Recent-context — camera-derived observations, or recent contact activity
    if re.search(r"\b(?:recent(?:ly)?|lately|today|what happened|who have i (?:been )?(?:talk|speak|messag|contact))\b", lower):
        return RecallDecision(True, "recent_context", "recent-context summary")
    return RecallDecision(True, "general_summary", "safe summary")

#!/usr/bin/env python3
"""Sprint 1 — the WEARER ('me') as a first-class entity (structural, CPU-only, no LLM).

The brain's worst mis-attribution bug: "what was I wearing" returns a STRANGER's outfit
because every caption says "the person is wearing ...". The 4-bit captioner cannot tell the
camera-wearer apart from the woman at the breakfast counter — so neither can a prompt. We fix
it with STRUCTURE: detect the frames that are EGOCENTRIC (about the wearer) by their cues, and
read the wearer's attributes only from those. 'my clothes', not a passer-by's.

EGOCENTRIC CUES we trust (each is a structural signal the captioner emits about the POV holder):
  - explicit POV phrasing: "first-person", "point of view", "looking down at ...".
  - the wearer's own body in frame: "the person's hand(s)/arm/wrist", "their hand", a hand
    HOLDING / reaching / gripping (you only see your OWN hands holding the camera-side object).
  - worn-on-self items read off those hands/feet: a watch/bracelet "on their left wrist",
    crocs/socks/pants "on their feet" — these co-occur with the hand cue, i.e. the wearer.
  - first-person language ("my").
  - being ADDRESSED by name in speech ("Okay, Joe, see you") — that name is the wearer's.

We deliberately DON'T treat a bare "a person/woman/man is wearing ..." (no hand/POV cue) as the
wearer — that is exactly the stranger trap (the counter clerk, the table opposite). Confidence is
borrowed from evidence_confidence.CHANNEL_REL so callers can threshold uniformly.

API:
  self_observations(memory_dir) -> [{t, cue, text, channel}]    # frames that are about the wearer
  self_attributes(memory_dir)   -> {clothing:[...], accessories:[...], name:str|None, confidence}

CLI / UNIT TEST (CPU-only, no ollama):
  python scripts/self_entity.py <memory_dir>          # prints detected self attributes + name
  python scripts/self_entity.py --selftest <memory_dir>   # asserts crocs/sweatpants/watch + 'Joe'
"""
from __future__ import annotations
import json
import os
import re
import sys

# Reuse the channel-reliability table so 'self' confidence is on the SAME scale as the rest of
# the structural brain. Fall back to a local copy if imported standalone.
try:
    from evidence_confidence import CHANNEL_REL, load_observations
except Exception:  # pragma: no cover - allow `python scripts/self_entity.py`
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from evidence_confidence import CHANNEL_REL, load_observations
    except Exception:
        CHANNEL_REL = {"speech": 0.92, "ocr": 0.90, "screen": 0.88, "world": 0.60, "caption": 0.40}
        load_observations = None  # type: ignore


# ---------------------------------------------------------------------------
# Egocentric-cue detection over a single caption/ocr/speech string.
# ---------------------------------------------------------------------------

# Phrases that mark the frame as the WEARER's point of view.
_POV_RE = re.compile(
    r"first[\s-]person|point of view|pov\b|looking down (?:at|toward)|from (?:the|their|a) (?:rider|wearer|person)'s (?:perspective|point of view)",
    re.I,
)
# The wearer's own body in frame. We require a possessive ("person's"/"their"/"the rider's")
# or a holding/gripping verb — that is the camera-side hand, i.e. the wearer's. We also count
# "feet/legs are visible" (looking down at your own feet is an egocentric staple) and a hand/arm
# in the "foreground" (the camera-near hand is the wearer's, not a background passer-by's).
_OWN_BODY_RE = re.compile(
    r"(?:person's|persons|their|rider's|wearer's|a)\s+(?:hand|hands|arm|arms|wrist|fingers|feet|foot|legs?)\b"
    r"|(?:hand|hands|arm|feet|foot|legs?)\s+(?:is|are)?\s*(?:visible|holding|gripping|reaching|resting|interacting|pointing|pushing|zipping|tying|folding|rummaging|packing|extended|crossed)"
    r"|(?:holding|gripping)\s+the\s+handlebars",
    re.I,
)
_MY_RE = re.compile(r"\bmy\b|\bmine\b|\bmyself\b", re.I)

# Items read as WORN-ON-SELF. We only count these when the frame already has a body/POV cue
# (else "a person is wearing crocs" could be a stranger). The value lists are intentionally
# generic so this generalizes past this one clip.
_CLOTHING_RE = re.compile(
    r"\b(?:crocs?|sweatpants|sweat pants|joggers|t-?shirt|shirt|hoodie|jacket|pants|trousers|shorts|"
    r"socks?|shoes?|sneakers?|sandals?|jeans|sleeve|shorts)\b",
    re.I,
)
_ACCESSORY_RE = re.compile(
    r"\b(?:watch|wristwatch|smartwatch|bracelet|wristband|band|ring|glasses|eyewear|spectacles|"
    r"backpack|hat|cap|necklace|earbuds?)\b",
    re.I,
)
# A "wearing ... on their wrist/feet/left wrist" clause anchors the item to the wearer's body.
_WORN_CLAUSE_RE = re.compile(
    r"(?:wearing|wears|with)\s+([^.,;]{0,80}?)\b"
    r"(?:on (?:their|the|his|her) (?:left |right )?(?:wrist|feet|foot|hand|hands|legs?)\b"
    r"|on their feet\b)",
    re.I,
)


def _classify_cues(text):
    """Return the set of egocentric cue labels this string carries (possibly empty)."""
    cues = set()
    if not text:
        return cues
    if _POV_RE.search(text):
        cues.add("pov")
    if _OWN_BODY_RE.search(text):
        cues.add("own_body")
    if _MY_RE.search(text):
        cues.add("first_person")
    return cues


# ---------------------------------------------------------------------------
# Name from speech: who is the wearer ADDRESSED as?
# ---------------------------------------------------------------------------

# A vocative is a name set off by commas/greeting words. We distinguish two cases:
#   * the wearer is the ADDRESSEE  -> "Okay, Joe, see you" / "bye Joe" / "see you, Joe"
#     (a farewell/greeting aimed AT the camera holder -> that's the wearer's name)
#   * the wearer is the SPEAKER addressing someone ELSE -> "What's up, Brett?" (NOT the wearer)
# We can't perfectly diarize from text, but a name inside a "see you / have a good day / good
# morning / bye" farewell directed at a single person is a strong wearer-name signal, whereas
# "what's up, NAME" is the wearer hailing a friend. We score candidates and pick the best.
_NOT_NAMES = set(
    "okay ok yeah yes no hey hi bye hello morning afternoon evening night good later dude bro "
    "man sir maam ma'am guys everyone there here see you have day what up".split()
)
_NAME_TOKEN = r"([A-Z][a-z]+)"
# farewell/greeting words that, when next to a vocative, mean the line is aimed AT the listener
_ADDRESS_FAREWELL_RE = re.compile(
    r"(?:see you|have a good day|good morning|good night|good evening|take care|bye|goodbye|catch you)",
    re.I,
)
# "what's up, NAME" / "yo NAME" -> the wearer is hailing someone else
_HAIL_OTHER_RE = re.compile(r"(?:what'?s up|whats up|yo|sup)\b[\s,]*" + _NAME_TOKEN)


def _candidate_names_from_segment(text):
    """Yield (name, kind) where kind in {'addressee','other'} for vocatives in one ASR segment."""
    if not text:
        return
    # names the wearer is hailing (someone ELSE)
    for m in _HAIL_OTHER_RE.finditer(text):
        nm = m.group(1)
        if nm.lower() not in _NOT_NAMES:
            yield nm, "other"
    # vocatives: a capitalized token bounded by commas, optionally inside a farewell.
    # e.g. "Okay, Joe, see you." -> Joe between commas, line contains a farewell -> addressee.
    for m in re.finditer(r"(?:^|[,\s])" + _NAME_TOKEN + r"(?=[,\.\?!])", text):
        nm = m.group(1)
        if nm.lower() in _NOT_NAMES:
            continue
        if _HAIL_OTHER_RE.search(text):
            # already captured the hailed name above; skip a duplicate as addressee
            continue
        kind = "addressee" if _ADDRESS_FAREWELL_RE.search(text) else "other"
        yield nm, kind


def _detect_name(observations):
    """Return (name|None, confidence). Prefer a name that the wearer is ADDRESSED by in a
    farewell/greeting; demote names the wearer is hailing. Speech channel -> high reliability."""
    score = {}  # name -> net score (addressee +2, other -1)
    for t, ch, tx in observations:
        if ch != "speech":
            continue
        for nm, kind in _candidate_names_from_segment(tx):
            score.setdefault(nm, 0)
            score[nm] += 2 if kind == "addressee" else -1
    addressee = {n: s for n, s in score.items() if s > 0}
    if not addressee:
        return None, 0.0
    name = max(addressee, key=addressee.get)
    # confidence: speech reliability, dampened if the signal was weak/contested
    conf = CHANNEL_REL.get("speech", 0.92)
    if addressee[name] < 2:
        conf = round(conf * 0.7, 3)
    return name, round(conf, 3)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _iter_observations(memory_dir):
    if load_observations is not None:
        return load_observations(memory_dir)
    # minimal local fallback (kf captions/ocr + asr) if evidence_confidence is unavailable
    obs = []
    try:
        kf = json.load(open(os.path.join(memory_dir, "kf_memory.json")))
    except Exception:
        kf = []
    for r in kf if isinstance(kf, list) else []:
        obs.append((r.get("t"), "caption", r.get("caption") or ""))
        ocr = r.get("ocr") or []
        obs.append((r.get("t"), "ocr", " ".join(ocr) if isinstance(ocr, list) else str(ocr)))
    try:
        asr = json.load(open(os.path.join(memory_dir, "asr.json")))
        for s in asr.get("segments", []):
            obs.append((s.get("start"), "speech", s.get("text") or ""))
    except Exception:
        pass
    return [(t, ch, tx) for (t, ch, tx) in obs if (tx or "").strip()]


def self_observations(memory_dir):
    """Frames that are ABOUT the wearer. Each item: {t, cue, text, channel}.

    A frame qualifies if its caption carries an egocentric cue (POV phrasing, the wearer's own
    hand/arm in frame, or first-person language). We attach the strongest cue label so callers can
    audit WHY a frame was treated as 'me'."""
    out = []
    for t, ch, tx in _iter_observations(memory_dir):
        if ch != "caption":
            continue
        cues = _classify_cues(tx)
        if not cues:
            continue
        # strongest first: explicit POV > own body > first-person language
        cue = "pov" if "pov" in cues else ("own_body" if "own_body" in cues else "first_person")
        out.append({"t": t, "cue": cue, "text": tx, "channel": ch})
    return out


def _norm_item(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def self_attributes(memory_dir):
    """The wearer's attributes, read ONLY from egocentric frames + speech.

    Returns {clothing:[...], accessories:[...], name:str|None, confidence}. Clothing/accessory
    terms are collected only from frames that ALSO have a body/POV cue (so a stranger's outfit
    never leaks in). Confidence is the caption reliability boosted toward 1.0 when many egocentric
    frames corroborate the wearer (the wearer's body recurs; a one-frame stranger does not)."""
    ego = self_observations(memory_dir)

    clothing, accessories = {}, {}  # term -> support count (frames)
    for fr in ego:
        tx = fr["text"]
        # Prefer attributes inside an explicit "worn ... on their wrist/feet" clause; those are
        # unambiguously on the wearer's body. Then fall back to any clothing/accessory token in
        # an egocentric frame.
        worn_spans = " ".join(m.group(1) for m in _WORN_CLAUSE_RE.finditer(tx))
        for src in (worn_spans, tx):
            for m in _CLOTHING_RE.finditer(src):
                term = _norm_item(m.group(0)).replace("sweat pants", "sweatpants")
                clothing[term] = clothing.get(term, 0) + 1
            for m in _ACCESSORY_RE.finditer(src):
                term = _norm_item(m.group(0))
                accessories[term] = accessories.get(term, 0) + 1
            if worn_spans:  # don't double-count the same frame's whole-text pass when we had a clause
                break

    # Order by how often the wearer's frames mention them (recurrence = it's really on me).
    clothing_list = [w for w, _ in sorted(clothing.items(), key=lambda x: (-x[1], x[0]))]
    accessory_list = [w for w, _ in sorted(accessories.items(), key=lambda x: (-x[1], x[0]))]

    name, name_conf = _detect_name(_iter_observations(memory_dir))

    # Confidence for the visual attributes: caption is the source (0.40) but corroboration across
    # MANY egocentric frames raises it — same structural logic as evidence_confidence's >=2 boost.
    base = CHANNEL_REL.get("caption", 0.40)
    n_ego = len(ego)
    if n_ego >= 8:
        vis_conf = min(1.0, base + 0.30)
    elif n_ego >= 3:
        vis_conf = min(1.0, base + 0.20)
    elif n_ego >= 1:
        vis_conf = base
    else:
        vis_conf = 0.0
    # Overall self-entity confidence: blend visual recurrence with the (high) name signal if present.
    confidence = round(max(vis_conf, name_conf) if name else vis_conf, 3)

    return {
        "clothing": clothing_list,
        "accessories": accessory_list,
        "name": name,
        "confidence": confidence,
        "n_egocentric_frames": n_ego,
        "name_confidence": name_conf,
    }


# ---------------------------------------------------------------------------
# CLI / unit test (CPU-only — never calls an LLM)
# ---------------------------------------------------------------------------

def main(argv):
    selftest = False
    if argv and argv[0] == "--selftest":
        selftest = True
        argv = argv[1:]
    if not argv:
        print("usage: self_entity.py [--selftest] <memory_dir>")
        return 2
    mdir = argv[0]

    ego = self_observations(mdir)
    attrs = self_attributes(mdir)

    print("memory_dir: %s" % mdir)
    print("egocentric (about-the-wearer) frames: %d" % len(ego))
    for fr in ego[:6]:
        snippet = re.sub(r"\s+", " ", fr["text"])[:90]
        print("   t=%-6s cue=%-12s %s..." % (fr["t"], fr["cue"], snippet))
    if len(ego) > 6:
        print("   ... (+%d more)" % (len(ego) - 6))

    print("\nSELF ATTRIBUTES:")
    print("   name:        %r  (name_conf=%.3f)" % (attrs["name"], attrs["name_confidence"]))
    print("   clothing:    %s" % ", ".join(attrs["clothing"]) or "   clothing:    (none)")
    print("   accessories: %s" % ", ".join(attrs["accessories"]))
    print("   confidence:  %.3f  (over %d egocentric frames)" % (attrs["confidence"], attrs["n_egocentric_frames"]))

    if selftest:
        cloth = set(attrs["clothing"])
        acc = set(attrs["accessories"])
        checks = {
            "crocs detected": "crocs" in cloth,
            "sweatpants detected": "sweatpants" in cloth,
            "watch detected": ("watch" in acc or "wristwatch" in acc or "smartwatch" in acc),
            "name is Joe": attrs["name"] == "Joe",
            "egocentric frames found": attrs["n_egocentric_frames"] > 0,
        }
        print("\nSELFTEST:")
        ok = True
        for k, v in checks.items():
            print("   [%s] %s" % ("PASS" if v else "FAIL", k))
            ok = ok and v
        print("RESULT:", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

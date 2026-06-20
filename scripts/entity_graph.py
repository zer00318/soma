#!/usr/bin/env python3
"""Sprint 1 / increment 2 — the ENTITY GRAPH. The structural fix for MIS-ATTRIBUTION.

The day clip's hallucinations (Q13/17/18) are NOT perception phantoms — the right token IS
present, but the brain BINDS it to the WRONG entity: a stranger's outfit answered as "yours",
a clock that isn't the lecture's, another object's logo. A confidence score (increment 1) can't
catch that — the token is high-confidence, it's just attached to the wrong thing.

So we build the thing the brain was missing: a graph of ENTITIES. Observations from every text
channel are clustered into entities with a TYPE {self, person, object, screen, place}. Each entity
carries its own attributes, each attribute tagged with the channel it came from and a confidence
(REUSING evidence_confidence.term_confidence — channel reliability, not frequency).

Then the brain, instead of grabbing a free-floating token, asks: WHICH entity is this question
about? If several distinct entities fit (the day clip has multiple people — Joe, Brett, a woman,
the wearer), binding_confidence is LOW and the honest move is to REFUSE rather than pick one. That
refusal is the whole point: a wrong-entity guess is worse than "I'm not sure which one you mean".

Clustering is DETERMINISTIC and CPU-only (no LLM): type + lexical/temporal co-occurrence.
  - self    : first-person / wearer cues (hands, "looking down", "their chest/lap", worn items)
  - person  : greeted names in speech; other people described in captions ("a woman", "a person
              wearing X") — each grouped by descriptor + temporal proximity
  - object  : physical things from world_memory + captions (not displays/signs)
  - screen  : screen_memory OCR, plus laptop/tablet/tv/phone displays and digital signage
  - place   : venue/location markers (named signs: GARDEN WOK, the train platform/station, a room)

Public API:
  build_entities(memory_dir)              -> {"entities":[...], "by_id":{id:entity}}
  entities_for(question, graph)           -> [entity, ...]  candidates the question is about
  evidence_for(entity, graph)             -> [attribute, ...]  confidence-ranked
  binding_confidence(question, graph)     -> {"answerable":bool, "confidence":0..1, "reason":str}

Each entity: {id, type, label, mentions:[t...],
              attributes:[{attr,value,source_channel,t,confidence}, ...]}

This file does NOT call ollama. Its unit test is CPU-only.
"""
from __future__ import annotations
import json
import os
import re
import sys

# Reuse increment 1 for both observation loading and per-term confidence (channel reliability).
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import evidence_confidence as ec  # noqa: E402


# ----------------------------------------------------------------------------- lexicons
# A word that means "the wearer is being described in first person", i.e. the camera-self.
SELF_CUES = re.compile(
    r"\b(my|i'?m|first[- ]person|point of view|pov|looking down|"
    r"their (?:chest|lap|own)|own (?:hand|hands|feet|lap)|"
    r"the (?:viewer|wearer|camera)'?s?)\b", re.I)
# A hand/feet close-up with no OTHER person around is the wearer's own body (self), not a stranger.
OWN_BODY = re.compile(r"\b(hand|hands|wrist|finger|fingers|feet|foot|arm|legs?)\b", re.I)
OTHER_PERSON = re.compile(
    r"\b(a |another |the )?(person|man|woman|guy|lady|boy|girl|child|kid|stranger|"
    r"people|someone|individual)\b", re.I)
# world_memory.where strings that say an item is worn/held by the camera-wearer (self).
WEARER_WHERE = re.compile(r"\b(on feet|on person|in hand|hands|on (?:my|the) )", re.I)

# A surface that shows text/graphics = a SCREEN entity (laptop/phone/tv/board/sign/billboard).
SCREEN_NOUN = re.compile(
    r"\b(screen|laptop|tablet|monitor|tv|television|phone|display|billboard|"
    r"whiteboard|board|projector|digital display|advertisement|poster)\b", re.I)
# A named-location marker = a PLACE entity.
PLACE_NOUN = re.compile(
    r"\b(platform|station|track|tracks|room|restaurant|cafe|bar|store|shop|hallway|"
    r"lecture|classroom|sidewalk|street|park|building|exit|wall sign|signpost|sign wall)\b", re.I)

# Names greeted in speech ("Okay, Joe", "What's up, Brett?"). We pull capitalised tokens that
# follow a greeting/address word, and the bare vocative. Deterministic, no NER model.
GREETING = re.compile(
    r"\b(?:hey|hi|hello|okay|ok|yo|what'?s up|see you|bye|thanks?|good morning|morning)\b"
    r"[ ,]+([A-Z][a-z]+)", re.I)
ADDRESS_NAME = re.compile(r"\b([A-Z][a-z]{2,})\b")
# common words that are capitalised but are NOT person names
NOT_A_NAME = set(
    "good morning okay yes see you have day this can anything wants what field due positive "
    "negative charge later bro the a an i z brett joe".split())  # joe/brett handled explicitly


# ----------------------------------------------------------------------------- small helpers
def _as_list(x):
    if x is None:
        return []
    if isinstance(x, list):
        return [str(v) for v in x if v]
    return [str(x)]


def _norm_t(t):
    return round(t, 1) if isinstance(t, (int, float)) else t


def _load_world(mdir):
    p = os.path.join(mdir, "world_memory.json")
    try:
        w = json.load(open(p))
    except Exception:
        return []
    objs = w.get("objects") if isinstance(w, dict) else w
    return objs or []


def _load_kf(mdir):
    p = os.path.join(mdir, "kf_memory.json")
    try:
        kf = json.load(open(p))
        if isinstance(kf, list):
            return kf
    except Exception:
        pass
    rows = []
    for nm in ("kf_memory.json", "kf_memory.json.ckpt.ndjson"):
        fp = os.path.join(mdir, nm)
        try:
            for ln in open(fp):
                ln = ln.strip()
                if ln:
                    rows.append(json.loads(ln))
            if rows:
                return rows
        except Exception:
            continue
    return rows


def _load_screen(mdir):
    p = os.path.join(mdir, "screen_memory.json")
    try:
        sm = json.load(open(p))
        return sm if isinstance(sm, list) else []
    except Exception:
        return []


def _load_asr(mdir):
    p = os.path.join(mdir, "asr.json")
    try:
        return json.load(open(p)) or {}
    except Exception:
        return {}


def _load_entity_centric(mdir):
    """Already-bound entities from the Sprint-2 re-ID step (entity_centric.json).

    Contract (PHASE4 workorder §2): a list of
        {entity_id, type, attributes:[{attr,value,frames,confidence}], mentions:[t], ...}
    where the binding (who-wore-what) was done AT CAPTURE inside the VLM look, so we MUST
    trust it verbatim and NOT re-derive from mixed captions. Returns [] when absent so we
    fall back to heuristic clustering."""
    for nm in ("entity_centric.json", "entity_centric.json.ckpt.ndjson"):
        p = os.path.join(mdir, nm)
        try:
            with open(p) as source:
                blob = json.load(source)
            ents = blob.get("entities") if isinstance(blob, dict) else blob
            if isinstance(ents, list) and ents:
                return ents
        except Exception:
            rows = []
            try:
                for ln in open(p):
                    ln = ln.strip()
                    if ln:
                        rows.append(json.loads(ln))
            except Exception:
                rows = []
            if rows:
                return rows
    return []


# ----------------------------------------------------------------------------- entity typing
def _world_type(obj):
    """Map a world_memory object to an entity type by its noun + where."""
    name = (obj.get("name") or "").lower()
    where = " ".join(_as_list(obj.get("where"))).lower()
    blob = name + " " + where
    if SCREEN_NOUN.search(name):
        return "screen"
    # named venue signs ("wok sign" reads GARDEN WOK, "exit sign") are place markers
    if PLACE_NOUN.search(blob):
        return "place"
    # worn/held by the wearer -> contributes to SELF rather than a free object
    if WEARER_WHERE.search(where) or "on person" in where:
        return "self_item"
    return "object"


# ----------------------------------------------------------------------------- captured entities
# Map the capture step's record kinds onto the graph's 5 entity types. The capture VLM emits
# persons / text_objects / self-view; the re-ID step gives each a stable entity_id + type.
_CENTRIC_TYPE = {
    "person": "person", "people": "person",
    "self": "self", "self_view": "self", "wearer": "self",
    "screen": "screen", "text_object": "object", "object": "object",
    "place": "place", "location": "place", "venue": "place",
}


def _centric_type(rec):
    raw = (rec.get("type") or rec.get("kind") or "").strip().lower()
    if raw in _CENTRIC_TYPE:
        return _CENTRIC_TYPE[raw]
    if rec.get("is_self_view") or rec.get("self_attributes"):
        return "self"
    # a record that carries clothing/holding is a person; text_or_logo bound to a thing is object
    if rec.get("clothing") or rec.get("holding") or rec.get("accessories"):
        return "person"
    if rec.get("logo_or_text") or rec.get("object"):
        return "object"
    return "object"


def _centric_label(rec, etype):
    for k in ("label", "appearance", "object", "name", "descriptor"):
        v = rec.get(k)
        if v:
            return str(v)
    if etype == "self":
        return "the wearer (camera/self)"
    return etype


def _centric_attrs(rec):
    """Yield (attr, value, confidence, frames) from a captured record, preserving the AT-CAPTURE
    binding. We DO NOT re-attribute across records — each person's clothing stays on that person,
    each object's logo stays on that object."""
    out = []

    def emit(attr, value, conf, frames):
        value = (str(value) if value is not None else "").strip()
        if value:
            out.append((attr, value, conf, frames))

    # 1) explicit pre-scored attribute list (the re-ID step's canonical shape)
    for a in rec.get("attributes") or []:
        if isinstance(a, dict):
            emit(a.get("attr") or "attribute", a.get("value"),
                 a.get("confidence"), a.get("frames") or a.get("t"))
        else:
            emit("attribute", a, None, None)
    # 2) raw per-frame record fields (when the re-ID step passed them through verbatim)
    cl = rec.get("clothing") or {}
    if isinstance(cl, dict):
        for slot in ("top", "bottom"):
            emit("clothing_%s" % slot, cl.get(slot), None, None)
        for c in _as_list(cl.get("colors")):
            emit("clothing_color", c, None, None)
    for a in _as_list(rec.get("accessories")):
        emit("accessory", a, None, None)
    for h in _as_list(rec.get("holding")):
        emit("holding", h, None, None)
    if rec.get("logo_or_text"):
        # a logo is bound to ITS object: keep the binding explicit in the attr name.
        emit("logo_or_text_on_%s" % re.sub(r"\W+", "_",
             str(rec.get("object") or "object").lower()).strip("_"),
             rec.get("logo_or_text"), None, None)
    for k, v in (rec.get("self_attributes") or {}).items() if isinstance(
            rec.get("self_attributes"), dict) else []:
        emit("self_%s" % k, v, None, None)
    return out


def _build_from_entity_centric(records, memory_dir):
    """Build the graph from already-bound captured entities. Trust their binding; only compute
    confidence where the capture step didn't supply one (reuse channel reliability of 'world' for
    a VLM structured read, never below it). Each record becomes exactly ONE entity — no merging,
    no re-attribution, so who-wore-what cannot be scrambled here."""
    entities = []
    seen = {}
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            continue
        etype = _centric_type(rec)
        eid = str(rec.get("entity_id") or rec.get("id")
                  or "%s:c%d" % (etype, i))
        if eid in seen:
            e = seen[eid]
        else:
            e = {"id": eid, "type": etype, "label": _centric_label(rec, etype),
                 "mentions": [], "attributes": [], "from_capture": True}
            # mark the single canonical self so referent resolution can exclude it
            if etype == "self":
                e["is_self"] = True
            entities.append(e)
            seen[eid] = e
        for ment in _as_list(rec.get("mentions")) or []:
            try:
                e["mentions"].append(_norm_t(float(ment)))
            except (TypeError, ValueError):
                pass
        for attr, value, conf, frames in _centric_attrs(rec):
            try:
                c = float(conf)
            except (TypeError, ValueError):
                c = ec.CHANNEL_REL.get("world", 0.60)  # structured VLM read ≈ world reliability
            t = None
            for f in _as_list(frames):
                try:
                    t = _norm_t(float(f)); break
                except (TypeError, ValueError):
                    continue
            e["attributes"].append({
                "attr": attr, "value": value, "source_channel": "capture",
                "t": t, "confidence": round(max(0.0, min(1.0, c)), 3),
            })
            if t is not None:
                e["mentions"].append(t)
    for e in entities:
        e["mentions"] = sorted(set(m for m in e["mentions"] if m is not None))
    by_id = {e["id"]: e for e in entities}
    return {"entities": entities, "by_id": by_id}


# ----------------------------------------------------------------------------- the builder
def build_entities(memory_dir):
    """Build typed entities for a memory dir. Deterministic, CPU-only.

    PREFERS entity_centric.json (already-bound entities from the Sprint-2 re-ID step) when
    present — that is where who-wore-what was bound AT CAPTURE, so it must be trusted over the
    mixed-caption heuristic. Falls back to the heuristic clustering below otherwise.

    Returns {"entities":[entity...], "by_id":{id:entity}}.
    """
    centric = _load_entity_centric(memory_dir)
    if centric:
        return _build_from_entity_centric(centric, memory_dir)

    # Support table from increment 1 gives us per-term confidence (channel reliability).
    obs = ec.load_observations(memory_dir)
    sup = ec.build_support(obs)

    def conf(value, channel):
        """Confidence for an attribute value: the most distinctive content token's confidence,
        but never below the raw channel reliability of where we read it."""
        sc = ec.score_claim(value, sup)
        base = ec.CHANNEL_REL.get(channel, 0.40)
        return round(max(sc["confidence"], base) if sc["key"] else base, 3)

    entities = []

    def new_entity(eid, etype, label):
        e = {"id": eid, "type": etype, "label": label, "mentions": [], "attributes": []}
        entities.append(e)
        return e

    def add_attr(e, attr, value, channel, t):
        value = (value or "").strip()
        if not value:
            return
        e["attributes"].append({
            "attr": attr, "value": value, "source_channel": channel,
            "t": _norm_t(t), "confidence": conf(value, channel),
        })
        if t is not None:
            e["mentions"].append(_norm_t(t))

    # ----- 1) SELF: the camera-wearer. One entity, anchored by first-person/own-body cues.
    self_e = new_entity("self", "self", "the wearer (camera/self)")
    self_e["is_self"] = True
    kf = _load_kf(memory_dir)
    for r in kf:
        t = r.get("t")
        cap = r.get("caption") or ""
        has_self = bool(SELF_CUES.search(cap))
        # an own-body close-up with NO other person mentioned = the wearer's own body
        own_body = bool(OWN_BODY.search(cap)) and not OTHER_PERSON.search(cap)
        if has_self or own_body:
            self_e["attributes"].append({
                "attr": "self_observation", "value": cap[:200], "source_channel": "caption",
                "t": _norm_t(t), "confidence": conf(cap, "caption"),
            })
            self_e["mentions"].append(_norm_t(t))

    # ----- 2) OBJECTS / SCREENS / PLACES from world_memory, plus SELF-worn items.
    screen_objs, place_objs = [], []
    for obj in _load_world(memory_dir):
        name = (obj.get("name") or "").strip()
        if not name:
            continue
        etype = _world_type(obj)
        attrs = _as_list(obj.get("attributes"))
        where = "; ".join(_as_list(obj.get("where")))
        if etype == "self_item":
            # an item the wearer is wearing/holding -> attribute of SELF, not its own entity
            for a in (attrs or [""]):
                add_attr(self_e, "wears_or_holds",
                         (name + (" (" + a + ")" if a else "")), "world", None)
            continue
        eid = "%s:%s" % (etype, re.sub(r"\W+", "_", name.lower()).strip("_"))
        e = new_entity(eid, etype, name)
        for a in attrs:
            add_attr(e, "appearance", a, "world", None)
        if where:
            add_attr(e, "location", where, "world", None)
        if etype == "screen":
            screen_objs.append(e)
        elif etype == "place":
            place_objs.append(e)

    # ----- 3) SCREEN text: screen_memory OCR is verbatim on-screen text -> a content screen.
    screen_text = new_entity("screen:on_screen_text", "screen", "on-screen text (screen OCR)")
    for r in _load_screen(memory_dir):
        t = r.get("t")
        txt = (r.get("screen_ocr_txt") or " ".join(r.get("screen_ocr") or [])).strip()
        if txt:
            add_attr(screen_text, "reads", txt[:160], "screen", t)
    if not screen_text["attributes"]:
        entities.remove(screen_text)

    # ----- 4) PEOPLE: greeted names in speech (each a distinct person), + described others.
    asr = _load_asr(memory_dir)
    named = {}  # canonical name -> entity
    for seg in asr.get("segments", []):
        txt = seg.get("text") or ""
        t = seg.get("start")
        for m in GREETING.finditer(txt):
            nm = m.group(1)
            if nm.lower() in NOT_A_NAME and nm.lower() not in ("joe", "brett"):
                continue
            key = nm.lower()
            if key not in named:
                named[key] = new_entity("person:" + key, "person", nm)
            add_attr(named[key], "greeted_in_speech", txt.strip(), "speech", t)
    # explicit known vocatives the regex may miss across punctuation
    for nm in ("Joe", "Brett"):
        key = nm.lower()
        if key not in named and re.search(r"\b" + nm + r"\b", asr.get("full_text", ""), re.I):
            e = new_entity("person:" + key, "person", nm)
            for seg in asr.get("segments", []):
                if re.search(r"\b" + nm + r"\b", seg.get("text", ""), re.I):
                    add_attr(e, "greeted_in_speech", seg["text"].strip(), "speech", seg.get("start"))
            named[key] = e

    # described OTHER people in captions, grouped by the wearable descriptor near them in time.
    # (a "woman" / "person wearing green shirt" who is NOT the wearer = a separate person)
    described = {}  # descriptor -> entity
    for r in kf:
        t = r.get("t")
        cap = r.get("caption") or ""
        if not OTHER_PERSON.search(cap):
            continue
        if SELF_CUES.search(cap):  # that's the wearer, already handled
            continue
        # Identity key anchors on the PERSON noun (woman/man/...), refined by a worn item when
        # one is stated. A bare clothing phrase with no person noun is NOT its own person — it's
        # an "unidentified person" (avoids splitting one figure into 'black pants' + 'green shirt').
        noun = re.search(r"\b(woman|man|guy|lady|boy|girl|child|kid)\b", cap, re.I)
        worn = re.search(r"\b(?:wearing|in) (?:a |an |the )?([a-z]+(?: [a-z]+){0,1} "
                         r"(?:shirt|dress|jacket|pants|hoodie|sweater|hat))", cap, re.I)
        if noun:
            base = noun.group(1).lower()
            key = "a %s (%s)" % (base, worn.group(1).lower().strip()) if worn else "a " + base
        else:
            key = "an unidentified person"
        if key not in described:
            described[key] = new_entity(
                "person:desc:" + re.sub(r"\W+", "_", key).strip("_"), "person", key)
        add_attr(described[key], "appearance", cap[:180], "caption", t)

    # de-dup mentions, sort
    for e in entities:
        e["mentions"] = sorted(set(m for m in e["mentions"] if m is not None))

    by_id = {e["id"]: e for e in entities}
    return {"entities": entities, "by_id": by_id}


# ----------------------------------------------------------------------------- query side
# question phrasings -> which entity TYPE the question is about
_Q_SELF = re.compile(r"\b(i|me|my|mine|myself|am i|was i|i'?m|did i|do i|we|our|us)\b", re.I)
_Q_PERSON = re.compile(
    r"\b(who|person|people|man|woman|guy|someone|anyone|greet|greeted|say hi|"
    r"talk|talking|name(?:d)?)\b", re.I)
_Q_SCREEN = re.compile(
    r"\b(screen|laptop|tablet|monitor|phone|tv|display|board|whiteboard|"
    r"lecture|slide|read|reads|reading|text|written|says|logo|sign)\b", re.I)
_Q_PLACE = re.compile(
    r"\b(where|place|room|restaurant|cafe|bar|station|platform|location|venue|"
    r"building|outside|inside)\b", re.I)

# A THIRD-PERSON referent: the question is explicitly about someone who is NOT the wearer.
# "what was HE wearing", "his shirt", "that guy", "the other person", "she", "their jacket".
# When this fires, a 'self' entity is NEVER an eligible referent (Sprint-1 Q13: HE -> self).
_REF_OTHER = re.compile(
    r"\b(he|him|his|she|her|hers|they(?!\s+were\s+i)|them|their|theirs|"
    r"that (?:guy|man|woman|person|lady|kid|child)|the other (?:guy|man|woman|person|one)|"
    r"the (?:guy|man|woman|lady|stranger|person))\b", re.I)
# A POSSESSIVE/RELATIONAL referent: "the mate's logo", "Joe's backpack", "his shirt's text".
# Group 1 = the OWNER phrase (a person/role), group 2 = the owned thing. The owned thing must be
# resolved as an attribute OF the owner entity, NOT as a free-floating object (Sprint-1: the
# mate's logo -> a whiteboard). 'mate' is a person-role even though it is not a captured name.
_REF_POSSESSIVE = re.compile(
    r"\b(?:the |my |his |her |their )?"
    r"(mate|friend|buddy|guy|man|woman|lady|kid|child|stranger|person|"
    r"[A-Z][a-z]+)'s\s+([a-z]+)", re.I)
_REF_RELATIONAL = re.compile(
    r"\b(logo|brand|text|clothing|outfit|shirt|jacket|hat)\s+"
    r"(?:on|of)\s+(?:the\s+|my\s+)?"
    r"(mate|friend|buddy|guy|man|woman|lady|kid|child|stranger|person|companion|"
    r"colleague|partner)\b", re.I)
_PERSON_ROLE = re.compile(
    r"\b(mate|friend|buddy|guy|man|woman|lady|kid|child|stranger|person|companion|"
    r"colleague|partner|she|he|they)\b", re.I)


def _qtoks(q):
    return set(ec._toks(q))


def entities_for(question, graph):
    """Candidate entities the question is about — by type intent AND lexical overlap with labels.
    Returns a list (possibly several). Several candidates => the question is ambiguous."""
    ents = graph["entities"]
    q = question or ""
    qtok = _qtoks(q)

    # 1) lexical: any entity whose label/attributes share a content token with the question.
    lexical = []
    for e in ents:
        hay = (e["label"] + " " + " ".join(a["value"] for a in e["attributes"])).lower()
        haytok = set(ec._toks(hay))
        # also let the label noun match directly
        if qtok & haytok or any(w in hay for w in qtok):
            lexical.append(e)

    # 2) intent: which types does the question's phrasing point at?
    want_types = set()
    if _Q_SELF.search(q):
        want_types.add("self")
    if _Q_PERSON.search(q):
        want_types.add("person")
    if _Q_SCREEN.search(q):
        want_types.add("screen")
    if _Q_PLACE.search(q):
        want_types.add("place")

    if want_types:
        typed = [e for e in ents if e["type"] in want_types]
        # prefer entities that are BOTH the right type AND lexically relevant
        both = [e for e in lexical if e["type"] in want_types]
        if both:
            return both
        # a 'self' question is unambiguous if there's exactly one self entity
        if want_types == {"self"}:
            return [e for e in ents if e["type"] == "self"] or typed
        # otherwise all entities of the wanted type are candidates (ambiguity surfaces here)
        return typed or lexical
    return lexical


def evidence_for(entity, graph=None):
    """That entity's attributes, ranked most-confident first (ties: more recent / earlier t)."""
    if entity is None:
        return []
    return sorted(entity.get("attributes", []),
                  key=lambda a: (-a.get("confidence", 0.0),
                                 a.get("t") if isinstance(a.get("t"), (int, float)) else 1e9))


def _is_self(e):
    return e.get("is_self") or e.get("type") == "self"


def _resolve_referent(question, graph, cands):
    """Resolve WHICH real entity a third-person / possessive question points at, BEFORE counting
    ambiguity. This is the Sprint-1 fix:
      * 'what was HE wearing'  -> a PERSON who is NOT the self; self is excluded outright.
      * "the mate's logo"      -> the owner (a person/role) entity, and the owned thing must be
                                  read from THAT entity's attributes, never from a free object.
    Returns (group, note) where group is the eligible entity list, or (None, None) if no explicit
    referent applies (caller keeps its normal type-based logic)."""
    q = question or ""

    # Relational ownership without apostrophe: "logo on the mate", "shirt of
    # the person". It has the same semantics as "the mate's logo": resolve the
    # owner person first and never offer an unrelated logo-bearing object.
    mrel = _REF_RELATIONAL.search(q)
    if mrel:
        owner_phrase = mrel.group(2).lower()
        persons = [e for e in graph["entities"]
                   if e["type"] == "person" and not _is_self(e)]
        owners = [e for e in persons
                  if owner_phrase in e["label"].lower()
                  or any(owner_phrase in a["value"].lower() for a in e["attributes"])]
        if not owners and _PERSON_ROLE.search(owner_phrase):
            owners = persons
        if owners:
            return owners, ("relational referent %r -> resolved to its owner person(s); "
                            "the detail is read from the owner, not a free object"
                            % mrel.group(0))
        return [], ("relational referent %r names no known person; refusing rather than "
                    "binding the detail to an unrelated object" % mrel.group(0))

    # (A) possessive/relational: "the mate's logo", "Joe's backpack", "his shirt".
    mposs = _REF_POSSESSIVE.search(q)
    if mposs:
        owner_phrase = mposs.group(1).lower()
        # the owner must be a PERSON entity (named or described), and never the self unless the
        # owner phrase is first-person (it isn't here — possessive of a third party).
        persons = [e for e in graph["entities"]
                   if e["type"] == "person" and not _is_self(e)]
        # match the owner to a person by name/label, else by the role word appearing in its label
        owners = [e for e in persons
                  if owner_phrase in e["label"].lower()
                  or any(owner_phrase in a["value"].lower() for a in e["attributes"])]
        if not owners and _PERSON_ROLE.search(owner_phrase):
            owners = persons  # a role like 'mate' with several people => ambiguous owner
        if owners:
            return owners, ("possessive referent %r -> resolved to its owner person(s); "
                            "the owned thing is read from the owner, not a free object"
                            % mposs.group(0))
        # owner phrase names nobody we have -> cannot bind the possessive at all (do NOT fall
        # through to a free object like the whiteboard).
        return [], ("possessive referent %r names no known person; refusing rather than "
                    "binding the owned thing to an unrelated object" % mposs.group(0))

    # (B) bare third-person: HE / she / that guy / the other person -> a non-self PERSON.
    # An explicit third-person pronoun wins over incidental first-person event
    # language ("I greeted him" is about him, not the wearer).
    if _REF_OTHER.search(q):
        others = [e for e in graph["entities"]
                  if e["type"] == "person" and not _is_self(e)]
        return others, "third-person referent -> only non-self person entities are eligible"

    return None, None


def binding_confidence(question, graph):
    """Can this question be bound to ONE entity confidently?

    Step 1 — REFERENT RESOLUTION: if the question names a third-person or possessive referent,
    restrict the candidate set to the real referent BEFORE counting ambiguity. This is what keeps
    the Sprint-1 failures from recurring: 'what was HE wearing' can never resolve to the self, and
    "the mate's logo" can never resolve to a whiteboard (it must be the mate's own attribute, else
    we refuse).
    Step 2 — AMBIGUITY: answerable=False / low confidence when SEVERAL distinct entities of the
    relevant type still fit (day clip Q13: multiple non-self people -> don't pick one)."""
    q = question or ""

    # Step 1: explicit referent resolution.
    group, note = _resolve_referent(q, graph, entities_for(q, graph))
    if group is not None:
        if not group:
            return {"answerable": False, "confidence": 0.0, "reason": note}
        dom_type = group[0]["type"]
        n = len(group)
        if n == 1:
            e = group[0]
            ev = evidence_for(e, graph)
            top = ev[0]["confidence"] if ev else 0.0
            return {"answerable": top > 0.0, "confidence": top,
                    "reason": "%s; exactly one %s entity (%r) -> %s"
                              % (note, dom_type, e["label"],
                                 "unambiguous" if top > 0.0 else "no evidence on it")}
        labels = [e["label"] for e in group]
        amb = round(min(0.49, 1.0 / n), 3)
        return {"answerable": False, "confidence": amb,
                "reason": "%s; but %d distinct %s entities still fit (%s) -> refusing to pick one"
                          % (note, n, dom_type, ", ".join(repr(x) for x in labels[:5]))}

    # Step 2: no explicit referent -> normal type-based ambiguity logic.
    cands = entities_for(q, graph)
    if not cands:
        return {"answerable": False, "confidence": 0.0,
                "reason": "no entity in memory matches this question"}

    types = {}
    for e in cands:
        types.setdefault(e["type"], []).append(e)
    # a single 'self' candidate wins only for an explicit first-person question.
    if any(_is_self(e) for e in cands) and _Q_SELF.search(q):
        dom_type, group = "self", [e for e in cands if _is_self(e)]
    else:
        dom_type, group = max(types.items(), key=lambda kv: len(kv[1]))

    n = len(group)
    if n == 1:
        e = group[0]
        ev = evidence_for(e, graph)
        top = ev[0]["confidence"] if ev else 0.0
        return {"answerable": top > 0.0, "confidence": top,
                "reason": "exactly one %s entity (%r) matches; "
                          "binding is unambiguous" % (dom_type, e["label"])}

    labels = [e["label"] for e in group]
    amb = round(min(0.49, 1.0 / n), 3)
    return {
        "answerable": False, "confidence": amb,
        "reason": "%d distinct %s entities could be meant (%s); refusing to bind to one"
                  % (n, dom_type, ", ".join(repr(x) for x in labels[:5])),
    }


# ----------------------------------------------------------------------------- CLI / smoke
def _summary(graph):
    ents = graph["entities"]
    by_type = {}
    for e in ents:
        by_type.setdefault(e["type"], []).append(e)
    lines = ["%d entities: %s" % (len(ents),
             ", ".join("%s=%d" % (k, len(v)) for k, v in sorted(by_type.items())))]
    for typ in ("self", "person", "screen", "place", "object"):
        for e in by_type.get(typ, []):
            ev = evidence_for(e, graph)
            top = ev[0] if ev else None
            lines.append("  [%-6s] %-34s mentions=%-3d attrs=%-2d  top=%s" % (
                e["type"], e["label"][:34], len(e["mentions"]), len(e["attributes"]),
                ("%.2f %s" % (top["confidence"], top["value"][:42]) if top else "-")))
    return "\n".join(lines)


def main(argv):
    if not argv:
        print("usage: entity_graph.py <memory_dir> [question]")
        return 2
    g = build_entities(argv[0])
    print(_summary(g))
    if len(argv) > 1:
        q = argv[1]
        print("\nquestion: %s" % q)
        cands = entities_for(q, g)
        print("candidates: %s" % ", ".join("%s(%s)" % (e["label"], e["type"]) for e in cands))
        print("binding: %s" % json.dumps(binding_confidence(q, g)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

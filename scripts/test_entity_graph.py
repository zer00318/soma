#!/usr/bin/env python3
"""CPU-only unit test for entity_graph (NO ollama). Runs on BOTH clips.

Checks the task's acceptance criteria:
 (a) a 'self' entity exists for the day clip;
 (b) the day clip has MULTIPLE distinct person-entities -> 'which person' is ambiguous
     -> binding_confidence is LOW (refuse) for a Q13-type 'what were they wearing' question;
 (c) build_entities runs without error on both memory dirs.
"""
from __future__ import annotations
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import entity_graph as G  # noqa: E402

ROOT = os.path.dirname(_HERE)
DAY = os.path.join(ROOT, "data/walks/day_in_life_20260618/memory")
WALK = os.path.join(ROOT, "data/walks/walk_outside_20260614/memory")


def main():
    failures = []

    # (c) runs without error on BOTH
    graphs = {}
    for slug, mdir in (("day", DAY), ("walk", WALK)):
        g = G.build_entities(mdir)
        graphs[slug] = g
        print("=" * 78)
        print("CLIP: %s   (%s)" % (slug, mdir))
        print(G._summary(g))

    day = graphs["day"]

    # (a) a 'self' entity exists for the day clip, with at least one observation
    selfs = [e for e in day["entities"] if e["type"] == "self"]
    if len(selfs) == 1 and selfs[0]["attributes"]:
        print("\n[PASS a] day clip has a 'self' entity with %d attributes"
              % len(selfs[0]["attributes"]))
    else:
        failures.append("(a) expected exactly one non-empty 'self' entity in day clip, got %d"
                        % len(selfs))

    # (b) MULTIPLE distinct person-entities in the day clip
    people = [e for e in day["entities"] if e["type"] == "person"]
    print("\nday person-entities (%d): %s" % (len(people), [e["label"] for e in people]))
    if len(people) >= 2:
        print("[PASS b1] day clip has %d distinct person-entities (ambiguity is possible)"
              % len(people))
    else:
        failures.append("(b1) expected >=2 person-entities in day clip, got %d" % len(people))

    # ... so a Q13-type "what was the person wearing" must NOT bind to one (LOW confidence)
    q13 = "What was the person wearing?"
    bc = G.binding_confidence(q13, day)
    print("\nQ13-type: %r\n   binding=%s" % (q13, bc))
    if (not bc["answerable"]) and bc["confidence"] < 0.5:
        print("[PASS b2] Q13-type refuses to bind (answerable=False, conf=%.3f) -> no wrong-entity guess"
              % bc["confidence"])
    else:
        failures.append("(b2) Q13-type should be unbindable/low-confidence; got %s" % bc)

    # bonus sanity: a clearly self-directed question binds to the wearer unambiguously
    qself = "What am I doing with my hands?"
    bs = G.binding_confidence(qself, day)
    print("\nself-question: %r\n   binding=%s" % (qself, bs))
    if bs["answerable"]:
        print("[PASS bonus] self-question binds to the wearer (answerable=True, conf=%.3f)"
              % bs["confidence"])
    else:
        print("[warn] self-question did not bind (non-fatal): %s" % bs["reason"])

    # bonus sanity: walk clip builds and yields screen/place/object entities
    walk = graphs["walk"]
    wtypes = {e["type"] for e in walk["entities"]}
    print("\nwalk entity types present: %s" % sorted(wtypes))

    print("\n" + "=" * 78)
    if failures:
        print("FAILURES:")
        for f in failures:
            print("  - " + f)
        return 1
    print("ALL CHECKS PASSED (a, b1, b2, c).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

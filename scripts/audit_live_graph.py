#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from soma_hub.graph_audit import GraphAuditor, audit_to_dict


def get_json(url: str, token: str) -> dict:
    request = Request(url, headers={"X-SOMA-Token": token})
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def print_report(payload: dict, iteration: int) -> None:
    print(f"\n=== SOMA Live Graph Audit #{iteration}: {payload['grade']} ({payload['score']}%) ===")
    print(f"Counts: {payload['counts']}")
    print(f"Relation types: {payload['relation_types']}")
    if payload["strengths"]:
        print("Strengths:")
        for item in payload["strengths"]:
            print(f"- {item}")
    if payload["issues"]:
        print("Issues:")
        for item in payload["issues"]:
            print(f"- {item}")
    if payload["current_entities"]:
        print("Current entities:")
        for entity in payload["current_entities"][:8]:
            print(f"- {entity['label']} ({entity['kind']}, obs {entity['observation_count']}, conf {entity['confidence']:.2f})")
    if payload["recent_relations"]:
        print("Recent relations:")
        for relation in payload["recent_relations"][:8]:
            print(f"- {relation['subject']} {relation['relation_type']} {relation['object']} [{relation['status']}]")
    if payload.get("recent_attributes"):
        print("Recent attributes:")
        for attribute in payload["recent_attributes"][:8]:
            print(
                f"- {attribute['entity']} {attribute['attribute_key']} = "
                f"{attribute['attribute_value']} [{attribute['status']}, obs {attribute['observation_count']}]"
            )
    if payload.get("profiles"):
        print("Profiles:")
        for profile in payload["profiles"][:4]:
            canonical_slots = profile.get("canonical_slots") or {}
            slot_bits = [
                f"{key}={slot['value']}"
                for key, slot in list(canonical_slots.items())[:5]
            ]
            if not slot_bits:
                for key, values in list(profile["slots"].items())[:5]:
                    if values:
                        slot_bits.append(f"{key}={values[0]['value']}")
            suffix = "; ".join(slot_bits) if slot_bits else "no slots yet"
            print(f"- {profile['label']} ({profile['status']}, obs {profile['observation_count']}): {suffix}")
    if payload.get("profile_quality"):
        print("Profile quality:")
        for profile in payload["profile_quality"][:4]:
            missing = ", ".join(profile["missing_slots"][:3]) if profile["missing_slots"] else "none"
            meaningful = ", ".join(profile["meaningful_slots"][:4]) if profile["meaningful_slots"] else "none"
            print(
                f"- {profile['label']}: {profile['present_count']} slots, "
                f"{profile['coverage']:.0%} coverage, meaningful={meaningful}, missing next={missing}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Poll a running SOMA hub and audit the relational graph.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--token", default="dev-token")
    parser.add_argument("--interval", type=float, default=10)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--label", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    auditor = GraphAuditor()
    iterations = max(1, args.iterations)
    for index in range(1, iterations + 1):
        try:
            graph = get_json(f"{args.base_url.rstrip('/')}/graph", args.token)
            relation_url = f"{args.base_url.rstrip('/')}/graph/relations"
            if args.label:
                relation_url = f"{relation_url}?{urlencode({'label': args.label})}"
            relations = get_json(relation_url, args.token).get("relations", [])
            profile_url = f"{args.base_url.rstrip('/')}/graph/profiles"
            if args.label:
                profile_url = f"{profile_url}?{urlencode({'label': args.label})}"
            profiles = get_json(profile_url, args.token).get("profiles", [])
        except (HTTPError, URLError, TimeoutError) as exc:
            print(f"SOMA graph audit could not reach hub: {exc}", file=sys.stderr)
            return 2

        payload = audit_to_dict(auditor.audit(graph, relations, profiles))
        payload["recent_attributes"] = graph.get("recent_attributes", [])
        payload["profiles"] = profiles
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print_report(payload, index)

        if index < iterations:
            time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

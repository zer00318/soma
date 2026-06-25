from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from trace_hub.policy import decide_recall_intent, redact_for_public_summary
from trace_hub.storage import MemoryStore

if TYPE_CHECKING:
    from trace_hub.graph import RelationalMemoryGraph

_LLM_MODEL = "gemma3:12b-it-qat"


def _latest_their_quote(messages_block: str, min_len: int = 25) -> str:
    """Most recent substantive THEM line from the arc-sampled messages.

    Extractive by design: recall answers quote stored evidence verbatim and
    never paraphrase it through a generative model — generated prose invents
    relationships and people regardless of prompt-level prohibitions
    (empirically: hallucinated persons in who_is answers, 2026-06-10).
    """
    for line in reversed(messages_block.splitlines()):
        line = line.strip()
        if line.startswith("THEM:"):
            quote = line[len("THEM:"):].strip()
            if len(quote) >= min_len:
                return quote
    return ""


def _relative_date(ts_str: str) -> str:
    """Convert an ISO/date string to a human-readable relative description."""
    if not ts_str:
        return "unknown"
    try:
        # Accept YYYY-MM-DD or full ISO
        clean = ts_str[:10]
        dt = datetime.strptime(clean, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        days = (now - dt).days
        if days == 0:
            return "today"
        if days == 1:
            return "yesterday"
        if days < 7:
            return f"{days} days ago"
        if days < 14:
            return "last week"
        if days < 30:
            return f"{days // 7} weeks ago"
        if days < 60:
            return "last month"
        if days < 365:
            return f"{days // 30} months ago"
        return f"{days // 365} year{'s' if days >= 730 else ''} ago"
    except (ValueError, TypeError):
        return ts_str[:10]


class RecallFirewall:
    def __init__(self, store: MemoryStore, graph: RelationalMemoryGraph | None = None) -> None:
        self.store = store
        self.graph = graph

    def answer(self, message: str) -> dict:
        decision = decide_recall_intent(message)
        if not decision.allowed:
            return {
                "answer": decision.reason,
                "intent": decision.intent,
                "used_private_memory": False,
                "citations": [],
            }

        # Deterministic aggregation: distance from the GPS trail (walk-1 Q25
        # — the data was in the graph, no intent could add it up).
        if self.graph and re.search(
            r"\b(?:how (?:far|much distance)|what distance|distance (?:did|have|we|i))\b",
            message.lower(),
        ):
            result = self._graph_distance(message)
            if result:
                return result

        if decision.intent == "where_is":
            result = self._where_is(message)
            if self.graph and "do not have a reliable" in result.get("answer", ""):
                grounded = self._grounded_answer(message)
                if grounded:
                    return grounded
                return self._honest_miss(message)
            return result
        if decision.intent == "recent_context":
            msg_lower = message.lower()
            # A named contact or a content topic beats the generic recency
            # dump: 'what did Ziwei and I talk about recently' is about HER;
            # 'did anyone mention munich recently' is about MUNICH — neither
            # wants a list of recent conversations.
            if self.graph and (
                self._names_a_contact(message)
                or re.search(r"\b(?:mention\w*|bring up|brought up)\b", msg_lower)
            ):
                grounded = self._grounded_answer(message)
                if grounded:
                    return grounded
            # "who have I been talking/messaging" → WhatsApp contacts path
            if self.graph and any(k in msg_lower for k in ("talk", "messag", "contact", "speak", "chatting", "lately", "recently")):
                contacts_result = self._graph_recent_contacts()
                if contacts_result:
                    return contacts_result
            # "who did I see" / "who did I meet" → vision people path
            if self.graph and any(k in msg_lower for k in ("see", "meet", "who")):
                people_result = self._graph_people_today()
                if people_result:
                    return people_result
            return self._recent_context()
        if decision.intent == "delete_scope":
            return {
                "answer": "Use the memory controls to delete by time range, category, or all memories.",
                "intent": decision.intent,
                "used_private_memory": False,
                "citations": [],
            }

        if self.graph:
            name = self._extract_name(message)
            item = self._extract_item(message)
            if decision.intent == "who_is":
                result = self._graph_who_is(name)
                if result:
                    return result
            elif decision.intent == "what_was":
                result = self._graph_what_was(item)
                if result:
                    return result
            elif decision.intent == "commitments":
                result = self._graph_commitments(name)
                if result:
                    return result
            elif decision.intent == "last_contact":
                result = self._graph_last_contact(name)
                if result:
                    return result
            elif decision.intent == "message_search":
                result = self._graph_message_search(message)
                if result:
                    return result

            # Template miss → grounded answering: deterministic sealed
            # retrieval assembles the evidence; the local LLM may answer
            # ONLY from it (refusal-by-default). This replaces both the
            # legacy observation dump and the dead-end canned miss.
            grounded = self._grounded_answer(message)
            if grounded:
                return grounded
            if decision.intent in (
                "who_is", "what_was", "commitments", "last_contact", "message_search",
            ):
                return self._honest_miss(message, intent=decision.intent)

        if self.graph:
            grounded = self._grounded_answer(message)
            if grounded:
                return grounded
        return self._general_summary(message)

    def _llm_generate(self, prompt: str, timeout: int = 45) -> str:
        """Single seam for local-LLM generation — tests stub this out."""
        payload = json.dumps({
            "model": _LLM_MODEL, "prompt": prompt, "stream": False,
            "options": {"temperature": 0},
        }).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload, headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read()).get("response", "").strip()

    def _names_a_contact(self, question: str) -> bool:
        """True when the question names a person the graph actually knows —
        used to keep person-specific questions out of generic dumps."""
        if not self.graph:
            return False
        for run in re.findall(r"\b([A-Z][\w'.ß-]*(?:\s+[A-Z][\w'.ß-]*){0,3})\b", question):
            tokens = [t for t in run.split() if t.lower() not in self._MISS_QUESTION_WORDS]
            if tokens and self.graph.resolve_person(" ".join(tokens), limit=1):
                return True
        # lowercase mentions ('what did ziwei say') — substring match only,
        # persons only (profiles() also matches object entities)
        for t in re.split(r"\W+", question.lower()):
            if len(t) >= 4 and t not in self._MISS_QUESTION_WORDS:
                hits = self.graph.profiles(label=t, limit=3).get("profiles", [])
                if any(p.get("kind") == "person" for p in hits):
                    return True
        return False

    _MISS_QUESTION_WORDS = frozenset(
        "what who whom whose where when why how did do does is are was were "
        "the my our tell show find which i has have had can could should "
        "would will whats about and or in on at to from with".split()
    )

    def _honest_miss(self, question: str, intent: str = "grounded_answer") -> dict:
        """A miss that still helps: name what is unknown, and for object
        questions say what the camera HAS seen — deterministic, no LLM."""
        answer = "I don't have anything about that in memory yet."
        if self.graph and not question.lower().strip().startswith("who"):
            known = self.graph.known_object_labels(limit=5)
            if known:
                answer += " Objects I have seen recently: " + ", ".join(known) + "."
        return {
            "answer": answer,
            "intent": intent,
            "used_private_memory": True,
            "citations": [],
            "confidence": 0.0,
        }

    # Time-scope phrases → restrict vision evidence to today. Walk-1 lesson:
    # "did I wear headphones during my walk" answered from desk-era facts
    # was the entire hallucination class (3/3 wrong answers).
    _TODAY_SCOPE_RE = re.compile(
        r"\b(?:today|this (?:morning|afternoon|evening)|tonight|right now|"
        r"currently|just now|(?:during|on|in) (?:my|the|our) "
        r"(?:walk|stroll|trip|outing|commute))\b",
        re.IGNORECASE,
    )

    def _question_since(self, question: str) -> str | None:
        if self._TODAY_SCOPE_RE.search(question):
            return datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00")
        return None

    def _graph_distance(self, question: str) -> dict | None:
        since = self._question_since(question) or datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT00:00:00"
        )
        km, fixes = self.graph.distance_covered_km(since)
        if fixes < 2:
            return None
        meters = km * 1000
        dist = f"{km:.1f} km" if km >= 1 else f"about {int(round(meters / 10) * 10)} meters"
        return {
            "answer": f"You covered roughly {dist} today ({fixes} GPS fixes; "
                      "straight-line between observations, so this is a floor).",
            "intent": "distance",
            "used_private_memory": True,
            "citations": [{
                "id": "", "captured_at": since, "source": "vision",
                "attributes": ["gps_trail"], "confidence": 0.6,
            }],
            "confidence": 0.6,
        }

    def _grounded_answer(self, question: str) -> dict | None:
        """RAG over the sealed graph: retrieval is deterministic and
        auditable; generation is constrained to the retrieved context with
        an explicit refusal default. The LLM never answers from itself —
        that distinction is what makes generation safe here where the old
        free-form synthesis was not."""
        bundle = self.graph.context_bundle(question, since=self._question_since(question))
        if not bundle:
            return None
        ctx_lines = [
            f"[{i+1}] ({item['kind']} · {item['label']}) {item['text']}"
            for i, item in enumerate(bundle)
        ]
        prompt = (
            "You answer questions from a personal memory graph. Use ONLY the "
            "context items below — never outside knowledge, never guesses. "
            "Answer the question and nothing else: do not mention context "
            "items that are unrelated to it. Facts carry [observed DATE] "
            "tags: if the question asks about a specific time or outing and "
            "the only evidence is from a different time, say NOT IN MEMORY "
            "or state the observation date explicitly — never present old "
            "evidence as current. If the context does not contain "
            "the answer, reply exactly: NOT IN MEMORY, then one short clause "
            "naming what is missing. Answer in 1-3 plain sentences.\n\n"
            "CONTEXT:\n" + "\n".join(ctx_lines)[:6000] +
            f"\n\nQUESTION: {question}\nANSWER:"
        )
        try:
            text = self._llm_generate(prompt)
        except Exception:
            return None
        if not text:
            return None
        if text.upper().startswith("NOT IN MEMORY"):
            missing = text[len("NOT IN MEMORY"):].strip(" ,.—-")
            miss = self._honest_miss(question)
            if missing:
                miss["answer"] = f"Not in my memory yet — {missing}. " + (
                    miss["answer"].partition("yet.")[2].strip()
                )
                miss["answer"] = miss["answer"].strip()
            return miss
        # Model sometimes answers AND THEN appends a refusal for the parts
        # it could not ground ('…lavender back. NOT IN MEMORY, location').
        # The grounded part is the answer; drop the residue.
        residue = text.upper().find("NOT IN MEMORY")
        if residue > 0:
            text = text[:residue].rstrip(" ,.;—-") + "."
        citations = [
            {
                "id": "", "captured_at": item.get("observed") or "",
                "source": item.get("source", "graph"),
                "attributes": [item["kind"]], "confidence": 0.7,
            }
            for item in bundle[:5]
        ]
        return {
            "answer": text[:900],
            "intent": "grounded_answer",
            "used_private_memory": True,
            "citations": citations,
            "confidence": 0.7,
        }

    # ── Owner message-content search ──────────────────────────────────────

    _MSG_BOILERPLATE = frozenset((
        "what", "was", "is", "the", "a", "an", "i", "my", "our", "me",
        "message", "messages", "long", "longest", "last", "first", "wrote",
        "write", "written", "sent", "send", "text", "texted", "mention",
        "mentioned", "mentioning", "in", "conversation", "chat", "with",
        "to", "from", "had", "did", "find", "which", "that", "about",
        "say", "said", "of", "on", "and", "for",
    ))
    _MONTHS = {
        "january": "01", "february": "02", "march": "03", "april": "04",
        "may": "05", "june": "06", "july": "07", "august": "08",
        "september": "09", "october": "10", "november": "11", "december": "12",
    }

    def _graph_message_search(self, question: str) -> dict | None:
        if not self.graph:
            return None
        lower = question.lower().rstrip("?").strip()

        # Person: capitalized run after to/with/from/and (original casing)
        person = ""
        m = re.search(
            r"\b(?:to|with|from|and)\s+([A-Z][\w'.-]*(?:\s+[A-Z][\w'.-]*)*)",
            question,
        )
        if m:
            person = m.group(1).strip()
        if not person:
            person = self._extract_name(question)
        if not person:
            return None

        from_me: bool | None = None
        if re.search(r"\bi (?:wrote|sent|texted|said|write|send)\b", lower):
            from_me = True
        elif re.search(r"\b(?:he|she|they)\s+(?:wrote|sent|said)\b", lower):
            from_me = False

        longest = bool(re.search(r"\blong(?:est)?\b", lower))

        # Date scoping: "on 14 of february" / "february 14" / bare month
        date_patterns: list[str] = []
        for month, num in self._MONTHS.items():
            if month in lower:
                day_m = re.search(
                    rf"(?:(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{month}|{month}\s+(\d{{1,2}}))",
                    lower,
                )
                day = (day_m.group(1) or day_m.group(2)) if day_m else None
                date_patterns.append(f"%-{num}-{int(day):02d}%" if day else f"%-{num}-%")

        person_tokens = {t.lower() for t in re.split(r"\W+", person) if t}
        terms = [
            t for t in re.split(r"\W+", lower)
            if len(t) >= 3 and t not in self._MSG_BOILERPLATE
            and t not in person_tokens and t not in self._MONTHS
        ]

        matches = self.graph.search_messages(
            label=person, terms=terms, from_me=from_me,
            date_prefixes=date_patterns or None, longest=longest, limit=3,
        )
        if not matches:
            return {
                "answer": f"No stored messages with {person} match that.",
                "intent": "message_search",
                "used_private_memory": True,
                "citations": [],
                "confidence": 0.0,
            }
        lines: list[str] = []
        citations: list[dict] = []
        for msg in matches:
            who = "You" if msg["from_me"] else person
            when = (msg["sent_at"] or "")[:10]
            kind = f" [{msg['media_kind']}]" if msg.get("media_kind") else ""
            lines.append(f'{when} — {who}{kind}: "{msg["text"][:400]}"')
            citations.append({
                "id": "", "captured_at": msg["sent_at"] or "",
                "source": "whatsapp", "attributes": ["message"],
                "confidence": 0.95,
            })
        return {
            "answer": "  •  ".join(lines),
            "intent": "message_search",
            "used_private_memory": True,
            "citations": citations,
            "confidence": 0.95,
        }

    def _where_is(self, message: str) -> dict:
        item = self._extract_item(message)
        if not item:
            return {
                "answer": "I need an item name to look up a location.",
                "intent": "where_is",
                "used_private_memory": False,
                "citations": [],
            }

        graph_answer = self._graph_where_is(item) if self.graph else None
        if graph_answer:
            return graph_answer

        matches = self.store.search_private_for_purpose("where_is", [item], limit=5)
        if not matches:
            return {
                "answer": f"I do not have a reliable stored memory for {item}.",
                "intent": "where_is",
                "used_private_memory": True,
                "citations": [],
            }
        best = matches[0]
        answer = self._location_sentence(item, best["private_excerpt"], best["confidence"])
        return {
            "answer": answer,
            "intent": "where_is",
            "used_private_memory": True,
            "citations": [self._citation(best)],
        }

    def _confidence_label(self, confidence: float) -> str:
        if confidence >= 0.8:
            return "confirmed"
        if confidence >= 0.5:
            return "likely"
        return "uncertain"

    def _graph_where_is(self, item: str) -> dict | None:
        if not self.graph:
            return None
        spatial_matches = self.graph.spatial_object_locations(item, limit=3)
        if spatial_matches:
            return self._spatial_where_is_answer(spatial_matches)

        relations = self.graph.query_relations(label=item, relation_type="located_at", limit=3)
        located = [r for r in relations if r.get("object") and r.get("status") in ("current", "provisional")]
        if not located:
            return None
        best = located[0]
        place = best["object"]
        confidence = best.get("confidence", 0.5)
        last_seen = (best.get("last_seen_at") or "")[:10]
        obs = best.get("observation_count", 1)
        obs_str = f" Seen {obs} times." if obs > 1 else ""
        return {
            "answer": f"{item} is at {place} ({self._confidence_label(confidence)}). Last seen: {last_seen}.{obs_str}",
            "intent": "where_is",
            "used_private_memory": True,
            "citations": [self._relation_citation(best)],
            "confidence": confidence,
        }

    def _spatial_where_is_answer(self, matches: list[dict]) -> dict:
        parts: list[str] = []
        citations: list[dict] = []
        for match in matches[:3]:
            confidence = 0.9 if match.get("verified") else 0.6
            last_seen = str(match.get("last_seen") or "")
            frame = str(match.get("frame") or "genesis")
            parts.append(
                f"{match.get('label')}: pinned in the room at "
                f"({self._meters(match.get('x'))}, {self._meters(match.get('y'))}, {self._meters(match.get('z'))}) "
                f"meters [frame: {frame}], size ~{self._meters(match.get('w'))}×{self._meters(match.get('h'))} m, "
                f"last seen {last_seen}, sightings {int(match.get('sightings') or 1)}."
            )
            citations.append(
                {
                    "id": match.get("entity_id", ""),
                    "captured_at": last_seen,
                    "source": "spatial_pose",
                    "attributes": ["spatial_pose"],
                    "confidence": confidence,
                }
            )
        return {
            "answer": " ".join(parts),
            "intent": "where_is",
            "used_private_memory": True,
            "citations": citations,
            "confidence": self._citations_confidence(citations),
        }

    @staticmethod
    def _meters(value: object) -> str:
        try:
            return f"{float(value):.2f}"
        except (TypeError, ValueError):
            return "0.00"

    @staticmethod
    def _relation_citation(relation: dict) -> dict:
        return {
            "id": relation.get("id", ""),
            "captured_at": relation.get("last_seen_at") or "",
            "source": relation.get("source") or "graph",
            "attributes": [relation.get("relation_type", "relation")],
            "confidence": relation.get("confidence", 0.5),
        }

    @staticmethod
    def _canonical(profile: dict) -> dict[str, str]:
        """Extract {key: value} from canonical_slots or fall back to slots."""
        cs = profile.get("canonical_slots") or {}
        return {k: v.get("value", "") for k, v in cs.items() if v.get("status") in ("current", "provisional", None)}

    @staticmethod
    def _slot_citations(profile: dict, keys: list[str]) -> list[dict]:
        """Provenance for the canonical slots an answer was built from.

        One citation per distinct (source, last_seen_at) pair so a profile
        whose facts all come from the same import yields a single citation.
        """
        cs = profile.get("canonical_slots") or {}
        seen: set[tuple[str, str]] = set()
        citations: list[dict] = []
        for key in keys:
            slot = cs.get(key)
            if not slot or not slot.get("value"):
                continue
            source = slot.get("source") or "graph"
            captured = slot.get("last_seen_at") or ""
            dedupe = (source, captured)
            if dedupe in seen:
                continue
            seen.add(dedupe)
            citations.append(
                {
                    "id": profile.get("id", ""),
                    "captured_at": captured,
                    "source": source,
                    "attributes": [k for k in keys if (cs.get(k) or {}).get("source") == source],
                    "confidence": slot.get("confidence", 0.5),
                }
            )
        return citations

    @staticmethod
    def _citations_confidence(citations: list[dict]) -> float:
        """Conservative answer confidence: the weakest cited fact bounds the claim."""
        if not citations:
            return 0.0
        return min(c.get("confidence", 0.5) for c in citations)

    def _graph_who_is(self, label: str) -> dict | None:
        if not self.graph:
            return None
        q = label.strip()
        profiles = self.graph.resolve_person(q, limit=3) if q else self.graph.profiles(limit=3).get("profiles", [])
        if not profiles:
            return None
        parts = []
        citations: list[dict] = []
        _WHO_IS_KEYS = [
            "last_contact_at", "last_event_at", "relationship_source",
            "message_count", "event_count", "recent_topics", "calendar_topics",
            "recent_messages", "open_commitments", "commitments_to_me",
            "hair_colour", "clothing", "build", "age_estimate",
        ]
        for p in profiles:
            entity_id = p.get("id", "")
            real_name = self.graph.get_entity_attribute(entity_id, "real_name") if entity_id else None
            display = real_name if real_name else (p.get("label") or "unknown person")
            attrs = self._canonical(p)
            sentences: list[str] = []
            # Opening: when + how many messages
            contact_ts = attrs.get("last_contact_at") or attrs.get("last_event_at")
            src = attrs.get("relationship_source", "WhatsApp")
            count = attrs.get("message_count") or attrs.get("event_count")
            if contact_ts:
                rel = _relative_date(contact_ts)
                if count:
                    sentences.append(
                        f"You last spoke {rel} on {src.title()} — {count} messages exchanged"
                    )
                else:
                    sentences.append(f"You last spoke {rel} on {src.title()}")
            elif count:
                sentences.append(f"{count} messages on {src.title()}")

            # Topics and evidence — strictly extractive, never generated
            topics = attrs.get("recent_topics") or attrs.get("calendar_topics")
            messages_block = attrs.get("recent_messages", "")
            if topics:
                sentences.append(f"Recent topics: {topics}")
            quote = _latest_their_quote(messages_block) if messages_block else ""
            if quote:
                sentences.append(f'They recently said: "{quote[:200]}"')

            # Commitments — most human-readable part
            if attrs.get("open_commitments"):
                try:
                    commits = json.loads(attrs["open_commitments"])
                    if commits:
                        sentences.append(
                            "Your open commitments: " + "; ".join(f'"{c}"' for c in commits[:2])
                        )
                except (ValueError, TypeError):
                    pass

            if attrs.get("commitments_to_me"):
                try:
                    theirs = json.loads(attrs["commitments_to_me"])
                    if theirs:
                        sentences.append(
                            "They promised: " + "; ".join(f'"{c}"' for c in theirs[:2])
                        )
                except (ValueError, TypeError):
                    pass

            # Visual attributes from camera enrichment (secondary)
            for key in ("hair_colour", "clothing", "build", "age_estimate"):
                if attrs.get(key):
                    sentences.append(f"{key.replace('_', ' ')}: {attrs[key]}")

            body = ". ".join(sentences) if sentences else "No conversation history yet."
            parts.append(f"{display}: {body}.")
            citations.extend(self._slot_citations(p, _WHO_IS_KEYS))

        return {
            "answer": " ".join(parts),
            "intent": "who_is",
            "used_private_memory": True,
            "citations": citations,
            "confidence": self._citations_confidence(citations),
        }

    def _graph_commitments(self, label: str) -> dict | None:
        """Surface open_commitments attributes — optionally filtered by person name."""
        if not self.graph:
            return None
        q = label.strip()
        profiles = self.graph.resolve_person(q, limit=20) if q else self.graph.profiles(limit=20).get("profiles", [])
        if not profiles and q:
            # 'do I have any promises to keep this week' leaves boilerplate
            # the name-stripper missed, not a person name — fall back to the
            # all-contacts scan. A single unknown token ('Bobo') stays a
            # miss: scope-wrong answers are worse than honest ones.
            tokens = q.split()
            if len(tokens) > 2 or any(t.lower() in self._MISS_QUESTION_WORDS for t in tokens):
                profiles = self.graph.profiles(limit=20).get("profiles", [])
        if not profiles:
            return None
        all_commits: list[str] = []
        citations: list[dict] = []
        for p in profiles:
            entity_id = p.get("id", "")
            real_name = self.graph.get_entity_attribute(entity_id, "real_name") if entity_id else None
            display = real_name if real_name else (p.get("label") or "unknown person")
            raw = self._canonical(p).get("open_commitments", "")
            if raw:
                try:
                    commits = json.loads(raw)
                    for c in commits[:3]:
                        all_commits.append(f'[{display}] "{c}"')
                    if commits:
                        citations.extend(self._slot_citations(p, ["open_commitments"]))
                except (ValueError, TypeError):
                    pass
        if not all_commits:
            return {
                "answer": "No open commitments found in contacts.",
                "intent": "commitments",
                "used_private_memory": True,
                "citations": [],
                "confidence": 0.0,
            }
        return {
            "answer": "Open commitments: " + "; ".join(all_commits[:6]) + ".",
            "intent": "commitments",
            "used_private_memory": True,
            "citations": citations,
            "confidence": self._citations_confidence(citations),
        }

    # Generic pronouns that mean "show all" rather than a specific person
    _GENERIC_SUBJECTS = frozenset(
        "someone anyone people them they contacts everyone anybody everybody".split()
    )

    def _graph_last_contact(self, label: str) -> dict | None:
        """Surface last_contact_at and recent_topics for a named person."""
        if not self.graph:
            return None
        name = label.strip()
        if name.lower() in self._GENERIC_SUBJECTS:
            name = ""
        profiles = self.graph.resolve_person(name, limit=10) if name else self.graph.profiles(limit=10).get("profiles", [])
        if not profiles:
            return None
        parts: list[str] = []
        citations: list[dict] = []
        for p in profiles:
            entity_id = p.get("id", "")
            real_name = self.graph.get_entity_attribute(entity_id, "real_name") if entity_id else None
            display = real_name if real_name else (p.get("label") or "unknown person")
            attrs = self._canonical(p)
            contact_ts = attrs.get("last_contact_at") or attrs.get("last_event_at")
            if not contact_ts:
                continue
            source = attrs.get("relationship_source", "WhatsApp")
            topics = attrs.get("recent_topics") or attrs.get("calendar_topics", "")
            rel = _relative_date(contact_ts)
            sentence = f"{display} — {rel} on {source.title()}"
            if topics:
                sentence += f"; topics: {topics}"
            parts.append(sentence)
            citations.extend(
                self._slot_citations(
                    p, ["last_contact_at", "last_event_at", "recent_topics", "calendar_topics"]
                )
            )
        if not parts:
            return None
        # For single person: full sentence; for multiple: list
        if len(parts) == 1:
            answer = f"You last spoke to {parts[0]}."
        else:
            answer = "Recent contacts: " + "; ".join(parts) + "."
        return {
            "answer": answer,
            "intent": "last_contact",
            "used_private_memory": True,
            "citations": citations,
            "confidence": self._citations_confidence(citations),
        }

    def _graph_what_was(self, context: str) -> dict | None:
        if not self.graph:
            return None
        relations = self.graph.query_relations(label=context, limit=5)
        active = [r for r in relations if r.get("status") in ("current", "provisional")]
        if not active:
            return None
        parts = [
            f"{r['subject']} {r['relation_type'].replace('_', ' ')} {r.get('object') or r.get('place', '')}"
            for r in active
        ]
        citations = [self._relation_citation(r) for r in active]
        return {
            "answer": "Recent context for " + context + ": " + "; ".join(parts) + ".",
            "intent": "what_was",
            "used_private_memory": True,
            "citations": citations,
            "confidence": self._citations_confidence(citations),
        }

    def _humanize(self, raw_text: str) -> str:
        """Convert 'OBJECT | keys | location=desk, near=laptop' to plain English."""
        if " | " not in raw_text:
            return raw_text
        parts = [p.strip() for p in raw_text.split(" | ")]
        if len(parts) < 2:
            return raw_text
        label = parts[1].replace("_", " ").title()
        attrs = parts[2] if len(parts) > 2 else ""
        loc_m = re.search(r"location=([^,\s]+)", attrs)
        near_m = re.search(r"near=([^,\s]+)", attrs)
        title_m = re.search(r"title=([^,\s]+)", attrs)
        if loc_m:
            place = loc_m.group(1).replace("_", " ").title()
            suffix = f", near {near_m.group(1).replace('_', ' ').title()}" if near_m else ""
            return f"{label} is at {place}{suffix}"
        if title_m:
            title = title_m.group(1).replace("_", " ").title()
            return f"{label} titled {title} was observed"
        return f"{label} was observed"

    def _graph_people_today(self) -> dict | None:
        if not self.graph:
            return None
        people = self.graph.recent_people(hours=24)
        if not people:
            return None
        count = len(people)
        noun = "person" if count == 1 else "people"
        # Bug 4 fix: resolve real_name attribute; never expose internal IDs
        names = []
        citations = []
        for p in people[:5]:
            real_name = self.graph.get_entity_attribute(p["id"], "real_name")
            names.append(real_name if real_name else "unknown person")
            citations.append(
                {
                    "id": p.get("id", ""),
                    "captured_at": p.get("last_seen_at") or "",
                    "source": "vision",
                    "attributes": ["encounter"],
                    "confidence": p.get("confidence", 0.5),
                }
            )
        details = ", ".join(names)
        return {
            "answer": f"I saw {count} {noun} today: {details}.",
            "intent": "recent_context",
            "used_private_memory": True,
            "citations": citations,
            "confidence": self._citations_confidence(citations),
        }

    def _graph_recent_contacts(self) -> dict | None:
        """Return WhatsApp contacts ordered by last_contact_at attribute."""
        if not self.graph:
            return None
        result = self.graph.profiles(label=None, limit=50)
        profiles = result.get("profiles", [])
        if not profiles:
            return None
        # Filter to contacts with last_contact_at and sort by date descending
        dated: list[tuple[str, str]] = []
        citations: list[dict] = []
        for p in profiles:
            canon = self._canonical(p)
            last_at = canon.get("last_contact_at", "")
            source = canon.get("relationship_source", "")
            if last_at and source == "whatsapp":
                dated.append((last_at, p.get("label") or "unknown"))
                citations.extend(self._slot_citations(p, ["last_contact_at"]))
        if not dated:
            return None
        dated.sort(key=lambda x: x[0], reverse=True)
        today_contacts = [name for date, name in dated if date >= dated[0][0][:10]][:8]
        recent_all = [name for _, name in dated[:8]]
        display = today_contacts if today_contacts else recent_all
        count = len(dated)
        names_str = ", ".join(display[:5])
        suffix = f" (+{count - 5} more)" if count > 5 else ""
        return {
            "answer": f"Recent conversations: {names_str}{suffix}. ({count} total WhatsApp contacts)",
            "intent": "recent_context",
            "used_private_memory": True,
            "citations": citations[:8],
            "confidence": self._citations_confidence(citations[:8]),
        }

    def _recent_context(self) -> dict:
        recent = self.store.recent_public(limit=5)
        if not recent:
            return {
                "answer": "I do not have recent memories yet.",
                "intent": "recent_context",
                "used_private_memory": False,
                "citations": [],
            }
        summaries = "; ".join(self._humanize(row["summary"]) for row in recent[:3])
        return {
            "answer": f"Recent context: {summaries}",
            "intent": "recent_context",
            "used_private_memory": False,
            "citations": [{"id": row["id"], "captured_at": row["captured_at"]} for row in recent[:3]],
        }

    def _general_summary(self, message: str) -> dict:
        terms = [word for word in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", message.lower()) if len(word) > 3]
        matches = self.store.search_private_for_purpose("general_summary", terms[:3], limit=3)
        if not matches:
            return {
                "answer": "I do not have enough allowed memory to answer that.",
                "intent": "general_summary",
                "used_private_memory": True,
                "citations": [],
            }
        safe = "; ".join(self._humanize(redact_for_public_summary(row["private_excerpt"])) for row in matches)
        return {
            "answer": f"Based on allowed memory: {safe}",
            "intent": "general_summary",
            "used_private_memory": True,
            "citations": [self._citation(row) for row in matches],
        }

    # Prefixes to strip when extracting a person name or subject from a query
    _NAME_STRIP = re.compile(
        r"^\s*(?:"
        r"what (?:were|are|was|is) (?:the |my |our )?(?:recent |latest |last )?topics? (?:with|about|of)|"
        r"topics? (?:with|about|of)|"
        r"who is|tell me about|what do i know about|describe|"
        r"info (?:on|about)|profile of|what(?:'s| is)(?: the)? story with|"
        r"when did i (?:last )?(?:talk|speak|messag|contact|hear from)(?: to| with| from)?|"
        r"how long (?:since|ago)(?: i)?(?: (?:talk|spoke|contact))?(?: to| with)?|"
        r"last (?:time i|time)? ?(?:talk|spoke|contact|messag|heard from)(?: to| with| from)?|"
        r"what did i (?:commit|say|tell|promise)(?: to)?|"
        r"what (?:are|were) (?:my )?(?:commit\w*|promis\w*)(?: (?:to|with|for))?|"
        r"what (?:commitments?|promises?) (?:do|did) i (?:have|owe)(?: (?:to|with|for|toward))?|"
        r"what (?:do|did) i (?:have|owe)(?: (?:to|with|for))?(?: (?:commit\w*|promis\w*))?|"
        r"what (?:do|did) i owe(?: to)?|"
        r"my "
        r")\s*",
        re.IGNORECASE,
    )

    def _extract_name(self, message: str) -> str:
        """Strip intent-specific query boilerplate; return the remaining name/subject."""
        cleaned = message.strip().rstrip("?").strip()
        cleaned = self._NAME_STRIP.sub("", cleaned).strip()
        return cleaned

    _WHERE_ITEM_RE = re.compile(
        r"^(?:where(?:'s| is| was)?|wo ist)\s+"
        r"(?:my |the |mein |meine |meinen |der |die |das )?"
        r"(?P<obj>[a-zäöüß ]+)$",
        re.IGNORECASE,
    )

    def _extract_item(self, message: str) -> str:
        """Extract a subject term — used for object-location and general queries."""
        lower = message.lower().strip().rstrip("?")
        if match := self._WHERE_ITEM_RE.match(lower):
            return " ".join(match.group("obj").split())
        lower = lower.replace("where did i put", "")
        lower = lower.replace("where's", "")
        lower = lower.replace("where was", "")
        lower = lower.replace("where is", "")
        lower = lower.replace("where are", "")
        lower = lower.replace("wo ist", "")
        lower = lower.replace("my ", "")
        lower = lower.replace("the ", "")
        return " ".join(lower.split())

    def _location_sentence(self, item: str, text: str, confidence: float) -> str:
        lower = text.lower()
        for marker in (" in ", " into ", " inside ", " on ", " at ", " near "):
            if marker in lower:
                location = text[lower.index(marker) + len(marker) :].strip(" .")
                location = redact_for_public_summary(location)
                return f"{item} was last remembered {marker.strip()} {location}. Confidence {confidence:.2f}."
        return f"I found a recent memory about {item}, but the location is uncertain. Confidence {confidence:.2f}."

    def _citation(self, row: dict) -> dict:
        return {
            "id": row["id"],
            "captured_at": row["captured_at"],
            "category": row["category"],
            "sensitivity": row["sensitivity"],
            "confidence": row["confidence"],
        }

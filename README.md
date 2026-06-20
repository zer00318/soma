# SOMA

SOMA is an input-only wearable memory: on-device perception converts the live
world to typed text observations, raw pixels and audio are discarded, and later
recall answers unconstrained questions from text evidence with citations or an
honest refusal.

`ops/NORTH_STAR.md` is the product source of truth. The founder's locked
architecture decisions supersede its outdated suggestion to constrain question
types.

## Architecture

The production system is a Python modular monolith under `src/soma/`:

- `domain/`: pure observations, entities, bindings, confidence, provenance, queries
- `application/`: capture, binding, recall, and grounding use cases
- `ports/`: perceiver, model, OCR, ASR, reasoner, and memory interfaces
- `adapters/`: device/host implementations and temporary legacy bridges
- `eval/`: engine-independent OAG calculation

The append-only observation log is the capture source of truth. Projections build
the typed EvidenceGraph; projections are disposable and replayable.

The current `scripts/ask_home.py` answer engine remains behind the new `Recall`
boundary while it is replaced capability by capability. `scripts/build_*.py`,
file-channel JSON memories, and `soma-native-fastvlm/` are migration inputs, not
the target architecture.

`archive/soma_hub_legacy/` contains the abandoned relational hub. It is retained
for archaeology only and is not a runtime dependency.

## Governance

Install development checks once, then run the same merge gate used by the
pre-push hook:

```bash
make install-dev
make check
```

The gate enforces formatting, linting, strict typing for domain/application,
complexity and function-length limits, no dead production code, frozen-gold
hashes, focused evaluator tests, and at least 80% domain/application coverage.

## Current Privacy Status

The target invariant is strict: raw media never persists and never egresses;
only typed text may leave the device. Existing `.MOV`, frames, and replay-based
evaluation artifacts predate this architecture and are evidence that the live
invariant is not yet proven. They must not be mistaken for production behavior.


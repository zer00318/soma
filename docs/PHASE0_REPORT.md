# Phase 0 — Foundation Reset (report)

Status: **complete locally, gate green.** Remote push + PR pending GitHub auth.

## What was verified against the live code (ground-truth corrections)

| Prior claim | Verified reality |
|---|---|
| Git "history unwalkable / 145 missing objects" | `git log` walked, but `git rev-list --objects HEAD` failed: HEAD's tree referenced missing objects. **~517** objects missing per connectivity fsck, including commit `24b08d6`. `git write-tree` blocked by a missing index blob (`.claude/launch.json` → `0d22eb6`). |
| `pre-overhaul-snapshot` tag is a safety net | **False** — the tag's tree was also broken. It protected nothing. |
| Recovery possible in place | **Impossible** — missing objects exist nowhere (no remote/backup). Only the working tree was a complete copy. |
| 285MB sqlite is the live store | Confirmed dead relative to the answer path; moved to archive. |
| ask_home.py broad excepts | 47 confirmed (legacy; carve-out target). |

## What was done

- **Git rebuilt from the gate-green working tree.** Corrupt `.git` (11MB) moved read-only to
  `archive/git-corrupt-20260620/` (nothing deleted — reversible). Fresh repo: `fsck` clean,
  `write-tree` works.
- **Privacy hardening of `.gitignore`**: raw video/audio/heic blocked globally as defense-in-depth
  (matching the code-level egress guard); removed a negation that force-tracked a 22MB model weight.
  Privacy gate at commit time confirmed **zero** media/model binaries staged.
- **Legacy data archived**: `soma_hub.sqlite3` (272M) + 2 backups → `archive/soma_hub_legacy/data/`
  (gitignored). Legacy soma_hub code already at `archive/soma_hub_legacy/`.
- **Governance gate wired** three ways — `make check`, `.githooks/pre-push` (`exec make check`),
  and `.github/workflows/check.yml` (runs on every push + PR to main).
- Baseline tagged `p0-foundation-reset`.

## Gate output (`make check`, EXIT=0)

- ruff + ruff-format: clean
- mypy --strict (domain + application, 14 files): clean
- complexity ≤10 / length limits (`tools/check_functions.py`): clean
- vulture: clean
- frozen-gold hash check: 2 files verified
- pytest: **27 passed**; coverage **87.13%** on domain+application (≥80% required)

## OAG (from the pre-rebuild run; engine code unchanged by the rebuild)

- **Walk (in-sample)**: OAG 44.0% — 14 correct, 2 wrong, 8 miss, 1 unresolved. RAS +50.0; hallucination 12.5%.
- **Validation (provisional, 17/19)**: OAG ~42.1% — 11 correct, 2 wrong, 3 miss, 1 unresolved, 2 unrun. Hallucination 15.4%.
- ⚠️ The "validation" clip is **contaminated by prior tuning** — not a legitimate held-out set.
  A genuinely held-out clip is required before any P3 hallucination/useful-rate claims.

## Known debt carried forward (strangler-fig: stays until carved out)

- App-code duplication: `App/`, `apps/ios/`, `soma-native-fastvlm/` coexist.
- `.bak` cruft committed (e.g. `scripts/ask_home.py.bak-*`) — remove in a cleanup PR.
- `ops/cockpit/*.json` runtime churn (consider gitignoring runtime state).
- 47 broad excepts in `ask_home.py`; 818-line `build_evidence_dossier`.
- Both binders still produce zero entities/bindings (P2 target).
- Live capture unproven; raw `.MOV` retained on disk (P1/P4 target).

## Remaining to close Phase 0

1. Push `main` + `codex/p0-foundation-reset` + tags to a private GitHub remote (needs auth).
2. Open PR → `main`; confirm CI gate goes green.
3. Establish a genuinely held-out eval clip (no tuning leakage) for OAG.

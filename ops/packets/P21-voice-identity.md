# P21 — Voice-identity clustering (WHO, anonymous-until-named)
wave: W2 · tag: judgment · executor: Opus effort=high · depends: P02

## Context (self-contained)
ASR already stores verbatim speech (delta-commit path, M5) but nobody knows WHO spoke.
Law of the product: people are anonymous-until-named — voices cluster on-device as
`person_A`, `person_B`; a cluster is christened retroactively when context reveals a name
("thanks, Marcus") or the owner names it in chat/review cards (W3/W4 wire those; this
packet only makes clusters + retroactive rename possible). Others' speech is kept
verbatim, attributed (founder decision — it never leaves the owner's hardware).

## Laws that bind you
L1: audio never leaves the phone; speaker embeddings are non-reversible fingerprints and
MAY cross (P02 `fingerprint` field on speech observations). L2: attribution carries
confidence — uncertain attribution says so ("someone, possibly person_A").

## Do
1. Phone: per-utterance speaker embedding on-device (SpeechAnalyzer/SNVoice or a small
   ANE model — executor evaluates against iOS 26 APIs, documents the call). Emit on each
   ASR observation: `fingerprint` + `speaker_cluster_id` (session-local clustering; the
   owner's own voice becomes its own stable cluster fast — it's the most frequent).
2. Store/sleep: cross-session cluster reconciliation (same person across days) via
   fingerprint similarity — conservative: merge only above a measured threshold, else
   leave separate (identity-resolution brain, P32, owns the clever merging later).
3. Rename semantics in the store: naming a cluster re-labels ALL its past and future rows
   (retroactive christening) without touching raw verbatim text.
4. Validate on real audio: two-person conversation captured; clusters separate; a
   deliberate "thanks <name>" utterance exists for W3 to test christening against.

## Done when
Real two-speaker capture yields ≥80% utterances attributed to the correct stable cluster
(founder verifies by reading the rows); "what did person_A say about X" answers through
/ask; rename re-labels history; pytest + battery hold. INDEX flipped with the measured
attribution numbers.

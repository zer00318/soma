import { readFile } from "node:fs/promises";

const logFile =
  process.argv[2] ||
  `${process.env.HOME}/Library/Application Support/SOMA/soma_native_text.ndjson`;
const text = await readFile(logFile, "utf8").catch(() => "");
const entries = text
  .split("\n")
  .filter(Boolean)
  .map((line) => {
    try {
      return JSON.parse(line);
    } catch {
      return null;
    }
  })
  .filter(Boolean);

const statusEntries = entries.filter((entry) => entry.type === "native_status");
const memoryEntries = entries.filter((entry) => entry.type === "native_inference_result");
const snapshotEntries = entries.filter((entry) => entry.type === "native_context_snapshot");
const digestEntries = entries.filter((entry) => entry.type === "native_context_digest");
const facts = new Map();
const sourceCounts = {};
const issueCounts = {};

for (const entry of memoryEntries.slice(-80)) {
  const source = String(entry.source || "unknown");
  sourceCounts[source] = (sourceCounts[source] || 0) + 1;
  const memory = String(entry.memory_text || "");
  if (/native_vision_no_record/i.test(memory)) {
    issueCounts["no-record entered memory"] = (issueCounts["no-record entered memory"] || 0) + 1;
  }
  if (/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f]/u.test(memory)) {
    issueCounts["control characters in memory"] = (issueCounts["control characters in memory"] || 0) + 1;
  }
  if (/\b(optical equipment|sunglasses|raw glass|camera view|taking a picture|object name|relation\/location)\b/i.test(memory)) {
    issueCounts["schema/noisy label entered memory"] = (issueCounts["schema/noisy label entered memory"] || 0) + 1;
  }
  if (source === "native_speech" && /^EVENT \| nearby speech \| transcript: "\s*"/i.test(memory)) {
    issueCounts["empty speech transcript"] = (issueCounts["empty speech transcript"] || 0) + 1;
  }
  for (const line of memory.split("\n").filter(Boolean)) {
    facts.set(line.toLowerCase(), line);
  }
}

const latestSnapshot = snapshotEntries.at(-1);
const latestDigest = digestEntries.at(-1);
const strongestContext = latestSnapshot?.facts
  ?.slice()
  ?.sort((a, b) => (b.observations || 0) - (a.observations || 0))
  ?.slice(0, 20)
  ?.map((fact) => ({
    observations: fact.observations,
    age_seconds: fact.age_seconds,
    active_score: fact.active_score,
    text: fact.text,
    last_seen: fact.last_seen,
  })) || [];

const lastStatus = statusEntries.slice(-10).map((entry) => ({
  timestamp: entry.timestamp,
  status: entry.status,
  scene_phase: entry.scene_phase,
  motion_score: entry.motion_score,
  stable_frames: entry.stable_frames,
  frame_index: entry.frame_index,
  frame_count: entry.frame_count,
  ocr_count: entry.ocr_count,
  body_count: entry.body_count,
  face_count: entry.face_count,
  accepted_classifications: entry.accepted_classifications,
  raw_classifications: entry.raw_classifications,
  audio_status: entry.audio_status,
  location_status: entry.location_status,
  location_hint: entry.location_hint,
  detector_status: entry.detector_status,
}));

const latestAudioStatuses = statusEntries
  .filter((entry) => entry.status === "audio_status")
  .slice(-5)
  .map((entry) => ({
    timestamp: entry.timestamp,
    audio_status: entry.audio_status,
  }));

const latestLocationStatuses = statusEntries
  .filter((entry) => entry.status === "location_status" || entry.status === "location_hint_updated")
  .slice(-5)
  .map((entry) => ({
    timestamp: entry.timestamp,
    status: entry.status,
    location_status: entry.location_status,
    location_hint: entry.location_hint,
  }));

const latestDetectorStatuses = statusEntries
  .filter((entry) => entry.status === "detector_status")
  .slice(-8)
  .map((entry) => ({
    timestamp: entry.timestamp,
    detector_status: entry.detector_status,
  }));

const latestCandidates = statusEntries
  .filter((entry) => entry.status === "native_vision_candidates")
  .slice(-5)
  .map((entry) => ({
    timestamp: entry.timestamp,
    scene_phase: entry.scene_phase,
    frame_index: entry.frame_index,
    raw_ocr_count: entry.raw_ocr_count,
    ocr_count: entry.ocr_count,
    accepted_ocr_samples: entry.accepted_ocr_samples || [],
    rejected_ocr_samples: entry.rejected_ocr_samples || [],
    body_count: entry.body_count,
    face_count: entry.face_count,
    accepted_classifications: entry.accepted_classifications || [],
    raw_classifications: entry.raw_classifications || [],
  }));

console.log(
  JSON.stringify(
    {
      logFile,
      totalEntries: entries.length,
      statusEntries: statusEntries.length,
      memoryEntries: memoryEntries.length,
      snapshotEntries: snapshotEntries.length,
      sourceCounts,
      recentFacts: Array.from(facts.values()).slice(-30),
      latestContext: latestSnapshot
        ? {
            timestamp: latestSnapshot.timestamp,
            reason: latestSnapshot.reason,
            scene_phase: latestSnapshot.scene_phase,
            motion_score: latestSnapshot.motion_score,
            fact_count: latestSnapshot.fact_count,
            strongestContext,
          }
        : null,
      latestContextDigest: latestDigest
        ? {
            timestamp: latestDigest.timestamp,
            reason: latestDigest.reason,
            scene_phase: latestDigest.scene_phase,
            motion_score: latestDigest.motion_score,
            location_hint: latestDigest.location_hint,
            active_fact_count: latestDigest.active_fact_count,
            stable_facts: latestDigest.stable_facts || [],
            provisional_facts: latestDigest.provisional_facts || [],
            stale_but_remembered_facts: latestDigest.stale_but_remembered_facts || [],
          }
        : null,
      latestCandidates,
      latestAudioStatuses,
      latestLocationStatuses,
      latestDetectorStatuses,
      lastStatus,
      issueCounts,
    },
    null,
    2,
  ),
);

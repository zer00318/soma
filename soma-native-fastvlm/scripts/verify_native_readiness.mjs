import { readdir, readFile, stat } from "node:fs/promises";
import { join } from "node:path";

const args = new Set(process.argv.slice(2));
const requireSpeech = args.has("--require-speech");
const requireDetectorMemory = args.has("--require-detector-memory");
const requireOcrMemory = args.has("--require-ocr");
const logFile =
  process.env.SOMA_NATIVE_LOG ||
  `${process.env.HOME}/Library/Application Support/SOMA/soma_native_text.ndjson`;
const storageDir =
  process.env.SOMA_NATIVE_STORAGE ||
  `${process.env.HOME}/Library/Application Support/SOMA`;

const rawMediaExtensions = new Set([
  ".aac",
  ".aif",
  ".aiff",
  ".caf",
  ".heic",
  ".jpeg",
  ".jpg",
  ".m4a",
  ".mov",
  ".mp3",
  ".mp4",
  ".png",
  ".tiff",
  ".wav",
  ".webm",
]);

function parseEntries(text) {
  return text
    .split("\n")
    .filter(Boolean)
    .map((line) => {
      try {
        return JSON.parse(line);
      } catch {
        return { type: "parse_error", raw: line };
      }
    });
}

async function listFiles(root) {
  const files = [];
  async function walk(dir) {
    let entries = [];
    try {
      entries = await readdir(dir, { withFileTypes: true });
    } catch {
      return;
    }

    for (const entry of entries) {
      const fullPath = join(dir, entry.name);
      if (entry.isDirectory()) {
        await walk(fullPath);
      } else {
        const info = await stat(fullPath).catch(() => null);
        files.push({
          path: fullPath,
          size: info?.size ?? 0,
        });
      }
    }
  }
  await walk(root);
  return files;
}

function sourceCounts(memoryEntries) {
  const counts = {};
  for (const entry of memoryEntries) {
    const source = String(entry.source || "unknown");
    counts[source] = (counts[source] || 0) + 1;
  }
  return counts;
}

function memoryIssues(memoryEntries) {
  const issues = {};
  const add = (name) => {
    issues[name] = (issues[name] || 0) + 1;
  };

  for (const entry of memoryEntries) {
    const memory = String(entry.memory_text || "");
    if (/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f]/u.test(memory)) {
      add("control characters in memory");
    }
    if (/\b(optical equipment|sunglasses|raw glass|camera view|taking a picture|object name|relation\/location)\b/i.test(memory)) {
      add("schema/noisy label entered memory");
    }
    if (!/^(OBJECT|EVENT) \|/m.test(memory)) {
      add("memory without OBJECT/EVENT line");
    }
  }

  return issues;
}

function requirement(name, passed, evidence) {
  return { name, passed: Boolean(passed), evidence };
}

const text = await readFile(logFile, "utf8").catch(() => "");
const entries = parseEntries(text);
const memoryEntries = entries.filter((entry) => entry.type === "native_inference_result");
const statusEntries = entries.filter((entry) => entry.type === "native_status");
const snapshotEntries = entries.filter((entry) => entry.type === "native_context_snapshot");
const digestEntries = entries.filter((entry) => entry.type === "native_context_digest");
const counts = sourceCounts(memoryEntries);
const issues = memoryIssues(memoryEntries);
const files = await listFiles(storageDir);
const rawMediaFiles = files.filter((file) => {
  const lower = file.path.toLowerCase();
  return [...rawMediaExtensions].some((extension) => lower.endsWith(extension));
});

const latestSnapshot = snapshotEntries.at(-1);
const latestDigest = digestEntries.at(-1);
const runtimeStatuses = statusEntries.filter((entry) => entry.status === "local_runtime_status");
const latestRuntimeStatus = runtimeStatuses.at(-1);
const audioStatuses = statusEntries
  .filter((entry) => entry.status === "audio_status")
  .map((entry) => String(entry.audio_status || ""));
const detectorStatuses = statusEntries
  .filter((entry) => entry.status === "detector_status")
  .map((entry) => String(entry.detector_status || ""));
const locationHints = statusEntries
  .map((entry) => String(entry.location_hint || ""))
  .filter(Boolean);
const ocrCandidateStatuses = statusEntries.filter((entry) => entry.status === "native_vision_candidates");
const acceptedOcrSamples = ocrCandidateStatuses.flatMap((entry) => entry.accepted_ocr_samples || []);
const rawOcrSamples = ocrCandidateStatuses.flatMap((entry) => [
  ...(entry.accepted_ocr_samples || []),
  ...(entry.rejected_ocr_samples || []),
]);
const ocrMemoryEntries = memoryEntries.filter((entry) =>
  /OBJECT \| visible sign\/board \| OCR text:/i.test(String(entry.memory_text || "")),
);

const requirements = [
  requirement("native log exists and is parseable", entries.length > 0 && !entries.some((entry) => entry.type === "parse_error"), {
    logFile,
    entries: entries.length,
  }),
  requirement("local runtime dependencies are present", Boolean(latestRuntimeStatus?.detector_ready_for_start && latestRuntimeStatus?.whisper_ready_for_start), {
    detectorReady: latestRuntimeStatus?.detector_ready_for_start || false,
    whisperReady: latestRuntimeStatus?.whisper_ready_for_start || false,
    detectorPythonExists: latestRuntimeStatus?.detector_python_exists || false,
    detectorModelExists: latestRuntimeStatus?.detector_model_exists || false,
    whisperStreamExists: latestRuntimeStatus?.whisper_stream_exists || false,
    asrModelExists: latestRuntimeStatus?.asr_model_exists || false,
    missingDetectorRequirements: latestRuntimeStatus?.missing_detector_requirements || [],
    missingWhisperRequirements: latestRuntimeStatus?.missing_whisper_requirements || [],
  }),
  requirement("visual OBJECT/EVENT memory exists", (counts.native_vision || 0) > 0, counts),
  requirement("OCR sign/board memory exists when required", !requireOcrMemory || ocrMemoryEntries.length > 0, {
    requireOcrMemory,
    ocrMemoryCount: ocrMemoryEntries.length,
    acceptedOcrSamples: acceptedOcrSamples.slice(-8),
    rawOcrSamples: rawOcrSamples.slice(-8),
  }),
  requirement("YOLO detector OBJECT memory exists when required", !requireDetectorMemory || (counts.native_yolo_detector || 0) > 0, {
    requireDetectorMemory,
    sourceCounts: counts,
  }),
  requirement("progressive context snapshots exist", snapshotEntries.length > 0 && (latestSnapshot?.fact_count || 0) > 0, {
    snapshots: snapshotEntries.length,
    latestFactCount: latestSnapshot?.fact_count || 0,
  }),
  requirement("context snapshots expose recency scoring", Boolean(latestSnapshot?.facts?.some((fact) => typeof fact.active_score === "number" && typeof fact.age_seconds === "number")), {
    hasActiveScore: Boolean(latestSnapshot?.facts?.some((fact) => typeof fact.active_score === "number")),
    hasAgeSeconds: Boolean(latestSnapshot?.facts?.some((fact) => typeof fact.age_seconds === "number")),
  }),
  requirement("time-aware context digest exists", digestEntries.length > 0 && (latestDigest?.active_fact_count || 0) > 0, {
    digests: digestEntries.length,
    latestActiveFactCount: latestDigest?.active_fact_count || 0,
    latestStableFactCount: latestDigest?.stable_facts?.length || 0,
    latestProvisionalFactCount: latestDigest?.provisional_facts?.length || 0,
    latestStaleRememberedFactCount: latestDigest?.stale_but_remembered_facts?.length || 0,
  }),
  requirement("context digest separates current from stale memory", Boolean(latestDigest?.stable_facts || latestDigest?.provisional_facts || latestDigest?.stale_but_remembered_facts), {
    hasStableFacts: Boolean(latestDigest?.stable_facts),
    hasProvisionalFacts: Boolean(latestDigest?.provisional_facts),
    hasStaleRememberedFacts: Boolean(latestDigest?.stale_but_remembered_facts),
  }),
  requirement("GPS/location hint is attached", locationHints.some((hint) => /^GPS -?\d+\.\d+, -?\d+\.\d+/i.test(hint)), {
    latestLocationHints: locationHints.slice(-5),
  }),
  requirement("detector is submitting frames", detectorStatuses.some((status) => /Detector tracks: \d+/i.test(status)), {
    latestDetectorStatuses: detectorStatuses.slice(-8),
  }),
  requirement("local ASR engine starts", audioStatuses.some((status) => /Whisper/i.test(status)), {
    latestAudioStatuses: audioStatuses.slice(-8),
  }),
  requirement("speech EVENT memory exists when required", !requireSpeech || (counts.native_speech || 0) > 0, {
    requireSpeech,
    nativeSpeechCount: counts.native_speech || 0,
  }),
  requirement("memory text has no known hygiene issues", Object.keys(issues).length === 0, issues),
  requirement("no raw media files in SOMA storage", rawMediaFiles.length === 0, {
    storageDir,
    totalFiles: files.length,
    rawMediaFiles,
  }),
];

const passed = requirements.every((item) => item.passed);
console.log(
  JSON.stringify(
    {
      passed,
      logFile,
      storageDir,
      sourceCounts: counts,
      requirements,
    },
    null,
    2,
  ),
);

if (!passed) {
  process.exitCode = 1;
}

import { readdir, readFile, stat, writeFile } from "node:fs/promises";
import { join } from "node:path";

const args = process.argv.slice(2);
const getArg = (name, fallback = "") => {
  const index = args.indexOf(name);
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback;
};

const mode = getArg("--mode", "manual");
const logFile =
  getArg("--log") ||
  process.env.TRACE_NATIVE_LOG ||
  `${process.env.HOME}/Library/Application Support/Trace/trace_native_text.ndjson`;
const storageDir =
  getArg("--storage") ||
  process.env.TRACE_NATIVE_STORAGE ||
  `${process.env.HOME}/Library/Application Support/TRACE`;
const outFile =
  getArg("--out") ||
  "/Users/zer00/Documents/VLM/trace-native-fastvlm/TRACE_NATIVE_LIVE_REPORT.md";

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
        return null;
      }
    })
    .filter(Boolean);
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
        files.push({ path: fullPath, size: info?.size ?? 0 });
      }
    }
  }
  await walk(root);
  return files;
}

function countBy(items, keyFn) {
  const counts = {};
  for (const item of items) {
    const key = keyFn(item);
    counts[key] = (counts[key] || 0) + 1;
  }
  return counts;
}

function uniqueRecent(items, limit = 8) {
  return [...new Set(items.filter(Boolean))].slice(-limit);
}

function passFail(passed) {
  return passed ? "PASS" : "FAIL";
}

const text = await readFile(logFile, "utf8").catch(() => "");
const entries = parseEntries(text);
const memoryEntries = entries.filter((entry) => entry.type === "native_inference_result");
const statusEntries = entries.filter((entry) => entry.type === "native_status");
const snapshotEntries = entries.filter((entry) => entry.type === "native_context_snapshot");
const digestEntries = entries.filter((entry) => entry.type === "native_context_digest");
const runtime = statusEntries.findLast?.((entry) => entry.status === "local_runtime_status")
  ?? statusEntries.filter((entry) => entry.status === "local_runtime_status").at(-1);
const latestSnapshot = snapshotEntries.at(-1);
const latestDigest = digestEntries.at(-1);
const sourceCounts = countBy(memoryEntries, (entry) => String(entry.source || "unknown"));

const ocrCandidateStatuses = statusEntries.filter((entry) => entry.status === "native_vision_candidates");
const acceptedOcrSamples = uniqueRecent(ocrCandidateStatuses.flatMap((entry) => entry.accepted_ocr_samples || []));
const rejectedOcrSamples = uniqueRecent(ocrCandidateStatuses.flatMap((entry) => entry.rejected_ocr_samples || []));
const ocrMemory = memoryEntries
  .map((entry) => String(entry.memory_text || ""))
  .filter((memory) => /OBJECT \| visible sign\/board \| OCR text:/i.test(memory));
const speechMemory = memoryEntries
  .map((entry) => String(entry.memory_text || ""))
  .filter((memory) => /^EVENT \| nearby speech \| transcript:/i.test(memory));
const detectorMemory = memoryEntries
  .map((entry) => String(entry.memory_text || ""))
  .filter((memory) => String(memory).includes("| detector stream"));
const detectorStatuses = uniqueRecent(
  statusEntries
    .filter((entry) => entry.status === "detector_status")
    .map((entry) => entry.detector_status),
);
const audioStatuses = uniqueRecent(
  statusEntries
    .filter((entry) => entry.status === "audio_status")
    .map((entry) => entry.audio_status),
);
const locationHints = uniqueRecent(statusEntries.map((entry) => entry.location_hint));
const files = await listFiles(storageDir);
const rawMediaFiles = files.filter((file) => {
  const lower = file.path.toLowerCase();
  return [...rawMediaExtensions].some((extension) => lower.endsWith(extension));
});

const gates = [
  ["Runtime dependencies", Boolean(runtime?.detector_ready_for_start && runtime?.whisper_ready_for_start)],
  ["Visual memory", (sourceCounts.native_vision || 0) > 0],
  ["Detector memory", detectorMemory.length > 0],
  ["OCR sign/board memory", ocrMemory.length > 0],
  ["Speech memory", speechMemory.length > 0],
  ["GPS/location hint", locationHints.some((hint) => /^GPS -?\d+\.\d+, -?\d+\.\d+/i.test(hint || ""))],
  ["Context snapshot", Boolean(latestSnapshot?.fact_count > 0)],
  ["Context digest", Boolean(latestDigest?.active_fact_count > 0)],
  ["No raw media", rawMediaFiles.length === 0],
];

const lines = [];
lines.push("# TRACE Native Live Test Report");
lines.push("");
lines.push(`Mode: ${mode}`);
lines.push(`Generated: ${new Date().toISOString()}`);
lines.push(`Log: ${logFile}`);
lines.push("");
lines.push("## Gate Summary");
lines.push("");
for (const [name, passed] of gates) {
  lines.push(`- ${passFail(passed)}: ${name}`);
}
lines.push("");
lines.push("## Counts");
lines.push("");
lines.push(`- Log entries: ${entries.length}`);
lines.push(`- Memory entries: ${memoryEntries.length}`);
lines.push(`- Context snapshots: ${snapshotEntries.length}`);
lines.push(`- Context digests: ${digestEntries.length}`);
lines.push(`- Source counts: ${JSON.stringify(sourceCounts)}`);
lines.push(`- Raw media files: ${rawMediaFiles.length}`);
lines.push("");
lines.push("## OCR Evidence");
lines.push("");
lines.push(`- OCR memory records: ${ocrMemory.length}`);
lines.push(`- Accepted OCR samples: ${acceptedOcrSamples.length ? acceptedOcrSamples.join("; ") : "none"}`);
lines.push(`- Rejected OCR samples: ${rejectedOcrSamples.length ? rejectedOcrSamples.join("; ") : "none"}`);
lines.push("");
lines.push("## Speech Evidence");
lines.push("");
lines.push(`- Speech memory records: ${speechMemory.length}`);
for (const item of speechMemory.slice(-5)) {
  lines.push(`- ${item}`);
}
if (speechMemory.length === 0) {
  lines.push("- none");
}
lines.push("");
lines.push("## Detector Evidence");
lines.push("");
lines.push(`- Detector memory records: ${detectorMemory.length}`);
lines.push(`- Recent detector statuses: ${detectorStatuses.length ? detectorStatuses.join("; ") : "none"}`);
lines.push("");
lines.push("## Location And Context");
lines.push("");
lines.push(`- Recent location hints: ${locationHints.length ? locationHints.join("; ") : "none"}`);
lines.push(`- Latest context fact count: ${latestSnapshot?.fact_count || 0}`);
lines.push(`- Latest digest active facts: ${latestDigest?.active_fact_count || 0}`);
lines.push(`- Latest digest stable facts: ${latestDigest?.stable_facts?.length || 0}`);
lines.push(`- Latest digest provisional facts: ${latestDigest?.provisional_facts?.length || 0}`);
lines.push(`- Latest digest stale-but-remembered facts: ${latestDigest?.stale_but_remembered_facts?.length || 0}`);
if (latestDigest?.stable_facts?.length) {
  lines.push("- Stable digest examples:");
  for (const fact of latestDigest.stable_facts.slice(0, 5)) {
    lines.push(`  - ${fact.text} (seen ${fact.observations}x, age ${fact.age_seconds}s)`);
  }
}
lines.push("");
lines.push("## Raw Media Audit");
lines.push("");
if (rawMediaFiles.length === 0) {
  lines.push("- PASS: no raw audio/video/image files found in TRACE storage.");
} else {
  for (const file of rawMediaFiles) {
    lines.push(`- FAIL: ${file.path} (${file.size} bytes)`);
  }
}
lines.push("");

const report = `${lines.join("\n")}\n`;
await writeFile(outFile, report);
process.stdout.write(report);

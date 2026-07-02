import { readdir, stat } from "node:fs/promises";
import { join } from "node:path";

const targetDir =
  process.argv[2] || `${process.env.HOME}/Library/Application Support/TRACE`;

const rawMediaExtensions = new Set([
  ".wav",
  ".mp3",
  ".m4a",
  ".aac",
  ".caf",
  ".aiff",
  ".mov",
  ".mp4",
  ".m4v",
  ".avi",
  ".heic",
  ".jpg",
  ".jpeg",
  ".png",
  ".webp",
  ".tiff",
]);

async function walk(dir) {
  const entries = await readdir(dir, { withFileTypes: true }).catch(() => []);
  const files = [];
  for (const entry of entries) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await walk(path)));
    } else {
      const info = await stat(path);
      files.push({ path, bytes: info.size });
    }
  }
  return files;
}

const files = await walk(targetDir);
const rawMediaFiles = files.filter((file) => {
  const lower = file.path.toLowerCase();
  return [...rawMediaExtensions].some((extension) => lower.endsWith(extension));
});

console.log(
  JSON.stringify(
    {
      targetDir,
      totalFiles: files.length,
      rawMediaFiles,
      passed: rawMediaFiles.length === 0,
    },
    null,
    2,
  ),
);

if (rawMediaFiles.length > 0) {
  process.exitCode = 1;
}

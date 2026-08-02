import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { Orchestrator } from "../src/orchestrator";

const runId = process.argv[2];
const manifestPath = process.argv[3];
const force = process.argv.includes("--force");

if (!runId || !manifestPath) {
  throw new Error(
    "usage: run-search-manifest.ts RUN_ID MANIFEST_PATH [--force]",
  );
}

const manifest = JSON.parse(readFileSync(resolve(manifestPath), "utf8")) as {
  question_ids?: unknown;
};
if (
  !Array.isArray(manifest.question_ids) ||
  manifest.question_ids.length === 0
) {
  throw new Error("manifest question_ids must be a non-empty array");
}
if (
  !manifest.question_ids.every((value) => typeof value === "string" && value)
) {
  throw new Error("manifest question_ids must contain only non-empty strings");
}
const questionIds = manifest.question_ids as string[];
if (new Set(questionIds).size !== questionIds.length) {
  throw new Error("manifest question_ids must be unique");
}

await new Orchestrator().run({
  provider: "llm-memory-store",
  benchmark: "longmemeval",
  judgeModel: "gpt-4o",
  answeringModel: "gpt-4o",
  runId,
  questionIds,
  concurrency: { default: 1 },
  force,
  phases: ["ingest", "indexing", "search"],
});

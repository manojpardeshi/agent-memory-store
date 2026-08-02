import { Orchestrator } from "../src/orchestrator";

const runId = process.argv[2];
const perCategory = Number(process.argv[3] || "10");
const force = process.argv.includes("--force");

if (!runId)
  throw new Error(
    "usage: run-search-sample.ts RUN_ID [PER_CATEGORY] [--force]",
  );
if (!Number.isInteger(perCategory) || perCategory < 1) {
  throw new Error("PER_CATEGORY must be a positive integer");
}

await new Orchestrator().run({
  provider: "llm-memory-store",
  benchmark: "longmemeval",
  judgeModel: "gpt-4o",
  answeringModel: "gpt-4o",
  runId,
  sampling: {
    mode: "sample",
    perCategory,
    sampleType: "consecutive",
  },
  concurrency: { default: 1 },
  force,
  phases: ["ingest", "indexing", "search"],
});

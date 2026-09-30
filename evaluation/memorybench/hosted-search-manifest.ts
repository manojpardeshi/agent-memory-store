// Retrieval-only MemoryBench run for a hosted comparator over a frozen question manifest.
//
// Copy to <memorybench>/scripts/ and run with bun. It performs ingest, indexing, and search
// only; answering and judging happen in this repository's kimi runner so every arm shares
// one frozen answer protocol. Provider credentials come from the environment, which the
// launcher populates from the macOS Keychain for this process alone.
//
// usage: bun scripts/hosted-search-manifest.ts PROVIDER RUN_ID MANIFEST_PATH CONCURRENCY [--force]
import { readFileSync } from "node:fs"
import { resolve } from "node:path"

import { Orchestrator } from "../src/orchestrator"

const HOSTED = new Set(["mem0", "supermemory"])
const [provider, runId, manifestPath, concurrencyArg] = process.argv.slice(2)
const force = process.argv.includes("--force")

if (!provider || !HOSTED.has(provider) || !runId || !manifestPath || !concurrencyArg) {
  throw new Error(
    "usage: hosted-search-manifest.ts {mem0|supermemory} RUN_ID MANIFEST_PATH CONCURRENCY [--force]",
  )
}
const concurrency = Number(concurrencyArg)
if (!Number.isInteger(concurrency) || concurrency < 1 || concurrency > 8) {
  // Free tiers rate-limit; the provider's own default of 50 would trip them.
  throw new Error("CONCURRENCY must be an integer from 1 to 8")
}

const manifest = JSON.parse(readFileSync(resolve(manifestPath), "utf8")) as {
  question_ids?: unknown
}
if (!Array.isArray(manifest.question_ids) || manifest.question_ids.length === 0) {
  throw new Error("manifest question_ids must be a non-empty array")
}
if (!manifest.question_ids.every((value) => typeof value === "string" && value)) {
  throw new Error("manifest question_ids must contain only non-empty strings")
}
const questionIds = manifest.question_ids as string[]
if (new Set(questionIds).size !== questionIds.length) {
  throw new Error("manifest question_ids must be unique")
}

try {
  await new Orchestrator().run({
  provider: provider as "mem0" | "supermemory",
  benchmark: "longmemeval",
  judgeModel: "gpt-4o",
  answeringModel: "gpt-4o",
  runId,
  questionIds,
  concurrency: { default: concurrency },
  force,
  phases: ["ingest", "indexing", "search"],
  })
} catch (error) {
  // Bun can exit 0 after an uncaught rejection here; make failure visible to the driver.
  console.error(`hosted run failed: ${error}`)
  process.exit(1)
}

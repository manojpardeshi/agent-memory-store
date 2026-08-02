import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { createHash } from "node:crypto";
import { createInterface } from "node:readline";
import { join, resolve } from "node:path";
import type {
  Provider,
  ProviderConfig,
  IngestOptions,
  IngestResult,
  SearchOptions,
  IndexingProgressCallback,
} from "../../types/provider";
import type { UnifiedSession } from "../../types/unified";
import { logger } from "../../utils/logger";

interface BridgeResponse {
  id: number;
  ok: boolean;
  result?: unknown;
  error?: string;
}

/**
 * Copy this directory to `src/providers/llm-memory-store` in the pinned MemoryBench checkout.
 * The bridge deliberately uses stdio rather than adding a benchmark HTTP service.
 */
export class LLMMemoryStoreProvider implements Provider {
  name = "llm-memory-store";
  concurrency = { default: 1 };

  private child: ChildProcessWithoutNullStreams | null = null;
  private nextId = 1;
  private pending = new Map<
    number,
    { resolve: (value: unknown) => void; reject: (reason: Error) => void }
  >();

  async initialize(_config: ProviderConfig): Promise<void> {
    const repo = process.env.LLM_MEMORY_STORE_REPO;
    if (!repo) {
      throw new Error(
        "LLM_MEMORY_STORE_REPO must point to the agent-memory-store checkout",
      );
    }
    const repository = resolve(repo);
    const dataDir = resolve(
      process.env.LLM_MEMORY_BENCH_DATA_DIR ||
        join(repository, "demo-artifacts", "memorybench", "stores"),
    );
    const args = [
      "run",
      "python",
      join(repository, "scripts", "memorybench_bridge.py"),
      "--data-dir",
      dataDir,
      "--embedder",
      process.env.LLM_MEMORY_BENCH_EMBEDDER || "fastembed",
    ];
    if (process.env.LLM_MEMORY_BENCH_OFFLINE === "1") args.push("--offline");
    if (process.env.LLM_MEMORY_BENCH_MODEL) {
      args.push("--model", process.env.LLM_MEMORY_BENCH_MODEL);
    }
    if (process.env.LLM_MEMORY_BENCH_CACHE_DIR) {
      args.push("--cache-dir", resolve(process.env.LLM_MEMORY_BENCH_CACHE_DIR));
    }
    if (process.env.LLM_MEMORY_BENCH_CONTEXT_POLICY) {
      args.push("--context-policy", process.env.LLM_MEMORY_BENCH_CONTEXT_POLICY);
    }

    this.child = spawn("uv", args, {
      cwd: repository,
      env: process.env,
      stdio: ["pipe", "pipe", "pipe"],
    });
    this.child.stderr.on("data", (chunk) => logger.debug(String(chunk).trim()));
    this.child.on("exit", (code) => {
      const error = new Error(
        `llm-memory-store bridge exited with code ${code}`,
      );
      for (const request of this.pending.values()) request.reject(error);
      this.pending.clear();
      this.child = null;
    });
    const lines = createInterface({ input: this.child.stdout });
    lines.on("line", (line) => {
      let response: BridgeResponse;
      try {
        response = JSON.parse(line) as BridgeResponse;
      } catch {
        const digest = createHash("sha256").update(line).digest("hex");
        logger.warn(
          `Ignored invalid JSON from llm-memory-store bridge: length=${Buffer.byteLength(line)} sha256=${digest} prefix=${JSON.stringify(line.slice(0, 64))}`,
        );
        return;
      }
      const request = this.pending.get(response.id);
      if (!request) return;
      this.pending.delete(response.id);
      if (response.ok) request.resolve(response.result);
      else request.reject(new Error(response.error || "bridge request failed"));
    });
    await this.request("initialize", {});
    logger.info(
      "Initialized llm-memory-store raw deterministic MemoryBench provider",
    );
  }

  private request(
    operation: string,
    value: Record<string, unknown>,
  ): Promise<unknown> {
    if (!this.child)
      throw new Error("llm-memory-store provider is not initialized");
    const id = this.nextId++;
    return new Promise((resolveRequest, rejectRequest) => {
      this.pending.set(id, { resolve: resolveRequest, reject: rejectRequest });
      this.child!.stdin.write(
        JSON.stringify({ id, operation, ...value }) + "\n",
      );
    });
  }

  async ingest(
    sessions: UnifiedSession[],
    options: IngestOptions,
  ): Promise<IngestResult> {
    return (await this.request("ingest", {
      container_tag: options.containerTag,
      sessions,
    })) as IngestResult;
  }

  async awaitIndexing(
    result: IngestResult,
    containerTag: string,
    onProgress?: IndexingProgressCallback,
  ): Promise<void> {
    const progress = (await this.request("await_indexing", {
      container_tag: containerTag,
      document_ids: result.documentIds,
    })) as { completedIds: string[]; failedIds: string[]; total: number };
    onProgress?.(progress);
  }

  async search(query: string, options: SearchOptions): Promise<unknown[]> {
    return (await this.request("search", {
      container_tag: options.containerTag,
      limit: options.limit || 10,
      query,
    })) as unknown[];
  }

  async clear(containerTag: string): Promise<void> {
    await this.request("clear", { container_tag: containerTag });
  }

  async close(): Promise<void> {
    const child = this.child;
    if (!child) return;
    child.stdin.end();
    if (child.exitCode === null) {
      await new Promise<void>((resolveClose) => {
        child.once("exit", () => resolveClose());
      });
    }
    this.child = null;
  }
}

export default LLMMemoryStoreProvider;

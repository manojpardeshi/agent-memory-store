# LLM Memory Store

A personal, local-first memory store for LLM applications and agents. The MVP runs as a Python library, CLI, or MCP server over stdio and keeps its data in one SQLite database.

## MVP Capabilities

- Durable raw turns and typed facts, preferences, summaries, and events.
- Local embeddings with exact semantic retrieval plus recency ranking.
- Private-by-default agent scopes and explicitly selected shared pools.
- Versioned corrections with provenance.
- Review-first local extraction and summarization proposals with explicit, idempotent acceptance.
- Previewable, verified hard deletion of a lineage and its derived descendants.
- Previewable, verified physical cleanup of safely purgeable expired memories.
- JSON export and consistent SQLite backup/restore.
- No HTTP listener, cloud service, authentication server, or always-on daemon.

## Installation

Requires Python 3.11 or newer:

```bash
python -m pip install llm-memory-store
```

This installs the `llm-memory` CLI and the `llm-memory-mcp` stdio server. The default FastEmbed
model downloads on first use and then runs locally.

## Development Setup

```bash
uv sync --dev
uv run pytest
```

The default local model is `BAAI/bge-small-en-v1.5`. FastEmbed downloads the model on first use; after that, commit and recall run locally. The store records a behavioral fingerprint and refuses to mix incompatible vector spaces. Tests use a deterministic offline embedder and never download model weights.

## Quick Start

```bash
llm-memory init --db ~/.llm-memory/memory.sqlite3

llm-memory remember-turn \
  --db ~/.llm-memory/memory.sqlite3 \
  --subject me --environment personal --agent codex \
  --role user --content "I prefer local-first tools."

llm-memory recall \
  --db ~/.llm-memory/memory.sqlite3 \
  --subject me --environment personal --agent codex \
  --query "What kind of tools do I prefer?"
```

Run the stdio MCP server with:

```bash
LLM_MEMORY_DB=~/.llm-memory/memory.sqlite3 llm-memory-mcp
```

MCP writes protocol messages to stdout; application diagnostics must go to stderr and never include full memory bodies by default.

Export always requires an explicit exact scope, subject, or whole-store selector. MCP export and backup first return a non-writing preview and require `confirm=true` to create an artifact. Backup and export refuse to overwrite existing files unless explicitly requested. Restore requires `--yes` and only writes to a new database path; it never overwrites a possibly live store.

## Retrieval Quality Gate

The evaluation and maintainer workflows below require a source checkout because their datasets and
supporting evidence are deliberately excluded from the installed package.

After the FastEmbed model has been downloaded once, run the versioned evaluation entirely from local files:

```bash
uv run llm-memory evaluate-retrieval \
  --dataset evaluation/retrieval_v1.json \
  --offline \
  --report demo-artifacts/retrieval-quality.json
```

The command exits nonzero when any written threshold fails. For a certified embedding identity it evaluates the identity-scoped product default; add `--no-relevance-filter` to measure the legacy unfiltered top-K behavior. The first real v1 unfiltered baseline retrieved 49/50 expected memories with zero scope violations, but failed the normative irrelevant-memory control: 12/50 designated distractors appeared in the top five versus a maximum of 5/50.

The relative semantic-gap filter is now the default for the exact FastEmbed identities certified by the frozen matrix: `BAAI/bge-small-en-v1.5` and `sentence-transformers/all-MiniLM-L6-v2` under the recorded runtime and behavioral fingerprints. It keeps results whose semantic score is within 0.20 of the top result and may return zero through the requested limit:

```python
results = store.recall("What editor do I prefer?", private_scope)

# Explicitly restore the legacy always-fill top-K behavior.
unfiltered = store.recall("What editor do I prefer?", private_scope, relevance_filter=None)
```

```bash
uv run llm-memory recall \
  --db ~/.llm-memory/memory.sqlite3 \
  --subject me --environment personal --agent codex \
  --query "What editor do I prefer?" \
  --no-relevance-filter
```

MCP callers use `relevance_filter: "default"`, `"off"`, or an explicit override such as `"relative:0.10"`. CLI/MCP bundles expose the effective filter and policy. Unknown or changed embedding identities remain unfiltered until re-certified.

Python uses the typed API rather than MCP strings: omit the argument or pass `"default"` for the identity-scoped policy, pass a `RelevanceFilter` override, or pass `None` to disable. `store.default_relevance_filter` and `store.status()` expose whether the current identity matched a certification.

The frozen two-corpus/two-model matrix reduced designated distractor leakage from 24%/18.3%/40%/16.7% unfiltered to 6%/10%/6%/5% with no Recall@5 or MRR change and zero scope violations. This closes the retrieval-default product gate only for those exact identities; it is not a general statistical claim. See `docs/architecture/benchmarks/2026-07-19-retrieval-quality-v2.md`.

## Hybrid Recall (Opt-In)

Vector recall finds memories by meaning. Hybrid recall also matches exact words, which helps when a
query repeats a name, code, or number that appears in the memory:

```python
results = store.recall("What is the Quarryhill tournament schedule?", private_scope, retrieval="hybrid")
```

```bash
uv run llm-memory recall --db ~/.llm-memory/memory.sqlite3 \
  --subject me --environment personal --agent codex \
  --query "Quarryhill tournament" --retrieval hybrid
```

MCP callers pass `retrieval: "hybrid"`. Hybrid results also carry a `fusion_score`, and results are
ordered by it.

Vector stays the default because hybrid has a measured trade-off. On held-out LongMemEval-S
questions it put every answer-bearing message in the top ten for 91 of 117 questions versus 80 for
vector. On the independently written `retrieval_v3` suite, however, it lowered MRR on questions that
share no words with their answer from 0.80 to 0.53. Use it when queries quote the memory; keep the
default for paraphrased questions.

Hybrid recall uses an FTS5 keyword index that 0.2 creates automatically (built once when an older
store is first opened writable). The index needs SQLite 3.44 or newer for its secure-delete mode,
which makes `forget` physically remove a memory's words; on older SQLite, hybrid recall is
unavailable and vector recall works as before. See
`docs/architecture/benchmarks/2026-10-02-hybrid-recall-product.md`.

## Looking Up Memories by Metadata

Applications that attach their own identifiers can fetch matching memories directly, for example
every stored message from one conversation:

```python
messages = store.find_by_metadata(private_scope, {"conversation_id": "c-42"})
```

Matching happens inside SQLite within one exact scope, so it stays fast as the store grows and never
crosses scopes. Superseded and expired memories are excluded by default, matching `recall`; pass
`include_superseded=True` or `include_expired=True` for audit views. Filters combine with AND, keys
must be plain identifiers, and values must be strings, numbers, or booleans.

## Expiry Cleanup

Expired memories are excluded from recall immediately, but physical cleanup is deliberately on demand. Preview the exact cutoff and candidate set first:

```bash
uv run llm-memory purge-expired \
  --db ~/.llm-memory/memory.sqlite3
```

Reuse the returned `cutoff` and `digest` when confirming:

```bash
uv run llm-memory purge-expired \
  --db ~/.llm-memory/memory.sqlite3 \
  --as-of "RETURNED_CUTOFF" \
  --expected-digest "RETURNED_DIGEST" \
  --yes
```

Routine expiry cleanup never cascades into an unexpired derived memory. An expired source still needed by a durable summary is reported as blocked and retained. Safely removable rows, vectors, and provenance edges are deleted atomically and verified. CLI/MCP confirmation requires the preview digest unless the caller deliberately selects `--force-current` or `force_current=true`; the Python domain API remains directly callable. MCP exposes the flow as `memory_purge_expired`; no background scheduler is installed.

## Embedding Migration

Embedding spaces are never rewritten in place. Preview a migration into a new database with both source and target model identities plus the synthetic quality corpus:

```bash
uv run llm-memory migrate-embeddings \
  --source ~/.llm-memory/memory.sqlite3 \
  --destination ~/.llm-memory/memory-bge-upgrade.sqlite3 \
  --source-model BAAI/bge-small-en-v1.5 \
  --target-model TARGET_FASTEMBED_MODEL \
  --quality-dataset evaluation/retrieval_v1.json \
  --report migration-report.json \
  --offline
```

Confirm by repeating the command with the returned preview digest and `--yes`. The migration snapshots the source, preserves public IDs, corrections, operation IDs, scopes, and provenance, rebuilds every active vector, and publishes only after logical, SQLite, vector, fingerprint, and retrieval-regression checks pass. The destination must not exist and concurrent creation cannot be overwritten. The source remains the immediate rollback path.

The quality report keeps structural success, source-to-target regression, and the absolute product gate separate. A regression blocks publication unless `--accept-quality-regression` is paired with `--quality-regression-reason`. That override is recorded. Migration is intentionally Python/CLI-only; MCP execution is deferred because arbitrary paths and long model loads do not belong in an agent-triggered tool yet.

## JSON Portability

JSON exports now use format v2, preserving operation IDs and SHA-256 content hashes while keeping vectors out of the interchange file. Import validates the complete document and creates a new compatible store:

```bash
uv run llm-memory import-json \
  --source memory-export.json \
  --destination ~/.llm-memory/imported.sqlite3 \
  --report import-report.json \
  --offline
```

Repeat with the preview digest and `--yes` to execute. Import supports v1 files, explicitly reports backfilled hashes and unavailable v1 operation IDs, regenerates active vectors, and atomically publishes only after integrity verification. Existing destinations are never overwritten.

Partial exports declare references to sources outside the selected scope without including their content. Such imports reject by default because the database cannot preserve a dangling provenance edge. `--allow-missing-sources` is an explicit loss-acceptance option; every dropped reference is retained in the import receipt. JSON import is Python/CLI-only and never merges into a live store.

## Review-First Extraction

Extraction never writes memory directly. Give it exact source memory IDs and an exact target scope; it creates a new owner-only JSON proposal artifact for review:

```bash
uv run llm-memory propose-extraction \
  --db ~/.llm-memory/memory.sqlite3 \
  --subject me --environment personal --owner my-app \
  --source SOURCE_MEMORY_ID \
  --output memory-proposals.json \
  --extractor ollama --ollama-model llama3.1:8b \
  --ollama-revision MODEL_CONTENT_DIGEST

uv run llm-memory review-proposals \
  --db ~/.llm-memory/memory.sqlite3 \
  --proposal-file memory-proposals.json \
  --output memory-proposal-review.json
```

Review output is store-aware and read-only. It reports source freshness, accepted replays, replayed
results that were later superseded or expired, planted operation-ID collisions, exact duplicates,
and identical-content/different-kind collisions in the exact target scope. Proposal and source text
is hidden by default; add `--show-proposal-content` and, separately, `--show-source-content` only for
a local interactive review. The owner-only output report can be loaded into the dashboard without
giving the browser a database handle.

After reviewing the exact proposal content and indicators, explicitly select what becomes durable memory:

```bash
uv run llm-memory accept-proposals \
  --db ~/.llm-memory/memory.sqlite3 \
  --proposal-file memory-proposals.json \
  --proposal-id SELECTED_PROPOSAL_ID \
  --expected-digest REVIEWED_BUNDLE_DIGEST \
  --yes
```

Acceptance revalidates the artifact, deterministic review safety, and every selected source, preserves exact provenance, and uses the proposal identity as an idempotency key. Repeating the same active acceptance returns the same memory rather than creating a duplicate. Deleted, expired, superseded, or changed sources and invalid replay state fail closed. The built-in `DeterministicRuleExtractor` supports network-free tests and recognizes explicit `Fact:`, `Preference:`, `Summary:`, `Event:`, `Remember that ...`, and `I prefer ...` forms.

Python applications can call `create_proposal_bundle`, `write_proposal_bundle`, `load_proposal_bundle`, `review_proposals`, and `accept_proposals` directly. The host must provide its own human-review UI before calling acceptance. MCP exposure is intentionally deferred because an agent echoing a digest is integrity checking, not proof of human consent.

The labelled local `llama3.1:8b` evidence created one valid proposal from three synthetic durable statements (33.3% observed coverage), wrote nothing before approval, accepted one provenance-linked preference, and created no duplicate on replay. This validates the safety workflow, not extraction completeness. See `docs/demo/results/2026-07-19-extraction-proposals-llama3-1-8b.json` and `docs/architecture/extraction-proposal-contract.md`.

Evaluate extraction separately from acceptance with the frozen, synthetic two-track corpus:

```bash
uv run llm-memory evaluate-extraction \
  --dataset evaluation/extraction_v1.json \
  --track offline --extractor deterministic \
  --report demo-artifacts/extraction-offline.json

uv run llm-memory evaluate-extraction \
  --dataset evaluation/extraction_v1.json \
  --track live --extractor ollama \
  --ollama-model llama3.1:8b --ollama-revision MODEL_CONTENT_DIGEST \
  --report demo-artifacts/extraction-live.json
```

The command runs each case in an isolated temporary store, maps model provenance back to stable
fixture IDs, and exits nonzero when a threshold fails. It never writes a proposal artifact or
accepts memory. The 12-case deterministic track passes. On the unchanged 50-case live track, the
selected conservative extraction-v2 prompt eliminated forbidden and invalid outputs but failed the
quality target at 0.50 precision, 0.25 recall, and 0.30 summary fact-unit coverage. This preserves
the review-first boundary and explicitly rules out automatic acceptance. See
`docs/architecture/benchmarks/2026-07-20-extraction-quality-v1.md`.

A second independently seeded 50-case corpus compared the preserved prompt across Llama 3.1 8B,
Qwen 2.5 7B, Qwen3 4B, and an experimental Llama two-pass design. Every candidate failed. Llama
single-pass was least-bad at 0.765 precision and 0.325 recall with zero forbidden/invalid output;
the two-pass design introduced both, so its code was removed. Qwen3 also exposed Ollama's documented
thinking response field: the adapter now requests `think: false`, accepts an optional bounded string,
and ignores it rather than persisting reasoning. See
`docs/architecture/benchmarks/2026-07-20-extraction-quality-v2.md`.

## Real-Application Starter

Run the full application-owned lifecycle offline through direct Python memory:

```bash
uv run python -m examples.memory_chat \
  --db demo-artifacts/starter-python.sqlite3 \
  --transport python --embedder deterministic --model offline --demo
```

Switch only the memory transport to exercise an actual MCP stdio subprocess:

```bash
uv run python -m examples.memory_chat \
  --db demo-artifacts/starter-mcp.sqlite3 \
  --transport mcp --embedder deterministic --model offline --demo
```

Use the same application with local Llama and production FastEmbed memory after the embedding model is cached:

```bash
uv run python -m examples.memory_chat \
  --db ~/.llm-memory/chat.sqlite3 \
  --transport python --embedder fastembed --offline-embeddings \
  --model ollama --ollama-model llama3.1:8b
```

The interactive commands are `/remember KIND TEXT`, `/correct ID TEXT`, `/forget ID`, `/status`, and `/quit`; ordinary text performs recall → bounded untrusted context injection → model call → post-success raw-turn capture. `--once` makes one non-interactive call and `--demo --report PATH` writes measurable lifecycle evidence. See `docs/demo/real-application-starter.md` for the deterministic gate and the labelled single-run Llama result.

## Model-Switching Demo

Run the provider-neutral offline gate. It exercises the Claude, GPT/Codex, and local/Ollama adapter roles without hosted calls:

```bash
uv run python -m demo.provider_matrix --mode offline
```

Run the live Claude Haiku → Claude Sonnet → GPT through Codex CLI → Claude Haiku matrix:

```bash
uv run python -m demo.provider_matrix --mode live
```

The verified single-run report at `docs/demo/results/2026-07-19-live-provider-matrix-llama3-1-8b.json` shows Sonnet, GPT, and local `llama3.1:8b` each recalled 0/3 synthetic slots without memory and 3/3 with the same 486-byte shared bundle. Codex reported 13,007 baseline input tokens and 13,208 with memory (+201). Ollama reported 80 direct-prompt tokens for Llama baseline and 281 with memory (+201). Each delta is assisted minus baseline for the whole prompt, not the memory-only cost. The separate ~122 value is a heuristic cross-provider approximation (characters ÷ 4), not tokenizer output. Codex and Ollama totals are transport-specific and must not be compared as provider benchmarks.

Live evidence is informational; the offline provider matrix is the release gate. The harness injected an identical memory bundle into each fresh consumer—it did not test models autonomously discovering or negotiating shared memory.

Test additional hosted GPT models by repeating `--gpt-model MODEL`. After a local runtime is installed, add it without changing the scenario:

```bash
uv run python -m demo.provider_matrix --mode live \
  --include-local --local-provider ollama --local-model llama3.1:8b
```

The measured Ollama endpoint is loopback-only and the local model is never silently substituted: requesting an unavailable endpoint or model fails explicitly. See `docs/demo/provider-matrix-demo-contract.md` for requirements, security boundaries, and trade-offs.

### Legacy two-model scenario

Run the deterministic, offline demonstration:

```bash
uv run python -m demo.model_switching --mode offline
```

Run a live Haiku → Sonnet → Haiku switch using isolated Claude CLI sessions:

```bash
uv run python -m demo.model_switching --mode live-claude
```

Each run generates random synthetic facts, measures the no-memory baseline versus memory-assisted accuracy, corrects a memory before switching back, checks private-scope isolation, and writes a JSON report plus SQLite database under the ignored `demo-artifacts/` directory. Live model latency is recorded as informational telemetry and is not a release gate. See `docs/demo/model-switching-demo-contract.md` for the exact claim and thresholds.

The preserved live Haiku → Sonnet → Haiku evidence report is at `docs/demo/results/2026-07-15-live-claude.json`: baseline accuracy `0%`, memory-assisted accuracy `100%`, memory lift `+100` percentage points, correction accuracy `100%`, and zero stale-value or private-scope leaks. The first handoff re-supplied 3 memory items (486 exact UTF-8 bytes, approximately 122 tokens) to Sonnet; the return handoff supplied 5 items (812 exact bytes, approximately 203 tokens) to Haiku.

Run the visual evidence dashboard:

```bash
cd demo/dashboard
npm install
npm run dev
```

Choose **Replay measured run** to animate the provider matrix, or **Load report** to inspect a schema-v2 or schema-v3 handoff report locally. The proposal-review section starts with a clearly synthetic example; choose **Load review report** to inspect and locally select from a CLI-generated schema-v1 review report. The dashboard never opens SQLite or accepts a memory. Imported files stay in browser memory and are not uploaded. See `docs/demo/model-switching-ui-contract.md` for the measurement definitions and UI trade-offs.

## Security Boundary

The MVP trusts the local OS account. The database directory is created with mode `0700`; databases, backups, and JSON exports are created with mode `0600` from the outset. Full-disk encryption such as FileVault is recommended. Verified deletion means absence from the active database after transactional cascade and verification; it does not erase prior backups, filesystem snapshots, synced copies, or SSD remanence.

See `docs/security/threat-model.md` for the complete trust boundaries and `SECURITY.md` for private-first vulnerability reporting.

## License

Licensed under the Apache License 2.0. See `LICENSE`. Contributions are accepted under the same terms as described in `CONTRIBUTING.md`.

## Project Status

The canonical public source repository is `https://codeberg.org/manojpardeshi/agent-memory-store`. Version 0.2.0 is available from PyPI and as a verified Codeberg release; see `CHANGELOG.md` for changes since 0.1.0. The repository was seeded from a reviewed clean tree with a Codeberg noreply identity; the private development history remains unpublished because its Git metadata contains a personal email address. The reproducible release gate and credential-minimizing publication sequence are documented in `docs/release/publishing.md`.

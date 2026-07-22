# Provider-Matrix Memory Demo Contract

Date: 2026-07-19
Status: accepted for implementation

## Users and outcome

The user is the project owner or an evaluator. The demo must show that one shared, local memory pool can re-supply the same synthetic facts to fresh sessions from different model providers. The live matrix is Claude Haiku → Claude Sonnet → GPT through Codex CLI → local Llama through Ollama → Claude Haiku.

This is a provider interoperability test of the memory layer. It is not a claim that model weights, hidden state, or provider-side conversation history are transferred.

## Requirements

1. Generate unpredictable synthetic values for every run.
2. Capture once with a producer model, then create typed memories in one explicit shared pool.
3. Give every consumer a new process, empty working directory, and distinct private scope.
4. Measure a no-memory baseline and a memory-assisted answer independently for every consumer.
5. Record exact transferred memory items, Unicode characters, UTF-8 bytes, prompt-character share, and bundle-budget use for every assisted prompt.
6. Label characters/4 token counts as estimates. Record provider-reported total token usage when a CLI exposes it, but never mislabel total prompt usage as memory-only token usage.
7. Verify private-scope isolation for every consumer.
8. Correct a shared preference after the consumer matrix and verify the producer receives the active correction without the stale value.
9. Permit multiple hosted GPT model slugs through repeatable CLI configuration, while keeping one verified default for the normal demo.
10. Implement local Ollama as the identical consumer interface over a loopback-only JSON API using stateless calls and `format=json`. A local run must fail explicitly when the endpoint/model is unavailable; it must never silently substitute a hosted model.
11. Produce a schema-v3 JSON report that the dashboard can replay and import locally.

## Constraints and scale

- Personal, local-first scale: one operator, one SQLite database per run, three canonical facts, one private canary, and normally two to five consumers.
- Cap a run at eight consumers to limit hosted cost, latency, and accidental fan-out.
- Hosted-model and local-model availability are external. Only the deterministic offline matrix is a release gate.
- The selected measured local target is `llama3.1:8b` (8.0B, Q4_K_M, 131,072-token context reported by Ollama). Other installed tags are outside this run; comparative local-model quality and latency thresholds remain open.

## Security boundary

- Claude runs with tools disabled, no session persistence, no browser, safe mode, and a minimal inherited environment.
- Codex runs ephemerally with user configuration and repository rules ignored, a read-only sandbox, an empty temporary working directory, and no repository access. Saved Codex authentication remains available through the user's home directory.
- Ollama calls use `http://127.0.0.1:11434` by default, require a loopback hostname or IP, send no tools or conversation history, request non-streamed JSON, and record model metadata plus Ollama's prompt/output token counts.
- Model subprocesses receive only a small allowlist of environment variables. API keys and unrelated environment secrets are not forwarded.
- Reports contain synthetic values only. Imported reports remain inside browser memory.
- Codex is an agent runtime and cannot be claimed to have “no tools.” The prompt instructs it not to use tools, while the harness constrains incidental use with an empty read-only workspace; tool non-use is not independently verified.

## Success criteria

For every available consumer in the scenario:

- baseline exact-slot result is `0/3` (stored as normalized accuracy `0.0` for machine checks);
- memory-assisted exact-slot result is `3/3` (stored as normalized accuracy `1.0` for machine checks);
- memory lift is at least `2/3`;
- shared recall hit rate is `1.0`;
- private-scope isolation violations are `0`;
- the model invocation exits successfully.

The final return-to-producer correction must return the one corrected value (`1/1`) with zero stale-value leaks. The live report is informational; the offline matrix is gating.

## Major trade-offs and assumptions

- A consumer matrix is more extensible and comparable than a long conversational chain, but it tests independent fresh sessions rather than organic multi-agent conversation.
- Codex CLI adds agent/system context. Its provider-reported total input tokens measure the complete Codex turn, while Ollama prompt-token counts measure its complete direct prompt. These transport-specific totals are not comparable provider benchmarks. Each reported delta is assisted minus baseline for that transport's whole prompt, not memory-only cost. Exact memory bytes remain the cross-provider comparison; characters ÷ 4 is only a heuristic approximation.
- The installed Codex CLI currently succeeds with its ChatGPT-account default, observed as `gpt-5.6-sol`; the public manual's `gpt-5.6` example was rejected for this account. The test pins the verified slug, records the Codex CLI version, exposes a configurable override, and fails without fallback if the selected slug becomes unavailable.
- Codex OSS was previously evaluated with `qwen2.5:7b` but returned tool-call wrapper syntax rather than the requested JSON. The selected `llama3.1:8b` is measured through the same direct Ollama structured-output adapter for a stable, agent-free local transport. This is a transport decision, not a comparison of Qwen and Llama quality.
- Local inference avoids hosted data transfer and recurring API cost, but latency and model quality depend heavily on Mac memory, quantization, runtime, and chosen model. Thresholds will be set only after measurement.
- Live outcomes are single-run, harness-injected observations rather than provider benchmarks or proof of autonomous retrieval. The report pins the Ollama model content digest so later runs can identify model-build drift.
- A future comparative benchmark should add an irrelevant-memory negative control to distinguish useful recall from indiscriminate prompt copying; it is not required for this interoperability MVP.

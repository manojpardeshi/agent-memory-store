# Model-Switching Demo Contract

Date: 2026-07-15
Status: approved for demo implementation; not a generalized product-quality benchmark

## Goal and User

The operator is the project owner or evaluator. The demo must make one narrow claim visible and reproducible: a fresh Model B session can use synthetic memories created while Model A was active, and Model A can later observe a correction created during Model B's turn.

The live preset switches Claude Haiku → Claude Sonnet → Claude Haiku. This proves cross-model continuity within one provider. It does not yet prove cross-vendor continuity.

## Requirements

1. Generate random, synthetic canonical values on every run so neither model can know them from training data or prior sessions.
2. Give Model A and Model B distinct exact private scopes.
3. Share only through one explicitly named shared pool.
4. Run a no-memory baseline before the memory-assisted Model B query.
5. Separate store retrieval success from model answer success.
6. Correct one shared memory through versioned supersession, switch back to Model A, and verify the corrected value appears while the stale value does not.
7. Put a separate secret in Model A's private scope and prove Model B cannot retrieve it without sharing.
8. Write a machine-readable JSON report and a concise terminal transcript.
9. Measure the exact memory payload copied into each receiving model prompt: item count, characters, UTF-8 bytes, prompt share, and character-budget utilization.

## Execution Tracks

- `offline`: deterministic embedding and deterministic model adapters. This track runs in automated tests and validates orchestration, scope behavior, correction, scoring, and report shape without network access.
- `live-claude`: deterministic embedding plus isolated Claude CLI calls using Haiku and Sonnet. The harness performs explicit store operations and supplies the recall bundle to the model. This measures memory consumption, not autonomous MCP tool selection.

Agent-initiated tool selection is a different evaluation and is intentionally excluded from this demo.

## Controls and Security

- Each live invocation uses a new empty temporary working directory, safe mode, no session persistence, no browser integration, no tools, and a minimal system prompt.
- Prompts and reports contain synthetic values only.
- Model subprocesses use argument arrays, never a shell.
- No database, report, or model cache is committed accidentally; generated artifacts live under ignored `demo-artifacts/` unless a sanitized evidence report is deliberately copied into documentation.
- The demo does not modify store schema, recall ranking, MCP behavior, or security boundaries.

## Scenario Metrics

Correctness metrics are deterministic exact normalized-string checks:

- `capture_accuracy`: Model A restates all synthetic onboarding values.
- `baseline_accuracy`: Model B guesses values without memory; expected to be zero because values are random.
- `memory_accuracy`: Model B answers using the explicit shared-pool recall bundle.
- `memory_lift`: `memory_accuracy - baseline_accuracy`.
- `correction_accuracy`: Model A reports the corrected value after switching back.
- `stale_value_leaks`: count of stale corrected values in the final answer or active recall.
- `private_isolation_violations`: count of Model A private values returned through Model B's private scope plus the explicitly allowed shared pool.
- `private_control_hit_rate`: positive control proving the same private value exists and is retrievable from Model A's exact private scope.
- `shared_recall_hit_rate`: expected shared values present in store recall.

Recall and model-call latencies are recorded as non-gating telemetry.

### Context transfer measurements

For every switch, `context_transfers` records the source and destination model, memory IDs, exact item/character/UTF-8 byte counts, total prompt characters, memory share of the prompt, and context-bundle budget utilization. `estimated_memory_tokens` is `ceil(memory characters / 4)`. It is clearly labeled as a tokenizer-independent estimate and must not be presented as an exact provider token count.

## Demo Acceptance Thresholds

These thresholds validate only this synthetic scenario. They do not close the open product-wide retrieval-quality threshold.

- `capture_accuracy == 1.0`
- `memory_accuracy == 1.0`
- `memory_lift >= 2/3`
- `correction_accuracy == 1.0`
- `shared_recall_hit_rate == 1.0`
- `stale_value_leaks == 0`
- `private_isolation_violations == 0`
- `private_control_hit_rate == 1.0`

The offline track is gating. The live track reports the same acceptance result for demonstration clarity but remains manual, informational, and non-gating because hosted-model cost, availability, and latency are external variables.

## Known Trade-offs

- Scripted memory operations isolate the memory layer from model tool-selection behavior, but do not demonstrate an autonomous agent deciding to remember.
- Two Anthropic models are available now; the adapter boundary should permit a later Ollama or other command-based model without changing the scenario.
- Exact slot scoring is less semantically flexible than an LLM judge, but it is reproducible, cheap, and resistant to evaluator drift.

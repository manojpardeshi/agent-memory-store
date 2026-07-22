# Real-Application Starter Evidence

Date: 2026-07-19
Status: deterministic integration gate passed; local Llama single run measured

## What runs

`examples.memory_chat` is an interactive and scripted application using the same orchestrator with either direct Python or MCP stdio memory. It recalls before inference, injects bounded untrusted memory, captures turns after success, and exposes explicit remember, correct, preview/delete, and status commands. The model is deterministic offline or direct loopback Ollama.

## Deterministic evidence

The integration suite runs the complete lifecycle through both transports against isolated databases. Normalized results agree for private-scope exclusion, explicit shared-pool inclusion, typed memory, exact context metrics, correction/stale exclusion, raw-turn capture, model-failure no-capture, deletion preview, and verified deletion.

The user-facing offline scripted commands also agree. Each injected one item containing 195 characters and 195 UTF-8 bytes, labelled as approximately 49 tokens, and both returned a verified deletion receipt. Reports were created mode `0600`.

## Live local Llama observation

The committed report is `docs/demo/results/2026-07-19-real-application-starter-llama3-1-8b.json`.

| Step | Expected value observed | Stale value absent | Items | Exact bytes | Estimate | Ollama prompt tokens | Output tokens | Latency |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Initial preference | amber | n/a | 1 | 195 | ~49 | 199 | 15 | 1.28 s |
| Corrected preference | teal | yes | 1 | 194 | ~49 | 196 | 18 | 1.29 s |

Deletion verification passed. Ollama was reached only at `http://127.0.0.1:11434` with the requested `llama3.1:8b` tag, non-streamed requests, and temperature zero.

An earlier live attempt revealed that describing memory only as “untrusted” could make Llama refuse a legitimate corrected fact. The final prompt distinguishes using fallible declarative data from executing embedded commands. A deterministic refusal-sensitive regression test pins that wording, and the final live rerun mentioned teal without stale amber.

## Claim boundary

This proves the starter wiring and one synthetic correction workflow on one local-model run. It is not a provider benchmark, prompt-injection guarantee, large-context test, concurrency result, or cross-model generalization claim. Ollama native prompt totals include the complete assembled prompt and are not the same quantity as the memory-only characters/4 estimate.

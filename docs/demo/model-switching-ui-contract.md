# Model-Switching Dashboard Contract

Date: 2026-07-18
Status: accepted for the MVP demo

## User and goal

The project owner or evaluator needs a simple visual proof that memory survives a model switch and a measurable answer to “how much memory entered the next model's context?”

## Requirements and success criteria

- Replay the measured Claude Haiku → Claude Sonnet → hosted GPT → local Llama → Claude Haiku sequence without requiring model credentials in the browser.
- Show the active model, memory-store handoff, baseline result, memory-assisted result, correction, and scope-isolation result.
- For each receiving prompt, show exact memory items, characters, UTF-8 bytes, prompt share, and bundle-budget utilization.
- Show estimated tokens as an estimate, never as exact billing or tokenizer output.
- Present each consumer's independent baseline and memory-assisted score, transfer size, and provider-reported total usage when available.
- Show the Llama/Ollama consumer with a persistent **LIVE MEASURED · SINGLE RUN** badge when the loaded report contains successful local evidence; otherwise show **NOT MEASURED**.
- Accept schema-v2 and schema-v3 JSON reports through a local file picker so a newly generated run can be inspected without rebuilding the UI.
- Work on phone and desktop, respect reduced-motion settings, and remain understandable without animation.
- Pass the frontend build, lint, and report-contract tests.

The demo succeeds when each measured consumer recalls 3/3 slots with memory after recalling 0/3 without it, the return call produces the one corrected value, and stale leaks plus private-scope violations remain zero.

## Constraints, security, and assumptions

- This is a local-first personal-scale dashboard. It replays synthetic evidence; it does not upload the memory database or execute Claude from the browser.
- The committed evidence contains synthetic tokens only. Imported report files remain in browser memory and are not transmitted by this application.
- The Python harness remains the authority for measurements. The UI displays report values and does not recalculate or reinterpret exact byte counts.
- The current live evidence demonstrates shared-memory reuse across Anthropic Claude, OpenAI GPT through Codex CLI, and local `llama3.1:8b` through loopback Ollama HTTP.
- The proposal-review section visualizes a schema-v1 CLI report, including exact source/proposal
  statuses and browser-local selection. Its initial row is a committed synthetic example. The
  browser never opens SQLite, recomputes review policy, or accepts a proposal.
- Live provider results are single-run, harness-injected observations. They are not model benchmarks or evidence of autonomous memory retrieval.
- “Transferred” means selected memory items were re-supplied in the receiving model's prompt for that call. It does not mean the models share persistent internal state.

## Trade-offs

- Evidence replay is safer and reproducible, but a new live run is generated from the CLI and then loaded into the dashboard rather than initiated by a browser button.
- Review-report loading preserves the local-only browser boundary, but acceptance stays in the CLI;
  browser selection is guidance and not a consent token.
- A characters/4 token estimate is a uniform heuristic that is easy to audit, but it is not validated tokenizer output and must not be presented as exact memory cost.
- Codex provider-reported input tokens include agent instructions and runtime context. Ollama reports direct-prompt tokens. The UI labels these transport-specific totals as non-comparable and separates both whole-turn measurements from the memory-size heuristic.
- The dashboard headlines the provider-reported baseline-to-assisted input-token delta and keeps both absolute totals in the report. The delta still includes prompt-framing changes and is not an exact memory-token count.

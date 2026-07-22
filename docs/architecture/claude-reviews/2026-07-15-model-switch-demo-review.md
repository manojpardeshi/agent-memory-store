# Claude Review: Cross-Model Memory-Continuity Demo

Date: 2026-07-15

> Verbatim Claude Sonnet review. This review was produced before implementation and is reconciled in the demo contract and architecture decision log.

## Requirements / Assumptions

- This is a demo/eval harness, not a store feature. `store.py`, `mcp_server.py`, and `cli.py` already provide everything the harness needs (`memory_remember`, `memory_recall`, `memory_correct`, exact-match scopes). Nothing here should touch the store's schema or contract.
- "Deterministic offline" already exists at one layer: `cli.py` has `--embedder {fastembed,deterministic}`. That solves embedding determinism for CI. It does **not** solve chat-model determinism — Haiku/Sonnet via the `claude` CLI are non-deterministic, rate-limited, and cost money. Treat these as two unrelated adapters, not one continuum.
- Per `mvp-contract.md`'s Known Deferrals: *"Numeric retrieval-quality release threshold and representative personal evaluation set"* is explicitly deferred, not yet an accepted decision. Item (6) of the proposal (pass/fail thresholds in a ship report) contradicts that deferral unless it's formally promoted first.
- Assumption to make explicit and challenge: two Anthropic models (Haiku, Sonnet) demonstrate *cross-model* continuity, not *cross-vendor* continuity (AD-002/AD-006 target model-agnosticism generally). Label the demo accordingly — don't let it imply more than it shows.

## Release-Blocking Flaws

1. **Undefined actor for memory writes/reads.** The proposal never states whether the MCP tool calls (`memory_remember`, `memory_recall`, `memory_correct`) are issued by the harness script or by the LLM's own tool-use decision. These are fundamentally different tests: scripted calls test the *store*; model-initiated calls test *prompting/agentic behavior*. Conflating them in one report means a tool-selection miss by Haiku gets reported as a memory-store regression. This must be split into two explicit tracks before any code is written.

2. **Scope defaults will fake success.** `cli.py:_add_private_scope_args` defaults `agent="default"` regardless of which chat model is invoking it. If the harness doesn't explicitly pass distinct `--agent` values per model, "Model A writes, Model B reads in a fresh session" will pass because both hit the same default private scope — not because sharing worked. The demo would then be validating nothing about the shared-pool mechanism it claims to showcase. Scope parameters per model/session must be pinned and asserted, not left to CLI defaults.

3. **Pass/fail thresholds precede the deferral they contradict.** Baking numeric accuracy/leakage/isolation thresholds into a ship gate (item 6) directly overrides a documented, accepted deferral. Either this report is informational-only, or someone needs to write the ADR that closes that deferral first — right now it's an undocumented scope expansion smuggled in through a "demo."

4. **Uncontrolled confound: the CLI's own session state.** Anthropic's Claude CLI can pick up `CLAUDE.md`, prior transcripts, and other session artifacts. If "fresh session" isn't a genuinely isolated working directory/config per query, the CLI's own continuity features — not the memory store — could be supplying the "recall," producing false positives that don't reproduce once the demo runs from a real user's machine.

5. **Correctness and latency thresholds are bundled into one gate.** Model latency for a hosted API depends on Anthropic's load, not on this project's code. Gating ship readiness on model latency conflates infrastructure variance the team doesn't control with recall latency the team does control (already benchmarked at p95 12.98ms per `2026-07-15-mvp-validation.md`). A flaky network day would block ship for a reason unrelated to the memory store.

6. **No live-model CI dependency should exist.** Running Haiku/Sonnet calls as a gating CI step introduces cost, external-outage flakiness, and possible secrets handling in CI for a personal, local-first, no-network-dependency project (AD-003). This has to be a manual or scheduled artifact, never a merge gate.

## Recommended Scenario and Metrics

Keep the scenario (facts under Model A, queried/corrected by Model B, verified by A, plus an isolation negative control) — it's a sound design — but split the report into three independent sections that can't contaminate each other:

- **Store-level (deterministic, CI-gated, offline embedder):** scripted `memory_remember` → `memory_correct` → `memory_recall` sequence, asserting active-version content, superseded-version exclusion, and exact-scope isolation directly against store return values. No LLM involved. This is the only section allowed numeric pass/fail thresholds today, and only after re-checking it doesn't reintroduce the deferred "retrieval-quality threshold" without an ADR.
- **Agentic tool-use (informational, manual/scheduled, live Haiku+Sonnet):** the same scenario but with the model deciding when to call MCP tools inside its own turn. Report tool-call rate, correct-tool selection rate, and final-answer fact accuracy as descriptive metrics — no ship gate.
- **Isolation negative control:** run as both directions — private scope A must not leak to private scope B (negative), and an explicit named shared pool must be visible to both (positive) — using explicitly distinct `--agent`/`--owner` values per model, asserted in the harness, not inferred from defaults.

Drop "recall latency" and "model latency" into a fourth, explicitly non-gating telemetry section.

## Prompt / Evaluation Controls

- **Scoring must stay deterministic even though generation isn't.** Use canonical slot values (e.g., store `favorite_editor: helix` as the fact content) and score the model's final answer with substring/normalized match against that canonical value, not an LLM-judge. An LLM-judge in the scoring loop makes the eval itself non-reproducible and adds a second live-model cost to every run.
- **Isolate the harness from the CLI's own memory.** Each query must run in a scratch working directory with no `CLAUDE.md`, no reused transcript, and an explicit, minimal system prompt that states only the MCP tools available — otherwise you can't attribute continuity to the store.
- **Fix scope parameters as first-class harness config**, not CLI defaults — one distinct agent identity per simulated model, one explicit named shared pool for the cross-model fact.
- **Separate "recall returned the right content" from "the model's answer reflects it."** Log both. A model can recall the correct active memory and still hallucinate past it — that's a prompting problem, not a store bug, and the report must not blur the two.

## Implementation Boundary

- Everything here is a new, separate harness (scripts + a JSON report writer) living outside `src/llm_memory_store/`. It should call the existing CLI/MCP surface as a black box — no changes to `store.py`, `database.py`, or the recall contract.
- The "generic command-model adapter" is reasonable as a thin subprocess wrapper around `claude --model ...`, but it is demo tooling, not a product feature, and shouldn't gain provider-specific branching beyond what's needed to shell out and capture stdout/stderr/latency.
- Do not add this harness to the default test suite (`tests/`) or default CI job; if kept, it belongs in a separate, manually or cron-triggered workflow given cost/flakiness.

## Ship Criteria

- The **store-level track** (deterministic, offline) can gate merges once its thresholds are reviewed against the existing deferral in `mvp-contract.md` — if kept, that deferral entry should be updated/closed via an ADR, not silently overridden.
- The **live-model track** should never gate ship. Its JSON report is a qualitative demo artifact (useful for a README recording or release notes), reviewed manually, not enforced.
- Before building either track, get explicit agreement on the actor question (harness-scripted vs. model-initiated tool calls) — that decision changes the harness architecture, not just its config.

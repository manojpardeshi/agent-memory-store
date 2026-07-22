# Claude Review: Local Llama/Ollama Integration

Date: 2026-07-19

## Prompt sent to Claude

Act as a skeptical principal architect reviewing a local-first LLM memory interoperability test. Use only the information below. Return a complete review now with sections Verdict, Ship blockers, Recommended improvements, and Wording corrections.

The user has Ollama listening on `http://127.0.0.1:11434`. The selected measured model is `llama3.1:8b`, reported by Ollama as 8.0B parameters, Q4_K_M, 4.92 GB, 131,072 context, with content digest `46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e`.

An initial Codex OSS probe reached Qwen but Codex warned that Ollama's OpenAI-compatible model-list response did not match its expected schema. Qwen then emitted Codex tool-call wrapper text instead of the requested JSON. This was rejected rather than counted as a pass.

The implementation supersedes Codex OSS for measured local inference with direct Ollama `POST /api/generate`: loopback HTTP endpoints only, no credentials, no tools or conversation history, `stream=false`, `format=json`, temperature zero, and a fresh stateless request for every baseline or assisted call. Hosted GPT remains through ephemeral/read-only Codex CLI.

The full real sequence was Claude Haiku → Claude Sonnet → hosted GPT → local Llama → Claude Haiku. Every consumer independently scored 0% without memory and 100% with the same 3-item, 486-byte shared-memory bundle. Llama's baseline used 80 Ollama-reported prompt tokens; its memory-assisted prompt used 281, a +201 whole-prompt delta. The provider-neutral memory-only estimate remains ~122 tokens via characters/4. Llama assisted latency was about 2.42 seconds. Private-scope violations, stale leaks, and invocation errors were zero; final correction accuracy was 100%.

The report records Ollama endpoint, version, model digest/details, token counts, durations, security controls, and marks local status `live-measured`. The dashboard shows Llama as **LIVE MEASURED · SINGLE RUN**. Live results remain informational; deterministic offline tests gate releases. The harness owns memory recall and injection; models do not autonomously share memory.

Review whether direct Ollama is the correct transport after the Codex OSS incompatibility, whether the metrics and security boundary are defensible, and whether any claim is overstated. Identify only concrete blockers or small improvements; do not propose a redesign without necessity.

Do not inspect or edit files. Reply only with the complete review text in this invocation.

## Claude response (verbatim)

### Verdict

The architectural call — dropping Codex OSS as the measured local-inference transport in favor of direct Ollama `POST /api/generate` — is correct and well-justified by the evidence given. The Qwen tool-wrapper leak was correctly rejected rather than papered over, which is the right instinct. The security boundary (loopback-only, stateless, no tools/history) is sound for a single-user local box. The core problem isn't the transport decision; it's that the report now mixes a real, provider-reported measurement (Llama's Ollama token counts) with a crude cross-provider heuristic (chars/4) in a way that could read as more comparable than it is, and it presents N=1 results with a precision (percentages, "100% accuracy") that a single trial doesn't support. Nothing here should block landing this as a labeled, informational demo artifact; several things should block treating its numbers as apples-to-apples measurement.

### Ship blockers

1. **Cross-provider transport asymmetry is unlabeled.** Hosted GPT is invoked via Codex CLI (a wrapper with its own scaffolding/token overhead); local Llama now bypasses any wrapper and hits `/api/generate` directly. If latency or token figures are shown side-by-side across providers as comparable, that's not a fair comparison — the CLI layer for GPT is not "free." Any table/dashboard row juxtaposing these numbers needs an explicit caption that transport shape differs per provider, or the comparison should be pulled until it does.

2. **The 201 vs. 122 token figures are being conflated.** The Ollama-reported +201 whole-prompt delta and the ~122 chars/4 estimate measure different things — one is total prompt-token growth (including formatting/instruction overhead), the other is a rough size of the memory payload alone. If both appear near each other without that distinction stated inline, a reader will reasonably conclude the memory bundle "costs" one figure or the other, when neither alone is true. This needs a caption fix before it's presented as authoritative, not just a nice-to-have.

3. **Percentage language overstates precision for N=1 / 3-item trials.** "0% without memory, 100% with memory" and "100% correction accuracy" read as measured rates but are single-trial, small-N outcomes (3 memory items, one run per provider). Report this as pass/fail or "3/3 items recalled correctly on this run," not as a percentage, until repeated trials justify rate language.

### Recommended improvements

- **Use the real Ollama delta to sanity-check the heuristic.** You now have ground truth (201 actual vs. 122 estimated) for one provider. Worth noting in the report whether the chars/4 estimate is a lower bound for GPT/Claude too (i.e., actual overhead there is probably similarly ~40-65% higher than the estimate implies), rather than treating the discrepancy as Llama-specific noise.
- **Log hardware/acceleration context for the 2.42s latency figure.** A single-run latency number for a Q4_K_M 8B model is meaningless without knowing CPU vs. GPU and rough specs. If this number will ever be used comparatively (vs. hosted providers, vs. future quantizations), capture that now while the run is fresh.
- **Reconsider what 100% correction accuracy actually demonstrates.** A 3-item, 486-byte bundle with an 8B Q4_K_M model is a low bar; passing it isn't strong evidence of local-model capability under memory injection, just that the harness's injection mechanism works end-to-end. Fine for a plumbing test, but don't let the framing imply a capability claim beyond that.
- **Clarify the Qwen/Codex-OSS incident's relationship to the llama3.1:8b result.** They're different models on different transports; a reader skimming the report could conflate "local model failed" (Qwen-via-Codex-OSS) with the unrelated, successful llama3.1:8b-via-direct-Ollama result. A one-line disambiguation avoids that.
- **State explicitly that Codex OSS is superseded only for the measured local-inference path**, not removed from the project generally — otherwise this reads as a broader architectural retirement than intended.

### Wording corrections

- "**No credentials**" as a listed security control is misleading — Ollama's loopback endpoint has no auth to waive; the actual control is **network isolation (127.0.0.1-only, no external exposure)**. Reword to avoid implying a credential mechanism was evaluated and deliberately skipped.
- "**Provider-neutral memory-only estimate**" invites the reader to think it's validated across providers; it's the same crude heuristic applied uniformly. Prefer "**heuristic cross-provider approximation (chars ÷ 4)**."
- "**live-measured**" status and "**LIVE MEASURED · SINGLE RUN**" should be consistent everywhere the numbers surface (report JSON, dashboard, any narrative doc) — if the dashboard chip carries the single-run caveat, the underlying report fields should carry the same qualifier, not just the UI.
- "**100% correction accuracy**" / "**0% / 100%**" → reword to item-level pass/fail counts (e.g., "3/3") per the blocker above, reserving percentage language for measurements with enough trials to support it.
- "**Supersedes Codex OSS**" → scope it explicitly to "for measured local inference," per the improvement above.

## Reconciliation

All three presentation blockers were resolved. The dashboard now displays item counts (`0/3`, `3/3`, and aggregate `0/9`, `9/9`), labels provider token totals as transport-specific and non-comparable, and distinguishes assisted-minus-baseline whole-prompt deltas from the separate characters ÷ 4 heuristic. The report already carries `evidence_scope: single-run-harness-injected`, while the UI badge says **LIVE MEASURED · SINGLE RUN**. The transport note now records the measured Apple M1/8 GB host, scopes the result as plumbing evidence, and distinguishes the historical Qwen/Codex OSS observation from the successful Llama/direct-Ollama run. AD-026 scopes the supersession to measured local inference; AD-027 records `llama3.1:8b` as the selected target.

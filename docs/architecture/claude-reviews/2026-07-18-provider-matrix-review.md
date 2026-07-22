# Claude Review: Cross-Provider and Local-Model Matrix

Date: 2026-07-18

## Prompt sent to Claude

Act as a skeptical principal architect reviewing a local-first LLM memory interoperability demo before shipment. Use only the information below; do not inspect files or describe future actions.

Implementation summary:

- A schema-v3 provider matrix captures random synthetic facts with Claude Haiku, stores typed facts in one explicit SQLite shared pool, then gives independent fresh consumers the same baseline and memory-assisted scenario.
- The live consumers are Claude Sonnet and hosted GPT through Codex CLI. The sequence returns to Haiku for a corrected preference.
- The real live run passed for both consumers: baseline exact-slot accuracy 0%, memory-assisted accuracy 100%, shared recall 100%, private isolation violations 0. Correction accuracy was 100% with zero stale leaks.
- Each consumer received the same 3-item, 486-character/UTF-8-byte bundle, estimated at 122 memory tokens via characters/4.
- Codex JSON telemetry reported 13,007 total input tokens for GPT baseline and 13,219 total input tokens for GPT memory-assisted. The UI labels these whole-Codex-turn totals and keeps them separate from the memory-only estimate.
- Hosted GPT uses `codex exec --json --ephemeral --ignore-user-config --ignore-rules --skip-git-repo-check --sandbox read-only` in a new empty temporary directory and with an environment allowlist. The prompt asks it not to use tools. The design does not claim Codex has no tools; it claims incidental tools are constrained by the empty read-only workspace.
- Claude uses safe mode, no session persistence, no browser, and no tools in a new temporary directory with the same environment allowlist.
- The installed Codex CLI's ChatGPT-account default was observed as `gpt-5.6-sol` and succeeded. The public-manual example `gpt-5.6` was rejected for this account. The harness uses the verified slug as a configurable default and accepts repeated `--gpt-model` values.
- A local consumer uses the identical Codex JSON adapter plus `--oss --local-provider ollama|lmstudio --model MODEL`. It is implemented and covered by deterministic offline tests, but it is labeled adapter-ready/not measured until the runtime and model are installed. It fails explicitly if local inclusion is requested without a model.
- Live evidence is informational; the offline provider matrix is the release gate. The harness, not the models, owns memory writes, recall, correction, and context injection.
- The dashboard replays the evidence and imports local reports; it does not execute models or upload reports.

Review these questions:

1. Is the cross-provider claim supported without overstating autonomous memory use?
2. Are memory-transfer and Codex token metrics labeled defensibly?
3. Is the hosted/local adapter security boundary reasonable for a personal demo?
4. Is using an observed, configurable account-specific Codex model slug acceptable?
5. Identify ship blockers, small improvements, and exact wording corrections.

Return sections: Verdict, Ship blockers, Recommended improvements, Wording corrections.

Provide the complete review now.

## Claude response

### Verdict

The architecture is sound and honestly framed. The cross-provider claim is defensible as “harness-mediated injection, verified across providers,” not “models autonomously share memory.” No redesign is required.

### Ship blockers

None in the implementation as described. User-facing wording would become a blocker if it implied Claude and GPT independently shared persistent state rather than receiving the same harness-injected bundle.

### Recommended improvements

1. State that characters/4 is an approximation everywhere, including raw reports.
2. Headline the Codex baseline-to-assisted input-token delta, with absolute whole-turn totals as supporting data.
3. Make the local provider's **NOT MEASURED** state persistent and unmistakable.
4. Pin the verified Codex model slug, record runtime version, and fail loudly without fallback when unavailable.
5. Record environment allowlist key names in every report without recording their values.

### Wording corrections

- Say “identical injected memory bundle,” not that consumers independently retrieved or negotiated access.
- State that Codex is instructed not to use tools and that non-use is not independently verified beyond the empty read-only workspace.
- Use “~122 tokens (characters/4 approximation, not a real tokenizer).”
- Put “Live evidence is informational; the offline provider matrix is the release gate” in the top-level README.

## Reconciliation

All recommendations were accepted. Schema-v3 reports now include the whole-turn input-token delta, CLI versions, environment allowlist key names, and explicit Codex control limitations. The dashboard headlines the delta and permanently marks the local slot **NOT MEASURED** until live evidence exists. The README and contracts now use harness-injection wording and repeat the live-versus-gating distinction.

# Claude Implementation Review: Model-Switching Demo

Date: 2026-07-15

> Verbatim Claude Sonnet review of the demo contract, complete harness, deterministic test, and first live JSON report. Medium findings were subsequently tightened before the final evidence run.

## Independent Review: Model-Switching Demo

**Ship/No-Ship: SHIP** (as a scoped, honestly-labeled demo — not as evidence for any broader retrieval-quality claim, which the contract itself disclaims).

### Blocking findings

None. Nothing here corrupts the offline gating test, leaks real secrets, or executes attacker-controlled input unsafely. `secure_write_text` enforces 0600, `demo-artifacts/` is gitignored, subprocess calls use arg arrays (no shell), and the correction test is grounded in real supersession (`status='superseded'`, excluded from default recall) rather than an assumption.

### Medium findings

1. **`slot_accuracy` isn't the "exact" check the contract promises** (`demo/model_switching.py:199`). It's substring containment over the whole response text, not slot-keyed. A model that echoes the entire recall bundle into the wrong JSON key, or wraps a value in extra text, still scores 1.0. This weakens the claim that capture/memory accuracy proves correct slot binding — it only proves the token appeared *somewhere* in the output.

2. **`private_isolation_violations` is close to tautological** (`:484`). It re-queries Model B's *own* private scope with `shared_pools=()` — the secret was never placed anywhere Model B could see it, so 0 violations is guaranteed by construction, not by a tested boundary. It documents "harness never leaked it" rather than "Model B is structurally blocked from getting it." Fine as a regression guard, weak as the "proof" requirement 7 asks for.

3. **`memory_lift >= 2/3` threshold is effectively dead code** (`:471`). Because `memory_accuracy == 1.0` is separately gated, lift only falls below 1.0 if a model hallucinates an exact 6-hex-char match to a random token — near-zero probability. The threshold reads as an independent check in the acceptance block but adds no real coverage beyond what's already gated.

4. **Full environment passthrough to the Claude CLI subprocess** (`:148`, `env=os.environ.copy()`). Reasonable for a local demo needing CLI auth, but any unrelated secrets in the operator's shell are exposed to that subprocess. Low severity given `--tools ""` and `--safe-mode`, worth a minimal env allowlist if this pattern gets reused elsewhere.

5. **Top-level `claim` field slightly outruns the mechanism** (`:373`). "Cross-model continuity through an explicit shared memory pool" is technically accurate but, read in isolation from the contract's Known Trade-offs section, could be misread as autonomous cross-session recall rather than harness-scripted store/recall with the model just transcribing a supplied bundle. The contract markdown is honest about this; the JSON artifact isn't self-documenting to the same degree.

### Evidence strengths

- **Randomized synthetic values per run** genuinely prevent training-data leakage as a confound — verified in `SyntheticProfile.generate`, and the live report's tokens (`PROJECT-CC3118`, `EDITOR-9ECA5D`, etc.) are plausible fresh hex, not memorable strings.
- **Correction/supersession is real, not simulated**: `store.correct()` marks the prior memory row `status='superseded'` and default `recall()` excludes superseded rows (confirmed by reading `store.py`), so `stale_value_leaks == 0` in the live report reflects genuine versioned supersession, not a scripted illusion.
- **Baseline-before-memory ordering is correctly sequenced** — Model B's no-memory baseline runs before any store write it could benefit from, and the live baseline response correctly returns all-`UNKNOWN`, giving real (not assumed) contrast for `memory_lift`.
- **Scope separation matches the stated design**: distinct `Scope.private` tuples for model-a/model-b plus one named `Scope.shared` pool, all visible and consistent in the report's `scopes` block.
- **Gating discipline is honest**: `acceptance.gating` is `true` only for `offline` and `false` for `live-claude` in the actual artifact — the code doesn't quietly promote live results to gating status, matching the contract's stated non-gating treatment of network-dependent runs.
- **Subprocess isolation is real**: fresh temp cwd per invocation, argument-array `subprocess.run` (no shell interpolation of prompt content), and a system prompt that explicitly instructs the model to treat recalled text as data, not instructions — reasonable prompt-injection mitigation given the demo's synthetic, low-stakes content.

### Bottom line

The demo does what its own contract says it does, and the contract is unusually careful about scoping its claims (explicitly disclaiming autonomous tool-selection, product-wide retrieval quality, and cross-vendor continuity). The metric-implementation gaps above (non-exact substring scoring, tautological isolation check, dead threshold) mean the acceptance JSON is a weaker proof than its field names suggest, but none of them let a broken system report as passing under the scenario as designed — they're precision gaps in the evaluation, not correctness bugs in the memory store. Fine to ship as-is; tightening `slot_accuracy` to check the parsed JSON key→value pair (not raw substring) would be the single highest-value follow-up if this harness gets reused for anything higher-stakes than a demo.

## Post-review disposition

- Exact scoring now parses the model's JSON and requires the expected value under the correct key. A rotated-key negative test proves raw token presence cannot pass.
- Isolation now queries every scope Model B is allowed to read and includes a positive control proving the private secret exists and is retrievable from Model A's private scope.
- The command adapter now passes only a minimal non-secret environment allowlist needed by the local CLI.
- The JSON report's claim and actor contract now state that the harness performs memory operations and models consume supplied context.
- The live evidence run was repeated after these changes and passed.

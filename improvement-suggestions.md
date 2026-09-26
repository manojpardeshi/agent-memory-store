# Improvement Suggestions — LLM Memory Store

Date: 2026-09-26
Basis: branch `scamper-candidate-generation` at `9656188`, plus every evidence document under
`docs/architecture/benchmarks/`. Scope: the memory store only.

## Where the project stands

- **Foundation is strong.** 0.1.0 is published with verified deletion, provenance, exact scope
  isolation, portability, migration, and review-first extraction. The evidence discipline is
  unusually rigorous for a project this size.
- **Retrieval looks excellent and is not the constraint.** Session-level Hit@10 is 97.0% on all
  500 LongMemEval-S questions.
- **Answers are the constraint.** 45/60 with kimi-k3 and 47/60 with Opus. Twelve of thirteen errors
  sit in multi-session (3/10) and temporal-reasoning (5/10).
- **The root cause is now measured.** A retrieved answer session contributes only 36–38% of its
  messages to the context. That within-session coverage tracks accuracy almost monotonically by
  category, while session-level Hit@10 is flat at 93–100% and cannot see the failure.
- **Measurement noise is about ±2 answers at n=60.** Two identical-protocol runs moved four labels.
- **Candidate history.** `session-diverse-v1` was rejected, `session-density-v2` was closed unrun,
  and `within-session-expansion-v1.1` failed Stage 1 while proving its mechanism: coverage rose
  from 36.1% to 57.6% at 0.968× baseline bytes.

---

## Priority 1 — Fix what the project steers by

### 1.1 Replace the headline retrieval metric
Session-level Hit@10 credits full marks for retrieving one message out of twelve. Adopt
**evidence-level coverage** as the primary retrieval gate: the share of each answer session's
messages present in context, or better, whether the specific answer-bearing messages are present.
Keep session Hit@10 as a secondary diagnostic. Every future retrieval candidate should be judged
on the metric that predicts answers.

### 1.2 Enlarge the answer-quality sample
At ±2 noise, sixty questions can only detect effects of four or more answers. Move answer gates
to the full 180 development questions. At the measured $2.16 per sixty single-arm, that is about
$6.50 per arm, which buys roughly three times the resolution for every future decision.

### 1.3 Fix the question-date defect in the paired runner
`scripts/run_memorybench_kimi_paired_development.py` still reads `questionDate` from a checkpoint
that never carries it, at lines 466 and 725. The single-arm runner was fixed. Apply the same
`--dataset` resolution before the next paired run, or that run silently repeats the defect.

### 1.4 Decide how to handle abstention questions
Supplying the question date fixed `8077ef71` but caused `gpt4_93159ced_abs` to over-answer an
abstention question. A prompt instruction to abstain when evidence is insufficient would likely
help. It changes the frozen answer protocol, so it needs a new protocol identity and a fresh
baseline rather than a quiet edit.

### 1.5 Put a watchdog in every runner
Stage 1 stalled twice on budget-fitting loops before the per-question deadline existed. Only the
Stage 1 runner has one now. Add the same `SIGALRM` deadline and `faulthandler` to the Mem0
comparator, the kimi baseline, and the paired runner.

---

## Priority 2 — Quality work, in order

### 2.1 Propose `within-session-expansion-v1.2`
The mechanism works; two specific defects failed it. Make exactly these changes:

- **Protect the anchor.** Never span-reduce each session's highest-ranked baseline message. On
  `18dcd5a5` the answer sat in that message, and largest-first reduction cut it to a span
  containing the title rather than the count. This is a bound, not a heuristic.
- **Fix latency without changing outputs.** Selection p95 was 34.1 ms against 15 ms because span
  fitting re-encodes the whole context repeatedly. Incremental exact byte accounting removes that.
  Verify byte-identical output on all 180 before treating it as the same policy.
- **Fix a latent truncation bug before it matters.** Expansion fetches at most 1,000 records per
  container through `list_memories`, ordered newest first. LongMemEval containers hold about 500
  messages, so the benchmark never hit it. A real user store exceeds 1,000 quickly, and older
  sessions would then silently lose their neighbours.

Keep every other v1.1 gate unchanged, so the only differences are the ones above.

### 2.2 Close the context-efficiency gap
The store sends a mean of 13,081 tokens per answer. Mem0 reports about 6,900 and Supermemory
about 720. Those are vendor claims, but even the conservative figure is half of ours. Span-level
projection, already built for expansion, can be evaluated on its own as a pure budget reduction:
same content selection, fewer tokens, with a gate that answer accuracy does not regress.

### 2.3 Add event dates alongside document dates
Temporal questions need when an event happened, not when it was mentioned. "I saw the dentist last
Tuesday," said on the 30th, is an event on the 24th. The store records only the source timestamp.
Deterministic date extraction at ingest needs no model and directly targets the 5/10 category.
Contract it separately from 2.1 so the two effects can be told apart.

### 2.4 Treat lexical fusion as lower priority
FTS5/BM25 fusion is cheap and both major competitors use hybrid retrieval. The measured loss,
however, is within-session coverage, not session ranking. Revisit after 2.1 and 2.3 report, and
only if a residual is attributable to ranking.

---

## Priority 3 — Library changes the evidence points to

### 3.1 Remove the N+1 query in `list_memories`
`list_memories` selects IDs, then calls `_record_by_internal_id` once per row, each a separate
joined query. Fetching 500 records costs 501 queries. One joined `SELECT` returning full rows
fixes it and benefits every caller, including export and review.

### 3.2 Add a session-neighbour lookup
Expansion currently loads every record in a container and filters by `session_id` in Python,
because `list_memories` has no metadata filter. A lookup by `(scope, session_id, message_index
range)` would make expansion cost proportional to the session rather than the whole store. It
removes most of the Stage 1 latency and the truncation bug in 2.1 at the same time.

### 3.3 Settle the extraction question as a product decision
Every locally measured extractor failed its automation gate. The Mem0 comparator reproduced the
same wall at 13.3% content retention under a local model. Mem0's published results suggest a
capable extraction model is worth a large accuracy gain. Choose one of these and write it down:

- keep extraction review-only and position the product as an auditable retrieval store; or
- offer an explicit, opt-in hosted extractor behind clear consent, while raw storage stays local
  and authoritative, so extraction can never destroy source data.

The current ambiguity leaves the project competing on a dimension it has deliberately disabled.

---

## Priority 4 — Competitive evidence

### 4.1 Run the hosted comparator
Matched comparators remain the unmet Phase 1 exit condition. Published figures contradict one
another: Mem0 claims 94.4% accuracy, Supermemory claims 95% Recall@15, and a third party claims a
36-point gap between them. Only a matched measurement settles where this store stands. It needs
the owner's credentials, a budget, and a contract amendment, because the current contract
requires local comparators.

### 4.2 Finish the Mem0-local comparison
Thirty of the sixty questions have paraphrastic gold answers that the lexical scorer cannot
measure for either arm. A judged pass would complete that comparison.

### 4.3 Publish per-axis results, not one score
Report quality, context cost, infrastructure, privacy, auditability, and deletion guarantees side
by side. The store loses a single-score comparison against hosted systems. It wins several axes
outright, and those are the reason it exists.

---

## Priority 5 — Repository hygiene

- **Merge and push.** Two branches carry more than twenty unpushed commits, including every
  benchmark result, the SCAMPER records, and three recorded negative results. Negative results
  belong on `main` too. Nothing here is backed up off this machine.
- **Back up the evidence artifacts.** Several committed documents cite SHA-256 digests of files in
  gitignored `demo-artifacts/`, such as the Stage 1 report, the kimi baseline, and the Mem0
  checkpoint. The Mem0 Qdrant stores exist only on the M2. If those files are lost, the digests
  point at nothing.
- **Install gitleaks locally.** The release gate depends on it and it is not on this machine.
- **Consolidate the two working copies.** `~/Documents/Memory Store For LLMs` is a pre-release
  copy at `ac81148` that is receiving new work. Its store code is identical to the live repo today,
  which makes this the cheapest moment to consolidate. Its working `pyproject.toml` also adds an
  unrelated package and its dependencies to the `llm-memory-store` wheel, which conflicts with the
  minimal-artifact decision in AD-044.

---

## What not to do

- **Do not chase "superior in all aspects."** Matching hosted systems on every axis means adopting
  a cloud dependency and per-ingest model calls, the two things this product exists to avoid.
- **Do not promote on small margins.** At n=60, anything under four answers is noise.
- **Do not cite the Mem0-local result as a general comparison.** It supports one claim only:
  extraction-based memory degrades under a local-model constraint.
- **Do not reopen context bundling.** The abandonment criterion stands. Within-session expansion
  proceeds under its own recorded reopening condition, not as a bundling variant.

## Suggested sequence

1. Merge, push, and back up the evidence artifacts. This is free and removes the largest risk.
2. Fix the paired-runner date defect and add watchdogs everywhere. Also free.
3. Implement 3.1 and 3.2. They are small library changes that remove v1.2's latency problem at
   its source.
4. Freeze and run `within-session-expansion-v1.2` Stage 1. Free.
5. If it passes, authorize a 180-question paid answer run, about $6.50 per arm.
6. In parallel, decide the extraction question and the hosted-comparator budget. Both are owner
   decisions that nothing else unblocks.

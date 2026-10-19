# Held-Out Renewal Plan

Date: 2026-10-19
Status: **proposed; needs three owner decisions (below) before any held-out data is touched.**

## Why

Every look at a held-out set leaks a little information into later design choices. The 120
design-blind LongMemEval-S development questions have now been looked at twice, both in aggregate
only:

1. `hybrid-rrf-v1` confirmed opt-in hybrid recall (80 → 91 of 117 complete evidence).
2. `gated-hybrid-v1` failed: 0.898 evidence recall on the tuning set, but below vector-only on the
   held-out set (78 vs 80).

The second result shows the risk is real: a variant tuned on sixty questions looked best there and
failed held out. The next goal, recovering on-topic evidence that recall misses, especially in
multi-session and temporal questions, needs a held-out set that has not already shaped earlier
decisions.

## Proposed roles

| Data | Size | Proposed role | Per-question inspection |
| --- | ---: | --- | --- |
| LongMemEval-S development (stratified 60 + former design-blind 120) | 180 | **Tuning pool** | allowed |
| **LoCoMo-10** (Maharana et al., snap-research/locomo) | 10 conversations, ~2,000 questions | **Primary fresh held-out** | not allowed: aggregate only |
| LongMemEval-S sealed validation | 150 | unchanged: final answer-quality evidence | not allowed |
| LongMemEval-S reserve | 170 | **owner decision** (see 3) | not allowed |

### 1. Retire the design-blind 120 into tuning

After two aggregate looks it no longer gives clean held-out evidence. Folding it into tuning
triples the tuning pool, from 60 to 180 questions (44 temporal, 40 multi-session), which reduces
the overfitting that sank `gated-hybrid-v1`. The retirement is recorded so no later document
calls it held-out.

### 2. LoCoMo as the primary fresh held-out

- **Never touched.** The project has not downloaded, ingested, or read LoCoMo.
- **Different distribution.** These are long two-person conversations, not one user's chat
  sessions. A gain that survives here is less likely to be a LongMemEval-specific fit.
- **Free metric.** Each question lists the dialogue turns that support its answer (`evidence`,
  for example `D3:12`), so evidence-level recall works exactly as on LongMemEval, with no paid
  answerer.
- **Covers the targets.** Its categories include multi-hop and temporal, the failure classes in
  question. Adversarial (unanswerable) questions have no evidence and are excluded from the metric.
- **License.** CC BY-NC 4.0. Evaluation use is permitted. The data is downloaded at run time and
  never committed, and results credit the authors.
- **Wired up.** MemoryBench at the pinned commit already has a LoCoMo loader.

### 3. Owner decision on the LongMemEval reserve

The contract keeps the reserve sealed for competitor comparisons. The hosted comparators are
finished and paid evaluation has stopped, so that purpose may not return. Options:

- **A (recommended).** Keep it sealed. LoCoMo plus synthetic retrieval_v3 give independent
  held-out evidence; the reserve stays available for a future matched comparison.
- **B.** Re-role it as a second, in-distribution product held-out (aggregate only). This is
  useful if LoCoMo and LongMemEval disagree, at the cost of the competitor reserve.

## Rules for using the held-out set

- **One look per frozen candidate.** A look happens only after a commit freezes the candidate,
  its parameters, and its pass/fail rule.
- **Each look is paired.** The baseline (vector recall) and the candidate are scored in the same
  look, so measuring the baseline does not cost a separate look.
- **Ledger.** Every look is appended to `evaluation/memorybench/held-out-ledger.json` with the
  candidate, freeze commit, date, and aggregate result.
- **Budget.** LoCoMo retires to tuning after three looks. A new held-out is then needed, or the
  owner decides on the reserve.
- **Aggregate-only tooling.** Held-out scripts print and write only aggregate and per-category
  results, never per-question outcomes.
- **Frozen data.** The LoCoMo file's SHA-256 is recorded at first download. Ingestion builds stores
  without printing questions or answers.

## Default pass/fail rule for retrieval candidates

Each candidate's frozen contract may tighten this rule, but not loosen it.

- **LoCoMo held-out, evidence-labelled questions:** complete-evidence-in-top-ten count is at least
  baseline + 2% of scored questions, and no category loses more than 1% of its questions.
- **Synthetic suites:** retrieval_v1, retrieval_v2, and retrieval_v3 still pass their gates with
  the certified default filter.
- **Latency:** median recall latency is at most 3 ms above baseline.
- **Answer quality:** not measured (no paid evaluation). Lexical answer presence, with the
  number-checked variant, is reported as a secondary signal.

## Sequence

1. **Owner decisions:** approve the roles above, choose A or B for the reserve, and approve
   LoCoMo's license terms for this use.
2. **Freeze.** Commit the ledger, the tuning-pool change, and this plan as accepted.
3. **Prepare LoCoMo.** Download it, record its digest, and build the 10 stores on the M2 with the
   pinned bridge. No scoring at this step.
4. **Build the aggregate-only evaluator.** It maps evidence `dia_id`s to stored turns, and its
   self-test runs on synthetic fixtures, not LoCoMo.
5. **Develop candidates on the tuning pool only.** Analysis of the topic misses in the 180 may
   suggest, for example, session-level pooling (find the right session, then the right turn),
   query reformulation by the free local model, or neighbour turns around strong hits. Each
   candidate gets a frozen contract before its single held-out look.

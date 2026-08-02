# Session-Density v2 Development Contract

Date: 2026-08-02  
Status: **CLOSED WITHOUT EXECUTION — 2026-08-02. Never frozen; never run; no paid call made.**

> **This contract is historical.** The context-bundling hypothesis was abandoned before this
> candidate executed, under the abandonment criterion in
> [`product-roadmap.md`](product-roadmap.md) and AD-053. The candidate's ceiling was one to three
> answers on sixty questions — below the noise floor of the gate that would have judged it — while
> twelve of thirteen observed answer errors fell in multi-session and temporal-reasoning, categories
> whose retrieval already succeeds at 0.892 and 0.858 answer-session recall@10. No baseline runner
> was built. The corpus and its completed cross-review are retained, unfrozen, as a reusable
> screening instrument. Nothing below authorizes execution; the text is preserved for provenance.

## Decision boundary

This draft defines a possible follow-up to `session-diverse-v1`. It is blocked until the current
fresh corpus is repaired, re-reviewed, receives its frozen baseline input, and an explicit freeze
review is recorded. The v1 paired human audit is complete and confirms failure. The first fresh
corpus revision was rejected before baseline because every case contained only 4–8 messages, making
top-ten retrieval exhaustive and the proposed swaps impossible. Its prior corpus/review hashes are
invalidated. This draft does not authorize local candidate execution, paid API calls, sealed
validation, reserve access, implementation, shipment, or an external claim.

The entire 180-question LongMemEval development split is now treated as observed development
evidence. The 60-question paired answer run is directly observed, and the remaining 120 questions
were included in the aggregate retrieval analysis used to select and assess `session-diverse-v1`.
None of the 180 may qualify or promote a v2 policy. They may be used only for disclosed failure
diagnosis.

The existing LongMemEval sealed-validation and competitor-reserve splits remain outside this
experiment. Their question content, labels, contexts, answers, and judge outputs must not be used
for corpus authoring, candidate selection, threshold selection, implementation tuning, or v2
development scoring.

## Observed evidence and hypothesis

The frozen v1 paired contract has SHA-256
`5a27276688253a52fa359aabc81573ae75a321bb4c8829f0c03dda74bca5666e`. Its raw paired run has
SHA-256 `c5c58bbdf0396ac8e49331a41a9d26b0d0e76d87739b1b12ad0f426a9eda658e`, and the current machine
evidence has SHA-256 `54ee33f8c2bfd27c7d760882cd18a3159106c4d81018e8d94aefadd6edfddf46`.
The automated score was 45/60 for the released baseline and 40/60 for the candidate, with eight
baseline-only correct answers and three candidate-only correct answers. The run cost $4.147215.

Across the 11 machine-judge-discordant outcomes, `session-diverse-v1` increased distinct sessions
from 30 to 69 while reducing labeled answer-session messages from 90 to 37. Seven of eight
baseline-only outcomes pruned the direct answer-bearing message despite preserving full labeled
answer-session coverage. This is observed diagnostic evidence, not a new promotion score. A
cap-four replay was simpler but missed the prior target-category retrieval gain and retained fewer
baseline messages than the bounded alternative below.

The proposed `session-density-v2-score-gated-two-swap` policy starts from the released top ten and
replaces at most two results. Only a third-or-later result from a duplicated provenance session may
be replaced, only by the highest-ranked top-50 result from a session absent from the current set,
and only when `removed.score - replacement.score <= 0.03`. Replacement opportunities are examined
from the lowest-ranked eligible top-ten result upward, and the final set is emitted in original
rank order. At least eight original top-ten messages are therefore retained when ten results are
available. Storage, embedding, relevance, base ranking, prompts, sources, and result schema remain
unchanged. The two-swap and 0.03 bounds are explicitly post-hoc and may not be tuned on this corpus.
No cap grid, threshold grid, adaptive rule, adjacent expansion, or second v2 candidate is permitted
under this draft.

## Blocking prerequisites

Before this contract can be frozen:

1. **Completed:** the existing blind human audit passed its reliability gates and authoritatively
   rescored baseline 47/60 versus candidate 41/60. V1 remains failed. Packet, key, adjudicated
   evidence, raw-run, checkpoint, and frozen-contract hashes are recorded in the machine draft.
2. **Revision in progress:** author a deterministic, fictional, owner-data-free corpus of 60
   questions, ten per category. Every case must contain 20–28 messages across 8–10 sessions and at
   least 12 plausible non-required distractors. All single-session categories use dense evidence in
   exactly one required session; all multi-session cases require 2–4 sessions; temporal and
   knowledge-update remain split between dense and diversity-required cases. The resulting corpus
   has 40 dense and 20 diversity-required questions.
3. **Must be repeated after revision:** record atomic required fact units mapped to required message
   and session IDs, ground-truth answers, question dates, categories, and strata. Two independent
   authors cross-review the corpus; neither may use candidate outputs when authoring or correcting
   labels.
4. **Must be repeated after revision:** verify zero exact question or message hash overlap and zero normalized 12-token-shingle overlap
   with all 500 LongMemEval questions and source messages. The corpus must contain no owner memory,
   telemetry, or private conversation data.
5. Record the revised deterministic build-script, corpus/embedded-label, ordered-selection,
   author-source, cross-review, and frozen baseline-input hashes. Replace all invalidated identities
   and change status only through an explicit freeze review before any candidate run.
6. Obtain a new, explicit owner authorization before any paid Kimi call. The earlier $5 approval was
   consumed by the completed v1 paired run and does not carry forward.

## Stage 1: local retrieval gate

Stage 1 is API-free and must complete before paid execution can be proposed. Baseline and candidate
use the same fresh 60-question corpus and unchanged ingestion, embedding, ranking, relevance, and
formatting behavior.

All of these gates must pass:

- all 60 questions complete in both arms, with ten questions per category, 40 dense-evidence
  questions, and 20 diversity-required questions;
- the baseline reproduces its frozen top-ten memory-ID prefix exactly, the candidate returns the
  same result count, retains at least eight original top-ten messages whenever ten are returned,
  performs at most two qualifying swaps, and has zero scope, lifecycle, source, or provenance
  failures;
- overall required-message recall@10 is no more than 0.01 below baseline;
- at most one of 40 dense-evidence questions loses complete required-evidence coverage;
- diversity-required complete answer-session coverage improves on at least two of 20 questions and
  regresses on at most one;
- overall answer-session recall@10 does not regress, MRR@10 is no more than 0.005 below baseline,
  and no more than two questions lose any required evidence;
- mean and p95 formatted context JSON bytes are at most 1.00 and 1.05 times baseline;
- pure selection p95 is at most 15 ms and search p95 is at most 225 ms; and
- the observed LongMemEval development180, sealed validation, and reserve contribute zero questions,
  labels, or score records.

Any miss ends this v2 candidate before a paid call. The negative result is retained, and another
swap count, score threshold, cap, or alternative requires a new corpus and contract.

## Stage 2: paid paired answer gate

Stage 2 remains blocked even after a local pass until the owner separately approves its paid budget.
If authorized, exact direct-API `kimi-k3` produces one answer and three arm-blind judge votes for
each baseline/candidate pair. Question order and arm execution order are deterministic; both arms
share the same prompts, dates, answer protocol, judge protocol, and one combined $5 hard ledger.
The runner must stop before a call when the conservative reservation for that call exceeds the
remaining ledger.

All automated gates must pass:

- exact response model identity, normal completion, complete usage records, zero failed or
  unreconciled calls, and total paid cost no greater than $5;
- at least 42/60 candidate answers correct after three-vote majority scoring;
- candidate overall correct count no more than one below baseline;
- no category loses more than one correct answer;
- the 40 dense-evidence questions lose no more than one correct answer in aggregate;
- the 20 diversity-required questions gain at least two correct answers in aggregate;
- judge-vote unanimity is at least 0.85 in each arm and differs by at most 0.10; and
- every Stage 1 context, provenance, cardinality, and split-isolation gate remains true.

Every question with discordant arm majorities or a non-unanimous answer in either arm then receives
blind human scoring. The audit contains at least four unique questions, hides arm identity and
context policy, grades each answer independently, repeats a deterministic 20% sample, requires at
least 0.90 intrarater agreement and 0.75 judge-human agreement, and substitutes authoritative human
labels before all scoring gates are rerun.

## Stop and authorization rules

Stop immediately on any corpus, source, selection, protocol, candidate-policy, split-isolation,
resume-identity, model-identity, or budget mismatch. A malformed response may receive at most one
identical-request reissue. Budget exhaustion produces incomplete evidence; the ceiling may not be
raised for the same experiment.

A final pass is development evidence only. It authorizes asking the owner whether to perform one
LongMemEval sealed-validation comparison. It does not open validation automatically, does not
authorize competitor-reserve use, and does not authorize shipment or a competitive claim. At 60
questions, the result is an engineering gate rather than statistical proof of superiority.

The corresponding machine-readable draft is
`evaluation/memorybench/session-density-v2-development-gates-draft-v1.json`.

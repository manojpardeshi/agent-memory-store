# Within-Session Expansion — Development Contract (v1.1)

Date: 2026-08-03
Status: **FROZEN v1.1 2026-09-04 by owner selection of fix A.** Supersedes the v1 freeze of
2026-08-03, which was found internally inconsistent before any run (see *Revision v1.1*). Bounds
and thresholds below are locked; any change creates a new contract and experiment identity.
Stage 1 is authorized (API-free). Stage 2 remains blocked pending separate budget authorization.

## Revision v1.1 — why v1 could not be run

v1 froze two bounds that cannot both hold: originally retrieved messages "never reduced below
full text", and total context "≤ 1.00× baseline". Expansion only adds bytes, so under v1 every
question's context exceeds baseline unless expansion is empty. The defect was found while
designing the span budget, before implementation and before any measurement, and was put to the
owner rather than reinterpreted. The owner selected **fix A**: baseline items may be reduced to
query-aware spans but are never dropped and never reordered, with a body floor; the ≤ 1.00×
budget stands; and a Stage 1 guard is added so pruned answer text is detectable.

## Freeze procedure

Freezing is the owner's act, not the author's. On freeze:

1. The owner confirms each bound in the table below and each gate threshold as one they
   will stand behind, knowing none may be adjusted after a result is observed.
2. The SHA-256 of this document and of the machine-readable gates file are recorded in the
   gates file, and its status changes from `draft-blocked-not-frozen` to `frozen`.
3. From that point, any change to a bound or threshold creates a new contract and a new
   experiment identity; it does not amend this one.
Diagnosis: [`benchmarks/2026-08-03-multi-session-error-analysis.md`](benchmarks/2026-08-03-multi-session-error-analysis.md)

## Hypothesis

Answer failures in multi-session and temporal-reasoning are caused by low **within-session
coverage**, not by failure to locate the relevant session.

Measured support: six of ten multi-session questions had every required session in the top
ten and only two were answered correctly. An answer session that is retrieved contributes a
mean of 38.0% and median 33.3% of its messages. Coverage tracks accuracy almost
monotonically across categories while session-level Hit@10 sits at 93–100% throughout and
discriminates nothing.

Predicted mechanism: given a session already judged relevant, admitting more of its content
supplies the aggregation components the answerer currently reports as missing.

## The one material variable

**Which content from an already-relevant session enters the context.**

Storage, embedding identity, base ranking, relevance policy, scope semantics, provenance,
prompts, and the answerer/judge protocol are unchanged.

### A note on the one-variable rule

The working rules require one material memory-system variable per paired benchmark. This
candidate changes selection in two visible ways — admitting more of a session, and admitting
message spans rather than whole messages — and that requires justification rather than
silence.

They are not independent variables. Expansion alone necessarily inflates context and would
fail the budget gate; spans alone reduce tokens without addressing coverage. The variable
under test is the **session-content selection policy**, and budget neutrality is imposed as
a *gate* rather than treated as a second experiment. If the candidate fails, the mechanism
check below distinguishes an implementation that did not increase coverage from a coverage
increase that did not help.

## Candidate policy: `within-session-expansion-v1`

Deterministic, provider-neutral, no model in the query path.

1. Rank exactly as the released store does today. The ranked pool is unchanged.
2. Identify the sessions represented in the current top ten. Retain them in original rank
   order; no session is dropped and no new session is introduced.
3. For each retained session, admit additional content from that same session: the messages
   adjacent to the highest-ranked retrieved message, expanding outward, bounded by a
   per-session cap.
4. Reduce content to query-aware spans so the total formatted context does not exceed the
   baseline's for the same question. Expansion bodies are reduced first; baseline bodies only
   if still over budget. A baseline item is **never dropped and never reordered**, and no body
   is reduced below 400 characters (or its full length if shorter). Expansions are dropped
   from the tail only after every body has reached the floor.
5. Emit in original rank order with full provenance on every item.

Bounds are fixed before execution and may not be tuned during a measurement cycle:

| Bound | Value |
| --- | --- |
| Sessions admitted | exactly those already in the baseline top ten |
| New sessions introduced | zero |
| Per-session expansion cap | at most 4 additional messages |
| Originally retrieved messages | never dropped, never reordered; body ≥ 400 chars or full |
| Total formatted context | ≤ 1.00× baseline mean, ≤ 1.05× baseline p95 |

Point 4's protection is deliberate. `session-diverse-v1` failed because seven of eight
losses **dropped** the answer-bearing message. This candidate never drops a baseline item; it
may shorten one to a query-aware window, and the Stage 1 answer-presence guard exists to catch
the case where that window misses the answer sentence.

## Stage 1 — local gate, API-free

Runs over **all 180 development questions**, not only the stratified sixty. Stage 1
involves no model, so the larger sample costs nothing and triples the evidence behind the
mechanism gate. Coverage on the 120 questions outside the stratified sixty is
retrieval-level observation only — already observed in the `session-diverse` development
run — and does not touch the answer-level purity Stage 3 depends on.

All must pass:

- all 180 questions complete; zero scope, lifecycle, source, or provenance failures;
- every baseline top-ten message is present in the candidate output, verified per question;
- zero new sessions introduced;
- **mechanism check:** mean within-session coverage on answer sessions reaches at least 55%
  **and** exceeds the baseline measured on the identical 180 by at least 15 points, with no
  category falling. The 38.0% figure was measured on the sixty; the baseline on the 180 is
  re-measured inside Stage 1 rather than assumed;
- mean formatted context bytes ≤ 1.00× baseline and p95 ≤ 1.05× baseline;
- **answer-presence guard:** on the stratified sixty, lexical answer presence in the top-ten
  context (`score_content_answer_presence` criterion, extractive categories) does not fall
  versus baseline. Coverage rising while answer presence falls means spans pruned answer text;
- pure selection p95 ≤ 15 ms and search p95 ≤ 225 ms;
- internal synthetic suites unchanged: Recall@5, MRR, distractor leakage, and zero
  inaccessible-scope results.

A Stage 1 miss ends the candidate before any paid call. The mechanism check is not a
success criterion for the hypothesis — it verifies the implementation does what it claims.
Failing it means the code is wrong, not the idea.

## Stage 2 — paid answer gate

**Blocked pending separate budget authorization.** Exact `kimi-k3` under the identical
frozen protocol as `2026-08-03-kimi-question-date-baseline60.md`: same prompts, model,
system prompts, efforts, token limits, three-vote majority, and question dates supplied.

Compared against that recorded baseline of **45/60**, whose per-category split is
single-session-user 10/10, single-session-assistant 10/10, knowledge-update 9/10,
single-session-preference 8/10, temporal-reasoning 5/10, multi-session 3/10.

Gates, sized above the ±2-answer noise floor measured in the same document:

- **multi-session and temporal-reasoning combined improve by at least 4 answers** (from 8/20
  to at least 12/20);
- multi-session alone does not regress;
- no other category loses more than 1 answer;
- overall total does not regress;
- every Stage 1 gate remains true on the executed run;
- total paid cost ≤ the authorized ceiling, with the runner refusing any call whose
  worst-case reservation exceeds the remaining ledger.

A 4-answer gate against 13 answers of combined headroom is deliberately demanding. At ±2
noise, a smaller margin cannot be distinguished from a re-run of the same system.

### Cost and design choice

Two options, for the owner to decide at authorization:

| Design | Cost | Trade-off |
| --- | ---: | --- |
| Candidate arm only, against the recorded baseline | ~$2.20 | Halves cost. Cross-run comparison carries the full ±2 noise, which the 4-answer gate already absorbs. |
| Paired baseline and candidate in one run | ~$4.40 | Controls for protocol drift and model-version change. Precedent of the earlier paired run. |

The single-arm option is defensible only because the baseline was produced today by this
exact runner and protocol. If any protocol element changes, paired becomes mandatory.

## Stage 3 — unobserved development validation

**The stratified sixty is fully observed.** It has been used for the harness diagnosis, the
question-date re-measurement, and the multi-session error analysis, including reading
individual failures. It may screen this candidate. It may not certify it.

A Stage 2 pass therefore authorizes only a request to run the **120 development questions
outside the stratified sixty**, which remain unobserved, under the same gates. Those 120 are
development, not sealed: this consumes no sealed-validation or reserve budget.

LongMemEval sealed validation and competitor reserve remain unopened. Their question
content, labels, answers, and judge outputs may not inform this candidate's design,
thresholds, or selection.

## Stop conditions

Stop on any corpus, selection, protocol, model-identity, provenance, or budget mismatch. A
malformed response may receive at most one identical reissue. Budget exhaustion produces
incomplete evidence; the ceiling may not be raised for the same experiment. A failed gate is
recorded and published; it is not tuned away within the measurement cycle, and no bound in
this contract may be adjusted after observing a result.

## What a full pass would and would not establish

It would establish that within-session expansion improves answer quality on 180 development
questions at constant context cost, on one benchmark, with one evaluator.

It would not establish a competitive claim, would not authorize shipping as default, and
would not open sealed validation. Default-off remains the shipping posture until a sealed
comparison is separately proposed and authorized.

# SCAMPER Candidate-Generation Methodology

Date: 2026-08-03
Status: active on the `scamper-candidate-generation` branch; generates candidates only

## Why this exists

This project's convergent machinery is strong: pre-registered thresholds, frozen corpora,
disjoint splits, blind human audits, and a standing rule that failed gates are published
rather than tuned away. Its divergent machinery is weak.

The evidence for that weakness is on the record. The entire post-0.1 cycle produced two
retrieval candidates — `session-diverse-v1` and `session-density-v2` — and both were
variants of one hypothesis, that changing which retrieved messages enter the context
bundle improves answer quality. The first failed under human adjudication. The second was
closed without execution because its ceiling was below the noise floor of the gate that
would have judged it (AD-053). Two attempts, one idea, ~$16 of paid evaluation, and no
queued alternative when the hypothesis closed.

The benchmark contract's "decision rule for the next product slice" lists mechanisms —
lexical fusion, temporal retrieval, context-budget control — but nothing systematically
generated that list, and nothing checks it for blind spots. SCAMPER supplies the missing
step: a structured sweep that forces candidates out of the regions attention does not
naturally visit.

## The firewall

**SCAMPER generates candidates. It promotes nothing.**

This is the load-bearing rule. A divergent technique attached to an evidence-gated project
is a standing temptation to launder an appealing idea past the gates by arriving with a
methodology attached. It does not.

Specifically, a SCAMPER candidate:

- does not acquire an entry condition, a threshold, or a budget by being generated;
- does not authorize a paid run, a sealed-validation comparison, or reserve access;
- does not justify tuning on an observed split, and may not be selected using sealed or
  reserve content;
- must still be frozen in its own pre-registered contract before any measured run;
- inherits every existing invariant — local-first operation, exact scope isolation,
  explicit destructive-operation confirmation, no new listener or daemon, and no owner
  data in evaluation corpora.

A candidate that cannot state a falsifiable gate is not a candidate. It is an opinion, and
it stays in the ideation record until someone can specify how it would be shown wrong.

**Anti-pattern to refuse:** running SCAMPER backwards over an idea already chosen, to
manufacture the appearance of systematic generation. If the lens was fitted to the
conclusion, the exercise produced nothing.

## The seven lenses

Each lens is stated as a question against this project's measured state, not in the
generic form.

| Lens | Project-specific prompt |
| --- | --- |
| **Substitute** | What component could be swapped for a different mechanism of the same kind — embedder, ranking function, retrieval unit, context format? |
| **Combine** | What two existing subsystems have never been run together? The store already contains subsystems built for unrelated purposes. |
| **Adapt** | What technique from an adjacent field, or from this repository's own other track, applies to the dominant failure? |
| **Modify** | What existing parameter or output shape is fixed by habit rather than evidence — depth, granularity, budget, cardinality? |
| **Put to another use** | What structure was built for one purpose and could serve a second? Provenance, corrections, expiry, and proposal artifacts all exist already. |
| **Eliminate** | What could be removed entirely — a dependency, a stage, a model — such that the failure it causes disappears with it? |
| **Reverse** | What order is assumed and could be inverted — ingest-time versus query-time, retrieve-then-answer versus answer-then-verify? |

## Standing evidence the lenses must respect

Any candidate contradicting these is generated in error:

1. Retrieval is near saturated. 97.0% Hit@10 and 92.1% answer-session recall@10 across
   all 500 questions. There is little headroom in finding the right session.
2. The loss is downstream. 78.3% answer accuracy against that retrieval, and the v1
   discordance diagnostic recorded full answer-session coverage in both arms on all
   eleven disputed questions.
3. The loss is concentrated. Multi-session 3/10 and temporal-reasoning 5/10, against
   39/40 combined across the other four categories.
4. Local extraction does not work. Every measured local extractor failed its automation
   gate (AD-038, AD-039), and the Mem0 comparator reproduced the same wall in a second
   independent system at 13.3% against the store's 96.7%.
5. Raw ingestion's advantage is that it destroys nothing. Any candidate that discards
   source content at ingest inherits Mem0's measured failure mode.

## Branch protocol

`scamper-candidate-generation` runs parallel to `main`, which stays at the published
0.1.0 tree. Ideation records, contracts, and prototypes live here. Nothing merges toward
`main` on the strength of the ideation record alone: a candidate leaves this branch only
by passing the gates in `competitive-benchmark-contract.md` on its own frozen contract,
exactly as `session-diverse-v1` was required to and failed to.

Negative results stay. A lens that produced nothing usable is recorded as having produced
nothing usable, because that is information about where the design space is exhausted.

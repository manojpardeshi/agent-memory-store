# SCAMPER Pass 002 — Applied to Mem0 and Elastic Atlas

Date: 2026-08-03
Status: ideation record. **No candidate here is frozen, contracted, or authorized to run.**
Method: `../scamper-methodology.md`

## Correction to the premise

There is no product called "ElasticMemory." The comparable Elastic product is **Atlas**,
open-sourced in June 2026: agent memory built on Elasticsearch, integrated over MCP.
This pass treats Atlas as the intended target.

## Competitor state, from public sources

| | **Mem0 (2026)** | **Elastic Atlas** | **This project** |
| --- | --- | --- | --- |
| LongMemEval | **94.4%** (93.4% on the Apr-2026 algorithm) | not stated | **78.3%** (stratified 60, Opus) |
| Retrieval | 3 signals: semantic + keyword + entity, fused | BM25 + Jina v5 + RRF + cross-encoder rerank | semantic + recency only |
| Reported recall | — | 0.89 R@10 | 0.97 Hit@10, 0.921 ans-session R@10 |
| Context/query | **~6,900 tokens** | — | **13,081 tokens mean** |
| Memory model | vector + graph + key-value; user/session/agent tiers | episodic / semantic / procedural, separate indices and lifecycles | typed turns, facts, preferences, summaries, events |
| Extraction | single-pass hierarchical, **ADD-only, never overwrites** | LLM consolidates episodic into semantic | review-first, human-approved, **raw never discarded** |
| Infrastructure | hosted platform for best numbers | requires Elasticsearch | single SQLite file, no daemon |

## The uncomfortable finding

**Mem0 reports 94.4% on LongMemEval. This project measures 78.3%.** The metrics are not
strictly comparable — theirs is the published full-benchmark figure, ours is 60 stratified
questions with Opus both answering and judging — but a ~16-point gap is far too wide to be
explained by that.

Worse for our prior reading: Mem0's largest 2026 gains were **+29.6 on temporal reasoning
and +23.1 on multi-hop** — precisely the two categories where this project is weakest
(5/10 and 3/10). They did not merely beat us overall; they specifically solved the two
things we have not.

This must be reconciled with `2026-08-03-mem0-local-comparator.md`, which measured Mem0 at
13.3% content retention against our 96.7%. Both are correct and they measure different
things. That run constrained Mem0 to `llama3.1:8b` for extraction, and the caveat recorded
there — "measures Mem0 outside its design envelope" — turns out to be the whole story. Mem0's
architecture is not weak; it is **dependent on extraction quality**, and given a capable
model it converts that dependency into a 16-point lead.

The local comparator remains valid for exactly one claim: extraction-based memory degrades
severely under a local-model constraint. It does not support any claim about Mem0 as
deployed, and it must never be cited as though it did.

## The goal as stated is not achievable

"Superior in all aspects" cannot be delivered, and pursuing it would destroy the position
worth holding.

Mem0's 94.4% is produced with hosted frontier-model extraction. Atlas's hybrid retrieval
runs on an Elasticsearch cluster. Matching both on quality means adopting a cloud
dependency and a heavyweight infrastructure requirement — which are the two things this
product exists to avoid. AD-046 already states the position: no feature-for-feature parity
with hosted context platforms.

Attempting universal superiority converts a defensible niche product into an
undifferentiated one that is worse at everything. The achievable and defensible goal is
narrower and stronger:

> **Close the quality gap far enough that the local-first, auditable, zero-infrastructure
> position becomes the deciding factor rather than a consolation.**

The lenses below are organised around that goal.

---

## Substitute — replace single-signal ranking with multi-signal fusion

Both competitors independently converged on fused multi-signal retrieval: Mem0 scores
semantic, keyword, and entity signals in parallel; Atlas fuses BM25 and dense vectors by
RRF and reranks with a cross-encoder. This project ranks by semantic similarity plus
recency alone.

Convergent adoption by two independent teams is materially stronger evidence than the
benchmark contract's own decision rule, which nominated lexical fusion without support.
**This upgrades candidate C5 from "deprioritised" to "primary."** Pass 001 deprioritised
it on the grounds that retrieval is saturated at 97% Hit@10 — that reasoning holds for
finding the right *session*, but temporal and entity questions turn on exact tokens
(dates, identifiers, names) that dense vectors handle poorly, and precision@10 is 0.700.

SQLite ships FTS5, so BM25 costs no new dependency and no network.

*Gate:* temporal and multi-session answers improve by at least three combined, with no
category regressing and no scope leakage.

## Combine — give the existing type system distinct retrieval and lifecycle

Atlas separates episodic, semantic, and procedural memory into distinct indices with
distinct lifecycle rules. Mem0 tiers by user, session, and agent.

This project **already has** a typed memory model — turns, facts, preferences, summaries,
events — and a TTL distinguishing raw turns from durable types. What it does not do is let
type influence retrieval or ranking. A preference and a raw transcript line compete in one
undifferentiated pool.

The structure exists; only the policy is missing. That makes this unusually cheap.

*Gate:* preference and knowledge-update categories improve with no regression elsewhere;
no schema change.

## Adapt — procedural memory, and what not to adapt

Atlas's procedural memory (playbooks with success/failure counters) has no analogue here.
Nothing in this project learns which approaches worked. It is genuinely novel and genuinely
outside the current product boundary, since it implies feedback capture the store does not
have.

*Status:* recorded as a direction, not a candidate. No falsifiable gate today.

Explicitly **not** to adapt: Mem0's ADD-only extraction, which never overwrites a fact.
That is Mem0 defending against exactly the destructive-extraction failure the local
comparator measured. This project already has a stronger answer — the raw substrate is
never discarded at all — and adopting their mitigation would be adopting a weaker form of
a guarantee we already hold.

## Modify — halve the context budget

Mem0 keeps each call near **6,900 tokens**. This project's measured mean answer input is
**13,081 tokens** — roughly double the context, for 16 points less accuracy.

That is the most concrete competitive gap in this document, and it is measurable today
without any model. It strongly validates C3 (span-level minification) from Pass 001: whole
messages are returned when spans would do, and inspection of the comparator run found a
full cake recipe occupying one of ten slots.

Context efficiency is also directly relevant to the local-first position: fewer tokens
means smaller local models remain viable.

*Gate:* mean context bytes fall at least 40% with answer accuracy not regressing and no
answer-bearing content pruned.

## Put to another use — two dormant structures

**The provenance DAG.** Built to compute deletion blast radius; never consulted at query
time. Mem0 ships graph-based relational storage and entity linking as a headline
capability. This project has a graph it does not use for retrieval.

**Versioned corrections.** Built for auditable supersession; never consulted at query time.
But *"what superseded what, and when"* is precisely temporal reasoning — the category where
Mem0 gained +29.6 and this project scores 5/10. Mem0 reranks "toward what's current";
this project already records exactly which fact replaced which, and ignores it.

This is the strongest structural insight in this pass: the temporal substrate competitors
built from scratch already exists here, unused, as a byproduct of the correction model.

*Gate:* temporal-reasoning improves by at least three of ten using only existing
correction and provenance records, with no new dependency.

## Eliminate — the axis where superiority is real

Mem0's 94.4% requires hosted frontier-model extraction. Atlas requires an Elasticsearch
cluster. Both carry an operational dependency this project does not.

Eliminating dependency is not a gap to close but the differentiator to defend and make
legible. Neither competitor can offer: a single inspectable SQLite file, no daemon or
listener, no cloud egress, verified hard deletion with computed blast radius, exact scope
isolation, and full provenance on every returned result.

*Not a candidate.* This is positioning, and the actionable form is measurement: publish
per-axis comparison — quality, context cost, infrastructure, privacy, auditability,
deletion guarantees — rather than a single score this project would lose.

## Reverse — query-time extraction, revisited against competitor evidence

Pass 001's C1 proposed inverting ingest-time extraction to query time. Mem0's results
complicate it: their ingest-time extraction works well when the model is capable, and
query-time synthesis pays a model cost on *every recall* rather than once per ingest —
worse economics at read-heavy usage, and a direct conflict with the offline-core invariant.

*Status:* retained, **downgraded** below the Substitute, Modify, and Put-to-another-use
candidates, all of which require no model in the query path.

---

## Revised ranking

| Rank | Candidate | Lens | Why | Model in query path? |
| ---: | --- | --- | --- | --- |
| 1 | Corrections and provenance as temporal substrate | Put to another use | Targets the worst category using structure already built | No |
| 2 | Multi-signal fusion with FTS5 BM25 | Substitute | Two competitors converged on it; no new dependency | No |
| 3 | Span-level context minification | Modify | Closes a measured 2× context gap | No |
| 4 | Type-aware retrieval and lifecycle | Combine | Structure exists; only policy missing | No |
| 5 | Deterministic temporal index (Pass 001 C2) | Eliminate | Still sound; overlaps rank 1 | No |
| 6 | Query-time synthesis (Pass 001 C1) | Reverse | Sound but costly and conflicts with offline core | Yes |

The top four require **no model in the query path**, no network, and no new dependency.
They are compatible with the local-first invariant rather than in tension with it, which is
what makes them the right first block of work.

## What this pass does not do

It authorizes nothing. Every candidate still requires its own frozen pre-registered
contract and explicit owner authorization before a measured run. The competitor figures
above are **published vendor claims, not matched local measurements**, and per the
benchmark contract they may not enter a comparison table as equivalent results. The only
way to know where this project actually stands is the hosted comparator run, which remains
the outstanding Phase 4 work.

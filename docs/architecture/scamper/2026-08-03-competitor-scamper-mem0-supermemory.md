# SCAMPER Pass 002 — Applied to Mem0 and Supermemory

Date: 2026-08-03
Status: ideation record. **No candidate here is frozen, contracted, or authorized to run.**
Method: `../scamper-methodology.md`
Supersedes: an earlier draft of this pass that analysed Elastic Atlas after misreading the
target product. Atlas is a real competitor but not the one under evaluation; that draft is
retained in git history only.

## Note on the benchmark relationship

Supermemory authors **MemoryBench**, the framework this project's competitive baseline runs
on (`118209a7...`). Benchmarking against a competitor using that competitor's own harness is
not disqualifying — the harness is open and the dataset is externally pinned — but it is a
disclosable asymmetry, and it belongs in the required report fields alongside the others.

## Competitor state, from published sources

Vendor figures below are **self-reported and mutually inconsistent**. Mem0 claims 94.4% on
LongMemEval; Supermemory claims 95% Recall@15 on LongMemEval-S; a third-party comparison
claims Supermemory leads Mem0 by 36 points. Those cannot all be true of the same quantity,
because they are not the same quantity — accuracy, recall, and depth differ. This is exactly
the condition the benchmark contract's matched-measurement rule exists to handle.

| | **Mem0** | **Supermemory** | **This project** |
| --- | --- | --- | --- |
| Headline | 94.4% LongMemEval (accuracy) | 95% Recall@15, LongMemEval-S | 97.0% Hit@10 / 92.1% ans-session R@10 |
| Answer accuracy | 94.4% | not separately stated | **78.3%** (stratified 60, Opus) |
| Context per query | ~6,900 tokens | **~720 tokens** (99.4% reduction) | **13,081 tokens** |
| Retrieval | semantic + keyword + entity, fused | hybrid: atomic memories **plus original chunks** | semantic + recency only |
| Extraction | single-pass hierarchical, ADD-only | session decomposition into semantic blocks; atomic memories with reference resolution | review-first, human-approved; raw never discarded |
| Versioning | temporal rerank toward current | **relational versioning** of updates/extensions/inferences | versioned corrections with provenance |
| Temporal | +29.6 gain in 2026 | **dual timestamps: document date and event date** | source timestamp, unused in ranking |
| Evaluator | — | GPT-4o, GPT-5, Gemini-3-Pro | Opus 5 / kimi-k3 |
| Infrastructure | hosted for best numbers | hosted API | single SQLite file, no daemon |

## The good news, stated precisely

Per-category retrieval is closer than the headlines suggest. Supermemory reports Recall@15;
this project measures answer-session recall@**10**, a shallower and therefore harder depth:

| Category | Supermemory R@15 | This project R@10 |
| --- | ---: | ---: |
| Single-session assistant | 100% | 100.0% |
| Knowledge update | 99% | 98.1% |
| Single-session user | 97% | 95.7% |
| Single-session preference | 90% | **93.3%** |
| Multi-session | 93% | 89.2% |
| Temporal reasoning | 91% | 85.8% |

**Retrieval is competitive, and at a shallower depth.** This project leads on preference,
matches on assistant and knowledge-update, and trails on temporal and multi-session — the
same two categories every other line of evidence has identified.

So the deficit is not finding evidence. It is two things: **context efficiency**, where the
gap is roughly 18× against Supermemory, and **synthesis**, where 97% retrieval becomes 78%
answers.

## The goal as stated is not achievable

"Superior in all aspects" cannot be delivered, and pursuing it would destroy the position
worth holding. Mem0's and Supermemory's numbers are produced with hosted infrastructure and
frontier-model extraction. Matching them on every axis means adopting a cloud dependency
and a per-ingest model dependency — the two things this product exists to avoid, and which
AD-046 already commits against.

The achievable and defensible goal:

> **Close the context-efficiency and synthesis gaps far enough that the local-first,
> auditable, zero-infrastructure position decides the choice rather than excusing it.**

---

## Substitute — multi-signal fusion instead of semantic-plus-recency

Both competitors fuse multiple retrieval signals; this project ranks on semantic similarity
and recency alone. Two independent teams converging is stronger evidence than the benchmark
contract's own unsupported nomination of lexical fusion.

**Upgrades Pass 001's C5 from deprioritised to primary.** Pass 001 deprioritised it because
retrieval is saturated at 97% Hit@10 — true for finding the right *session*, but temporal
and entity questions turn on exact tokens that dense vectors handle poorly, and
precision@10 is 0.700. SQLite ships FTS5: no new dependency, no network.

*Gate:* temporal and multi-session improve by at least three answers combined, no category
regresses, zero scope leakage.

## Combine — dual-layer retrieval, now with a reference design

Pass 001 proposed C4, a raw substrate with a derived index above it, and could not state a
falsifiable gate. **Supermemory has shipped exactly that**: hybrid retrieval over atomic
memories *plus injection of the original chunks*, so the model gets both the distilled fact
and the finer detail.

That is the architecture this project is one step from. It already has the substrate raw
and intact — the half Mem0 destroys and Supermemory has to reconstruct — plus a
review-first extraction pipeline producing atomic typed memories. What is missing is only
the retrieval policy that queries both layers and fuses without double-counting.

C4 is therefore promoted from direction to candidate, and its gate is now specifiable
because the reference design exists.

*Gate:* answer accuracy improves by at least three of sixty at equal or lower context cost,
with every returned item retaining full provenance to a source message.

## Adapt — dual timestamps, and one thing not to adapt

Supermemory extracts **two** dates per memory: the document date (when it was said) and the
event date (when the thing happened). This project records only ingestion-time source
timestamps. "I saw the dentist last Tuesday" said on the 30th is an event on the 24th, and
no amount of recency ranking recovers that.

They score 91% on temporal; this project scores 85.8% retrieval and 5/10 answers. Dual
timestamps are a small, deterministic, high-leverage addition — date extraction needs no
LLM, and dates are among the most tractable things to parse.

Explicitly **not** to adapt: Mem0's ADD-only extraction. That is their defence against the
destructive-extraction failure the local comparator measured. This project already holds a
stronger guarantee — the raw substrate is never discarded — and adopting their mitigation
would be adopting a weaker form of something it already has.

*Gate:* temporal-reasoning improves by at least three of ten, no new model dependency,
parse coverage reported honestly including failures.

## Modify — the context gap is 18×, not 2×

Supermemory adds **~720 mean tokens**, a claimed 99.4% context reduction. Mem0 runs ~6,900.
This project's measured mean answer input is **13,081 tokens**.

This is the largest and most concrete competitive gap in this document, it is measurable
today with no model, and it compounds: fewer tokens keeps smaller local models viable,
which is precisely the local-first position. Whole messages are returned where spans would
do — the comparator run found a full cake recipe occupying one of ten slots.

*Gate:* mean context bytes fall at least 60% with answer accuracy not regressing and no
answer-bearing content pruned. The no-pruning check is mandatory: pruning answer-bearing
messages is exactly how `session-diverse-v1` failed.

## Put to another use — the temporal substrate already exists here

Supermemory built **relational versioning** — tracking updates, extensions, and inferred
knowledge between memories — as a deliberate feature. Mem0 built temporal reranking toward
what is current, its single largest 2026 gain at +29.6.

This project already records, with full auditable provenance, exactly which fact superseded
which and when. It was built for correction integrity and it is **never consulted at query
time**. The same is true of the provenance DAG, built to compute deletion blast radius and
never used for retrieval.

Two competitors independently built, from scratch, a capability this project already has
and ignores. That remains the strongest structural insight across both passes.

*Gate:* temporal-reasoning improves by at least three of ten using only existing correction
and provenance records, with no new dependency.

## Eliminate — the axis where superiority is real and defensible

Mem0's and Supermemory's results require hosted infrastructure and frontier-model
extraction per ingest. Neither can offer a single inspectable SQLite file, no daemon or
listener, no cloud egress, verified hard deletion with computed blast radius, exact scope
isolation, or full provenance on every returned result.

This is not a gap to close but the position to defend and make legible. The actionable form
is measurement, not engineering: publish a per-axis comparison — quality, context cost,
infrastructure, privacy, auditability, deletion guarantees — rather than a single score
this project would lose while winning the axes that motivated it.

## Reverse — query-time synthesis, downgraded again

Pass 001's C1 proposed inverting ingest-time extraction to query time. Supermemory's result
weakens it further: they achieve 720-token contexts by doing the expensive work *once* at
ingest, then retrieving cheaply. Query-time synthesis pays a model cost on every recall and
conflicts directly with the offline-core invariant.

*Status:* retained, ranked last, below every candidate that needs no model in the query path.

---

## Revised ranking

| Rank | Candidate | Lens | Targets | Model in query path? |
| ---: | --- | --- | --- | --- |
| 1 | Corrections and provenance as temporal substrate | Put to another use | temporal 5/10, using structure already built | No |
| 2 | Span-level context minification | Modify | the 18× context gap | No |
| 3 | Dual timestamps: document date and event date | Adapt | temporal, deterministically | No |
| 4 | Multi-signal FTS5 fusion | Substitute | temporal and entity precision | No |
| 5 | Dual-layer raw-plus-derived retrieval | Combine | synthesis; now has a reference design | Ingest only |
| 6 | Query-time synthesis (Pass 001 C1) | Reverse | the 97→78 gap, expensively | Yes |

The top four require **no model in the query path**, no network, and no new dependency.
They are compatible with the local-first invariant rather than in tension with it. Ranks 1
and 3 both attack temporal reasoning by different deterministic routes and should be
contracted together so their contributions can be separated.

## What this pass does not do

It authorizes nothing. Every candidate still needs its own frozen pre-registered contract
and explicit owner authorization before a measured run. The competitor figures here are
**self-reported vendor claims that contradict one another**, not matched local
measurements, and per the benchmark contract they may not enter a comparison table as
equivalent results. Supermemory additionally discloses that its own evaluation processes
sessions rather than round-by-round, diverging from LongMemEval's methodology. The only way
to know where this project actually stands is the matched comparator run that remains
outstanding Phase 4 work.

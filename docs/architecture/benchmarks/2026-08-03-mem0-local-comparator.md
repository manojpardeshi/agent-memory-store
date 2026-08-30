# Matched-Local Mem0 Comparator — Stratified 60

Date: 2026-08-03
Status: completed; development evidence only. Not a competitive claim.

## What ran

Mem0 OSS 2.0.15 in a fully local configuration over the frozen
`longmemeval-stratified60-v1` selection, the same 60 questions the released store has
already been measured on.

| Component | Value |
| --- | --- |
| Extraction LLM | `llama3.1:8b`, digest `46e0c10c...ca666e`, M2 loopback |
| Embedder | FastEmbed `BAAI/bge-small-en-v1.5`, 384 dims — identical to the product store |
| Vector store | Qdrant local, on-disk, one collection per question |
| Machine | Apple M2 Pro, 16 GB, macOS 15.7.7 |
| Wall time | 48,652 s (13.5 h) |
| Hosted API calls | 0 |
| Paid cost | $0.00 |
| Failures | 2 malformed source sessions of ~2,856; both non-fatal |

Embedder parity is exact: the same library, model identity, and ONNX runtime on both
arms, so the comparison isolates memory architecture rather than embedding quality.

## Finding 1: provenance metrics cannot compare these architectures

The deterministic session-label diagnostic scored Mem0 at 6.7% Hit@10 — below the
~10% expected from returning the same number of distinct sessions at random. That is a
defect in the measurement, not a result.

Proof, from question `58bf7951` ("What play did I attend at the local community
theater?"):

- The gold evidence is in `haystack_sessions[29]`; index alignment verified directly.
- Mem0's top hit scored 0.858 and was substantively correct: "The user recently attended
  a play at the local community theater and was impressed by the lead actress's
  performance."
- Mem0 labelled that memory `session-30`. Session 30 is about Chinese news websites and
  contains no mention of a play or theater.

Mem0 rewrites a memory's source metadata when a later ingest call updates it, so
retrieved provenance identifies the last touching call rather than the originating
session. A raw-message store carries provenance by construction; an extractive store
destroys it by design. **Any provenance-based retrieval metric structurally favours the
former and must not be used to compare them.**

## Finding 2: the gap is extraction loss, measured provenance-free

`scripts/score_content_answer_presence.py` scores both arms through one code path on a
provenance-free lexical criterion: does the top-10 retrieved context contain the gold
answer text?

The 60 questions split by whether gold answers are quotable. `single-session-preference`,
`temporal-reasoning`, and `multi-session` gold answers are synthesised or computed
("The user would prefer responses that provide tips tailored to their slow cooker") and
appear verbatim in no source message, so no retrieval system can satisfy a lexical test
on them. Those 30 are excluded as unmeasurable for **both** arms.

On the 30 extractive-answer questions where the metric is valid:

| Arm | Answer content in top-10 |
| --- | ---: |
| llm-memory-store (raw ingestion) | **29/30 — 96.7%** |
| Mem0 OSS local (`llama3.1:8b`) | **4/30 — 13.3%** |

Per category: the store scored 10/10 single-session-user, 10/10 single-session-assistant,
9/10 knowledge-update; Mem0 scored 1, 1, and 2.

The bottleneck is ingest, not ranking. Mem0 compressed ~501 messages per question into a
mean of 72.3 memories, and the gold answer survived anywhere in the stored set for only
7/60 questions (11.7%) — close to the 13.3% top-10 figure, so the missing answers were
never stored rather than ranked low. Manual confirmation: zero of the 135 memories for
`58bf7951` contain "Menagerie". Extraction preserved that a play was attended and
discarded which play.

## Declared bias and limits

- The lexical criterion **favours the store**. It returns verbatim source text; Mem0
  returns paraphrase, which can be semantically correct yet fail a lexical test. The
  corroborating extraction-recall measurement and manual inspection indicate the gap is
  larger than that bias explains, but the number is a floor, not a judged score.
- The 30 paraphrastic questions remain unmeasured. An LLM-judge pass is required.
- **This is Mem0 OSS driven by `llama3.1:8b`, not Mem0's hosted platform**, which uses
  frontier models for extraction. Matched-local forces a local extractor and therefore
  measures Mem0 outside its design envelope. Nothing here describes Mem0 as deployed.
- Latency and footprint are not comparable: this ran on the M2 Pro while the store's
  baseline was measured on the M1. Recall, MRR, and context-token metrics are
  machine-independent and unaffected.
- Mem0 OSS enables PostHog telemetry by default. The runner disables it before import.
  Any future run must keep that switch set.

## Interpretation

Extraction-based memory carries a hard dependency on extraction-LLM quality. Under a
local constraint that dependency is not satisfied, and information is destroyed at ingest
where no retrieval improvement can recover it. This reproduces, in a second independent
system, the wall recorded in AD-038 and AD-039: every locally measured extractor failed
its automation gate.

The defensible claim is architectural — raw ingestion has no such dependency — not that
this project outperforms Mem0. Establishing anything competitive requires the hosted
comparator and a judged answer run.

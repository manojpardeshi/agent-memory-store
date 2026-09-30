# Competitive Benchmark Contract — Hosted Comparator Amendment

Date: 2026-09-30
Status: **proposed, pending owner acceptance.** Amends `competitive-benchmark-contract.md`.

## Why

The contract requires "matched local comparator configurations on the same machine" and bars
managed-platform results from the comparison table as equivalent. MemoryBench's built-in Mem0
and Supermemory providers are hosted API clients, so that requirement cannot be met with them.
The matched-local substitute, Mem0 OSS on `llama3.1:8b`, measured an architecture outside its
design envelope and supports only one claim: extraction-based memory degrades under a local-model
constraint (`benchmarks/2026-08-03-mem0-local-comparator.md`).

This amendment adds a second, separately labelled track rather than relaxing the first.

## Track H — hosted comparator, own measurement

A hosted provider's result is this project's **own measurement of that provider's service**, run
on the same questions and the same frozen answer protocol as the store. It is neither a matched
local result nor the provider's published claim, and it is never reported as either.

| Fixed element | Value |
| --- | --- |
| Questions | the 180 development questions of `longmemeval-kimi-development-v1.json` |
| Retrieval | MemoryBench `118209a7...`, ingest, indexing, search only; depth 10 |
| Answer and judge | exact `kimi-k3` single-arm protocol of `2026-09-27-kimi-question-date-baseline180.md`, dates supplied |
| Store baseline for comparison | 134/180 from that report |
| Primary metric | judged answer accuracy. Session-label retrieval metrics are **not** used: the local comparator showed Mem0 rewrites source metadata on update, which makes provenance-based metrics structurally unfair to it. |
| Design-blind set | the 120 questions outside the stratified sixty stay aggregate-only |

## Mandatory disclosures for any Track H report

- Service tier and date of the run. For Mem0: the Hobby tier, which excludes the graph memory and
  memory consolidation that Pro includes; the harness sets `enable_graph: false` regardless.
- That the provider's extraction model is hosted and undisclosed.
- That MemoryBench's Mem0 provider writes `custom_instructions` to the Mem0 project on
  initialisation, and the text it writes.
- Ingestion granularity: one request per session, `async_mode`, completion confirmed by polling
  event status.
- Indexing failures, retries, and any sessions that did not index.
- That Supermemory authors MemoryBench.
- That the Mem0 JS client's default PostHog telemetry was disabled with `MEM0_TELEMETRY=false`.
- That retrieval ran on the M2 Pro and answering on the M1. Latency figures from Track H are
  therefore not comparable with the store's, and none are reported.
- That the answering model sees each system's own result objects, serialised identically.

## Budget and quota

Track H consumes provider quota, not project budget, for retrieval. The Mem0 Hobby tier allows
10,000 add requests and 1,000 retrieval requests a month. The 180 questions need 8,590 add
requests and 180 searches. Ingestion checkpoints per session, so retries resend only failed
sessions. A one-question smoke run of about 48 adds precedes the full run to validate plumbing
and result shape.

Answering and judging are paid through the existing kimi ledger under a stated ceiling.

## What a Track H result may support

A statement of the form *"on these 180 LongMemEval-S development questions, under this
project's answer protocol, the store scored X and the provider's Y-tier service scored Z."*

It may not support a general superiority claim, a comparison with the provider's published
figures, or any statement about tiers or configurations not measured.

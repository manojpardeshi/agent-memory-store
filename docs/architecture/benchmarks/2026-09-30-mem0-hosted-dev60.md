# Track H — Hosted Mem0 vs the Store, Stratified Sixty

Date: 2026-09-30
Status: completed. **This project's own measurement of Mem0's hosted Hobby-tier service** under
Track H of `../hosted-comparator-amendment.md`, run under owner-delegated authority before the
amendment was accepted on 2026-10-09. Not a comparison with Mem0's published figures.
Answers: `demo-artifacts/kimi-mem0-hosted-dev60.json`, SHA-256 `dd6279eaafef6e79e882a351810b49f7a95f4ee8d79daa4fcd4897470036b90b`
Retrieval checkpoint: `demo-artifacts/memorybench/upstream/data/runs/mem0-hosted-dev60-v1/checkpoint.json`, SHA-256 `84056908dec5de557a2c0557b2aa18d7275baa6c9c20638e1bc560c56ec139aa`

## Result

Identical 60 questions, identical kimi-k3 answer and three-vote judge protocol, dates supplied. The
store column is the 2026-09-27 180-question baseline restricted to these sixty.

| Category | Store | Mem0 (Hobby) |
| --- | ---: | ---: |
| single-session-assistant | **10/10** | 2/10 |
| single-session-user | **10/10** | 6/10 |
| knowledge-update | **9/10** | 7/10 |
| single-session-preference | **7/10** | 5/10 |
| multi-session | 3/10 | **4/10** |
| temporal-reasoning | 5/10 | **7/10** |
| **Total** | **44/60** | **31/60** |

Paired outcomes: both correct 25, store only 19, Mem0 only 6, neither 10. Exact two-sided sign test
on the 25 discordant pairs: **p = 0.015**.

Kimi answering cost: $1.315 for Mem0's sixty against about $2.16 for the store's, because Mem0
returns ten short extracted memories rather than raw messages.

## Reading it

- **The gap is concentrated where extraction discards content.** Single-session-assistant questions
  ask what the assistant said. Mem0's extraction records facts about the user and largely drops
  assistant-authored detail, scoring 2/10 where raw retention scores 10/10. Excluding that category,
  the totals are 34/50 against 29/50.
- **Mem0 leads on temporal (+2) and multi-session (+1).** Ten questions per category cannot establish
  either, but the temporal direction agrees with the hypothesis behind `event-date-annotation-v1`:
  Mem0 stores a dated fact per memory, where the store hands the answerer raw text and a session date.
- **This does not reconcile with Mem0's published 94.4%.** Different tier, configuration, evaluator,
  and methodology. Nothing here supports a statement about Mem0 as deployed on other tiers.

## Mandatory Track H disclosures

- **Tier:** Hobby (free). Graph memory and memory consolidation, Pro features, were not available;
  the harness also sets `enable_graph: false`.
- **Extraction model:** hosted and undisclosed by Mem0.
- **Harness patches**, both in `evaluation/memorybench/`: `mem0-session-timestamp.patch` passes each
  session's date as Mem0's add timestamp (unpatched, memories were dated at ingestion time, in 2026);
  `mem0-rate-limit-retry.patch` retries only Mem0's explicit rate-limit rejection.
- **Project instructions:** MemoryBench writes its `custom_instructions` to the Mem0 project on
  initialisation.
- **Ingestion:** one request per session, `async_mode`, completion confirmed by polling event status.
  2,800 events confirmed succeeded, 0 failed. About 80 further sessions were accepted during the
  first, rate-limited attempt and processed by Mem0, but their event ids were not carried into the
  resumed run's tracking, so their completion was not individually confirmed before search. They
  were submitted about twenty minutes before search ran.
- **Telemetry:** Mem0 client telemetry disabled with `MEM0_TELEMETRY=false`.
- **Machines:** retrieval on the M2 Pro, answering on the M1. No latency comparison is made.
- **Harness authorship:** Supermemory authors MemoryBench.
- **Answer context:** each system's own result objects, serialised identically into the same prompt.
- **Sample:** sixty questions, one run. Measured identical-protocol churn is about one answer per
  sixty; the 13-answer total gap and p = 0.015 are well outside it.

The remaining 120 development questions are running as batch B and will be reported in aggregate
only, under the design-blind rule.

## Correction, same day

The temporal and multi-session leads above did not hold at scale. On 163 questions the store leads in every category, including temporal 30/44 against 24/44 and multi-session 23/44 against 19/44. See `2026-09-30-mem0-hosted-dev163.md`.

# Unattended Session Report — 2026-09-30

Branch: `scamper-candidate-generation`. `main` untouched. Nothing pushed to Codeberg.
Private backup of every branch and all evidence: `~/backups/agent-memory-store/` on the M2.

## Headline

1. **Your store beats hosted Mem0 by about 23 points under an identical protocol.** All 180
   development questions: store 134 (74.4%), Mem0 Hobby tier 93 (51.7%), p = 0.000003. The store
   leads in every category.
2. **Both candidates tested today failed at the answer level.** More session context and resolved
   event dates each left multi-session and temporal answers where they were. That rules out the two
   explanations the project had pursued since August.
3. **`recall` makes about 20× fewer database queries and is up to 65% faster, with provably identical
   results.** There is also a new metadata-lookup API and batched listing.
4. **Kimi ran out of balance at 14:00.** After the $20 recharge, the last 17 Mem0 answers were completed.

## Hosted Mem0 vs the store (all 180)

| Category | Store | Mem0 (Hobby) |
| --- | ---: | ---: |
| single-session-assistant | 22/22 | 3/22 |
| single-session-user | 25/26 | 17/26 |
| knowledge-update | 24/29 | 21/29 |
| temporal-reasoning | 30/44 | 24/44 |
| multi-session | 23/44 | 19/44 |
| single-session-preference | 10/15 | 9/15 |
| **Total** | **134/180** | **93/180** |

The largest gaps are in what the assistant said and in user facts that Mem0's extraction discards.
This measures Mem0's free tier with three disclosed harness patches. It is not a statement about
Mem0's published numbers or its paid tiers. Details: `docs/architecture/benchmarks/2026-09-30-mem0-hosted-dev180.md`.

**A correction I made during the session.** On the first 60 questions, Mem0 led on temporal (7 vs 5),
and I briefly used that to suggest a direction for the next candidate. Over all 44 temporal questions
the store leads, 30 vs 24. The early lead was noise, and I withdrew the inference in the documents
with a dated correction rather than editing it away.

## Candidates

| Candidate | Stage 1 (free) | Answers (paid) | Verdict |
| --- | --- | --- | --- |
| within-session-expansion v1.2 | 11 of 12 gates; coverage 53.8% vs 55% | diagnostic 134/180, multi+temporal +1 | **closed, line closed** |
| event-date annotation v1 | 8 of 8 gates | 137/180, temporal 29/44 vs bar 34 | **closed** |

**What this establishes.** Within-session coverage *tracks* answer accuracy but does not *drive* it.
Raising it from 36% to 54% at equal cost changed nothing. Resolved dates are not what temporal
questions are missing either. The remaining multi-session and temporal failures look like the answering
model's synthesis across evidence it already has. That is the next hypothesis, and it needs its own contract.

## Decisions I made under your delegated authority

Each is in a commit and, where it touches evidence, in a document written before results existed.

1. **Froze two contracts myself** (v1.2 and event-date) before measuring either.
2. **Closed v1.2 at Stage 1 on a 1.2-point miss** rather than relax the gate. I recorded that the gate was
   miscalibrated but did not use that to rescue it.
3. **Ran a pre-registered answer diagnostic on the closed v1.2.** I relaunched it once with a higher spending cap
   after 8 questions, because the first cap would have cut it short. Nothing else changed.
4. **Ran hosted Mem0 under the proposed Track H amendment**, which still needs your acceptance.
5. **Patched the Mem0 harness three times**, all disclosed: session timestamps, rate-limit retries, and
   dropping blank messages.
6. **Backed up every branch and all evidence to the M2.**

## Product and tooling changes on the branch

All are tested and listed in `CHANGELOG.md` under Unreleased.

| Change | Effect |
| --- | --- |
| `recall` batching | ~123 → 6 SQL statements at limit 10; ~603 → 6 at limit 50. Median latency 1.05 → 0.52 ms and 4.30 → 1.52 ms on 3,000 memories. Identical results across 360 checked combinations. |
| `list_memories` / export batching | 2N+1 queries → constant, identical output. |
| `find_by_metadata(scope, filters)` | New: exact-scope metadata lookup in SQLite. Hides superseded and expired memories by default. |
| `temporal.resolve_event_dates` | New, experimental, model-free relative-date resolver. |
| Kimi runner | Retries only explicit HTTP 429. The paired runner gets opt-in question dates. |
| Hosted comparator | Runs unattended on the M2, survives rate limits, never reports false success. |

## Paid spend this session (kimi-k3)

| Run | Cost |
| --- | ---: |
| v1.2 diagnostic, abandoned first launch | $0.39 |
| v1.2 diagnostic | $6.72 |
| event-date Stage 2 | $6.48 |
| Mem0 answers, first 60 | $1.32 |
| Mem0 answers, other 120 (including the 17 after recharge) | $2.56 |
| **Total** | **$17.48** |

Mem0 retrieval cost nothing. It used 8,827 of the free tier's 10,000 monthly add requests.

## What needs you

1. **Review, then accept, amend, or reject** the Track H amendment and the two contracts I froze.
2. **Supermemory is still unmeasured.** It needs a Supermemory API key.
3. **Push to Codeberg** when you are satisfied. About sixty commits exist only on this Mac and in the M2 backup.

## Known follow-up

Kimi reports an exhausted balance as HTTP 429, the same code as a rate limit. The runner therefore
retried for about 2.5 minutes before stopping. It should read the error type and stop immediately on
`exceeded_current_quota_error`.

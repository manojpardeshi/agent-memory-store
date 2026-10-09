# Gated Hybrid v1 — Default-Flip Decision

Date: 2026-10-09
Status: **failed; the default stays vector.** Measured once, after the rule was frozen. Free and local.
Frozen choice and rule: `evaluation/memorybench/gated-hybrid-v1-frozen.json` (commit 7061f16, before retrieval_v3 existed).
Deciding corpus: `evaluation/retrieval_v3.json` (frozen in 1830d4b before any evaluation; SHA-256 `7ed937fb3c4ed3e90052eab2c738af3542dbc55df1669865af80671b0a573c79`).
Harness: `scripts/prototype_gated_hybrid.py --variants vector rrf idf_gate_0.02_floor2`.

## Candidate

Hybrid recall whose keyword ranking keeps only memories containing a rare query term: one found
in at most max(2, 2% of reachable) memories. It was tuned on the stratified sixty, retrieval_v1,
and retrieval_v2, where it kept fusion's complete-evidence gain (47/57), raised evidence recall
to 0.898, and passed retrieval_v2 (MRR 0.856) where plain fusion failed.

## The deciding corpus

retrieval_v3 was written by two independent authors working from a written specification. Neither
saw repository code, the other's half, or the candidate. It covers a wildlife photographer's
assistant, a household-renovation assistant, and a shared community-garden pool. Half the
questions repeat one distinctive word from their memory (anchor). Half share no content word with
it (paraphrase). The builder enforces every mechanical rule. Each author reviewed the other's
half, and both independently found the same double answer in the shared pool, which was fixed
before freezing. The reviews are in `evaluation/retrieval_v3_authoring/`.

## Result (certified default relevance filter for synthetic suites)

| Measure | Vector | Plain fusion | Gated (candidate) | Bar |
| --- | ---: | ---: | ---: | --- |
| retrieval_v3 MRR | **0.867** | 0.759 | 0.782 | ≥ 0.857 — **fail** |
| — anchor questions | 0.931 | 0.983 | 0.983 | reported |
| — paraphrase questions | **0.804** | 0.534 | 0.581 | reported |
| retrieval_v3 Recall@5 | 1.000 | 0.967 | 1.000 | ≥ 0.983 — pass |
| retrieval_v3 distractor leak | 0.050 | 0.050 | 0.050 | ≤ 0.067 — pass |
| retrieval_v3 absolute gate | pass | fail | **fail** (MRR < 0.85) | must pass when vector does |
| retrieval_v1 gate | pass | pass | pass | pass |
| retrieval_v2 gate | pass | fail | pass | pass (not independent) |
| Held-out 120 complete evidence (117 scored) | 80 | 91 | **78** | ≥ 84 — **fail** |
| Held-out evidence recall | 0.777 | 0.836 | 0.765 | reported |

Held-out complete evidence by category, vector / plain fusion / gated: knowledge-update 13 / 17 /
16; multi-session 17 / 21 / **13**; temporal-reasoning 21 / 24 / 20; the other three categories
were identical across arms. Two of the five frozen conditions fail, so the latency condition was
not measured.

## Reading

- **The gate overfit.** Its tuning-set evidence recall (0.898, above plain fusion) did not carry
  over: held out, it fell below vector alone. Multi-session lost four complete-evidence
  questions, because the evidence for those questions is reached through common words the gate
  removes.
- **Keyword fusion helps anchor questions and hurts paraphrase questions, at any gating tried.**
  On the independent corpus, adding the keyword ranking lifted anchor MRR from 0.93 to 0.98 and
  cut paraphrase MRR from 0.80 to 0.53–0.58. That is a structural trade-off, not a tuning detail:
  when the answer shares no word with the question, every keyword match is a wrong memory pushed
  above a right one.
- **Plain fusion remains the best option where exact-word recall dominates** (held-out
  LongMemEval +11). It stays available as the explicit opt-in `retrieval="hybrid"`, and its
  documentation now carries the retrieval_v3 paraphrase cost.

## Decision

Per the rule frozen in advance, the product default stays `vector`, and opt-in hybrid is
unchanged. The gated variant does not ship. A future default needs a mechanism that can tell when
keyword evidence is trustworthy for a given query without lowering paraphrase recall. It must be
judged on retrieval_v3, now itself observed, plus a fresh independently authored corpus.

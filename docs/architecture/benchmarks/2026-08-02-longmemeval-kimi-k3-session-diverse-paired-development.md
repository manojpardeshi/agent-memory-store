# LongMemEval-S paired Kimi development result

Date: 2026-08-02  
Status: final failed after blind human adjudication  
Split: development only; sealed validation and competitor reserve unopened

## Decision

Do not advance or enable `session-diverse-v1`. The candidate improved the earlier deterministic
answer-session retrieval diagnostic, but it reduced matched answer quality in this 60-question
paired run. The completed blind human audit strengthened the result to 47/60 baseline versus 41/60
candidate. It remains default-off and is rejected from sealed validation.

## Result

| Category | Released baseline | Session-diverse v1 | Delta |
| --- | ---: | ---: | ---: |
| Knowledge update | 9/10 | 8/10 | -1 |
| Multi-session | 4/10 | 4/10 | 0 |
| Single-session assistant | 10/10 | 10/10 | 0 |
| Single-session preference | 7/10 | 7/10 | 0 |
| Single-session user | 10/10 | 7/10 | -3 |
| Temporal reasoning | 5/10 | 4/10 | -1 |
| **Overall** | **45/60 (75.0%)** | **40/60 (66.7%)** | **-5 (-8.3 pp)** |

The paired outcomes were 37 both correct, 12 both incorrect, 8 baseline-only correct, and 3
candidate-only correct. The candidate failed minimum accuracy, overall non-inferiority, combined
target-category gain, untargeted-category non-inferiority, and per-category non-inferiority.

## Context, judge, and cost controls

| Measure | Released baseline | Session-diverse v1 |
| --- | ---: | ---: |
| Mean context JSON bytes | 30,634.8 | 25,943.3 |
| p95 context JSON bytes | 43,984 | 36,259 |
| Answer-call cost | $1.716024 | $1.549107 |
| Judge-vote unanimity | 95.0% | 100.0% |

The smaller context and lower answer-call cost did not compensate for the answer-quality loss.
Total run cost, including all answer and judge calls, was **$4.147215**, below the frozen $5 ceiling.
Exact response-model identity, context limits, judge consistency, call completion, and cost gates
passed.

One judge request received HTTP 429 before any response or usage record. The runner logged the
event and reissued the identical request once; the recovery was charged $0.00. There are no
unreconciled calls and no duplicate result was counted.

## Human adjudication

The frozen protocol's blind human audit is complete: 13 unique questions and 3 blinded reliability
duplicates. Intrarater agreement was 100% and human–judge agreement was 88.46%, passing both human
gates. Authoritative substitution produced 47/60 baseline versus 41/60 candidate, with 1 candidate
win, 7 losses, and 52 ties. All five answer-quality gates remained failed.

- Audit packet: `demo-artifacts/memorybench/kimi-k3-session-diverse-paired-human-audit-v1.json`
- Machine evidence: `docs/architecture/benchmarks/2026-08-02-longmemeval-kimi-k3-session-diverse-paired-development.json`
- Frozen contract: `evaluation/memorybench/kimi-paired-answer-development-gates-v1.json`
- Raw run: `demo-artifacts/memorybench/kimi-k3-session-diverse-paired-development60-v1.json`

No sealed-validation or reserve question was opened. No second candidate may be tuned on this
now-observed development result without a newly disclosed, frozen protocol.

# LongMemEval-S paired Kimi human adjudication

Date: 2026-08-02  
Status: completed; candidate failed  
Split: development only; sealed validation and competitor reserve unopened

## Final decision

Reject `session-diverse-v1` and end this candidate. The blind human audit confirmed that its
retrieval-only gains do not translate to matched answer quality. The policy remains default-off and
must not advance to sealed validation or shipment.

## Human-adjudicated result

| Measure | Released baseline | Session-diverse v1 |
| --- | ---: | ---: |
| Correct answers | 47/60 (78.3%) | 41/60 (68.3%) |
| Knowledge update | 10/10 | 8/10 |
| Multi-session | 4/10 | 4/10 |
| Single-session assistant | 10/10 | 10/10 |
| Single-session preference | 8/10 | 8/10 |
| Single-session user | 10/10 | 7/10 |
| Temporal reasoning | 5/10 | 4/10 |

The human-substituted paired outcomes were 1 candidate win, 7 candidate losses, and 52 ties. The
candidate's final accuracy delta was -10.0 percentage points.

## Audit validity

- Unique audited questions: 13.
- Blinded reliability duplicates: 3.
- Intrarater agreement: 100% (required at least 90%).
- Human–judge agreement: 88.46% (required at least 75%).
- Both human-quality gates passed.
- Packet, key, machine evidence, raw run, checkpoint, and frozen-contract hashes were verified.

After authoritative human substitution, the candidate still failed minimum candidate accuracy,
overall non-inferiority, target-category gain, untargeted-category non-inferiority, and per-category
non-inferiority. Exact model, context, cost, completion, and judge-consistency controls passed.

## Consequence

The completed audit resolves the v1 prerequisite in the blocked v2 draft. It does not itself freeze
or authorize v2. The fresh-corpus baseline input, explicit freeze review, local gate execution, and
separate authorization for any paid run remain required. Sealed validation and reserve remain
unopened.

- Adjudicated evidence: `docs/architecture/benchmarks/2026-08-02-longmemeval-kimi-k3-session-diverse-paired-human-audit.json`
- Diagnostic explanation: `docs/architecture/benchmarks/2026-08-02-longmemeval-kimi-k3-session-diverse-discordance-diagnostic.md`
- Frozen v1 contract: `evaluation/memorybench/kimi-paired-answer-development-gates-v1.json`

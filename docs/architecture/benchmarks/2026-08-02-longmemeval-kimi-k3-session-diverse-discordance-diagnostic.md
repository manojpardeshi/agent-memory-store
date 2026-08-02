# Kimi Paired Session-Diverse Discordance Diagnostic

Date: 2026-08-02  
Status: completed development-only, label-aware, non-tuning diagnostic

## Finding

The session-diverse policy increased session coverage but frequently removed the decisive message inside a retained answer session. Session-level recall therefore masked fact-level evidence loss.

## Aggregate evidence

- Discordant questions: 11 (8 baseline wins, 3 candidate wins).
- Distinct sessions: 30 to 69 (3.55 more per question).
- Labeled answer-session messages: 90 to 37; 54 were removed and 1 added.
- Full answer-session coverage: 11/11 baseline and 11/11 candidate.
- Context bytes: 354,988 to 273,988 (77.2%); candidate was smaller on 9/11 questions.
- Fully unanimous three-vote judge sets in both arms: 10/11.

## Causal patterns

- `direct-answer-bearing-message-pruned`: 7
- `direct-useful-message-added`: 1
- `salience-or-wording-boundary`: 2
- `unsupported-inference-after-context-perturbation`: 1

## Per-question evidence

| Question | Category | Outcome | Sessions B→C | Labeled messages B→C | Bytes ratio | Diagnosis |
| --- | --- | --- | ---: | ---: | ---: | --- |
| `caf03d32` | single-session-preference | baseline-win | 1→7 | 10→2 | 0.994 | `direct-answer-bearing-message-pruned` |
| `1da05512` | single-session-preference | candidate-win | 1→7 | 10→2 | 0.548 | `salience-or-wording-boundary` |
| `e01b8e2f` | single-session-user | baseline-win | 2→6 | 4→2 | 0.982 | `direct-answer-bearing-message-pruned` |
| `c5e8278d` | single-session-user | baseline-win | 1→7 | 10→2 | 0.514 | `direct-answer-bearing-message-pruned` |
| `bc8a6e93` | single-session-user | baseline-win | 5→6 | 5→2 | 1.049 | `direct-answer-bearing-message-pruned` |
| `3fdac837` | multi-session | candidate-win | 4→5 | 7→4 | 0.735 | `direct-useful-message-added` |
| `b5ef892d` | multi-session | baseline-win | 4→6 | 9→6 | 1.013 | `direct-answer-bearing-message-pruned` |
| `gpt4_93159ced_abs` | temporal-reasoning | baseline-win | 6→8 | 5→3 | 0.730 | `unsupported-inference-after-context-perturbation` |
| `c7dc5443` | knowledge-update | baseline-win | 2→7 | 10→4 | 0.603 | `direct-answer-bearing-message-pruned` |
| `a2f3aa27` | knowledge-update | candidate-win | 2→4 | 10→6 | 0.686 | `salience-or-wording-boundary` |
| `10e09553` | knowledge-update | baseline-win | 2→6 | 10→4 | 0.832 | `direct-answer-bearing-message-pruned` |

## Reproducibility and scope

The analyzer verifies the frozen contract and development source hashes, derives each arm label by two-of-three judge majority, diffs retrieved messages by `memory_id`, and maps benchmark answer sessions to checkpoint session IDs by their position in `haystack_session_ids`. The diagnostic-label file covers exactly the computed discordant set and explicitly forbids tuning.

The script accepts no human-audit key, validation manifest, or reserve manifest input. It does not authorize tuning, opening sealed validation, shipment, or external performance claims.

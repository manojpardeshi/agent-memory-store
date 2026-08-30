# Question-Date Re-measurement — kimi-k3 Baseline, Stratified 60

Date: 2026-08-03
Status: completed. **Negative result: the fix works mechanically and changes the score by
zero.**
Cost: $2.162986 of an authorized $3.00 ceiling. Zero unresolved dates.

## Design

A single-arm re-run of the released store's answer quality with the question date supplied,
against the baseline arm of `kimi-k3-session-diverse-paired-development60-v1`, which covered
the **identical 60 questions** with the **identical evaluator, prompts, model, efforts, and
three-vote majority rule** and no question date. Verified: the paired selection overlaps the
stratified sixty at 60 of 60. Exactly one variable differs.

## Result

| Category | Without dates | With dates |
| --- | ---: | ---: |
| single-session-user | 10/10 | 10/10 |
| single-session-assistant | 10/10 | 10/10 |
| knowledge-update | 9/10 | 9/10 |
| single-session-preference | 7/10 | 8/10 |
| multi-session | 4/10 | 3/10 |
| temporal-reasoning | 5/10 | 5/10 |
| **Total** | **45/60** | **45/60** |

## The mechanism works; the score does not move

On `8077ef71` the fix did precisely what was predicted. Without a date the answerer said it
"can't compute a different day count." With `2022/04/04` supplied it answered:

> "You attended the networking event on March 9, 2022 — 26 days ago."

Gold: 26 days. Correct.

Four labels changed in total:

| Question | Change | Category | Attribution |
| --- | --- | --- | --- |
| `8077ef71` | incorrect → correct | temporal | **Causal.** Arithmetic became possible. |
| `gpt4_93159ced_abs` | correct → incorrect | temporal | **Plausibly causal, adverse.** |
| `1da05512` | incorrect → correct | preference | No date mechanism; likely nondeterminism. |
| `7024f17c` | correct → incorrect | multi-session | No date mechanism; likely nondeterminism. |

`gpt4_93159ced_abs` is an abstention case whose gold answer is "the information provided is
not enough." Without a reference date the answerer declined and scored correct. With one it
computed confidently — "about 4 years and 3 months" — and scored incorrect. **Supplying the
date induced over-answering on a question whose correct response was abstention.** The fix
therefore carries a real counter-effect, not merely noise.

## Corrections to earlier claims

Two statements in `2026-08-03-question-date-harness-defect.md` are now falsified by
measurement and are corrected here rather than edited away:

1. "Roughly two of five temporal failures are attributable ... would move the stratified
   sixty from 47/60 to about 49/60." **Wrong.** One temporal question recovered, one
   regressed, and the total did not move.
2. "Every answer-quality figure produced so far ... is a **floor**." **Wrong.** The prior
   figures were accurate. The defect was real, and its effect on scores was approximately
   nil.

The defect was still worth fixing: a prompt that silently omits a field the benchmark
supplies is a correctness problem regardless of its score impact, and the answerer's
declining behaviour was masking it.

## Measurement noise, now quantified

Two of four flips have no mechanism connecting them to the changed variable. At n=60 with a
three-vote majority over a non-deterministic answerer and judge, roughly **±2 questions move
between identical-protocol runs**.

This independently confirms the reasoning that closed the context-bundling hypothesis
(AD-053). That closure argued a candidate with a one-to-three answer ceiling could not be
distinguished from noise at this sample size. This run measures that noise floor directly
and finds it in the same range. The abandonment criterion was correctly calibrated.

It also constrains every future gate: **no candidate at this sample size may be promoted on
a margin of two or three answers.** Gates must either demand larger effects or move to a
larger sample.

## Standing conclusion

Temporal reasoning remains 5/10 and multi-session 3/10. The dominant failure is unchanged
and is not an artifact of the harness. Retrieval finds the evidence; synthesis does not use
it. Candidate selection should proceed from that, with gates sized above the measured noise
floor.

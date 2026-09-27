# kimi-k3 Baseline — All 180 Development Questions, Dates Supplied

Date: 2026-09-27
Status: completed. Development evidence only; not a competitive claim.
Cost: $6.483568 of a $9.00 ceiling. Zero unresolved question dates. Judge unanimity 98.3%.
Report: `demo-artifacts/kimi-question-date-baseline180.json`, SHA-256 `3ef03236b4d533ce5bd662e7c1b113308b87e892fee70d4c54f6f530eef4e19c`

## Design

The single-arm runner and frozen protocol from
`2026-08-03-kimi-question-date-baseline60.md`, unchanged except for experiment identity and
selection: all 180 development questions, fresh answers for every one, including the sixty
already measured. The 120 questions outside the stratified sixty are recorded in the report as
**design-blind**: they may be aggregated, as below, but no per-question answer or label from them
may be read to design or tune a candidate.

## Result

| Category | All 180 | Stratified 60 | Design-blind 120 |
| --- | ---: | ---: | ---: |
| single-session-assistant | 22/22 (100%) | 10/10 | 12/12 |
| single-session-user | 25/26 (96%) | 10/10 | 15/16 |
| knowledge-update | 24/29 (83%) | 9/10 | 15/19 |
| temporal-reasoning | 30/44 (68%) | 5/10 | 25/34 |
| single-session-preference | 10/15 (67%) | 7/10 | 3/5 |
| multi-session | 23/44 (52%) | 3/10 | 20/34 |
| **Total** | **134/180 (74.4%)** | **44/60** | **90/120** |

## Correction 1 — the stratified sixty overstated the two worst categories

Every diagnosis since August cited multi-session at 3/10 and temporal at 5/10. At 44 questions each
the rates are **52% and 68%**, not 30% and 50%. Ten questions per category carries a binomial
standard error near fifteen points, and the stratified sixty takes the first ten of each category in
loaded order rather than a random ten.

The **ordering** survives: multi-session is still clearly worst, and the within-session coverage
diagnosis holds at 180, where Stage 1 measured multi-session and temporal coverage lowest at 29.3%
and 31.5%. The **magnitude** was overstated. Headroom is 21 wrong multi-session answers and 14 wrong
temporal answers across 88 questions: large in absolute terms, but the category is roughly half
right, not two-thirds wrong.

Temporal and preference are now statistically indistinguishable at this sample size; preference has
only 15 questions.

## Correction 2 — measurement noise is smaller than recorded

`2026-08-03-kimi-question-date-baseline60.md` recorded roughly ±2 answers moving between runs at
n=60, from four label changes of which two lacked a mechanism. That comparison changed a variable,
the question date, so it did not measure noise alone.

This run repeats the stratified sixty under an **identical** protocol. One label changed out of
sixty: 45/60 became 44/60. A single repeat is one data point, but it indicates identical-protocol
churn of about one answer per sixty, not two. Across 180 that implies about three flips and a
standard deviation of roughly two answers on a net total.

Consequences:

- The AD-053 closure stands on its other ground: the session-density ceiling was computed from the
  paired run's win/loss counts, not from noise alone.
- Gates should be sized on **180**, not 60. On 180, a net improvement of five answers overall, or
  four within multi-session plus temporal, is about two and a half standard deviations of churn.
- The two unexplained flips in the dated-versus-undated comparison were more likely effects of the
  date than noise. That comparison's net-zero conclusion is unchanged.

## What this is the baseline for

Any within-session-expansion successor's paid stage should compare against this report on the full
180, with gates restated in these terms. The design-blind rule means that successor's design may
use the stratified sixty's individual failures and the aggregates above, and nothing per-question
from the other 120.

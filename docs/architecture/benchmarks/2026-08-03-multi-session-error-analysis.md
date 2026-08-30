# Error Analysis — Multi-Session and the Within-Session Coverage Gap

Date: 2026-08-03
Status: diagnosis complete. API-free, from data already on disk. No candidate authorized.
Satisfies the written-diagnosis entry condition for roadmap Phase 5.

## Question

Multi-session scores 3/10 and temporal 5/10 while session-level retrieval reports 97.0%
Hit@10. Where is the loss?

## Method

For the ten multi-session questions in the stratified sixty, the required answer sessions
were compared against the sessions actually represented in the top-ten context, then the
four failures with complete session coverage were read individually. The finding was then
quantified across all sixty questions.

## Result 1: complete coverage does not produce correct answers

| Coverage of required sessions | Questions | Correct |
| --- | ---: | ---: |
| Complete — every required session in top ten | 6 | **2** |
| Partial | 4 | 1 |

Four multi-session questions failed **with every required session present**. That is not a
retrieval-recall failure by the project's own metric.

## Result 2: the four failures are aggregation, and the components are missing

All four require composing values across sessions. Two state the problem explicitly:

- `3fdac837` — "total days in Japan and Chicago", gold 11 days. Answer: *"I don't know. The
  context gives Japan as April 15–22 (8 days inclusive), but **no Chicago trip duration is
  provided**."*
- `f0e564bc` — "total spent on the handbag and skincare", gold $1,300. Answer: *"I don't
  know — the context lists $500 spent on high-end skincare products, but **no amount for the
  designer handbag**."*

The answerer found one component and reported the other missing. It was right.

## Result 3: the session was retrieved; the answer-bearing message was not

| Question | Required session | Session size | Messages retrieved |
| --- | ---: | ---: | ---: |
| `3fdac837` | 16 (holds the Chicago content) | 12 messages | **1** |
| `f0e564bc` | 11 (holds the handbag content) | 12 messages | **3** |

A session counts as retrieved when **any one** of its messages appears. Session 16 was
"covered" by 1 of its 12 messages, and the duration fact was in one of the other eleven.

Across all sixty questions, for every answer session that *was* retrieved, the share of its
messages reaching the context is:

- **mean 38.0%, median 33.3%**
- 8% of retrieved answer sessions are represented by a single message

## Result 4: within-session coverage predicts accuracy; session-level recall does not

| Category | Within-session coverage | Answers |
| --- | ---: | ---: |
| single-session-assistant | **63.6%** | 10/10 |
| single-session-user | 43.0% | 10/10 |
| knowledge-update | 39.2% | 9/10 |
| single-session-preference | 38.9% | 8/10 |
| multi-session | **29.1%** | 3/10 |
| temporal-reasoning | **28.8%** | 5/10 |

The ordering is near-monotonic: the best-performing category has more than twice the
within-session coverage of the two worst. Session-level Hit@10 sits between 93% and 100%
across every category and therefore discriminates nothing.

**The project has been steering by a metric that cannot see its dominant failure.**

## Consequences

**The retrieval metric is at the wrong granularity.** The deterministic session-label
diagnostic — including the headline 97.0% Hit@10 and 92.1% answer-session recall@10 — credits
full marks for retrieving one message out of twelve. It is not wrong, but it measures
something that is not the constraint. An evidence-level or message-level metric is required
before any further retrieval candidate is judged.

**This explains why `session-diverse-v1` failed and why it failed the way it did.** That
candidate capped each provenance session at two messages to broaden session coverage. Under
this analysis it reduced within-session coverage — already the binding constraint — in
exchange for session breadth that was not scarce. AD-052 recorded that seven of eight losses
"pruned the direct answer-bearing message." This is the mechanism behind that observation.

**The corrective direction is the opposite of what was tried.** Given a session is relevant,
the evidence says include *more* of it, not less. That makes context budget the binding
resource and pairs directly with span-level minification: spans are what make wider
within-session inclusion affordable at constant tokens.

## Relationship to the abandonment criterion

AD-053 closed context bundling and forbade further bundling variants including
adjacent-expansion rules. It also recorded its own reopening condition:

> "Reopening requires evidence that message selection rather than synthesis dominates
> multi-session or temporal failure."

**That condition is now met.** Four of ten multi-session questions failed with complete
session coverage, and in the two examined in detail the specific answer-bearing message was
absent while its session was present. This is message-selection failure, established by
inspection rather than inference.

This does not reopen anything by itself. It means a candidate may now be *proposed* under
the existing contract process, with a gate sized above the ±2-answer noise floor measured in
`2026-08-03-kimi-question-date-baseline60.md`. Given that floor and a 7-answer multi-session
headroom, an honest gate is a four-answer improvement or better.

## Limits

Sixty questions, one evaluator, one run. The four synthesis failures were read individually;
the remaining conclusions are counts, not judged causation. The within-session coverage
statistic is computed over answer sessions that were retrieved at all, so it excludes
questions that missed their session entirely and is therefore an optimistic view of context
completeness.

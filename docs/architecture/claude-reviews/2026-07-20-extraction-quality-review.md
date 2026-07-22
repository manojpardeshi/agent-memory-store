# Claude Review: Extraction Quality Gate

Date: 2026-07-20
Reviewer: Claude Sonnet through stateless Claude CLI prompts

## Availability record

The initial comprehensive prompt and one continuation prompt returned blank and were not treated as advice. Two smaller review prompts succeeded. Work continued independently as authorized.

## Adopted advice

Claude agreed that precision, recall, kind accuracy, provenance accuracy, duplicates, invalid cases, forbidden extraction, and no-write verification form an appropriate first-pass product metric set. It required:

- forbidden proposal count to be an explicit zero-tolerance gate;
- no-write to be a hard invariant rather than an average metric;
- anchors to have meaningful coverage rather than accepting any short substring;
- summary scoring through preregistered atomic fact units and anchor groups; and
- results from a small corpus to be described as directional engineering evidence.

For summaries, Claude recommended normalized alternative anchors within fact units, unit coverage, an 0.85 completeness target, and mandatory critical units. This judge-free design is adopted.

## Advice modified or deferred

Claude suggested a semantic-similarity fallback for paraphrases. It is rejected for the release gate because it would couple extraction scoring to another embedding model and threshold, weakening reproducibility. Unmatched proposals are retained in reports for manual audit, and anchor-based scores are explicitly a conservative lower bound.

Claude suggested approximately 100 or more natural cases for stable statistical claims. The first live track uses at least 50 cases to bound local runtime and authoring effort. Wilson intervals and explicit non-statistical scope prevent overclaiming. A multi-author 100+ case corpus is a future trigger before broader quality claims or automation.

## Implementation gate

Implementation must prove the scorer cannot write or accept memory, rejects ambiguous/invalid datasets, maps model IDs back to exact fixtures, reports unmatched proposals, enforces hard safety failures, and produces deterministic owner-only evidence.

## Live-result consultations

The frozen v1 run scored 0.537 precision, 0.725 recall, 0/10 summaries, four invalid cases, and
four forbidden proposals. Claude diagnosed missing negative-pattern rules, undefined summary
semantics, and insufficient structured-output recovery. It recommended explicit positive/negative
category examples, one validation retry, and a separate summary pass. The implementation adopted
the negative rules, precise category definitions, bounded output, and one retry. A separate pass is
deferred because it changes the extractor architecture and needs its own corpus-backed decision.

V2 eliminated forbidden and invalid outputs but reduced recall to 0.25. A second Claude review
recommended explicit affirmed-fact capture, retaining named preference context, pronoun resolution,
mandatory linked-source summaries, and no fact splitting. Those prompt edits were measured as v3
against the unchanged corpus. V3 restored facts but reduced precision to 0.367, destabilized event
classification, and still produced no exact summaries.

V3 is rejected and v2 is retained as the conservative product prompt. Neither result passes the
live target. Claude's suggestion that summaries require at least three turns was not adopted because
the accepted corpus intentionally measures two-source synthesis. More prompt iterations on this
corpus are stopped to limit benchmark overfitting.

## Implementation review

Claude's first implementation verdict called the 0.25 live recall a ship blocker because it
interpreted “ship” as enabling automatic extraction. That conclusion does not match this slice:
automatic acceptance is prohibited, extraction remains explicit and review-first, and the commit
ships measurement plus safer failure behavior rather than a passing model claim.

After the scope was clarified, Claude returned **no remaining blockers** for committing the
evaluator, frozen corpus, safer prompt, and honest failed evidence. It required the reports to state
the recall failure explicitly and extraction to remain off/review-first. Both constraints are met.
Its recommended quality follow-up is captured in the roadmap rather than expanding this commit.

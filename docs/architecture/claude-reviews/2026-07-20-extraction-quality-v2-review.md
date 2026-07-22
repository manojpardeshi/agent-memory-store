# Claude Review: Extraction Quality v2 Direction

Date: 2026-07-20
Reviewer: Claude through stateless no-tools CLI prompts

## Availability

After the user reset the Claude session, the first comprehensive prompt returned blank. A shorter
no-tools review succeeded. Two larger corpus-authoring prompts also returned blank; bounded five-case
requests produced usable blind seeds. Blank output is not treated as advice or authored evidence.

## Recommendation

Claude recommended testing the dedicated two-pass architecture before a model comparison. It read
the v1 failure signature—safe structured output but low recall and summary coverage—as evidence of
task overload. It proposed a narrow atomic pass, a linked-source summary pass, deterministic merge,
and a new frozen corpus. Model comparison becomes the fallback if the architecture experiment
plateaus.

Claude required loopback-only inference, review-only output, no durable writes, exact provenance,
zero forbidden/invalid output, and a stop rule preventing prompt tuning on observed corpus results.
Those constraints are adopted.

## Reconciliation

Claude proposed precision/recall/summary gates of 0.65/0.55/0.60. Those values are rejected because
they weaken the already accepted 0.75/0.65/0.85 live targets. The experiment keeps the stricter
absolute gates and adds paired improvement requirements.

Claude also proposed source-span offsets. They are deferred: the current proposal workflow binds
exact immutable source IDs and hashes, while offsets would require new canonicalization, staleness,
and storage semantics. This experiment revalidates exact whole-source provenance instead.

## Blind corpus seeds

Claude authored fictional fact, preference, event, linked-summary, retraction, and quoted-injection
seeds without access to existing files or prompts. Seeds that violated the requested source count or
made an unconfirmed assistant question into an expected fact were excluded during pre-run label
audit. Accepted seed wording is preserved in the build script; Codex authors the remaining balanced
cases. This curation occurred before corpus freezing or any model run.

## Result and resolution

The paired evidence rejected Claude's selected two-pass hypothesis. Summary coverage improved from
0.25 to 0.60, but precision fell from 0.765 to 0.255, recall fell from 0.325 to 0.300, runtime nearly
tripled, and forbidden/invalid counts rose from zero to one each. The implementation was removed and
is not exposed as a product option.

The preregistered model fallback also failed. Qwen 2.5 7B scored 0.45 precision and 0.225 recall.
Qwen3 4B first exposed a documented Ollama thinking-envelope incompatibility; after the adapter was
fixed without changing prompt or corpus, it scored 0.476 precision and 0.25 recall, invented source
IDs in 25 cases, and extracted one forbidden quoted claim. Llama single-pass remains review-only and
failed, but is the least-bad safe candidate in this matrix. The roadmap moves to deterministic review
ergonomics rather than further tuning against this corpus.

## Final implementation review

The first detailed final-review prompt returned blank. A shorter no-tools review found no blockers
to committing the synthetic corpus, honest failed reports, removal of the rejected two-pass option,
and bounded Ollama thinking-field compatibility. Claude asked for confirmation that the existing
1 MB envelope bound still covers thinking text, no dead two-pass imports/tests remain, reports contain
only synthetic data, and the full suite plus offline gate pass. These checks are release requirements
for this slice.

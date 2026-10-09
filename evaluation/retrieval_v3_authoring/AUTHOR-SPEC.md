# Retrieval v3 — Authoring Specification

You are one of two independent authors of a synthetic retrieval test corpus. Write from your own
imagination. **Do not read any file in this repository other than this specification**, do not
run any code, and do not look at any other corpus. The other author is writing in parallel and
you will not see their work until review.

The corpus tests whether a memory system, given a question, returns the one memory that answers
it. It contains no real people's data: every name, place, number and code is invented.

## What you write: 30 items

Each item is one memory plus one question that it, and only it, answers.

- **20 private items** in your assigned private domain.
- **10 shared items** in your assigned shared-pool domain.

Across your 30 items, use each memory kind exactly 6 times:

| kind | what it is |
| --- | --- |
| `turn` | one chat message, with `role` `user` or `assistant` (use both roles) |
| `fact` | a standalone factual note |
| `preference` | someone's stated preference |
| `summary` | a multi-detail recap of several things |
| `event` | something that happened at a particular time |

Split the kinds sensibly between private and shared (for example 4 of each kind private and 2 of
each shared).

## Two question styles, exactly 15 of each

- **`anchor`** — the question repeats one distinctive token from its memory verbatim: an invented
  proper name, a product or model code, an unusual number, an unusual word (for example
  "Vantablack", "SKU 88-QZ", "Halvorsen"). Apart from that token, phrase the question differently
  from the memory. The token must appear in **only that one memory** in your 30.
- **`paraphrase`** — the question shares **no content word** with its memory: no shared nouns,
  verbs, adjectives, names or numbers, not even as a different form of the same word ("renovate" vs
  "renovation" counts as shared). Function words such as "the", "what", "did", "is" are fine. A
  person who read the memory should still recognize the question as asking about it.

## Make it realistic and hard

- Write in a natural voice, like real notes and chat. Memories of 1–3 sentences, questions of one
  sentence.
- Within each domain, deliberately include **lexical traps**: other memories that share common
  words with a question but do not answer it (a question about the "studio lease" when three other
  memories mention the "studio"). Traps are what make this corpus useful.
- Every question must have exactly one correct answer among all 30 of your memories. No two
  memories may both answer the same question.
- Avoid dates relative to "today" ("yesterday", "last week"); absolute dates are fine.

## Output

Write one JSON file at the path you are given, with exactly this shape:

```json
{
  "author": "<your author label>",
  "private_domain": "<your private domain>",
  "shared_domain": "<your shared domain>",
  "items": [
    {
      "local_id": 1,
      "pool": "private",
      "kind": "turn",
      "role": "user",
      "content": "…the memory…",
      "query": "…the question…",
      "style": "anchor",
      "anchor_token": "Halvorsen"
    }
  ]
}
```

- `local_id` runs 1–30. Items 1–20 have `pool` `private`, items 21–30 `shared`.
- `role` is present only for `turn` items. `anchor_token` is present only for `anchor` items.
- Interleave the styles and kinds; do not group them.

Before finishing, check your own file against every rule above, especially the no-shared-content-
word rule for paraphrase questions and the one-memory rule for anchor tokens, and fix anything
that fails.

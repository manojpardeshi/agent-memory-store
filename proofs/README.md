# Machine-checked proofs (Rocq)

You can't verify Python code directly. For each Python function covered here, this directory has a hand-written
Rocq model and proofs of safety properties about that model. Rocq checks the proofs, and nothing is admitted.
The guarantees therefore only cover the models. How closely each model matches the Python is a separate,
human-reviewed claim, and each section below spells it out.

Check everything from the repository root:

```
scripts/check_proofs.sh
```

The script does the following:

1. It scans the sources for `Admitted`, `admit`, `Axiom`, `Parameter`, `Conjecture`, `Abort`, `Hypothesis` and `Variable`.
2. It copies `proofs/` to the Rocq host (`PROOF_HOST`, default `manojpardeshi@10.10.10.2`).
3. It compiles each file with `coqc -Q . AMS`.
4. It requires every `Print Assumptions` in a file to print `Closed under the global context`.
5. It re-checks every compiled module with `coqchk -o`, Rocq's independent checker. The report must show
   `Axioms: <none>` and no type-in-type, no unsafe fixpoints and no assumed positivity.

Every remote `coqc`/`coqchk` runs under a `perl alarm` limit (`PROOF_TIMEOUT`, default 600 s). The proofs use only the
Rocq 9.3 standard library (`Stdlib`).

Some hypotheses are written as `Context` inside a `Section`. They are not axioms. When the section closes, they become
ordinary arguments, so each theorem holds for every instantiation. `Print Assumptions` and `coqchk` confirm this.

## What is not proved, for all four files

- That the Python code conforms to the model. The models were written by reading the code and are argued to match in
  the sections below. No tool connects the two.
- That CPython, its `re` engine, `str.lower`, `datetime`, `json`, `subprocess` and git behave as documented.
  The same goes for SQLite and FTS5, including how FTS5 parses a quoted phrase, and for sqlite-vec.
- Floating-point behaviour. Scores are modelled with exact rationals; see RankFusion below.
- Anything about the surrounding code that is not named in that file's section.

---

## KeywordQuery.v: `keyword_query` in `src/llm_memory_store/store.py`

**Correspondence**

| Python | Model |
|---|---|
| `text.lower()` | arbitrary `lower : list A -> list A`. It can change length, e.g. `'İ'.lower()` gives two code points. Every theorem holds for every `lower`. |
| `_KEYWORD_TOKEN.findall(...)`, `[^\W_]+` | `tokens`, the maximal runs of characters satisfying the abstract decidable `word_char` |
| `token not in KEYWORD_STOPWORDS and len(token) > 1` | `eligible t = negb (is_stopword t) && (1 <? length t)`, with `is_stopword` arbitrary |
| `list(dict.fromkeys(terms))` | `dedup`, which keeps the first occurrence |
| `[:MAX_KEYWORD_QUERY_TERMS]` (64) | `firstn 64` |
| `" OR ".join(f'"{t}"' ...)` / `None` if empty | `join` / `None` when the term list is empty |

Characters are an abstract type `A`, standing for code points. Only these facts are assumed:

- `word_char dquote = false`. Python's `\w` never matches `"`.
- The separator characters (space, `O`, `R`) differ from `"`.

To show these hypotheses can be satisfied, and to cross-check the model against Python, the file builds an ASCII
instance:

- `word_char` is `[A-Za-z0-9]`, `lower` is ASCII lowercasing, and the stopword list is the full `KEYWORD_STOPWORDS`.
- Five `Example`s compute the model's output by evaluation. Each must equal the output of the real Python function on
  the same input; those outputs were captured from the project venv.
- `ascii_keyword_query_sound` states the main theorem for that instance with every side condition discharged.

**Theorems**

- `keyword_query_sound`: if `keyword_query text = Some s`, then there is a list `ts` with all of the following:
  - `s = join ts` and `ts = terms_of text`
  - `ts <> []`
  - `s` is in the grammar `Q (" OR " Q)*`, where `Q = " word_char+ "`
  - `decode s = ts`: splitting `s` at double quotes gives back exactly `ts`, so no extra phrase, operator or column filter can appear
  - `length ts <= 64`
  - `NoDup ts`
  - every term is a non-empty run of word characters with no `"`, has length ≥ 2, is not a stopword, and is a token of `lower text`

  This covers properties (a)–(d).
- `keyword_query_quote_count`: the output contains exactly `2 × (number of terms)` double quotes.
- `keyword_query_none_iff` (property e): the result is `None` exactly when no token of `lower text` is a non-stopword
  of length > 1.
- `keyword_query_complete_under_cap`: if there are at most 64 distinct eligible tokens, every eligible token appears
  in the query.
- `tokens_concat`, `tokens_split`, `tokens_run`: these pin down the tokenizer.
  - It keeps every word character, in order (`concat (tokens s) = filter word_char s`).
  - It splits at every non-word character.
  - A non-empty word run is exactly one token.

  Together these determine the maximal-munch semantics of `findall` for a one-class `+` pattern.

**Not proved / assumptions**

- That Python's `\w` (Unicode, `re` without `ASCII`) never matches `"`. This is true by CPython's definition of `\w`
  as alphanumerics plus `_`.
- How FTS5 interprets a double-quoted phrase containing only word characters.

---

## RankFusion.v: the reciprocal rank fusion (RRF) step of `MemoryStore.recall` (hybrid branch, `fusion_scores`, `HYBRID_RRF_K = 60`) in `src/llm_memory_store/store.py`

**Correspondence**

- **Rankings.** A ranking is a `list nat` of internal ids. `recall` passes two rankings:
  - `[item[2] for item in vector_ranked]`
  - `[i for i in keyword_ranked if i in by_internal_id]`
- **Score.** `score rs id` is the sum over rankings, and over every position `p` (1-based) where `id` occurs, of
  `1 # (60 + p)`. This matches the loop exactly, including repeated occurrences.
- **Dict key order.** `keys rs = dedup (concat rs)`, the insertion order of `fusion_scores`.
- **Sort.** `sorted(..., key=(-fusion, memory_id))` is modelled as a stable insertion sort `isort` under `before_by sc`:
  `a` goes first if `sc a > sc b`, or if `sc a == sc b` and `key_leb a b`. Here `key_leb` is the abstract comparison of
  the tie-break `memory_id`.
- **Score function.** `fuse_by sc rs = isort (before_by sc) (keys rs)` works for any score function `sc : nat -> Q`.
  `fuse rs = fuse_by (score rs) rs` is the exact-arithmetic instance.

**Theorems**

The generic theorems (`fuse_by`) hold for every `sc`. That includes the exact rational value of each float score
Python computes, so they don't depend on float rounding.

- `fuse_In` (a): `x` is in the output exactly when `x` is in some input ranking. No id is invented.
- `fuse_scope_isolation`: if every input id satisfies `P` (for example "lies in one of the caller's scopes"), so does
  every output id.
- `recall_output_isolated`: the same holds after `recall`'s later relevance filter and `[:limit]`, and the result
  stays duplicate-free.
- `fuse_NoDup` (b): the output has no duplicates.
- `fuse_sorted`: the output is sorted by `(-score, key)`, assuming `key_leb` is total.
- `fuse_unique`: if `key_leb` is total, transitive and antisymmetric (`memory_id` is `UNIQUE` in the schema), the
  output is the *only* sorted permutation of the keys. So it equals whatever `sorted()` returns, whatever algorithm
  CPython uses.
- `fuse_single`, `fuse_keyword_empty`, `fuse_vector_empty` (c): for a duplicate-free ranking `r`,
  `fuse [r] = fuse [r; []] = fuse [[]; r] = r`. This holds for any `key_leb`.
- `fuse_by_passthrough`: for any score function strictly decreasing along `r`, the output is `r`.
- Examples:
  - `two_rankings` is a worked two-list case.
  - `duplicate_ranking_reorders` shows why (c) needs `NoDup`: for `[1;2;3;2]` the output is `[2;1;3]`.

  The rankings `recall` passes are duplicate-free: `scored` comes from a dict, and FTS rowids are unique.

**Simplifications and a found discrepancy (floats)**

- Python sums `float`s. The exact-score order (`fuse`) can differ from Python's in one case: when two ids have
  *exactly equal* rational RRF scores, but their float sums round differently. The model breaks that tie by
  `memory_id`; Python orders the pair by rounding noise.
- **Concrete case, checked in Python:**
  - Id A is only in the vector ranking, at rank 5: score `1/65`.
  - Id B is at vector rank 18 and keyword rank 330: score `1/78 + 1/390 = 1/65` exactly.
  - In floats, `0.0 + 1/78 + 1/390 != 1/65`.
  - Searching ranks up to 500 finds 120 such (rank, rank) pairs that tie exactly with a single-ranking score but
    differ as floats.
- **What is unaffected:** properties (a) and (b), scope isolation, and uniqueness relative to the float scores, because
  the generic `fuse_by` theorems hold for any score function.
- **What still needs an assumption:** property (c) holds for Python's float scores if `1.0/(60+r)` is strictly decreasing in `r`.
  `fuse_by_passthrough` gives this, given that IEEE-754 assumption, which holds for every rank `recall` can produce
  (≤ 500). The IEEE fact itself is not proved here.
- **What only the exact model gives:** the claim that the hybrid order equals "sort by exact RRF score, then
  `memory_id`" holds only up to these float ties.
- The tie-break `memory_id` string comparison is abstracted as `key_leb`.

**Not proved**

- That the inputs are scope-correct. This rests on the SQL filters (`scope_id = ?` in the vector query and
  `m.scope_id IN (...)` in `_keyword_ranking`) and on `_vector_distances` only looking up given ids.
- The candidate scoring, the relevance-filter anchor, and record loading.

---

## HeldOutLedger.v: `record_look` and `main` (look command) in `scripts/locomo_heldout.py`

The data files and the ledger were not opened. The model comes from the code alone.

**Correspondence**

- **Ledger.** `ledger = {st; looks; max_looks; digest}` models `held_out_sets["locomo10"]`.
  - `st` is `Active` (the string `"active"`) or `Retired` (any other string).
  - Commits, digests and candidate names are `nat`s.
- **Guard.** `guard env l` is the conjunction of the five checks, in the code's order:
  - worktree clean
  - `merge-base --is-ancestor` succeeds
  - status is active
  - digest matches
  - `len(looks) < max_looks`

  Every failing check raises before any write, so a refused attempt leaves the ledger unchanged.
- **Append.** `append_look` appends `{..., result: None}` and sets the status to `Retired` once
  `len(looks) >= max_looks`.
- **One invocation (`run`):**
  - `build`: no ledger access, no scoring
  - bad arguments: refused
  - refused `record_look`
  - successful `record_look` followed by `score`
  - successful `record_look` followed by a crash during scoring

  `main` calls `score(...)` only after `record_look` returns, that is, after the ledger write.
- **Reachability.** `reachable l0 l tr` covers sequential executions from a valid initial ledger: `Active`,
  `looks = []`, `max_looks ≥ 1`.

**Theorems (sequential model)**

- `budget_respected` (a): `length looks <= max_looks`, and `max_looks` never changes.
- `retired_iff_exhausted`: the status is `Retired` exactly when `length looks = max_looks`.
- `retired_refuses` (b): once retired, `record_look` fails in every environment.
- `retired_is_final` (b): every later sequence of invocations leaves the ledger unchanged and records or scores nothing.
- `ledger_is_audit_log`: the ledger's looks are exactly the looks recorded in the trace, and each has `result = None`.
- `score_after_look` (c): every `EScored lk` event in the trace is immediately preceded by `ELookRecorded lk`.
- `scores_within_budget`: the number of scoring passes is at most the number of recorded looks, which is at most `max_looks`.
- `look_requires_checks`: every recorded look passed all five checks against the ledger as it then was.

**Property found false for the real script (concurrency)**

The sequential model assumes one invocation at a time and that only `record_look` changes the ledger file.
`record_look` does a non-atomic read → check → write, with no lock or compare-and-swap.

- **The race.** Two concurrent `look` invocations can both read the ledger before either writes. Both see a clean
  worktree and `len(looks) < max_looks`, so both pass. The second write overwrites the first (a lost update).
- **The counterexample.** `concurrent_budget_violation` constructs this interleaving with `max_looks = 1`. The run
  contains **two scoring passes**, but the file records **one look**.
- **What fails.** "Scoring passes ≤ max_looks" and "the ledger is an exact audit log" both fail for concurrent runs.
- **What still holds.** `concurrent_file_bound` proves the file itself still never exceeds `max_looks`.
- **Possible fixes (not applied):** take an exclusive lock on the ledger file around the read–check–write, or
  re-read and compare before writing.

**Other simplifications, not modelled**

- A crash *inside* `LEDGER.write_text`, which could truncate the JSON so later reads fail.
- External edits to the ledger, and `git checkout` of an older ledger.
- That the stores directory matches the frozen data. Only the dataset bytes are digest-checked.
- The data `score` reads is parsed from the same bytes whose digest was checked; the model doesn't depend on this.

---

## OccurredAt.v: `MemoryStore._validate_occurred_at` and `OCCURRED_AT_CLOCK_SKEW` in `src/llm_memory_store/store.py`

**Correspondence**

- **Parsed value.** A parsed datetime is `{local : Z; offset : option Z}`: the wall-clock reading in microseconds and
  the UTC offset in microseconds, with `None` meaning naive. Its instant is `local - offset`.
- **Parsing.** `occurred_at.replace('Z', '+00:00')` followed by `datetime.fromisoformat` is an arbitrary
  `parse : Str -> option dt`. `None` stands for `ValueError`.
- **Clock and skew.** `now` is the instant of `datetime.now(UTC)`. `skew_us = 5*60*10^6`, checked to equal 300000000.
- **The future check.** `value > now + skew` is a comparison of instants. Python compares aware datetimes by
  UTC instant. When both share the same `tzinfo` object (`fromisoformat` returns the `timezone.utc` singleton for
  `+00:00`), it compares wall clocks instead, which gives the same answer for offset 0.
- **Normalisation.** `astimezone(UTC)` is `to_utc v off = {local - off; Some 0}`. The ISO string formatting is not
  modelled; the result is the normalised value.

**Theorems**

- `accepted_sound`: every accepted value
  - came from a parsed aware input,
  - has offset `Some 0` (it has a timezone, UTC),
  - has the same instant as the input,
  - and satisfies `instant <= now + skew`.
- `naive_rejected`, `future_rejected`: naive inputs and inputs more than 5 minutes ahead are rejected.
- `within_bound_accepted`: every aware value within the bound is accepted (completeness).
- `none_passes`: a `None` input is accepted as `None`.
- `to_utc_preserves_instant`, `to_utc_idempotent`: normalisation keeps the instant, and normalising twice changes nothing.
- `revalidation_stable`: if a stored value parses back to itself, validating it again at any later clock reading
  accepts it unchanged.

**Simplifications**

- **Unbounded integers.** The model uses them; Python datetimes span years 1–9999.
  - `astimezone(UTC)` near the range edges raises `OverflowError` (checked: `0001-01-01T00:00:00+05:00`), which is a
    rejection the model does not have.
  - So Python accepts a *subset* of what the model accepts, and the safety theorems (every accepted value is aware,
    UTC and not in the future) still apply to it.
  - That error is `OverflowError`, not `ValueError`. Callers catching only `ValueError` will see it propagate.
- **Clock correctness.** The bound is relative to the host clock, which is not modelled.
- **Parsing details.** Which strings `fromisoformat` accepts (fraction truncation, offsets with seconds) lives inside
  the abstract `parse`.

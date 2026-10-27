# Embedding Runtime Equivalence — FastEmbed 0.9.1 and ONNX Runtime

Date: 2026-10-27
Why: 0.4.0's release gate found about 40 Pillow advisories. The fixed Pillow 13 requires FastEmbed
0.9.1. Checking that upgrade exposed a fragility in published releases: routine dependency updates
change the store's embedding behaviour fingerprint, which makes existing stores refuse to open.

## Findings

The behaviour fingerprint hashes two sentinel embeddings to 8 decimals.

| Model | FastEmbed | ONNX Runtime | Fingerprint |
| --- | --- | --- | --- |
| BAAI/bge-small-en-v1.5 | 0.8.0 | 1.27 | `36d7909e…`, the certified value |
| BAAI/bge-small-en-v1.5 | 0.9.1 | 1.27.0 (this lock) | `36d7909e…`, identical |
| BAAI/bge-small-en-v1.5 | 0.9.1 | 1.31.1 (fresh pip install) | `625b4f33…`, different |

The drift comes from ONNX Runtime, not FastEmbed. FastEmbed's version string therefore does not
predict behaviour.

Is the difference real? Comparing FastEmbed 0.8.0 with 0.9.1 on ONNX Runtime 1.31.1:

- **Probe embeddings:** cosine similarity of 1.000000 on every probe text, at most 2.2e-4
  absolute difference per component.
- **Synthetic suites:** retrieval_v1/v2/v3 with the filter off gave identical recall, MRR, and
  distractor leak. 169 of 170 top-k rankings were identical; the remaining one swapped a near-tie.
- **Tuning pool:** under the new lock (FastEmbed 0.9.1, ONNX Runtime 1.27.0), the development 180
  gives vector 121/174 and re-ranked 138/174, exactly as before.

## Change (AD-055)

- **Equivalent fingerprints.** `EQUIVALENT_FINGERPRINTS` (in `embeddings.py`) records measured
  equivalent fingerprints, currently bge-small `36d7909e…` and `625b4f33…`. Stores open under
  any fingerprint in their group.
- **Certified default by behaviour.** The certified relevance default now applies when the
  certified model's fingerprint is certified or equivalent, regardless of the runtime version
  string. Any other fingerprint stays unfiltered.
- **Verified both ways.** A store created under FastEmbed 0.8.0 opens under FastEmbed 0.9.1 with
  either ONNX Runtime, with the certified filter active in both.
- **Dependencies.** `fastembed>=0.9.1,<1` and a `pillow>=13` security floor. pip-audit reports no
  known vulnerability in the locked runtime set.

## Separate finding: stale all-MiniLM-L6-v2 certification

A fresh download of `sentence-transformers/all-MiniLM-L6-v2` under FastEmbed 0.8.0 gives
fingerprint `b6702b95…`, not the certified `d448bfe0…`. The model files served today differ from
the ones certified in July. That certification therefore no longer applies to new downloads, and
those stores run unfiltered until re-certified. The default model, bge-small, is unaffected. This
needs a separate re-certification and is not fixed here.

## Limit

Releases before 0.4.0 lack the equivalence table. They still need an exact fingerprint match, so
an older runtime cannot open a store whose fingerprint differs from its own.

# all-MiniLM-L6-v2 Re-certification

Date: 2026-10-31
Why: the 0.4.0 equivalence work found that today's download of
`sentence-transformers/all-MiniLM-L6-v2` gives a different behaviour fingerprint from the one
certified in July. The certified relevance filter (relative 0.20) therefore stopped applying to new
MiniLM stores, which ran unfiltered. The default model, bge-small, was not affected.

## Method

The July certification matrix was re-run unchanged: retrieval_v1 (50 queries) and retrieval_v2
(60 queries), each with the filter off and with relative 0.20. The model came from today's download
(`qdrant/all-MiniLM-L6-v2-onnx`, snapshot `d1395466…`). Each query's top-k ranking was compared
with the July report.

| Runtime | Fingerprint |
| --- | --- |
| July certification | `d448bfe0…` |
| FastEmbed 0.9.1, ONNX Runtime 1.27.0 (this lock) | `08625e07…` |
| FastEmbed 0.9.1, ONNX Runtime 1.31.1 (fresh pip install) | `08625e07…` |

## Results

The results were the same under both ONNX Runtime versions:

| Suite | Filter | Identical rankings | Recall@k | MRR | Leak | Gate |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| retrieval_v1 | off | 50 / 50 | 0.980 | 0.960 | 0.400 | Fail, as in July |
| retrieval_v1 | relative 0.20 | 50 / 50 | 0.980 | 0.960 | 0.060 | Pass, as in July |
| retrieval_v2 | off | 60 / 60 | 0.983 | 0.947 | 0.167 | Fail, as in July |
| retrieval_v2 | relative 0.20 | 60 / 60 | 0.983 | 0.947 | 0.050 | Pass, as in July |

Every metric matches the July reports exactly (`2026-07-19-retrieval-quality-v{1,2}-minilm-*.json`).

## Change

`08625e07…` joins `d448bfe0…` in its own group in `EQUIVALENT_FINGERPRINTS` (AD-055):

- **Filter restored.** The certified filter applies again to stores created with today's MiniLM
  download.
- **July stores open.** Stores created in July open under the current runtime.
- **Groups stay per model.** No fingerprint certifies a different model.

## Limit

The July model files are no longer available locally, and no July MiniLM store survives. The
evidence is therefore behavioural: rankings and metrics. It does not include the direct
probe-embedding cosine used for bge-small. The fingerprint FastEmbed 0.8.0 gives for today's
download (`b6702b95…`) is not added. 0.4.0 requires FastEmbed 0.9.1, and that fingerprint was not
re-measured on the suites.

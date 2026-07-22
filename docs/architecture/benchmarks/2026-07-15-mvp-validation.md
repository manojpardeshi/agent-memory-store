# MVP Validation Evidence

Date: 2026-07-15

Reference machine:

- macOS 15.6.1
- Apple Silicon (`arm64`)
- Python 3.13.3
- SQLite 3.50.4
- `sqlite-vec` 0.1.9
- FastEmbed 0.8.0

## Exact Vector Retrieval

Command:

```bash
uv run python scripts/benchmark_retrieval.py --records 20000 --queries 60
```

Dataset and query shape:

- 20,000 normalized random float32 vectors
- 384 dimensions
- Exact cosine KNN
- One partition-key scope
- `k=20`

Results:

| Metric | Result |
| --- | ---: |
| p50 | 11.98 ms |
| p95 | 12.98 ms |
| max | 22.18 ms |

Conclusion: exact `sqlite-vec` retrieval passes the proposed 200 ms p95 target with substantial margin at the representative 20K-record scale. This benchmark isolates storage retrieval and does not include local query embedding or multi-scope fan-out.

## Real Local Embedding and Recall

Provider configuration:

- Model: `BAAI/bge-small-en-v1.5`
- Dimension: 384
- Runtime: FastEmbed 0.8.0 / ONNX Runtime
- Cache was initially empty and stored outside the repository.

Observed validation:

| Operation | Result |
| --- | ---: |
| Initial model download and initialization | 6.37 s |
| Warm semantic recall over two records | 3.68 ms |
| Intended preference ranked first | Yes |
| Store integrity check | `ok` |
| Missing/orphan vectors | 0 / 0 |

The first run requires network access to obtain model assets. Subsequent operation uses the local cache. The store persists a behavioral embedding fingerprint and refuses to open with an incompatible runtime vector space.

## Final Implementation Verification

- 25 tests pass, including an actual stdio MCP client/server subprocess exchange, confirmation-abort behavior, a forced concurrent operation-ID race, deterministic model-switch demo scoring, and model-subprocess environment isolation.
- Ruff lint and format checks pass.
- Tests pass with unclosed SQLite `ResourceWarning` treated as an error.
- Combined line coverage is 74%; core `store.py` coverage is 81% and `database.py` coverage is 88%. MCP is exercised in a subprocess, which the parent coverage process does not attribute.
- Source distribution and universal Python wheel build successfully.
- The built wheel installs into an isolated `uvx` environment and exposes the complete `llm-memory` CLI.
- Database, JSON export, backup, and restored database artifacts are verified as mode `0600`.
- Portability tests verify that export, backup, and restore do not clobber existing files by default.

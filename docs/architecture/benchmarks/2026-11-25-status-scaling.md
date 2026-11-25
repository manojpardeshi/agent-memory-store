# `status()` scaling audit — November 25, 2026

`status()` previously fetched every memory, vector, and ready-memory ID into Python sets to count
missing and orphan vectors. This audit measured that path against SQL `EXCEPT` counts before
changing production code. The benchmark uses synthetic facts in a temporary local SQLite store;
one fifth are embedded with the deterministic 64-dimensional embedder. No network or paid model is
used.

Run `uv run python scripts/benchmark_status_scaling.py 50000` to reproduce. The script measures
both implementations twice on the same store with `perf_counter` and `tracemalloc`, then requires
their entire status reports to match. Reported memory is peak traced **Python allocation during
one status call**, not process RSS or SQLite's internal allocations. Times include the existing
FTS and SQLite integrity checks. The database is removed after each run.

| Memories | Former status time (s) | SQL status time (s) | Former Python peak (MiB) | SQL Python peak (MiB) |
| ---: | ---: | ---: | ---: | ---: |
| 1,000 | 0.006–0.007 | 0.005 | 0.117–0.162 | 0.002–0.003 |
| 10,000 | 0.080–0.083 | 0.057 | 1.829–1.920 | 0.002 |
| 50,000 | 0.546–0.575 | 0.376–0.377 | 8.929–9.020 | 0.002–0.004 |

The repeated 50,000-memory run is shown because a first concurrent run had one 1.924 s former-path
outlier. On every measured store, the full reports matched, `integrity_check` and the keyword index
were `ok`, and both vector discrepancy counts were zero. A focused test separately deletes a ready
vector and inserts an orphan vector, then verifies the new counts are both one.

The SQL path still scans the database and performs full integrity checks. These numbers support a
lower Python memory footprint and modest latency gain at personal scale; they do not establish
large multi-user database behavior.

"""Benchmark exact sqlite-vec retrieval with deterministic 384-dim vectors."""

from __future__ import annotations

import argparse
import random
import sqlite3
import statistics
import tempfile
import time
from pathlib import Path

import sqlite_vec


def normalized_vector(randomizer: random.Random, dimension: int) -> list[float]:
    values = [randomizer.uniform(-1.0, 1.0) for _ in range(dimension)]
    norm = sum(value * value for value in values) ** 0.5
    return [value / norm for value in values]


def benchmark(records: int, queries: int, dimension: int = 384) -> dict[str, float | int]:
    randomizer = random.Random(42)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "benchmark.sqlite3"
        connection = sqlite3.connect(path)
        connection.enable_load_extension(True)
        sqlite_vec.load(connection)
        connection.enable_load_extension(False)
        connection.execute(
            f"""
            CREATE VIRTUAL TABLE vectors USING vec0(
                embedding float[{dimension}] distance_metric=cosine,
                scope_id integer partition key
            )
            """
        )
        batch = []
        for rowid in range(1, records + 1):
            batch.append(
                (rowid, sqlite_vec.serialize_float32(normalized_vector(randomizer, dimension)), 1)
            )
            if len(batch) == 500:
                connection.executemany(
                    "INSERT INTO vectors(rowid, embedding, scope_id) VALUES(?, ?, ?)", batch
                )
                batch.clear()
        if batch:
            connection.executemany(
                "INSERT INTO vectors(rowid, embedding, scope_id) VALUES(?, ?, ?)", batch
            )
        connection.commit()

        timings = []
        for _ in range(queries):
            query = sqlite_vec.serialize_float32(normalized_vector(randomizer, dimension))
            started = time.perf_counter()
            connection.execute(
                """
                SELECT rowid, distance FROM vectors
                WHERE embedding MATCH ? AND k=20 AND scope_id=1
                ORDER BY distance
                """,
                (query,),
            ).fetchall()
            timings.append((time.perf_counter() - started) * 1000)
        connection.close()
    ordered = sorted(timings)
    return {
        "records": records,
        "queries": queries,
        "dimension": dimension,
        "p50_ms": statistics.median(timings),
        "p95_ms": ordered[max(0, int(len(ordered) * 0.95) - 1)],
        "max_ms": max(timings),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, default=20_000)
    parser.add_argument("--queries", type=int, default=50)
    args = parser.parse_args()
    print(benchmark(args.records, args.queries))


if __name__ == "__main__":
    main()

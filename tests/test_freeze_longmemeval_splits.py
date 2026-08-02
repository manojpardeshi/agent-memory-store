from __future__ import annotations

from scripts.freeze_longmemeval_splits import SPLIT_COUNTS, split_complement


def test_split_complement_is_deterministic_disjoint_and_complete() -> None:
    question_types = list(SPLIT_COUNTS["validation"])
    dataset = []
    observed_ids = set()
    for question_type in question_types:
        required = sum(split[question_type] for split in SPLIT_COUNTS.values())
        for index in range(required + 1):
            question_id = f"{question_type}-{index}"
            dataset.append({"question_id": question_id, "question_type": question_type})
            if index == required:
                observed_ids.add(question_id)

    first = split_complement(dataset, observed_ids, question_types)
    second = split_complement(list(reversed(dataset)), observed_ids, question_types)

    assert first == second
    assert {name: len(ids) for name, ids in first.items()} == {
        "development-complement": 120,
        "validation": 150,
        "reserve": 170,
    }
    all_ids = [question_id for ids in first.values() for question_id in ids]
    assert len(all_ids) == len(set(all_ids)) == 440
    assert observed_ids.isdisjoint(all_ids)

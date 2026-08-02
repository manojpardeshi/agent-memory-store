from __future__ import annotations

import pytest

from scripts.probe_kimi_api import ProbeError, build_request, calculate_cost_usd


def test_build_request_has_frozen_low_cost_identity_contract() -> None:
    body, digest = build_request()

    assert b'"model":"kimi-k3"' in body
    assert b'"reasoning_effort":"low"' in body
    assert b'"max_completion_tokens":256' in body
    assert len(digest) == 64


def test_calculate_cost_separates_cached_and_uncached_input() -> None:
    result = calculate_cost_usd(
        {
            "prompt_tokens": 1_000,
            "completion_tokens": 100,
            "prompt_tokens_details": {"cached_tokens": 400},
        }
    )

    assert result == {
        "prompt_tokens": 1_000,
        "cached_input_tokens": 400,
        "uncached_input_tokens": 600,
        "completion_tokens": 100,
        "calculated_cost_usd": pytest.approx(0.00342),
    }


def test_calculate_cost_rejects_impossible_cache_usage() -> None:
    with pytest.raises(ProbeError, match="cannot exceed"):
        calculate_cost_usd(
            {
                "prompt_tokens": 10,
                "completion_tokens": 1,
                "prompt_tokens_details": {"cached_tokens": 11},
            }
        )

#!/usr/bin/env python3
"""Run a minimal, secret-safe Kimi K3 API identity and billing probe."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any

API_URL = "https://api.moonshot.ai/v1/chat/completions"
MODEL = "kimi-k3"
INPUT_CACHE_HIT_USD_PER_MILLION = 0.30
INPUT_CACHE_MISS_USD_PER_MILLION = 3.00
OUTPUT_USD_PER_MILLION = 15.00


class ProbeError(RuntimeError):
    """Raised when the identity probe does not satisfy its frozen contract."""


def calculate_cost_usd(usage: dict[str, Any]) -> dict[str, int | float]:
    prompt_tokens = int(usage.get("prompt_tokens", 0))
    completion_tokens = int(usage.get("completion_tokens", 0))
    details = usage.get("prompt_tokens_details") or {}
    cached_tokens = int(details.get("cached_tokens", 0))
    if min(prompt_tokens, completion_tokens, cached_tokens) < 0:
        raise ProbeError("token usage cannot be negative")
    if cached_tokens > prompt_tokens:
        raise ProbeError("cached input tokens cannot exceed prompt tokens")
    uncached_tokens = prompt_tokens - cached_tokens
    cost = (
        cached_tokens * INPUT_CACHE_HIT_USD_PER_MILLION
        + uncached_tokens * INPUT_CACHE_MISS_USD_PER_MILLION
        + completion_tokens * OUTPUT_USD_PER_MILLION
    ) / 1_000_000
    return {
        "prompt_tokens": prompt_tokens,
        "cached_input_tokens": cached_tokens,
        "uncached_input_tokens": uncached_tokens,
        "completion_tokens": completion_tokens,
        "calculated_cost_usd": cost,
    }


def build_request() -> tuple[bytes, str]:
    payload = {
        "model": MODEL,
        "reasoning_effort": "low",
        "max_completion_tokens": 256,
        "messages": [
            {
                "role": "system",
                "content": "Return only valid JSON matching the supplied schema.",
            },
            {
                "role": "user",
                "content": (
                    "Synthetic identity probe. Report status ok and "
                    "model_requested kimi-k3."
                ),
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "kimi_identity_probe",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "const": "ok"},
                        "model_requested": {"type": "string", "const": MODEL},
                    },
                    "required": ["status", "model_requested"],
                    "additionalProperties": False,
                },
            },
        },
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return body, hashlib.sha256(body).hexdigest()


def run_probe(api_key: str) -> dict[str, Any]:
    if not api_key.strip():
        raise ProbeError("MOONSHOT_API_KEY is empty")
    body, request_sha256 = build_request()
    request = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            result = json.load(response)
    except urllib.error.HTTPError as error:
        raise ProbeError(f"Kimi API returned HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise ProbeError("Kimi API connection failed") from error

    if result.get("model") != MODEL:
        raise ProbeError(f"expected response model {MODEL!r}, got {result.get('model')!r}")
    choices = result.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise ProbeError("Kimi API response must contain exactly one choice")
    content = choices[0].get("message", {}).get("content")
    if not isinstance(content, str):
        raise ProbeError("Kimi API response did not contain string content")
    try:
        parsed_content = json.loads(content)
    except json.JSONDecodeError as error:
        raise ProbeError("Kimi API response content was not valid JSON") from error
    expected = {"status": "ok", "model_requested": MODEL}
    if parsed_content != expected:
        raise ProbeError("Kimi API response content did not match the identity schema")
    usage = result.get("usage")
    if not isinstance(usage, dict):
        raise ProbeError("Kimi API response did not include token usage")

    return {
        "schema_version": 1,
        "status": "passed",
        "completed_at": datetime.now(UTC).isoformat(),
        "endpoint_host": "api.moonshot.ai",
        "model_requested": MODEL,
        "model_reported": result["model"],
        "reasoning_effort": "low",
        "max_completion_tokens": 256,
        "request_sha256": request_sha256,
        "response_content_sha256": hashlib.sha256(content.encode()).hexdigest(),
        "usage": calculate_cost_usd(usage),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    api_key = os.environ.get("MOONSHOT_API_KEY", "")
    print(json.dumps(run_probe(api_key), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

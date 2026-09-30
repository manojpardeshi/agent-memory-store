#!/usr/bin/env bash
# Launch a retrieval-only hosted comparator run with the provider key taken from Keychain.
#
# The key is read into this process's environment only. It is never written to disk,
# echoed, placed on a command line, or stored in a report. MemoryBench reads MEM0_API_KEY
# or SUPERMEMORY_API_KEY from the environment.
#
# usage: scripts/run_hosted_comparator.sh {mem0|supermemory} RUN_ID MANIFEST CONCURRENCY
set -euo pipefail

provider="${1:?provider}"; run_id="${2:?run id}"; manifest="${3:?manifest}"; concurrency="${4:?concurrency}"
repo="$(cd "$(dirname "$0")/.." && pwd)"
bench="$repo/demo-artifacts/memorybench/upstream"
bun_bin="${BUN_BIN:-$HOME/.bun/bin/bun}"

case "$provider" in
  mem0) service="agent-memory-store-mem0-api"; var="MEM0_API_KEY" ;;
  supermemory) service="agent-memory-store-supermemory-api"; var="SUPERMEMORY_API_KEY" ;;
  *) echo "provider must be mem0 or supermemory" >&2; exit 2 ;;
esac

[ -x "$bun_bin" ] || { echo "bun not found at $bun_bin" >&2; exit 2; }
key="$(security find-generic-password -s "$service" -w 2>/dev/null)" || {
  echo "Keychain item $service not found; store the key first" >&2; exit 2; }
[ -n "$key" ] || { echo "Keychain item $service is empty" >&2; exit 2; }

manifest_abs="$(cd "$repo" && realpath "$manifest")"
cp "$repo/evaluation/memorybench/hosted-search-manifest.ts" "$bench/scripts/"
cd "$bench"
# `export` is a shell builtin, so the key never appears in any process's argv or in ps.
# exec replaces this shell, so bun is the only process holding it.
export "$var=$key"
unset key
exec "$bun_bin" scripts/hosted-search-manifest.ts "$provider" "$run_id" "$manifest_abs" "$concurrency"

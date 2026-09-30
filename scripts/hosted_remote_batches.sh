#!/usr/bin/env bash
# Runs ON the M2. Reads the provider key from stdin once, then runs several retrieval-only
# batches back to back in one detached driver, so later batches proceed unattended.
# The key lives only in the driver's environment and is inherited by each bun child.
#
# usage (key on stdin): hosted_remote_batches.sh VAR PROVIDER CONCURRENCY RUN_ID:MANIFEST...
set -euo pipefail
var="$1"; provider="$2"; conc="$3"; shift 3
case "$var" in MEM0_API_KEY|SUPERMEMORY_API_KEY) ;; *) echo "bad variable name" >&2; exit 2 ;; esac
[[ "$conc" =~ ^[1-8]$ ]] || { echo "concurrency must be 1 to 8" >&2; exit 2; }
[ "$#" -ge 1 ] || { echo "at least one RUN_ID:MANIFEST pair required" >&2; exit 2; }
for pair in "$@"; do [[ "$pair" =~ ^[A-Za-z0-9._-]+:manifests/[A-Za-z0-9._-]+\.json$ ]] || {
  echo "bad pair: $pair" >&2; exit 2; }; done
IFS= read -r key || true
[ -n "${key:-}" ] || { echo "no key received on stdin" >&2; exit 2; }
export "$var=$key"; unset key
export MEM0_TELEMETRY=false
cd "$HOME/bench/memorybench"
driver_log="$HOME/bench/memorybench/batches-$(date +%Y%m%dT%H%M%S).log"
nohup caffeinate -i bash -c '
  for pair in "$@"; do
    run_id="${pair%%:*}"; manifest="${pair#*:}"
    echo "$(date -u +%FT%TZ) start $run_id ($manifest)"
    "$HOME/.bun/bin/bun" scripts/hosted-search-manifest.ts "'"$provider"'" "$run_id" "$manifest" "'"$conc"'" \
      > "$HOME/bench/memorybench/$run_id.log" 2>&1
    echo "$(date -u +%FT%TZ) end $run_id exit=$?"
  done
  echo "$(date -u +%FT%TZ) all batches finished"
' _ "$@" > "$driver_log" 2>&1 < /dev/null &
echo "driver pid $! on $(hostname); driver log $driver_log"

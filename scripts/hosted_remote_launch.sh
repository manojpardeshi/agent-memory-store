#!/usr/bin/env bash
# Runs ON the M2. Reads the provider key from stdin, exports it for one detached benchmark
# process, and exits. The key is never an argument, never written to disk, never logged.
#
# usage (key on stdin): hosted_remote_launch.sh VAR PROVIDER RUN_ID MANIFEST CONCURRENCY
# self-test (no provider contact): hosted_remote_launch.sh VAR selftest - - -
set -euo pipefail
var="$1"; provider="$2"; run_id="$3"; manifest="$4"; conc="$5"
case "$var" in MEM0_API_KEY|SUPERMEMORY_API_KEY) ;; *) echo "bad variable name" >&2; exit 2 ;; esac
IFS= read -r key || true
[ -n "${key:-}" ] || { echo "no key received on stdin" >&2; exit 2; }
export "$var=$key"
unset key
export MEM0_TELEMETRY=false   # the Mem0 JS client sends PostHog telemetry unless this is set

if [ "$provider" = "selftest" ]; then
  value="${!var}"
  echo "selftest: $var received, length ${#value}; in own argv: $(ps -o args= -p $$ | grep -c -- "$value" || true)"
  exit 0
fi

cd "$HOME/bench/memorybench"
log="$HOME/bench/memorybench/$run_id.log"
nohup caffeinate -i "$HOME/.bun/bin/bun" scripts/hosted-search-manifest.ts \
  "$provider" "$run_id" "$manifest" "$conc" >"$log" 2>&1 </dev/null &
echo "started pid $! on $(hostname); log $log"

#!/usr/bin/env bash
# Runs ON the M2. Operates a Supermemory Local server backed by loopback Ollama and runs the
# MemoryBench Supermemory provider against it. Free: no hosted API, no paid model.
#
# usage: supermemory_local_remote.sh start
#        supermemory_local_remote.sh run RUN_ID MANIFEST CONCURRENCY
#        supermemory_local_remote.sh sequential RUN_PREFIX MANIFEST
#        supermemory_local_remote.sh status RUN_ID
#        supermemory_local_remote.sh stop
#
# Supermemory Local v0.0.8 binds every interface and ignores SUPERMEMORY_HOST. `start` refuses
# to run unless the macOS application firewall is on and blocks incoming connections to the
# server binary, which the owner configures (it needs sudo). The harness reaches the server
# over loopback, which the application firewall does not filter.
#
# The harness reads the server's own owner-only key file ($data/api-key); the key is never
# printed or copied.
set -euo pipefail

bin="$HOME/.local/bin/supermemory-server"
fw=/usr/libexec/ApplicationFirewall/socketfilterfw
base="$HOME/bench/supermemory-local"
# data-v3: fresh store. Two bulk attempts (1,420 sessions queued at once) grew the server's
# in-memory queue until v0.0.8 crashed; `sequential` instead ingests one question at a time.
data="$base/data-v3"
server_log="$base/server.log"
key_file="$data/api-key"               # written by the server on first boot
bench="$HOME/bench/memorybench"
port=6767
mkdir -p "$data"
chmod 700 "$base"

listening() { lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; }

require_firewall_block() {
  "$fw" --getglobalstate | grep -q "State = 1" ||
    { echo "refusing to start: macOS firewall is off" >&2; exit 4; }
  "$fw" --getappblocked "$bin" | grep -q "is blocked" ||
    { echo "refusing to start: incoming connections to $bin are not blocked" >&2; exit 4; }
}

case "${1:?mode}" in
  start)
    if listening; then echo "already listening on $port"; exit 0; fi
    [ -x "$bin" ] || { echo "supermemory-server is not installed at $bin" >&2; exit 2; }
    require_firewall_block
    export SUPERMEMORY_DATA_DIR="$data"
    export SUPERMEMORY_HOST=127.0.0.1           # honoured from the release after v0.0.8
    export SUPERMEMORY_DISABLE_TELEMETRY=1
    export OPENAI_BASE_URL=http://127.0.0.1:11434/v1
    export OPENAI_API_KEY=ollama                 # Ollama accepts any non-empty key
    export OPENAI_MODEL=qwen2.5-7b-16k           # qwen2.5:7b with a 16k context, temperature 0
    cd "$base"
    nohup caffeinate -i "$bin" >"$server_log" 2>&1 </dev/null &
    echo "started pid $!"
    for _ in $(seq 1 180); do listening && break; sleep 1; done
    listening || { echo "server did not start; see $server_log" >&2; exit 3; }
    [ -s "$key_file" ] || echo "warning: server key file $key_file not found" >&2
    echo "listening on $port:"
    lsof -nP -iTCP:"$port" -sTCP:LISTEN | awk 'NR>1 {print "  " $9}' ;;
  run)
    run_id="${2:?run id}"; manifest="${3:?manifest}"; conc="${4:?concurrency}"
    [[ "$run_id" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "bad run id" >&2; exit 2; }
    [[ "$conc" =~ ^[1-4]$ ]] || { echo "concurrency must be 1 to 4" >&2; exit 2; }
    listening || { echo "server not running; use start" >&2; exit 2; }
    [ -s "$key_file" ] || { echo "no local API key at $key_file" >&2; exit 2; }
    export SUPERMEMORY_BASE_URL="http://127.0.0.1:$port"
    SUPERMEMORY_API_KEY="$(head -1 "$key_file")"
    export SUPERMEMORY_API_KEY
    cd "$bench"
    log="$bench/$run_id.log"
    nohup caffeinate -i "$HOME/.bun/bin/bun" scripts/hosted-search-manifest.ts \
      supermemory "$run_id" "$manifest" "$conc" >"$log" 2>&1 </dev/null &
    echo "started pid $! ; log $log" ;;
  sequential)
    # One question per run, restarting the server between questions so v0.0.8 never holds
    # more than one question's sessions in its queue. Resumable: finished questions are skipped.
    prefix="${2:?run prefix}"; manifest="${3:?manifest}"
    [[ "$prefix" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "bad run prefix" >&2; exit 2; }
    py="$HOME/.local/bin/python3.12"
    ids="$("$py" -c 'import json,sys; print(" ".join(json.load(open(sys.argv[1]))["question_ids"]))' "$bench/$manifest")"
    mkdir -p "$bench/manifests/$prefix"
    progress="$bench/$prefix.progress"
    for qid in $ids; do
      run_id="$prefix-$qid"
      checkpoint="$bench/data/runs/$run_id/checkpoint.json"
      if [ -f "$checkpoint" ] && grep -q '"search"' "$checkpoint" &&
        "$py" -c 'import json,sys; c=json.load(open(sys.argv[1])); q=next(iter(c["questions"].values())); sys.exit(0 if q["phases"]["search"].get("status")=="completed" else 1)' "$checkpoint"; then
        continue
      fi
      single="manifests/$prefix/$qid.json"
      printf '{"question_ids": ["%s"]}\n' "$qid" >"$bench/$single"
      for attempt in 1 2; do
        "$0" stop >/dev/null 2>&1 || true
        sleep 5
        if ! "$0" start >/dev/null 2>&1; then
          echo "$(date -u +%FT%TZ) $qid FAILED attempt $attempt (server did not start)" >>"$progress"
          continue
        fi
        export SUPERMEMORY_BASE_URL="http://127.0.0.1:$port"
        SUPERMEMORY_API_KEY="$(head -1 "$key_file")"
        export SUPERMEMORY_API_KEY
        force=""; [ "$attempt" -gt 1 ] && force="--force"   # retry from scratch, not resume
        started=$(date +%s)
        (cd "$bench" && exec caffeinate -i "$HOME/.bun/bin/bun" scripts/hosted-search-manifest.ts \
          supermemory "$run_id" "$single" 1 $force >"$bench/$run_id.log" 2>&1 </dev/null) &
        harness=$!
        # Watchdog: the harness waits forever on indexing if the server dies, so stop it when
        # the server goes down or the question exceeds three hours.
        reason=""
        while kill -0 "$harness" 2>/dev/null; do
          sleep 30
          listening || { reason="server down"; break; }
          [ $(( $(date +%s) - started )) -gt 10800 ] && { reason="timeout"; break; }
        done
        if [ -n "$reason" ]; then
          pkill -P "$harness" 2>/dev/null || true
          kill "$harness" 2>/dev/null || true
          wait "$harness" 2>/dev/null || true
          echo "$(date -u +%FT%TZ) $qid FAILED attempt $attempt ($reason)" >>"$progress"
          continue
        fi
        if wait "$harness"; then
          echo "$(date -u +%FT%TZ) $qid done in $(( $(date +%s) - started ))s (attempt $attempt)" >>"$progress"
          break
        fi
        echo "$(date -u +%FT%TZ) $qid FAILED attempt $attempt (harness error)" >>"$progress"
      done
    done
    "$0" stop >/dev/null 2>&1 || true
    echo "$(date -u +%FT%TZ) sequence finished" >>"$progress" ;;
  status)
    run_id="${2:?run id}"
    if listening; then echo "server: listening"; else echo "server: DOWN"; fi
    tail -5 "$bench/$run_id.log" 2>/dev/null || echo "no log for $run_id" ;;
  stop)
    # $bin is a wrapper that execs the real binary, so match the real binary's path; also stop
    # the per-data-directory workflow engine it spawns, which otherwise outlives a crash.
    stopped=""
    pkill -f "$HOME/.supermemory/bin/supermemory-server" && stopped=1
    pkill -f "$data/runtime/rivet/rivet-engine" && stopped=1
    # The data directory stays locked until the old server has exited, so wait for it.
    for _ in $(seq 1 60); do
      pgrep -f "$HOME/.supermemory/bin/supermemory-server" >/dev/null || break
      sleep 1
    done
    if [ -n "$stopped" ]; then echo stopped; else echo "not running"; fi ;;
  *) echo "unknown mode" >&2; exit 2 ;;
esac

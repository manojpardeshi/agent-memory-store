#!/usr/bin/env bash
# Runs ON the M2. Operates a Supermemory Local server backed by loopback Ollama and runs the
# MemoryBench Supermemory provider against it. Free: no hosted API, no paid model.
#
# usage: supermemory_local_remote.sh start
#        supermemory_local_remote.sh run RUN_ID MANIFEST CONCURRENCY
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
data="$base/data"
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
  status)
    run_id="${2:?run id}"
    if listening; then echo "server: listening"; else echo "server: DOWN"; fi
    tail -5 "$bench/$run_id.log" 2>/dev/null || echo "no log for $run_id" ;;
  stop)
    if pkill -f "$bin"; then echo stopped; else echo "not running"; fi ;;
  *) echo "unknown mode" >&2; exit 2 ;;
esac

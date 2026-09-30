#!/usr/bin/env bash
# Launch or fetch a hosted comparator run on the M2 over the Thunderbolt link.
#
# The provider key is read from THIS Mac's Keychain and streamed over SSH stdin to a launcher
# on the M2, which exports it for the one benchmark process it starts. There is one stored
# copy of the key. It never appears in any command line, file, log, or report.
#
# usage: scripts/run_hosted_comparator.sh launch {mem0|supermemory} RUN_ID MANIFEST CONCURRENCY
#        scripts/run_hosted_comparator.sh selftest {mem0|supermemory}
#        scripts/run_hosted_comparator.sh status RUN_ID
#        scripts/run_hosted_comparator.sh fetch RUN_ID
set -euo pipefail

host="${HOSTED_HOST:-manojpardeshi@10.10.10.2}"
repo="$(cd "$(dirname "$0")/.." && pwd)"
local_bench="$repo/demo-artifacts/memorybench/upstream"
remote_bench="bench/memorybench"
ssh_opts=(-o BatchMode=yes -o ConnectTimeout=10)
mode="${1:?mode}"

key_for() {
  local service
  case "$1" in
    mem0) service="agent-memory-store-mem0-api"; var="MEM0_API_KEY" ;;
    supermemory) service="agent-memory-store-supermemory-api"; var="SUPERMEMORY_API_KEY" ;;
    *) echo "provider must be mem0 or supermemory" >&2; exit 2 ;;
  esac
  key="$(security find-generic-password -s "$service" -w 2>/dev/null)" || {
    echo "Keychain item $service not found on this Mac; store the key first" >&2; exit 2; }
  [ -n "$key" ] || { echo "Keychain item $service is empty" >&2; exit 2; }
}

push_tools() {
  scp -q "${ssh_opts[@]}" "$repo/evaluation/memorybench/hosted-search-manifest.ts" \
    "$repo/scripts/hosted_remote_launch.sh" "$host:$remote_bench/scripts/"
  ssh "${ssh_opts[@]}" "$host" "chmod +x $remote_bench/scripts/hosted_remote_launch.sh; mkdir -p $remote_bench/manifests"
}

case "$mode" in
  selftest)
    key_for "${2:?provider}"; push_tools
    printf '%s\n' "$key" | ssh "${ssh_opts[@]}" "$host" "$remote_bench/scripts/hosted_remote_launch.sh $var selftest - - -"
    unset key ;;
  launch)
    provider="${2:?provider}"; run_id="${3:?run id}"; manifest="${4:?manifest}"; conc="${5:?concurrency}"
    [[ "$run_id" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "run id may use letters, digits, . _ -" >&2; exit 2; }
    [[ "$conc" =~ ^[1-8]$ ]] || { echo "concurrency must be 1 to 8" >&2; exit 2; }
    key_for "$provider"; push_tools
    name="$(basename "$manifest")"
    scp -q "${ssh_opts[@]}" "$repo/$manifest" "$host:$remote_bench/manifests/$name"
    # printf is a bash builtin, so the key is not on this side's argv either.
    printf '%s\n' "$key" | ssh "${ssh_opts[@]}" "$host" \
      "$remote_bench/scripts/hosted_remote_launch.sh $var $provider $run_id manifests/$name $conc"
    unset key ;;
  status)
    run_id="${2:?run id}"
    ssh "${ssh_opts[@]}" "$host" "tail -5 $remote_bench/$run_id.log; pgrep -fl 'hosted-search-manifest.ts.*$run_id' || echo '(process not running)'" ;;
  fetch)
    run_id="${2:?run id}"
    mkdir -p "$local_bench/data/runs/$run_id"
    rsync -a -e "ssh ${ssh_opts[*]}" "$host:$remote_bench/data/runs/$run_id/" "$local_bench/data/runs/$run_id/"
    echo "fetched to $local_bench/data/runs/$run_id" ;;
  *) echo "mode must be selftest, launch, status, or fetch" >&2; exit 2 ;;
esac

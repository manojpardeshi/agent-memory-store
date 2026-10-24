#!/usr/bin/env bash
# Check the Rocq proofs in proofs/ on the machine that has Rocq installed.
#
#   scripts/check_proofs.sh            # from the repository root
#
# Steps: reject forbidden constructs in the sources, copy proofs/ to the
# remote host, compile every file with coqc, require every
# `Print Assumptions` in a file to report "Closed under the global context",
# then re-check every compiled module with coqchk (Rocq's independent
# checker) and require it to report no axioms.  Exits non-zero on any failure.
#
# Environment overrides:
#   PROOF_HOST  ssh destination           (default manojpardeshi@10.10.10.2)
#   PROOF_DIR   remote working directory  (default agent-memory-proofs)
#   ROCQ_BIN    directory of coqc/coqchk  (default /opt/homebrew/bin)
#   PROOF_TIMEOUT  per-command time limit in seconds (default 600); every
#                  remote coqc/coqchk runs under perl alarm and is killed
#                  when it exceeds the limit
set -euo pipefail

HOST="${PROOF_HOST:-manojpardeshi@10.10.10.2}"
RDIR="${PROOF_DIR:-agent-memory-proofs}"
BIN="${ROCQ_BIN:-/opt/homebrew/bin}"
LIMIT="${PROOF_TIMEOUT:-600}"
# Remote command prefix: SIGALRM kills the checker after LIMIT seconds.
ALARM="perl -e 'alarm $LIMIT; exec @ARGV' --"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15)

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROOFS="$ROOT/proofs"
MODULES=(KeywordQuery RankFusion HeldOutLedger OccurredAt RerankOrder)

fail() { echo "FAIL: $*" >&2; exit 1; }

[[ -d "$PROOFS" ]] || fail "missing $PROOFS"
for m in "${MODULES[@]}"; do
  [[ -f "$PROOFS/$m.v" ]] || fail "missing proofs/$m.v"
done

echo "== static scan for forbidden constructs"
# Section-local Context declarations are allowed; they become ordinary
# universally quantified arguments when the section closes.
SOURCES=()
for m in "${MODULES[@]}"; do SOURCES+=("$PROOFS/$m.v"); done
if grep -nwE 'Admitted|admit|Axiom|Axioms|Parameter|Parameters|Conjecture|Abort|Hypothesis|Hypotheses|Variable|Variables' \
     "${SOURCES[@]}"; then
  fail "forbidden construct found (see lines above)"
fi
echo "ok: no Admitted/admit/Axiom/Parameter/Conjecture/Abort/Hypothesis/Variable"

echo "== copying proofs/ to $HOST:~/$RDIR"
ssh "${SSH_OPTS[@]}" "$HOST" "rm -rf ~/'$RDIR' && mkdir -p ~/'$RDIR'"
scp -q "${SSH_OPTS[@]}" "$PROOFS"/*.v "$PROOFS"/_CoqProject "$HOST:~/$RDIR/"

LOGDIR="$(mktemp -d)"
trap 'rm -rf "$LOGDIR"' EXIT

total_theorems=0
for m in "${MODULES[@]}"; do
  echo "== coqc $m.v"
  if ! ssh "${SSH_OPTS[@]}" "$HOST" "cd ~/'$RDIR' && $ALARM '$BIN/coqc' -Q . AMS '$m.v'" \
       >"$LOGDIR/$m.log" 2>&1; then
    cat "$LOGDIR/$m.log" >&2
    fail "coqc failed on $m.v (or exceeded ${LIMIT}s)"
  fi
  expected=$(grep -cE '^[[:space:]]*Print Assumptions ' "$PROOFS/$m.v" || true)
  closed=$(grep -c 'Closed under the global context' "$LOGDIR/$m.log" || true)
  if grep -qE '^Axioms:|Admitted|Error' "$LOGDIR/$m.log"; then
    cat "$LOGDIR/$m.log" >&2
    fail "$m.v: an assumption report lists axioms or the log contains an error"
  fi
  [[ "$expected" -gt 0 ]] || fail "$m.v has no Print Assumptions"
  if [[ "$closed" -ne "$expected" ]]; then
    cat "$LOGDIR/$m.log" >&2
    fail "$m.v: $closed of $expected Print Assumptions report 'Closed under the global context'"
  fi
  echo "ok: $m.v compiled; $closed/$expected theorems closed under the global context"
  total_theorems=$((total_theorems + closed))
done

echo "== coqchk (independent kernel re-check of every module)"
qualified=("${MODULES[@]/#/AMS.}")
if ! ssh "${SSH_OPTS[@]}" "$HOST" \
     "cd ~/'$RDIR' && $ALARM '$BIN/coqchk' -silent -o -Q . AMS ${qualified[*]}" \
     >"$LOGDIR/coqchk.log" 2>&1; then
  cat "$LOGDIR/coqchk.log" >&2
  fail "coqchk rejected the compiled modules (or exceeded ${LIMIT}s)"
fi
for line in '\* Axioms: <none>' \
            '\* Constants/Inductives relying on type-in-type: <none>' \
            '\* Constants/Inductives relying on unsafe \(co\)fixpoints: <none>' \
            '\* Inductives whose positivity is assumed: <none>'; do
  grep -qE "$line" "$LOGDIR/coqchk.log" || { cat "$LOGDIR/coqchk.log" >&2; fail "coqchk report lacks: $line"; }
done
echo "ok: coqchk verified ${qualified[*]}: no axioms, no type-in-type, no unsafe fixpoints, no assumed positivity"

echo "== summary: ${#MODULES[@]} files, $total_theorems Print Assumptions all closed; coqchk clean"

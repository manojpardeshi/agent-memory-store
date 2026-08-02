# Kimi Paired Answer-Quality Development Contract

Date: 2026-08-01
Status: frozen before paid execution

The already-observed stratified 60 development questions compare the released ranked top ten with
the single frozen `session-diverse-v1` context policy. Exact `kimi-k3` produces one answer and three
blind judge votes per arm. Calls are interleaved deterministically by question and share one $5
hard ledger. The candidate is the only changed variable.

The deterministic preflight passed before any paid call: all 60 questions are development data,
validation and reserve overlap are zero, every context exists, baseline checkpoint results match
their result files, and the candidate reduces mean/p95 formatted context bytes from
30,634.8/43,984 to 25,943.25/36,259.

Automated promotion requires at least 42/60 candidate answers, overall non-inferiority within one
answer, at least two additional correct answers across multi-session plus temporal questions, no
more than one lost answer across the other four categories or any single category, balanced judge
unanimity, exact model identity, zero failed calls, and the frozen context/budget gates.

Every majority-discordant question and every non-unanimous answer is then human-scored blind. Human
labels replace model labels for audited answers, a deterministic 20% repeat checks grader
reliability, and the scoring gates are rerun. Fewer than four audit questions is inconclusive.

Passing authorizes only a request to run one sealed comparison. It does not authorize opening the
sealed split automatically, shipping the policy, or making an external claim. The machine contract
is `evaluation/memorybench/kimi-paired-answer-development-gates-v1.json`.

"use client";

import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import measuredReport from "../../../docs/demo/results/2026-07-19-live-provider-matrix-llama3-1-8b.json";
import measuredReview from "../../../docs/demo/results/2026-07-20-proposal-review-synthetic.json";

type Usage = { input_tokens?: number; cached_input_tokens?: number; output_tokens?: number } | null;
type Transfer = {
  transfer_id: string;
  from_model: string;
  to_model: string;
  phase: string;
  origin: string;
  memory_item_count: number;
  memory_ids: string[];
  memory_character_count: number;
  memory_utf8_byte_count: number;
  estimated_memory_tokens: number;
  token_estimate_method: string;
  prompt_character_count: number;
  memory_share_of_prompt: number;
  bundle_character_budget: number;
  bundle_budget_utilization: number;
  truncated: boolean;
};
type ConsumerResult = {
  consumer_key: string;
  model: string;
  metrics: {
    baseline_accuracy: number;
    memory_accuracy: number;
    memory_lift: number;
    shared_recall_hit_rate: number;
    private_isolation_violations: number;
  };
  provider_usage?: { baseline: Usage; memory_assisted: Usage; input_token_delta?: number | null; delta_scope?: string | null };
  context_transfer_id: string;
};
type DemoReport = {
  schema_version: number;
  run_id: string;
  mode: string;
  completed_at?: string;
  models: {
    producer?: string;
    consumers?: string[];
    model_a?: string;
    model_b?: string;
    switch_sequence: string[];
  };
  local_model?: { included: boolean; provider: string; model: string | null; status: string };
  consumer_results?: ConsumerResult[];
  synthetic_profile: {
    project_code: string;
    editor_preference: string;
    locale_preference: string;
    corrected_editor_preference: string;
  };
  metrics: {
    consumer_count?: number;
    baseline_accuracy: number;
    memory_accuracy: number;
    memory_lift: number;
    correction_accuracy: number;
    stale_value_leaks: number;
    private_isolation_violations: number;
  };
  acceptance: { passed: boolean; gating: boolean };
  context_transfers: Transfer[];
};
type ProposalReviewItem = {
  proposal_id: string;
  kind: string;
  primary_status: string;
  acceptance_ready: boolean;
  recommended_action: string;
  source_memory_ids: string[];
  exact_duplicate_memory_ids: string[];
  exact_duplicate_proposal_ids: string[];
  kind_collision_memory_ids: string[];
  kind_collision_proposal_ids: string[];
  content?: string;
};
type ProposalReviewReport = {
  schema_version: 1;
  bundle_digest: string;
  target_scope: { kind: string; subject: string; environment: string; owner: string };
  proposal_content_included: boolean;
  source_content_included: boolean;
  read_only: true;
  counts: {
    source_count: number;
    proposal_count: number;
    acceptance_ready_count: number;
    source_statuses: Record<string, number>;
    proposal_statuses: Record<string, number>;
  };
  proposals: ProposalReviewItem[];
};
const REVIEW_STATUSES = new Set(["blocked_source", "operation_collision", "replayed_superseded", "replayed_expired", "accepted_replay", "exact_duplicate", "kind_collision", "new"]);
const REVIEW_ID = /^[0-9a-f]{64}$/;
const MAX_REVIEW_REPORT_BYTES = 1_000_000;

function percent(value: number) { return `${Math.round(value * 100)}%`; }
function slotCount(value: number, total: number) { return `${Math.round(value * total)}/${total}`; }
function titleCase(value: string) { return value.replace(/-/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function modelLabel(model: string) {
  if (model.startsWith("claude-")) return `Claude ${titleCase(model.slice(7))}`;
  if (model.startsWith("codex-gpt-")) return `GPT ${titleCase(model.slice(10))}`;
  if (model.startsWith("ollama-http-")) return `${model.slice(12)} (Local)`;
  if (model.startsWith("codex-ollama-")) return `Local ${titleCase(model.slice(13))}`;
  return titleCase(model.replace("offline-", ""));
}
function modelInitial(model: string) {
  if (model.includes("gpt")) return "G";
  if (model.includes("sonnet")) return "S";
  if (model.includes("qwen")) return "Q";
  if (model.includes("llama")) return "L";
  if (model.includes("local") || model.includes("ollama") || model.includes("lmstudio")) return "L";
  return "H";
}
function providerName(model: string) {
  if (model.startsWith("codex-")) return "CODEX CLI / OPENAI";
  if (model.startsWith("claude-")) return "CLAUDE CLI / ANTHROPIC";
  if (model.startsWith("ollama-http-")) return "OLLAMA HTTP / LOCAL";
  return "OFFLINE TEST DOUBLE";
}
function isReport(value: unknown): value is DemoReport {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<DemoReport>;
  return Boolean(
    (candidate.schema_version === 2 || candidate.schema_version === 3) &&
    Array.isArray(candidate.context_transfers) &&
    candidate.context_transfers.length >= 2 &&
    candidate.metrics && candidate.models && candidate.acceptance,
  );
}
function isReviewReport(value: unknown): value is ProposalReviewReport {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<ProposalReviewReport>;
  const scope = candidate.target_scope;
  const counts = candidate.counts;
  const proposals = candidate.proposals;
  return Boolean(
    candidate.schema_version === 1 && candidate.read_only === true &&
    typeof candidate.bundle_digest === "string" && REVIEW_ID.test(candidate.bundle_digest) &&
    scope && [scope.kind, scope.subject, scope.environment, scope.owner].every((item) => typeof item === "string" && item.length > 0 && item.length <= 256) &&
    counts && [counts.source_count, counts.proposal_count, counts.acceptance_ready_count].every((item) => Number.isInteger(item) && item >= 0) &&
    Array.isArray(proposals) && proposals.length <= 50 && counts.proposal_count === proposals.length &&
    proposals.every((proposal) =>
      proposal && REVIEW_ID.test(proposal.proposal_id) &&
      ["fact", "preference", "summary", "event"].includes(proposal.kind) &&
      REVIEW_STATUSES.has(proposal.primary_status) && typeof proposal.acceptance_ready === "boolean" &&
      typeof proposal.recommended_action === "string" && proposal.recommended_action.length <= 128 &&
      Array.isArray(proposal.source_memory_ids) && proposal.source_memory_ids.length > 0 && proposal.source_memory_ids.length <= 20 &&
      Array.isArray(proposal.exact_duplicate_memory_ids) && Array.isArray(proposal.exact_duplicate_proposal_ids) &&
      Array.isArray(proposal.kind_collision_memory_ids) && Array.isArray(proposal.kind_collision_proposal_ids) &&
      (proposal.content === undefined || (typeof proposal.content === "string" && proposal.content.length <= 2000)),
    ),
  );
}
function shortId(value: string) { return `${value.slice(0, 8)}…${value.slice(-6)}`; }
function lastStepFor(report: DemoReport) {
  const count = report.models.consumers?.length ?? (report.models.model_b ? 1 : Math.max(1, report.models.switch_sequence.length - 2));
  return count + 2;
}

export default function Home() {
  const [report, setReport] = useState<DemoReport>(measuredReport as DemoReport);
  const [activeStep, setActiveStep] = useState(() => lastStepFor(measuredReport as DemoReport));
  const [playing, setPlaying] = useState(false);
  const [transferIndex, setTransferIndex] = useState(0);
  const [fileError, setFileError] = useState("");
  const [reviewReport, setReviewReport] = useState<ProposalReviewReport | null>(measuredReview as ProposalReviewReport);
  const [reviewError, setReviewError] = useState("");
  const [selectedProposalIds, setSelectedProposalIds] = useState<string[]>([]);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const producer = report.models.producer ?? report.models.model_a ?? report.models.switch_sequence[0];
  const consumers = useMemo(
    () => report.models.consumers ?? (report.models.model_b ? [report.models.model_b] : report.models.switch_sequence.slice(1, -1)),
    [report.models.consumers, report.models.model_b, report.models.switch_sequence],
  );
  const consumerResults: ConsumerResult[] = report.consumer_results ?? consumers.map((model, index) => ({
    consumer_key: `legacy-${index}`,
    model,
    metrics: {
      baseline_accuracy: report.metrics.baseline_accuracy,
      memory_accuracy: report.metrics.memory_accuracy,
      memory_lift: report.metrics.memory_lift,
      shared_recall_hit_rate: report.metrics.memory_accuracy,
      private_isolation_violations: report.metrics.private_isolation_violations,
    },
    context_transfer_id: report.context_transfers[index]?.transfer_id ?? "legacy",
  }));
  const steps = useMemo(() => [
    { label: "Capture", detail: `${modelLabel(producer)} receives three unpredictable synthetic facts.`, model: producer, transfer: -1 },
    { label: "Remember", detail: "The harness writes typed facts into one explicit shared memory pool.", model: "memory-store", transfer: -1 },
    ...consumers.map((model, index) => ({
      label: model.includes("gpt") ? "GPT handoff" : `${modelLabel(model).replace("Claude ", "")} handoff`,
      detail: `${modelLabel(model)} starts cold, recalls 0/3 slots without memory, then receives the measured bundle.`,
      model,
      transfer: index,
    })),
    { label: "Return", detail: `${modelLabel(producer)} receives the corrected active preference after the provider matrix.`, model: producer, transfer: report.context_transfers.length - 1 },
  ], [consumers, producer, report.context_transfers.length]);

  useEffect(() => {
    if (!playing) return;
    intervalRef.current = setInterval(() => {
      setActiveStep((current) => {
        if (current >= steps.length - 1) {
          setPlaying(false);
          return current;
        }
        const next = current + 1;
        if (steps[next].transfer >= 0) setTransferIndex(steps[next].transfer);
        return next;
      });
    }, 1050);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [playing, steps]);

  function replay() {
    if (intervalRef.current) clearInterval(intervalRef.current);
    setTransferIndex(0);
    setActiveStep(0);
    setPlaying(true);
  }
  async function loadReport(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      if (file.size > MAX_REVIEW_REPORT_BYTES) throw new Error("Review report exceeds the 1 MB limit");
      const parsed: unknown = JSON.parse(await file.text());
      if (!isReport(parsed)) throw new Error("Expected a schema-v2 or schema-v3 demo report");
      setReport(parsed);
      setActiveStep(lastStepFor(parsed));
      setTransferIndex(0);
      setPlaying(false);
      setFileError("");
    } catch (error) {
      setFileError(error instanceof Error ? error.message : "Could not read report");
    } finally { event.target.value = ""; }
  }
  async function loadReviewReport(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const parsed: unknown = JSON.parse(await file.text());
      if (!isReviewReport(parsed)) throw new Error("Expected a schema-v1 read-only review report");
      setReviewReport(parsed);
      setSelectedProposalIds([]);
      setReviewError("");
    } catch (error) {
      setReviewError(error instanceof Error ? error.message : "Could not read review report");
    } finally { event.target.value = ""; }
  }
  function toggleProposal(proposalId: string) {
    setSelectedProposalIds((current) => current.includes(proposalId) ? current.filter((id) => id !== proposalId) : [...current, proposalId]);
  }

  const safeStep = Math.max(0, Math.min(activeStep, steps.length - 1));
  const transfer = report.context_transfers[Math.min(transferIndex, report.context_transfers.length - 1)];
  const memoryWidth = Math.max(4, transfer.bundle_budget_utilization * 100);
  const fields = [
    ["Project", report.synthetic_profile.project_code],
    ["Editor", report.synthetic_profile.editor_preference],
    ["Locale", report.synthetic_profile.locale_preference],
  ];
  const local = report.local_model ?? { included: false, provider: "ollama", model: null, status: "adapter-ready-not-run" };

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="Memory Handoff Lab home">
          <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span><span>Memory Handoff Lab</span>
        </a>
        <div className="topbar-meta"><span className="privacy-pill"><span /> Local evidence</span><span className="run-id">{report.run_id}</span></div>
      </header>

      <section className="hero" id="top">
        <div>
          <p className="eyebrow">CROSS-PROVIDER MEMORY / RECORDED LIVE RUN</p>
          <h1>Change providers.<br /><em>Keep the facts.</em></h1>
          <p className="hero-copy">One local memory pool, replayed across fresh Claude, GPT, and Llama sessions—including a real loopback Ollama run.</p>
        </div>
        <div className="hero-actions">
          <button className="primary-button" onClick={replay} disabled={playing}><span className="play-icon" aria-hidden="true" />{playing ? "Replaying…" : "Replay measured run"}</button>
          <label className="secondary-button">Load report<input type="file" accept="application/json,.json" onChange={loadReport} /></label>
          <p className="privacy-copy">File stays in your browser. Nothing is uploaded.</p>
          {fileError && <p className="file-error" role="alert">{fileError}</p>}
        </div>
      </section>

      <section className="switch-card" aria-label="Provider matrix timeline">
        <div className="card-kicker"><span>Recorded live provider sequence</span><span className={report.acceptance.passed ? "passed" : "failed"}>{report.acceptance.passed ? "All checks passed" : "Checks failed"}</span></div>
        <div className="matrix-track">
          {steps.map((step, index) => (
            <div className="matrix-unit" key={`${step.label}-${index}`}>
              {index > 0 && <div className={`matrix-arrow ${index <= safeStep ? "complete" : ""}`}><span>→</span></div>}
              <article className={`model-node ${step.model === "memory-store" ? "store" : step.model.includes("gpt") ? "gpt" : "claude"} ${index === safeStep ? "active" : ""}`}>
                <span className="node-index">{String(index + 1).padStart(2, "0")}</span>
                {step.model === "memory-store" ? <div className="store-orb"><span /><span /><span /></div> : <div className="model-orb">{modelInitial(step.model)}</div>}
                <div><small>{step.model === "memory-store" ? "LOCAL SHARED POOL" : providerName(step.model)}</small><h2>{step.model === "memory-store" ? "Memory store" : modelLabel(step.model)}</h2></div>
              </article>
            </div>
          ))}
        </div>
        <div className="step-strip" style={{ gridTemplateColumns: `repeat(${steps.length}, minmax(110px, 1fr))` }} aria-live="polite">
          {steps.map((step, index) => <button key={`${step.label}-button`} className={index === safeStep ? "current" : index < safeStep ? "done" : ""} onClick={() => { setPlaying(false); setActiveStep(index); if (step.transfer >= 0) setTransferIndex(step.transfer); }}><span>{String(index + 1).padStart(2, "0")}</span><strong>{step.label}</strong></button>)}
        </div>
        <p className="step-narration"><b>{steps[safeStep].label}.</b> {steps[safeStep].detail}</p>
      </section>

      <section className="provider-results" aria-label="Per-model results">
        <div className="section-heading"><div><p className="eyebrow">CONSUMER MATRIX</p><h2>Same memory. Independent fresh sessions.</h2></div><span className="evidence-mode">{report.mode}</span></div>
        <div className="result-table">
          <div className="result-head"><span>Consumer</span><span>No memory</span><span>With memory</span><span>Bundle</span><span>Whole model turn</span></div>
          {consumerResults.map((result, index) => {
            const itemTransfer = report.context_transfers.find((item) => item.transfer_id === result.context_transfer_id) ?? report.context_transfers[index];
            const totalInput = result.provider_usage?.memory_assisted?.input_tokens;
            const inputDelta = result.provider_usage?.input_token_delta;
            return <div className="result-row" key={result.consumer_key}>
              <span><b>{modelLabel(result.model)}</b><small>{providerName(result.model)}</small></span>
              <span className="score cold">{slotCount(result.metrics.baseline_accuracy, 3)}</span>
              <span className="score warm">{slotCount(result.metrics.memory_accuracy, 3)}</span>
              <span><b>{itemTransfer?.memory_utf8_byte_count ?? "—"} bytes</b><small>~{itemTransfer?.estimated_memory_tokens ?? "—"} tokens · chars ÷ 4 heuristic</small></span>
              <span><b>{inputDelta !== null && inputDelta !== undefined ? `+${inputDelta.toLocaleString()} tokens` : "Not exposed"}</b><small>{totalInput ? `${totalInput.toLocaleString()} assisted total · assisted − baseline` : "CLI usage unavailable"}</small></span>
            </div>;
          })}
        </div>
        <p className="method-note">Single-run item counts. Token totals are transport-specific: Codex CLI includes agent/runtime scaffolding; Ollama counts the direct prompt. Do not compare them as provider benchmarks. Each +delta is assisted minus baseline for the whole prompt, not the memory-only cost; ~tokens is a separate chars ÷ 4 heuristic.</p>
        <div className="local-ready-row"><div className="local-icon">L</div><div><small>{local.status === "live-measured" ? "LOCAL CONSUMER" : "FUTURE LOCAL CONSUMER"}</small><strong>{local.status === "live-measured" ? `${local.model} via ${titleCase(local.provider)}` : `Local adapter ready for ${titleCase(local.provider)}`}</strong><p>{local.status === "live-measured" ? "Single-run, harness-injected evidence: fresh baseline, memory-assisted recall, native token counts, and isolation checks." : "No live local-model evidence yet. Install a runtime and choose a model; the same checks will run."}</p></div><span>{local.status === "live-measured" ? "LIVE MEASURED · SINGLE RUN" : "NOT MEASURED"}</span></div>
      </section>

      <section className="dashboard-grid">
        <article className="transfer-card">
          <div className="section-heading"><div><p className="eyebrow">CONTEXT TRANSFER</p><h2>What entered each prompt?</h2></div><div className="transfer-tabs" role="tablist" aria-label="Context transfers">{report.context_transfers.map((item, index) => <button key={item.transfer_id} role="tab" aria-selected={transferIndex === index} className={transferIndex === index ? "selected" : ""} onClick={() => setTransferIndex(index)}>{index === report.context_transfers.length - 1 ? "Return" : modelInitial(item.to_model)}</button>)}</div></div>
          <div className="handoff-route"><span>{modelLabel(transfer.from_model)}</span><i>→</i><span>{modelLabel(transfer.to_model)}</span></div>
          <div className="transfer-stats"><div><strong>{transfer.memory_item_count}</strong><span>memory items</span></div><div><strong>{transfer.memory_character_count.toLocaleString()}</strong><span>characters · exact</span></div><div><strong>{transfer.memory_utf8_byte_count.toLocaleString()}</strong><span>UTF-8 bytes · exact</span></div><div><strong>~{transfer.estimated_memory_tokens.toLocaleString()}</strong><span>memory tokens · estimate</span></div></div>
          <div className="budget-block"><div className="budget-label"><span>Bundle budget used</span><strong>{percent(transfer.bundle_budget_utilization)}</strong></div><div className="budget-track"><span style={{ width: `${memoryWidth}%` }} /></div><div className="budget-foot"><span>{transfer.memory_character_count.toLocaleString()} included</span><span>{transfer.bundle_character_budget.toLocaleString()} character limit</span></div></div>
          <div className="prompt-composition"><span className="composition-memory" style={{ width: `${transfer.memory_share_of_prompt * 100}%` }} /><span className="composition-instructions" /></div>
          <div className="composition-legend"><span><i className="memory-dot" /> Memory {percent(transfer.memory_share_of_prompt)}</span><span><i /> Harness instructions {percent(1 - transfer.memory_share_of_prompt)}</span><b>{transfer.prompt_character_count.toLocaleString()} harness-prompt characters</b></div>
          <p className="method-note">Heuristic cross-provider approximation: {transfer.token_estimate_method}. It is not tokenizer output. Provider totals use different transport shapes and are not directly comparable.</p>
        </article>

        <article className="accuracy-card">
          <div className="section-heading"><div><p className="eyebrow">THIS RUN / AGGREGATE</p><h2>Every consumer recovered the facts.</h2></div></div>
          <div className="accuracy-bars"><div><span>Without memory</span><strong>{slotCount(report.metrics.baseline_accuracy, consumerResults.length * 3)}</strong><i><b style={{ width: `${report.metrics.baseline_accuracy * 100}%` }} /></i></div><div className="with-memory"><span>With memory</span><strong>{slotCount(report.metrics.memory_accuracy, consumerResults.length * 3)}</strong><i><b style={{ width: `${report.metrics.memory_accuracy * 100}%` }} /></i></div></div>
          <div className="lift-callout"><strong>+{Math.round(report.metrics.memory_lift * consumerResults.length * 3)}</strong><span>additional correct slots in this run</span></div>
          <div className="check-grid"><div><span className="check">✓</span><p><strong>{consumerResults.length}</strong> measured consumers</p></div><div><span className="check">✓</span><p><strong>{slotCount(report.metrics.correction_accuracy, 1)}</strong> corrected value</p></div><div><span className="check">✓</span><p><strong>{report.metrics.private_isolation_violations}</strong> private-scope violations</p></div></div>
        </article>
      </section>

      <section className="review-card" aria-label="Deterministic proposal review">
        <div className="section-heading">
          <div><p className="eyebrow">READ-ONLY MEMORY REVIEW</p><h2>Inspect before anything becomes durable.</h2></div>
          <label className="secondary-button review-loader">Load review report<input type="file" accept="application/json,.json" onChange={loadReviewReport} /></label>
        </div>
        <p className="review-intro">The initial row is a synthetic example. Generate a source-aware report with the local CLI, then load, inspect, and select it here. This browser view never opens SQLite and cannot accept a proposal.</p>
        {reviewError && <p className="file-error" role="alert">{reviewError}</p>}
        {!reviewReport ? <div className="review-empty"><strong>No review report loaded</strong><span>Content remains hidden unless the CLI report was created with an explicit reveal flag.</span></div> : <>
          <div className="review-metrics">
            <div><strong>{reviewReport.counts.proposal_count}</strong><span>proposals</span></div>
            <div><strong>{reviewReport.counts.acceptance_ready_count}</strong><span>acceptance-ready</span></div>
            <div><strong>{reviewReport.counts.source_count}</strong><span>source snapshots</span></div>
            <div><strong>{selectedProposalIds.length}</strong><span>selected locally</span></div>
          </div>
          <div className="review-scope"><span>{reviewReport.target_scope.kind}</span><code>{reviewReport.target_scope.subject} / {reviewReport.target_scope.environment} / {reviewReport.target_scope.owner}</code><b>digest {shortId(reviewReport.bundle_digest)}</b></div>
          <div className="proposal-list">
            {reviewReport.proposals.map((proposal) => <label className={`proposal-row ${proposal.acceptance_ready ? "ready" : "blocked"}`} key={proposal.proposal_id}>
              <input type="checkbox" checked={selectedProposalIds.includes(proposal.proposal_id)} disabled={!proposal.acceptance_ready} onChange={() => toggleProposal(proposal.proposal_id)} />
              <span><small>{proposal.kind} · {shortId(proposal.proposal_id)}</small><strong>{proposal.content ?? "Proposal content hidden in this report"}</strong><em>{proposal.recommended_action.replaceAll("_", " ")}</em></span>
              <i>{proposal.primary_status.replaceAll("_", " ")}</i>
            </label>)}
          </div>
          <div className="review-selection"><div><strong>{selectedProposalIds.length} selected</strong><span>Selection changes only this browser tab. Acceptance still requires explicit proposal IDs, bundle digest, and <code>--yes</code> in the CLI.</span></div><code>{selectedProposalIds.length ? selectedProposalIds.map(shortId).join(" · ") : "No proposal IDs selected"}</code></div>
        </>}
      </section>

      <section className="evidence-card">
        <div className="section-heading"><div><p className="eyebrow">SYNTHETIC EVIDENCE</p><h2>The facts both Claude and GPT recovered</h2></div><span className="evidence-mode">schema v{report.schema_version}</span></div>
        <div className="fact-list">{fields.map(([name, value], index) => <div key={name}><span>{String(index + 1).padStart(2, "0")}</span><strong>{name}</strong><code>{value}</code><i>recalled</i></div>)}</div>
        <div className="correction-row"><span>Correction preserved on return</span><code>{report.synthetic_profile.editor_preference}</code><i>→</i><code>{report.synthetic_profile.corrected_editor_preference}</code></div>
      </section>

      <footer><p>Real hosted and local model calls · synthetic values only · exact bytes, estimated memory tokens</p><p>Replay visualizes evidence; it does not call a model.</p></footer>
    </main>
  );
}

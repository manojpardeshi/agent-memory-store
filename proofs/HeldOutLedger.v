(* Formal model of the held-out look protocol in scripts/locomo_heldout.py:
   [record_look] and the [look] branch of [main].

   record_look(candidate, freeze_commit, dataset_sha):
     1. git status --porcelain must be empty           (worktree clean)
     2. git merge-base --is-ancestor freeze HEAD        (check=True: raises otherwise)
     3. entry = ledger[held_out_sets][locomo10]
        entry.status must equal the string active
     4. dataset_sha must equal entry.dataset_sha256
     5. len(entry.looks) < entry.max_looks
     then append {candidate, frozen_in, evaluated_at_commit, started, result: None},
     set status to retired when len(looks) >= max_looks, and write the ledger.
   main (look): validates arguments, calls record_look, and only after it
   returns calls score(...) and writes the aggregate report.

   Commits, digests and candidate names are modelled as [nat]; the status
   string is modelled as [Active] (the string active) or [Retired] (any other
   string; the script only ever writes one).  Each failed check raises before
   any write, so a failed attempt leaves the ledger unchanged.  Section 1 is
   the sequential model (one process at a time, the ledger file changed only
   by record_look).  Section 2 shows that two concurrent processes break the
   scoring budget, because the read-check-write in record_look is not atomic. *)

From Stdlib Require Import List Arith Lia Bool.
Import ListNotations.

Inductive status := Active | Retired.

Definition is_active (s : status) : bool := match s with Active => true | Retired => false end.

Record look := mkLook {
  candidate : nat;
  frozen_in : nat;
  evaluated_at : nat;
  result : option nat
}.

Record ledger := mkLedger {
  st : status;
  looks : list look;
  max_looks : nat;
  digest : nat
}.

(* What the environment answers to the checks of one invocation. *)
Record env := mkEnv {
  worktree_clean : bool;
  freeze_is_ancestor : bool;
  dataset_digest : nat;
  head_commit : nat
}.

Record request := mkRequest { req_candidate : nat; req_freeze : nat }.

Definition guard (e : env) (l : ledger) : bool :=
  worktree_clean e && freeze_is_ancestor e && is_active (st l)
  && Nat.eqb (dataset_digest e) (digest l)
  && Nat.ltb (length (looks l)) (max_looks l).

Definition new_look (e : env) (rq : request) : look :=
  mkLook (req_candidate rq) (req_freeze rq) (head_commit e) None.

(* The ledger write performed after a successful check, applied to the
   ledger value that was read (in the sequential model: the current file). *)
Definition append_look (l : ledger) (lk : look) : ledger :=
  let looks' := looks l ++ [lk] in
  mkLedger (if max_looks l <=? length looks' then Retired else st l)
           looks' (max_looks l) (digest l).

Definition record_look (e : env) (rq : request) (l : ledger) : option (ledger * look) :=
  if guard e l then Some (append_look l (new_look e rq), new_look e rq) else None.

Inductive event :=
| ELookRecorded (lk : look)   (* the ledger file now contains lk *)
| EScored (lk : look)         (* score(...) ran for the look lk *)
| ERefused                    (* SystemExit / CalledProcessError, no write *)
| EBuild.                     (* the build command: no ledger access, no scoring *)

(* ================================================================== *)
(* Section 1: sequential executions                                     *)

(* One invocation of the script. *)
Inductive run : ledger -> ledger -> list event -> Prop :=
| run_build : forall l, run l l [EBuild]
| run_bad_args : forall l, run l l [ERefused]
| run_refused : forall e rq l, record_look e rq l = None -> run l l [ERefused]
| run_scored : forall e rq l l' lk,
    record_look e rq l = Some (l', lk) -> run l l' [ELookRecorded lk; EScored lk]
| run_crashed : forall e rq l l' lk,      (* scoring raised after the look was written *)
    record_look e rq l = Some (l', lk) -> run l l' [ELookRecorded lk].

Definition valid_initial (l : ledger) : Prop :=
  st l = Active /\ looks l = [] /\ 1 <= max_looks l.

Inductive reachable (l0 : ledger) : ledger -> list event -> Prop :=
| reach_init : valid_initial l0 -> reachable l0 l0 []
| reach_step : forall l tr l' evs,
    reachable l0 l tr -> run l l' evs -> reachable l0 l' (tr ++ evs).

Fixpoint recorded (tr : list event) : list look :=
  match tr with
  | [] => []
  | ELookRecorded lk :: tr' => lk :: recorded tr'
  | _ :: tr' => recorded tr'
  end.

Fixpoint scored (tr : list event) : list look :=
  match tr with
  | [] => []
  | EScored lk :: tr' => lk :: scored tr'
  | _ :: tr' => scored tr'
  end.

Lemma recorded_app : forall a b, recorded (a ++ b) = recorded a ++ recorded b.
Proof. induction a as [|x a IH]; intro b; [reflexivity|]. destruct x; simpl; rewrite IH; reflexivity. Qed.

Lemma scored_app : forall a b, scored (a ++ b) = scored a ++ scored b.
Proof. induction a as [|x a IH]; intro b; [reflexivity|]. destruct x; simpl; rewrite IH; reflexivity. Qed.

Lemma record_look_spec : forall e rq l l' lk,
  record_look e rq l = Some (l', lk) ->
  guard e l = true /\ l' = append_look l lk /\ lk = new_look e rq.
Proof.
  intros e rq l l' lk H. unfold record_look in H.
  destruct (guard e l) eqn:G; [|discriminate]. injection H as <- <-. auto.
Qed.

Lemma guard_spec : forall e l, guard e l = true ->
  worktree_clean e = true /\ freeze_is_ancestor e = true /\ st l = Active /\
  dataset_digest e = digest l /\ length (looks l) < max_looks l.
Proof.
  intros e l G. unfold guard in G.
  repeat rewrite andb_true_iff in G.
  destruct G as [[[[C A] S] D] L].
  apply Nat.eqb_eq in D. apply Nat.ltb_lt in L.
  destruct (st l); [|discriminate]. auto.
Qed.

(* The status/length invariant. *)
Definition inv (l0 l : ledger) : Prop :=
  max_looks l = max_looks l0 /\ digest l = digest l0 /\
  ((st l = Active /\ length (looks l) < max_looks l) \/
   (st l = Retired /\ length (looks l) = max_looks l)).

Lemma run_inv : forall l0 l l' evs, inv l0 l -> run l l' evs -> inv l0 l'.
Proof.
  intros l0 l l' evs Hi Hr. destruct Hr as [l|l|e rq l H|e rq l l' lk H|e rq l l' lk H];
    try exact Hi;
    apply record_look_spec in H; destruct H as [G [-> ->]];
    apply guard_spec in G; destruct G as [_ [_ [S [_ L]]]];
    destruct Hi as [M [D _]]; unfold inv, append_look; simpl;
    rewrite length_app; simpl;
    (split; [exact M|split; [exact D|]]);
    destruct (max_looks l <=? length (looks l) + 1) eqn:E.
  all: try (apply Nat.leb_le in E; right; split; [reflexivity|lia]).
  all: apply Nat.leb_gt in E; left; split; [exact S|lia].
Qed.

Lemma reachable_inv : forall l0 l tr, reachable l0 l tr -> inv l0 l.
Proof.
  intros l0 l tr H. induction H as [Hv|l tr l' evs H IH Hr].
  - destruct Hv as [S [L M]]. unfold inv. split; [reflexivity|]. split; [reflexivity|].
    left. split; [exact S|]. rewrite L. simpl. lia.
  - eapply run_inv; eassumption.
Qed.

(* (a) The look budget is never exceeded. *)
Theorem budget_respected : forall l0 l tr,
  reachable l0 l tr -> length (looks l) <= max_looks l /\ max_looks l = max_looks l0.
Proof.
  intros l0 l tr H. destruct (reachable_inv l0 l tr H) as [M [_ [[_ L]|[_ L]]]]; lia.
Qed.

(* The set is retired exactly when the budget is used up. *)
Theorem retired_iff_exhausted : forall l0 l tr,
  reachable l0 l tr -> (st l = Retired <-> length (looks l) = max_looks l).
Proof.
  intros l0 l tr H. destruct (reachable_inv l0 l tr H) as [_ [_ [[S L]|[S L]]]];
    rewrite S; split; intro X; try discriminate; try reflexivity; try exact L; exfalso; lia.
Qed.

(* (b) A retired set accepts no further look, from any environment. *)
Theorem retired_refuses : forall l e rq, st l = Retired -> record_look e rq l = None.
Proof.
  intros l e rq S. unfold record_look, guard. rewrite S. simpl.
  rewrite !andb_false_r. reflexivity.
Qed.

Inductive runs : ledger -> ledger -> list event -> Prop :=
| runs_nil : forall l, runs l l []
| runs_cons : forall l l1 l2 evs tr, run l l1 evs -> runs l1 l2 tr -> runs l l2 (evs ++ tr).

(* (b) Once retired, every later sequence of invocations leaves the ledger
   unchanged and scores nothing. *)
Theorem retired_is_final : forall l l' tr,
  st l = Retired -> runs l l' tr -> l' = l /\ recorded tr = [] /\ scored tr = [].
Proof.
  intros l l' tr S H. induction H as [l|l l1 l2 evs tr Hr Hs IH]; [auto|].
  assert (Hl1 : l1 = l /\ recorded evs = [] /\ scored evs = []).
  { destruct Hr as [l|l|e rq l Hn|e rq l l1 lk Hn|e rq l l1 lk Hn]; auto;
      rewrite retired_refuses in Hn by exact S; discriminate. }
  destruct Hl1 as [-> [R1 S1]]. destruct (IH S) as [-> [R2 S2]].
  rewrite recorded_app, scored_app, R1, R2, S1, S2. auto.
Qed.

(* The ledger is an exact audit log of the recorded looks in the trace,
   every recorded look has result None, and scoring never outruns it. *)
Theorem ledger_is_audit_log : forall l0 l tr,
  reachable l0 l tr ->
  looks l = recorded tr /\ Forall (fun lk => result lk = None) (looks l).
Proof.
  intros l0 l tr H. induction H as [Hv|l tr l' evs H IH Hr].
  - destruct Hv as [_ [L _]]. rewrite L. split; [reflexivity|constructor].
  - destruct IH as [IH1 IH2]. rewrite recorded_app.
    destruct Hr as [l|l|e rq l Hn|e rq l l' lk Hn|e rq l l' lk Hn];
      try (simpl; rewrite app_nil_r; split; assumption);
      apply record_look_spec in Hn; destruct Hn as [_ [-> ->]];
      unfold append_look; simpl; rewrite IH1; split; try reflexivity;
      rewrite <- IH1; apply Forall_app; split; try assumption;
      repeat constructor.
Qed.

(* (c) Every scoring event is immediately preceded by the recording of the
   same look. *)
Definition score_preceded (tr : list event) : Prop :=
  forall i lk, nth_error tr i = Some (EScored lk) ->
    exists j, i = S j /\ nth_error tr j = Some (ELookRecorded lk).

Lemma score_preceded_app : forall a b,
  score_preceded a -> score_preceded b ->
  (forall lk, nth_error b 0 <> Some (EScored lk)) -> score_preceded (a ++ b).
Proof.
  intros a b Ha Hb H0 i lk Hi.
  destruct (Nat.lt_ge_cases i (length a)) as [Lt|Ge].
  - rewrite nth_error_app1 in Hi by exact Lt. destruct (Ha i lk Hi) as [j [-> Hj]].
    exists j. split; [reflexivity|]. rewrite nth_error_app1 by lia. exact Hj.
  - rewrite nth_error_app2 in Hi by exact Ge.
    destruct (Hb (i - length a) lk Hi) as [j [Ej Hj]].
    exists (j + length a). split; [lia|].
    rewrite nth_error_app2 by lia. replace (j + length a - length a) with j by lia. exact Hj.
Qed.

Lemma run_events_ok : forall l l' evs, run l l' evs ->
  score_preceded evs /\ (forall lk, nth_error evs 0 <> Some (EScored lk)).
Proof.
  intros l l' evs Hr.
  destruct Hr; split; try (intros lk' Hx; discriminate);
    intros [|[|[|i]]] lk' Hx; simpl in Hx; try discriminate.
  injection Hx as <-. exists 0. split; reflexivity.
Qed.

Theorem score_after_look : forall l0 l tr, reachable l0 l tr -> score_preceded tr.
Proof.
  intros l0 l tr H. induction H as [Hv|l tr l' evs H IH Hr].
  - intros [|i] lk Hi; discriminate.
  - destruct (run_events_ok l l' evs Hr) as [P0 P1].
    apply score_preceded_app; assumption.
Qed.

Lemma run_scored_le : forall l l' evs, run l l' evs ->
  length (scored evs) <= length (recorded evs).
Proof. intros l l' evs Hr. destruct Hr; simpl; auto. Qed.

(* Scoring passes never outnumber recorded looks, hence never exceed the budget. *)
Theorem scores_within_budget : forall l0 l tr, reachable l0 l tr ->
  length (scored tr) <= length (looks l) /\ length (looks l) <= max_looks l0.
Proof.
  intros l0 l tr H.
  assert (Hc : length (scored tr) <= length (recorded tr)).
  { induction H as [Hv|l tr l' evs H IH Hr]; [simpl; lia|].
    rewrite scored_app, recorded_app, !length_app.
    pose proof (run_scored_le l l' evs Hr). lia. }
  destruct (ledger_is_audit_log l0 l tr H) as [Ha _].
  destruct (budget_respected l0 l tr H) as [B M].
  rewrite Ha in *. lia.
Qed.

(* Every recorded look passed all five checks against the ledger as it was. *)
Theorem look_requires_checks : forall e rq l l' lk,
  record_look e rq l = Some (l', lk) ->
  worktree_clean e = true /\ freeze_is_ancestor e = true /\ st l = Active /\
  dataset_digest e = digest l /\ length (looks l) < max_looks l /\
  result lk = None /\ looks l' = looks l ++ [lk].
Proof.
  intros e rq l l' lk H. apply record_look_spec in H. destruct H as [G [-> ->]].
  apply guard_spec in G. destruct G as [C [A [S [D L]]]].
  repeat split; assumption.
Qed.

(* ================================================================== *)
(* Section 2: concurrent executions break the scoring budget.          *)
(* record_look reads the ledger, checks it, and later writes back the   *)
(* value it read plus one look.  Two processes that both read before    *)
(* either writes both pass the checks; the second write overwrites the  *)
(* first (lost update), so the file shows one look while two scoring    *)
(* passes run.  This is a counterexample to (c)'s budget consequence    *)
(* and to the audit-log property for the real script; the file bound    *)
(* length looks <= max_looks still holds.                               *)

Inductive pstate :=
| Idle
| Checked (snap : ledger) (lk : look)   (* read + passed the checks, not yet written *)
| Written (lk : look)                   (* ledger written, scoring may start *)
| Finished.

Record cstate := mkC { file : ledger; p1 : pstate; p2 : pstate }.

Inductive pstep : ledger -> pstate -> ledger -> pstate -> list event -> Prop :=
| ps_check : forall f e rq, guard e f = true ->
    pstep f Idle f (Checked f (new_look e rq)) []
| ps_write : forall f snap lk,
    pstep f (Checked snap lk) (append_look snap lk) (Written lk) [ELookRecorded lk]
| ps_score : forall f lk, pstep f (Written lk) f Finished [EScored lk].

Inductive cstep : cstate -> cstate -> list event -> Prop :=
| cs_p1 : forall f a b f' a' evs, pstep f a f' a' evs -> cstep (mkC f a b) (mkC f' a' b) evs
| cs_p2 : forall f a b f' b' evs, pstep f b f' b' evs -> cstep (mkC f a b) (mkC f' a b') evs.

Inductive csteps : cstate -> cstate -> list event -> Prop :=
| cs_nil : forall c, csteps c c []
| cs_cons : forall c c1 c2 evs tr, cstep c c1 evs -> csteps c1 c2 tr -> csteps c c2 (evs ++ tr).

Definition init1 : ledger := mkLedger Active [] 1 42.
Definition env_ok : env := mkEnv true true 42 7.
Definition rq1 : request := mkRequest 1 5.

Theorem concurrent_budget_violation :
  exists c tr,
    csteps (mkC init1 Idle Idle) c tr /\
    valid_initial init1 /\ max_looks init1 = 1 /\
    length (scored tr) = 2 /\ length (looks (file c)) = 1.
Proof.
  set (lk := new_look env_ok rq1).
  assert (G : guard env_ok init1 = true) by reflexivity.
  eexists. eexists. split.
  - eapply cs_cons. { apply cs_p1. apply (ps_check init1 env_ok rq1 G). }
    eapply cs_cons. { apply cs_p2. apply (ps_check init1 env_ok rq1 G). }
    eapply cs_cons. { apply cs_p1. apply ps_write. }
    eapply cs_cons. { apply cs_p1. apply ps_score. }
    eapply cs_cons. { apply cs_p2. apply ps_write. }
    eapply cs_cons. { apply cs_p2. apply ps_score. }
    apply cs_nil.
  - repeat split; reflexivity.
Qed.

(* Even concurrently, the file itself never exceeds the budget: every write
   is a checked snapshot of the same set plus one look. *)
Definition pinv (m : nat) (p : pstate) : Prop :=
  match p with
  | Checked snap _ => length (looks snap) < m /\ max_looks snap = m
  | _ => True
  end.

Definition cinv (m : nat) (c : cstate) : Prop :=
  length (looks (file c)) <= m /\ max_looks (file c) = m /\ pinv m (p1 c) /\ pinv m (p2 c).

Lemma pstep_inv : forall m f a f' a' evs,
  length (looks f) <= m -> max_looks f = m -> pinv m a -> pstep f a f' a' evs ->
  length (looks f') <= m /\ max_looks f' = m /\ pinv m a'.
Proof.
  intros m f a f' a' evs L M P H. destruct H as [f e rq G|f snap lk|f lk].
  - apply guard_spec in G. destruct G as [_ [_ [_ [_ Lt]]]].
    simpl. repeat split; try assumption; try lia; auto.
  - simpl in P. destruct P as [Ls Ms]. unfold append_look. simpl.
    rewrite length_app. simpl. repeat split; try lia; auto.
  - simpl. repeat split; assumption || auto.
Qed.

Theorem concurrent_file_bound : forall c c' tr m,
  cinv m c -> csteps c c' tr -> length (looks (file c')) <= m.
Proof.
  intros c c' tr m Hi H. induction H as [c|c c1 c2 evs tr Hs Hss IH].
  - apply Hi.
  - apply IH. destruct Hi as [L [M [P1 P2]]].
    destruct Hs as [f a b f' a' evs Hp|f a b f' b' evs Hp]; simpl in *.
    + destruct (pstep_inv m f a f' a' evs L M P1 Hp) as [L' [M' P']].
      unfold cinv. simpl. auto.
    + destruct (pstep_inv m f b f' b' evs L M P2 Hp) as [L' [M' P']].
      unfold cinv. simpl. auto.
Qed.

Print Assumptions budget_respected.
Print Assumptions retired_iff_exhausted.
Print Assumptions retired_refuses.
Print Assumptions retired_is_final.
Print Assumptions ledger_is_audit_log.
Print Assumptions score_after_look.
Print Assumptions scores_within_budget.
Print Assumptions look_requires_checks.
Print Assumptions concurrent_budget_violation.
Print Assumptions concurrent_file_bound.

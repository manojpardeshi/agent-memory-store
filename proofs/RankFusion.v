(* Formal model of the reciprocal-rank-fusion step in the hybrid branch of
   MemoryStore.recall (src/llm_memory_store/store.py):

     fusion_scores: dict[int, float] = {}
     for ranking in (vector_ids, keyword_ids):
         for rank, internal_id in enumerate(ranking, start=1):
             fusion_scores[internal_id] = fusion_scores.get(internal_id, 0.0) + 1.0 / (
                 HYBRID_RRF_K + rank)
     scored = sorted((by_internal_id[i] for i in fusion_scores),
                     key=lambda item: (-fusion_scores[item[2]], item[1]))

   with HYBRID_RRF_K = 60.  Rankings are lists of internal ids ([nat]); the
   score is computed exactly in [Q] (Python uses binary floating point, see
   README).  The dictionary's key order is insertion order, i.e. the first
   occurrence of each id in the concatenated rankings.  The tie-break key
   item[1] (the public memory_id string) is abstracted as a boolean
   comparison [key_leb] on internal ids; facts about it are assumed only where
   stated (totality for sortedness; totality, transitivity and antisymmetry -
   memory_id is UNIQUE in the schema - for the uniqueness theorem). *)

From Stdlib Require Import List Bool Arith Lia ZArith QArith Lqa.
From Stdlib Require Import Sorting.Sorted Sorting.Permutation.
Import ListNotations.

Definition rrf_k : nat := 60.

(* Contribution of one ranking to [id]'s score, ranks counted from [pos]. *)
Fixpoint contrib (id : nat) (r : list nat) (pos : nat) : Q :=
  match r with
  | [] => 0
  | x :: r' =>
      (if Nat.eqb x id then 1 # Pos.of_nat (rrf_k + pos) else 0) + contrib id r' (S pos)
  end.

(* fusion_scores[id]: sum over rankings, rank 1-based *)
Definition score (rs : list (list nat)) (id : nat) : Q :=
  fold_right (fun r acc => contrib id r 1 + acc) 0 rs.

(* Dictionary key order: first occurrences in the concatenated rankings. *)
Fixpoint dedup_acc (seen : list nat) (l : list nat) : list nat :=
  match l with
  | [] => []
  | x :: l' =>
      if in_dec Nat.eq_dec x seen then dedup_acc seen l' else x :: dedup_acc (x :: seen) l'
  end.

Definition keys (rs : list (list nat)) : list nat := dedup_acc [] (concat rs).

(* Stable insertion sort, parameterised by a boolean comparison. *)
Section Sort.
  Context (leb : nat -> nat -> bool).

  Fixpoint insert (x : nat) (l : list nat) : list nat :=
    match l with
    | [] => [x]
    | y :: l' => if leb x y then x :: l else y :: insert x l'
    end.

  Fixpoint isort (l : list nat) : list nat :=
    match l with
    | [] => []
    | x :: l' => insert x (isort l')
    end.

  Lemma insert_perm : forall x l, Permutation (insert x l) (x :: l).
  Proof.
    intros x l. induction l as [|y l IH]; simpl; [reflexivity|].
    destruct (leb x y); [reflexivity|].
    rewrite IH. apply perm_swap.
  Qed.

  Lemma isort_perm : forall l, Permutation (isort l) l.
  Proof.
    induction l as [|x l IH]; simpl; [reflexivity|].
    rewrite insert_perm. apply perm_skip. exact IH.
  Qed.

  Definition R (a b : nat) : Prop := leb a b = true.

  Lemma insert_sorted : (forall a b, leb a b = true \/ leb b a = true) ->
    forall x l, Sorted R l -> Sorted R (insert x l).
  Proof.
    intros Htot x l. induction l as [|y l IH]; intro Hs; simpl.
    - repeat constructor.
    - destruct (leb x y) eqn:Exy.
      + constructor; [exact Hs|]. constructor. exact Exy.
      + assert (Hyx : leb y x = true) by (destruct (Htot x y); congruence).
        inversion Hs as [|y' l' Hl Hhd]; subst.
        constructor; [apply IH; exact Hl|].
        destruct l as [|z l'']; simpl.
        * constructor. exact Hyx.
        * destruct (leb x z); constructor; [exact Hyx|].
          inversion Hhd; assumption.
  Qed.

  Lemma isort_sorted : (forall a b, leb a b = true \/ leb b a = true) ->
    forall l, Sorted R (isort l).
  Proof.
    intros Htot l. induction l as [|x l IH]; simpl; [constructor|].
    apply insert_sorted; assumption.
  Qed.

  (* Sorting an already sorted list changes nothing (no totality needed). *)
  Lemma isort_id : forall l, Sorted R l -> isort l = l.
  Proof.
    induction l as [|x l IH]; intro Hs; simpl; [reflexivity|].
    inversion Hs as [|x' l' Hl Hhd]; subst. rewrite IH by exact Hl.
    destruct l as [|y l']; simpl; [reflexivity|].
    inversion Hhd as [|? ? Hxy]; subst. unfold R in Hxy. rewrite Hxy. reflexivity.
  Qed.
End Sort.

Lemma isort_ext : forall (f g : nat -> nat -> bool),
  (forall a b, f a b = g a b) -> forall l, isort f l = isort g l.
Proof.
  intros f g Hfg l. induction l as [|x l IH]; simpl; [reflexivity|].
  rewrite IH. generalize (isort g l). intro m.
  induction m as [|y m IHm]; simpl; [reflexivity|].
  rewrite Hfg, IHm. reflexivity.
Qed.

Section Fusion.

Context (key_leb : nat -> nat -> bool).

(* Python's sort key (-score, memory_id): a goes first iff its score is
   larger, or the scores are equal and its memory_id is not larger.
   The comparison is parameterised by an arbitrary score function [sc]; the
   theorems stated for [fuse_by] hold for every [sc], in particular for the
   exact rational values of the floats CPython computes.  [fuse] is the
   exact-arithmetic instance. *)
Definition before_by (sc : nat -> Q) (a b : nat) : bool :=
  if Qlt_le_dec (sc b) (sc a) then true
  else if Qeq_dec (sc a) (sc b) then key_leb a b
  else false.

Definition fuse_by (sc : nat -> Q) (rs : list (list nat)) : list nat :=
  isort (before_by sc) (keys rs).

Definition before (rs : list (list nat)) := before_by (score rs).
Definition fuse (rs : list (list nat)) : list nat := fuse_by (score rs) rs.

(* ---------------- dedup facts ---------------- *)

Lemma dedup_acc_In : forall l seen y,
  In y (dedup_acc seen l) <-> In y l /\ ~ In y seen.
Proof.
  induction l as [|x l IH]; intros seen y; simpl.
  - tauto.
  - destruct (in_dec Nat.eq_dec x seen) as [Hin|Hnin].
    + rewrite IH. split; [tauto|].
      intros [[Heq|Hl] Hns]; [subst; contradiction|tauto].
    + simpl. rewrite IH. simpl. split.
      * intros [Heq|[Hl Hns]]; [subst; tauto|tauto].
      * intros [[Heq|Hl] Hns]; [left; exact Heq|].
        destruct (Nat.eq_dec x y); [left; assumption|right; split; [assumption|]].
        intros [H|H]; contradiction.
Qed.

Lemma dedup_acc_NoDup : forall l seen, NoDup (dedup_acc seen l).
Proof.
  induction l as [|x l IH]; intro seen; simpl; [constructor|].
  destruct (in_dec Nat.eq_dec x seen); [apply IH|].
  constructor; [|apply IH]. rewrite dedup_acc_In. simpl. tauto.
Qed.

Lemma dedup_acc_id : forall l seen,
  NoDup l -> (forall x, In x l -> ~ In x seen) -> dedup_acc seen l = l.
Proof.
  induction l as [|x l IH]; intros seen Hnd Hdis; simpl; [reflexivity|].
  inversion Hnd as [|x' l' Hx Hl]; subst.
  destruct (in_dec Nat.eq_dec x seen) as [Hin|_].
  - exfalso. exact (Hdis x (or_introl eq_refl) Hin).
  - f_equal. apply IH; [exact Hl|].
    intros y Hy [Hyx|Hys]; [subst; contradiction|].
    exact (Hdis y (or_intror Hy) Hys).
Qed.

Lemma keys_In : forall rs x, In x (keys rs) <-> exists r, In r rs /\ In x r.
Proof.
  intros rs x. unfold keys. rewrite dedup_acc_In, in_concat. simpl. tauto.
Qed.

(* ---------------- (a) and (b): no invented ids, no duplicates ---------------- *)

Theorem fuse_perm : forall sc rs, Permutation (fuse_by sc rs) (keys rs).
Proof. intros sc rs. apply isort_perm. Qed.

Theorem fuse_In : forall sc rs x, In x (fuse_by sc rs) <-> exists r, In r rs /\ In x r.
Proof.
  intros sc rs x. rewrite <- keys_In. split; intro H.
  - eapply Permutation_in; [apply fuse_perm|exact H].
  - eapply Permutation_in; [symmetry; apply fuse_perm|exact H].
Qed.

Theorem fuse_NoDup : forall sc rs, NoDup (fuse_by sc rs).
Proof.
  intros sc rs. eapply Permutation_NoDup; [symmetry; apply fuse_perm|].
  apply dedup_acc_NoDup.
Qed.

(* Scope isolation: any property of every input id (e.g. "belongs to one of
   the caller's scopes") holds of every output id. *)
Theorem fuse_scope_isolation : forall (P : nat -> Prop) sc rs,
  (forall r, In r rs -> Forall P r) -> Forall P (fuse_by sc rs).
Proof.
  intros P sc rs H. apply Forall_forall. intros x Hx.
  apply fuse_In in Hx. destruct Hx as [r [Hr Hxr]].
  specialize (H r Hr). rewrite Forall_forall in H. auto.
Qed.

Lemma firstn_In' : forall n (l : list nat) x, In x (firstn n l) -> In x l.
Proof.
  induction n as [|n IH]; intros l x H; [destruct H|].
  destruct l as [|y l]; [destruct H|]. simpl in *.
  destruct H; [left; assumption|right; eauto].
Qed.

Lemma firstn_NoDup' : forall n (l : list nat), NoDup l -> NoDup (firstn n l).
Proof.
  induction n as [|n IH]; intros l Hl; simpl; [constructor|].
  destruct l as [|y l]; [constructor|]. inversion Hl; subst.
  constructor; [|auto]. intro H. apply H1. eapply firstn_In'. exact H.
Qed.

Lemma NoDup_filter' : forall (f : nat -> bool) l, NoDup l -> NoDup (filter f l).
Proof.
  intros f l. induction l as [|x l IH]; intro Hl; simpl; [constructor|].
  inversion Hl; subst. destruct (f x); [|auto].
  constructor; [|auto]. rewrite filter_In. tauto.
Qed.

(* The rest of recall only filters (relevance filter) and truncates
   (scored[:limit]); both preserve isolation and distinctness. *)
Theorem recall_output_isolated : forall (P : nat -> Prop) (keep : nat -> bool) limit sc rs,
  (forall r, In r rs -> Forall P r) ->
  Forall P (firstn limit (filter keep (fuse_by sc rs))) /\
  NoDup (firstn limit (filter keep (fuse_by sc rs))).
Proof.
  intros P keep limit sc rs H. split.
  - apply Forall_forall. intros x Hx.
    apply firstn_In' in Hx. rewrite filter_In in Hx. destruct Hx as [Hx _].
    pose proof (fuse_scope_isolation P sc rs H) as Hf. rewrite Forall_forall in Hf. auto.
  - apply firstn_NoDup', NoDup_filter', fuse_NoDup.
Qed.

(* ---------------- the output is sorted by (-score, memory_id) ---------------- *)

Lemma before_total :
  (forall a b, key_leb a b = true \/ key_leb b a = true) ->
  forall sc a b, before_by sc a b = true \/ before_by sc b a = true.
Proof.
  intros Hk sc a b. unfold before_by.
  destruct (Qlt_le_dec (sc b) (sc a)) as [H1|H1]; [left; reflexivity|].
  destruct (Qlt_le_dec (sc a) (sc b)) as [H2|H2]; [right; reflexivity|].
  destruct (Qeq_dec (sc a) (sc b)) as [H3|H3]; [|exfalso; apply H3; lra].
  destruct (Qeq_dec (sc b) (sc a)) as [H4|H4]; [|exfalso; apply H4; lra].
  apply Hk.
Qed.

Theorem fuse_sorted :
  (forall a b, key_leb a b = true \/ key_leb b a = true) ->
  forall sc rs, Sorted (fun a b => before_by sc a b = true) (fuse_by sc rs).
Proof.
  intros Hk sc rs. apply isort_sorted. intros a b. apply before_total. exact Hk.
Qed.

(* ---------------- uniqueness: any correct sort yields the same list ---------------- *)

Lemma before_trans :
  (forall a b c, key_leb a b = true -> key_leb b c = true -> key_leb a c = true) ->
  forall sc a b c, before_by sc a b = true -> before_by sc b c = true -> before_by sc a c = true.
Proof.
  intros Ht sc a b c. unfold before_by.
  destruct (Qlt_le_dec (sc b) (sc a)) as [Hab|Hab];
  destruct (Qlt_le_dec (sc c) (sc b)) as [Hbc|Hbc];
  destruct (Qlt_le_dec (sc c) (sc a)) as [Hac|Hac];
  try reflexivity;
  destruct (Qeq_dec (sc a) (sc b)) as [Eab|Eab];
  destruct (Qeq_dec (sc b) (sc c)) as [Ebc|Ebc];
  destruct (Qeq_dec (sc a) (sc c)) as [Eac|Eac];
  intros H1 H2; try discriminate; try (exfalso; lra); eauto.
Qed.

Lemma before_antisym :
  (forall a b, key_leb a b = true -> key_leb b a = true -> a = b) ->
  forall sc a b, before_by sc a b = true -> before_by sc b a = true -> a = b.
Proof.
  intros Ha sc a b. unfold before_by.
  destruct (Qlt_le_dec (sc b) (sc a)) as [H1|H1];
  destruct (Qlt_le_dec (sc a) (sc b)) as [H2|H2];
  try (exfalso; lra);
  destruct (Qeq_dec (sc a) (sc b)) as [E1|E1];
  destruct (Qeq_dec (sc b) (sc a)) as [E2|E2];
  intros X Y; try discriminate; try (exfalso; lra); eauto.
Qed.

Lemma strongly_sorted_unique : forall (Rel : nat -> nat -> Prop),
  (forall a b, Rel a b -> Rel b a -> a = b) ->
  forall l1 l2, Permutation l1 l2 -> StronglySorted Rel l1 -> StronglySorted Rel l2 -> l1 = l2.
Proof.
  intros Rel Hanti l1. induction l1 as [|a l1 IH]; intros l2 Hp H1 H2.
  - apply Permutation_nil in Hp. subst. reflexivity.
  - destruct l2 as [|b l2]; [apply Permutation_sym, Permutation_nil in Hp; discriminate|].
    inversion H1 as [|? ? Hs1 Hf1]; subst. inversion H2 as [|? ? Hs2 Hf2]; subst.
    assert (Hab : a = b).
    { assert (Ha : In a (b :: l2)) by (eapply Permutation_in; [exact Hp|left; reflexivity]).
      assert (Hb : In b (a :: l1)) by (eapply Permutation_in; [symmetry; exact Hp|left; reflexivity]).
      destruct Ha as [Ha|Ha]; [symmetry; exact Ha|].
      destruct Hb as [Hb|Hb]; [exact Hb|].
      rewrite Forall_forall in Hf1, Hf2. apply Hanti; auto. }
    subst. f_equal. apply IH; [eapply Permutation_cons_inv; exact Hp|exact Hs1|exact Hs2].
Qed.

(* With a total, transitive, antisymmetric tie-break (memory_id is UNIQUE),
   the fused order is the only ordering of the fused ids that is sorted by
   (-score, memory_id); hence it coincides with Python's sorted() output,
   whatever sorting algorithm CPython uses. *)
Theorem fuse_unique :
  (forall a b, key_leb a b = true \/ key_leb b a = true) ->
  (forall a b c, key_leb a b = true -> key_leb b c = true -> key_leb a c = true) ->
  (forall a b, key_leb a b = true -> key_leb b a = true -> a = b) ->
  forall sc rs l, Permutation l (keys rs) -> Sorted (fun a b => before_by sc a b = true) l ->
  l = fuse_by sc rs.
Proof.
  intros Htot Htr Hanti sc rs l Hp Hs.
  assert (Tr : Relations_1.Transitive (fun a b => before_by sc a b = true)).
  { intros a b c. apply before_trans. exact Htr. }
  apply (strongly_sorted_unique (fun a b => before_by sc a b = true)).
  - apply before_antisym. exact Hanti.
  - rewrite Hp. symmetry. apply fuse_perm.
  - apply Sorted_StronglySorted; [exact Tr|exact Hs].
  - apply Sorted_StronglySorted; [exact Tr|]. apply fuse_sorted. exact Htot.
Qed.

(* ---------------- (c) a single ranking passes through unchanged ---------------- *)

Lemma inv_pos_lt : forall a b, (0 < a)%nat -> (a < b)%nat ->
  1 # Pos.of_nat b < 1 # Pos.of_nat a.
Proof.
  intros a b Ha Hb. unfold Qlt. simpl.
  assert (Ea : Z.pos (Pos.of_nat a) = Z.of_nat a)
    by (rewrite <- positive_nat_Z, Nat2Pos.id by lia; reflexivity).
  assert (Eb : Z.pos (Pos.of_nat b) = Z.of_nat b)
    by (rewrite <- positive_nat_Z, Nat2Pos.id by lia; reflexivity).
  rewrite Ea, Eb. lia.
Qed.

Lemma inv_nonneg : forall p, 0 <= 1 # p.
Proof. intro p. unfold Qle. simpl. lia. Qed.

Lemma contrib_notin : forall id r pos, ~ In id r -> contrib id r pos == 0.
Proof.
  intros id r. induction r as [|x r IH]; intros pos Hn; cbn [contrib]; [reflexivity|].
  destruct (Nat.eqb x id) eqn:E.
  - apply Nat.eqb_eq in E. subst. exfalso. apply Hn. left. reflexivity.
  - rewrite IH by (intro H; apply Hn; right; exact H). reflexivity.
Qed.

Lemma contrib_bound : forall id r pos, NoDup r ->
  contrib id r pos <= 1 # Pos.of_nat (rrf_k + pos).
Proof.
  intros id r. induction r as [|x r IH]; intros pos Hnd; cbn [contrib].
  - apply inv_nonneg.
  - inversion Hnd as [|? ? Hx Hr]; subst.
    destruct (Nat.eqb x id) eqn:E.
    + apply Nat.eqb_eq in E. subst. rewrite contrib_notin by exact Hx. lra.
    + specialize (IH (S pos) Hr).
      assert (Hlt := inv_pos_lt (rrf_k + pos) (rrf_k + S pos) ltac:(unfold rrf_k; lia) ltac:(lia)).
      lra.
Qed.

Lemma contrib_head : forall x r pos, NoDup (x :: r) ->
  contrib x (x :: r) pos == 1 # Pos.of_nat (rrf_k + pos).
Proof.
  intros x r pos Hnd. inversion Hnd as [|? ? Hx _]; subst. cbn [contrib].
  rewrite Nat.eqb_refl. rewrite contrib_notin by exact Hx. lra.
Qed.

Lemma contrib_tail : forall x r pos y, x <> y ->
  contrib y (x :: r) pos == contrib y r (S pos).
Proof.
  intros x r pos y Hxy. cbn [contrib]. destruct (Nat.eqb x y) eqn:E.
  - apply Nat.eqb_eq in E. contradiction.
  - lra.
Qed.

Lemma Sorted_In_impl : forall (R1 R2 : nat -> nat -> Prop) l,
  (forall a b, In a l -> In b l -> R1 a b -> R2 a b) -> Sorted R1 l -> Sorted R2 l.
Proof.
  intros R1 R2 l. induction l as [|x l IH]; intros Himp Hs; [constructor|].
  inversion Hs as [|? ? Hl Hhd]; subst. constructor.
  - apply IH; [|exact Hl]. intros a b Ha Hb. apply Himp; right; assumption.
  - destruct l as [|y l']; constructor. inversion Hhd; subst.
    apply Himp; [left; reflexivity|right; left; reflexivity|assumption].
Qed.

(* Within one duplicate-free ranking, scores strictly decrease with rank. *)
Lemma ranking_strict : forall r pos, NoDup r ->
  Sorted (fun a b => contrib b r pos < contrib a r pos) r.
Proof.
  intro r. induction r as [|x r IH]; intros pos Hnd; [constructor|].
  inversion Hnd as [|? ? Hx Hr]; subst. constructor.
  - apply (Sorted_In_impl (fun a b => contrib b r (S pos) < contrib a r (S pos))).
    + intros a b Ha Hb H.
      assert (Hxa : x <> a) by (intro; subst; contradiction).
      assert (Hxb : x <> b) by (intro; subst; contradiction).
      rewrite (contrib_tail x r pos a Hxa), (contrib_tail x r pos b Hxb). exact H.
    + apply IH. exact Hr.
  - destruct r as [|y r']; constructor.
    assert (Hxy : x <> y) by (intro; subst; apply Hx; left; reflexivity).
    rewrite (contrib_tail x (y :: r') pos y Hxy), (contrib_head x (y :: r') pos Hnd).
    assert (Hb := contrib_bound y (y :: r') (S pos) Hr).
    assert (Hlt := inv_pos_lt (rrf_k + pos) (rrf_k + S pos) ltac:(unfold rrf_k; lia) ltac:(lia)).
    lra.
Qed.

Lemma before_of_lt : forall sc a b, sc b < sc a -> before_by sc a b = true.
Proof.
  intros sc a b H. unfold before_by.
  destruct (Qlt_le_dec (sc b) (sc a)); [reflexivity|]. exfalso. lra.
Qed.

(* For ANY score function that strictly decreases along r (e.g. the float
   values 1.0/(60+rank) when IEEE division is strictly monotone on the ranks
   used), the fused order is r itself. *)
Theorem fuse_by_passthrough : forall sc rs r,
  keys rs = r -> Sorted (fun a b => sc b < sc a) r -> fuse_by sc rs = r.
Proof.
  intros sc rs r Hk Hs. unfold fuse_by. rewrite Hk. apply isort_id.
  apply (Sorted_In_impl (fun a b => sc b < sc a)); [|exact Hs].
  intros a b _ _ H. apply before_of_lt. exact H.
Qed.

Lemma fuse_passthrough : forall rs r,
  NoDup r -> keys rs = r -> (forall a, score rs a == contrib a r 1) -> fuse rs = r.
Proof.
  intros rs r Hnd Hk Hsc. apply fuse_by_passthrough; [exact Hk|].
  apply (Sorted_In_impl (fun a b => contrib b r 1 < contrib a r 1)).
  - intros a b _ _ H. rewrite !Hsc. exact H.
  - apply ranking_strict. exact Hnd.
Qed.

Lemma keys_single : forall r, NoDup r -> keys [r] = r.
Proof.
  intros r Hnd. unfold keys. simpl. rewrite app_nil_r.
  apply dedup_acc_id; [exact Hnd|]. intros x _ [].
Qed.

(* (c) One ranking alone is returned in its own order, regardless of key_leb. *)
Theorem fuse_single : forall r, NoDup r -> fuse [r] = r.
Proof.
  intros r Hnd. apply fuse_passthrough; [exact Hnd|apply keys_single; exact Hnd|].
  intro a. unfold score. cbn [fold_right contrib]. lra.
Qed.

(* (c) recall's case: the keyword ranking is empty. *)
Theorem fuse_keyword_empty : forall r, NoDup r -> fuse [r; []] = r.
Proof.
  intros r Hnd. apply fuse_passthrough; [exact Hnd| |].
  - unfold keys. simpl. rewrite !app_nil_r.
    apply dedup_acc_id; [exact Hnd|]. intros x _ [].
  - intro a. unfold score. cbn [fold_right contrib]. lra.
Qed.

(* (c) symmetric case: the vector ranking is empty. *)
Theorem fuse_vector_empty : forall r, NoDup r -> fuse [[]; r] = r.
Proof.
  intros r Hnd. apply fuse_passthrough; [exact Hnd| |].
  - unfold keys. simpl. rewrite !app_nil_r.
    apply dedup_acc_id; [exact Hnd|]. intros x _ [].
  - intro a. unfold score. cbn [fold_right contrib]. lra.
Qed.

End Fusion.

(* Counterexample showing why NoDup is needed in (c): a repeated id
   accumulates two contributions and overtakes an earlier id. *)
Example duplicate_ranking_reorders :
  fuse Nat.leb [[1; 2; 3; 2]%nat] = [2; 1; 3]%nat.
Proof. vm_compute. reflexivity. Qed.

(* A two-ranking example: 7 is ranked 2nd and 1st, so it wins. *)
Example two_rankings :
  fuse Nat.leb [[5; 7; 9]%nat; [7; 3]%nat] = [7; 5; 3; 9]%nat.
Proof. vm_compute. reflexivity. Qed.

Print Assumptions fuse_In.
Print Assumptions fuse_NoDup.
Print Assumptions fuse_scope_isolation.
Print Assumptions recall_output_isolated.
Print Assumptions fuse_sorted.
Print Assumptions fuse_unique.
Print Assumptions fuse_single.
Print Assumptions fuse_keyword_empty.
Print Assumptions fuse_vector_empty.
Print Assumptions fuse_by_passthrough.

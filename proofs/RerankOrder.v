(* Formal model of rerank_order in src/llm_memory_store/rerank.py:

     def rerank_order(scores, limit):
         def key(index):
             value = scores[index]
             return (math.inf if math.isnan(value) else -value, index)
         return sorted(range(len(scores)), key=key)[:limit]

   and of its use in MemoryStore.recall (src/llm_memory_store/store.py):

     scored = [pool[i] for i in rerank_order(scores, len(pool))]

   Scores live in an arbitrary type [Sc] ordered by a boolean total preorder
   [le] ([le s t = true] reads "s ranks no higher than t", i.e. key(s) >=
   key(t) in Python).  Python's key (-score, index) puts index i before j iff
   score j < score i, or the scores are equal and i <= j; that is [before]
   below.  Indices are distinct, so the key is a strict total order on them
   and the sorted list is unique ([rerank_order_unique]): the model sorts
   (index, score) pairs with a stable insertion sort, but any correct sort,
   stable or not, gives the same list.

   The generic theorems are instantiated for exact rationals [Q] and for
   [option Q], where [None] stands for NaN and ranks below every number. *)

From Stdlib Require Import List Bool Arith Lia QArith Lqa.
From Stdlib Require Import Sorting.Sorted Sorting.Permutation.
Import ListNotations.

(* ---------------- generic stable insertion sort ---------------- *)

Section Sort.
  Context {A : Type} (leb : A -> A -> bool).

  Fixpoint insert (x : A) (l : list A) : list A :=
    match l with
    | [] => [x]
    | y :: l' => if leb x y then x :: l else y :: insert x l'
    end.

  Fixpoint isort (l : list A) : list A :=
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

  Definition R (a b : A) : Prop := leb a b = true.

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

  (* Sorting an already sorted list changes nothing. *)
  Lemma isort_id : forall l, Sorted R l -> isort l = l.
  Proof.
    induction l as [|x l IH]; intro Hs; simpl; [reflexivity|].
    inversion Hs as [|x' l' Hl Hhd]; subst. rewrite IH by exact Hl.
    destruct l as [|y l']; simpl; [reflexivity|].
    inversion Hhd as [|? ? Hxy]; subst. unfold R in Hxy. rewrite Hxy. reflexivity.
  Qed.
End Sort.

(* ---------------- generic list facts ---------------- *)

Lemma firstn_In' : forall {A} n (l : list A) x, In x (firstn n l) -> In x l.
Proof.
  intros A n. induction n as [|n IH]; intros l x H; [destruct H|].
  destruct l as [|y l]; [destruct H|]. simpl in *.
  destruct H; [left; assumption|right; eauto].
Qed.

Lemma firstn_NoDup' : forall {A} n (l : list A), NoDup l -> NoDup (firstn n l).
Proof.
  intros A n. induction n as [|n IH]; intros l Hl; simpl; [constructor|].
  destruct l as [|y l]; [constructor|]. inversion Hl; subst.
  constructor; [|auto]. intro H. apply H1. eapply firstn_In'. exact H.
Qed.

Lemma firstn_seq' : forall n start len, firstn n (seq start len) = seq start (Nat.min n len).
Proof.
  induction n as [|n IH]; intros start len; simpl; [reflexivity|].
  destruct len as [|len]; simpl; [reflexivity|]. rewrite IH. reflexivity.
Qed.

Lemma Sorted_weaken : forall {A} (R1 R2 : A -> A -> Prop) l,
  (forall a b, R1 a b -> R2 a b) -> Sorted R1 l -> Sorted R2 l.
Proof.
  intros A R1 R2 l Himp. induction l as [|x l IH]; intro Hs; [constructor|].
  inversion Hs as [|? ? Hl Hhd]; subst. constructor; [apply IH; exact Hl|].
  destruct l as [|y l']; constructor. inversion Hhd; subst. apply Himp. assumption.
Qed.

Lemma Sorted_of_all : forall {A} (R1 : A -> A -> Prop) l,
  (forall a b, In a l -> In b l -> R1 a b) -> Sorted R1 l.
Proof.
  intros A R1 l. induction l as [|x l IH]; intro H; [constructor|]. constructor.
  - apply IH. intros a b Ha Hb. apply H; right; assumption.
  - destruct l as [|y l']; constructor. apply H; [left|right; left]; reflexivity.
Qed.

Lemma SS_map : forall {A B} (f : A -> B) (R1 : A -> A -> Prop) (R2 : B -> B -> Prop) l,
  (forall a b, In a l -> In b l -> R1 a b -> R2 (f a) (f b)) ->
  StronglySorted R1 l -> StronglySorted R2 (map f l).
Proof.
  intros A B f R1 R2 l. induction l as [|x l IH]; intros H HS; simpl; [constructor|].
  inversion HS as [|? ? HS' HF]; subst. constructor.
  - apply IH; [intros a b Ha Hb; apply H; right; assumption|exact HS'].
  - rewrite Forall_forall in *. intros y Hy. apply in_map_iff in Hy.
    destruct Hy as [b [<- Hb]].
    apply H; [left; reflexivity|right; exact Hb|apply HF; exact Hb].
Qed.

Lemma strongly_sorted_unique : forall {A} (Rel : A -> A -> Prop),
  (forall a b, Rel a b -> Rel b a -> a = b) ->
  forall l1 l2, Permutation l1 l2 -> StronglySorted Rel l1 -> StronglySorted Rel l2 -> l1 = l2.
Proof.
  intros A Rel Hanti l1. induction l1 as [|a l1 IH]; intros l2 Hp H1 H2.
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

(* If the first components of a strongly sorted list read l1 ++ i :: l2 and
   j occurs in l2, the pairs carrying i and j are related, i's first. *)
Lemma SS_fst_app : forall {A} (R1 : nat * A -> nat * A -> Prop) P l1 i l2 j,
  StronglySorted R1 P -> map fst P = l1 ++ i :: l2 -> In j l2 ->
  exists si sj, In (i, si) P /\ In (j, sj) P /\ R1 (i, si) (j, sj).
Proof.
  intros A R1 P l1. revert P. induction l1 as [|x l1 IH];
    intros P i l2 j HS Hm Hj; destruct P as [|[k s] P]; simpl in Hm; try discriminate;
    injection Hm as Hk Hm'; inversion HS as [|? ? HS' HF]; subst.
  - apply in_map_iff in Hj. destruct Hj as [[j' sj] [Hj' Hin]].
    simpl in Hj'. subst j'. exists s, sj. split; [left; reflexivity|].
    split; [right; exact Hin|]. rewrite Forall_forall in HF. apply HF. exact Hin.
  - destruct (IH P i l2 j HS' Hm' Hj) as [si [sj [Hi [Hj2 Hr]]]].
    exists si, sj. split; [right; exact Hi|]. split; [right; exact Hj2|exact Hr].
Qed.

(* ---------------- the model ---------------- *)

Section Rerank.

Context {Sc : Type} (le : Sc -> Sc -> bool).

(* Python key order on (index, score) pairs: (-si, i) <= (-sj, j). *)
Definition before (p q : nat * Sc) : bool :=
  let (i, si) := p in
  let (j, sj) := q in
  if le si sj then le sj si && Nat.leb i j else true.

(* range(len(scores)) paired with the scores: [(k, s_0); (k+1, s_1); ...]. *)
Fixpoint indexed_from (k : nat) (l : list Sc) : list (nat * Sc) :=
  match l with
  | [] => []
  | s :: l' => (k, s) :: indexed_from (S k) l'
  end.

Definition sorted_pairs (scores : list Sc) : list (nat * Sc) :=
  isort before (indexed_from 0 scores).

(* sorted(range(len(scores)), key=key) *)
Definition full_order (scores : list Sc) : list nat := map fst (sorted_pairs scores).

(* sorted(...)[:limit] *)
Definition rerank_order (scores : list Sc) (limit : nat) : list nat :=
  firstn limit (full_order scores).

(* "index i with score si strictly precedes index j with score sj":
   si is strictly higher, or the scores are equal and i < j. *)
Definition outranks (si : Sc) (i : nat) (sj : Sc) (j : nat) : Prop :=
  le si sj = false \/ (le si sj = true /\ le sj si = true /\ (i < j)%nat).

(* The same order on indices alone, looking the scores up. *)
Definition idx_before (scores : list Sc) (i j : nat) : bool :=
  match nth_error scores i, nth_error scores j with
  | Some si, Some sj => before (i, si) (j, sj)
  | _, _ => false
  end.

Lemma indexed_from_fst : forall l k, map fst (indexed_from k l) = seq k (length l).
Proof.
  induction l as [|s l IH]; intro k; simpl; [reflexivity|]. rewrite IH. reflexivity.
Qed.

Lemma indexed_from_nth : forall l k i s,
  In (i, s) (indexed_from k l) -> (k <= i)%nat /\ nth_error l (i - k) = Some s.
Proof.
  induction l as [|s0 l IH]; intros k i s H; simpl in H; [destruct H|].
  destruct H as [H|H].
  - injection H as <- <-. rewrite Nat.sub_diag. split; [lia|reflexivity].
  - destruct (IH (S k) i s H) as [Hk Hn]. split; [lia|].
    replace (i - k)%nat with (S (i - S k)) by lia. exact Hn.
Qed.

Lemma sorted_pairs_nth : forall scores i s,
  In (i, s) (sorted_pairs scores) -> nth_error scores i = Some s.
Proof.
  intros scores i s H. unfold sorted_pairs in H.
  apply (Permutation_in _ (isort_perm before _)) in H.
  apply indexed_from_nth in H. rewrite Nat.sub_0_r in H. apply H.
Qed.

Lemma full_order_perm : forall scores,
  Permutation (full_order scores) (seq 0 (length scores)).
Proof.
  intro scores. unfold full_order, sorted_pairs. rewrite <- indexed_from_fst.
  apply Permutation_map, isort_perm.
Qed.

Lemma full_order_NoDup : forall scores, NoDup (full_order scores).
Proof.
  intro scores. eapply Permutation_NoDup; [symmetry; apply full_order_perm|].
  apply seq_NoDup.
Qed.

Lemma before_spec : forall i si j sj,
  before (i, si) (j, sj) = true <->
  le si sj = false \/ (le si sj = true /\ le sj si = true /\ (i <= j)%nat).
Proof.
  intros i si j sj. unfold before.
  destruct (le si sj), (le sj si); simpl; rewrite ?Nat.leb_le; intuition congruence.
Qed.

Lemma before_strict : forall i si j sj,
  i <> j -> before (i, si) (j, sj) = true -> outranks si i sj j.
Proof.
  intros i si j sj Hne H. apply before_spec in H. unfold outranks.
  destruct H as [H|[H1 [H2 H3]]]; [left; exact H|right; repeat split; auto; lia].
Qed.

(* ---------------- (1) indices ---------------- *)

Theorem rerank_order_in_range : forall scores limit i,
  In i (rerank_order scores limit) -> (i < length scores)%nat.
Proof.
  intros scores limit i H. apply firstn_In' in H.
  apply (Permutation_in _ (full_order_perm scores)) in H.
  apply in_seq in H. lia.
Qed.

Theorem rerank_order_NoDup : forall scores limit, NoDup (rerank_order scores limit).
Proof.
  intros scores limit. apply firstn_NoDup', full_order_NoDup.
Qed.

Theorem rerank_order_length : forall scores limit,
  length (rerank_order scores limit) = Nat.min limit (length scores).
Proof.
  intros scores limit. unfold rerank_order. rewrite length_firstn.
  rewrite (Permutation_length (full_order_perm scores)), length_seq. reflexivity.
Qed.

(* ---------------- (2) subset / scope isolation ---------------- *)

(* [pool[i] for i in rerank_order(scores, limit)]: every item comes from the
   pool, so any property of every pool item (e.g. "lies in one of the
   queried scopes") holds of every re-ranked item.  The default [d] of [nth]
   is never used, because every index is < length scores <= length pool. *)
Theorem rerank_order_subset : forall {B} (pool : list B) (d : B) (P : B -> Prop) scores limit,
  (length scores <= length pool)%nat -> Forall P pool ->
  Forall P (map (fun i => nth i pool d) (rerank_order scores limit)).
Proof.
  intros B pool d P scores limit Hlen HP. apply Forall_forall. intros x Hx.
  apply in_map_iff in Hx. destruct Hx as [i [<- Hi]].
  apply rerank_order_in_range in Hi. rewrite Forall_forall in HP.
  apply HP, nth_In. lia.
Qed.

(* ---------------- sortedness (needs a total preorder) ---------------- *)

Section Preorder.

Context (le_total : forall a b, le a b = true \/ le b a = true).
Context (le_trans : forall a b c, le a b = true -> le b c = true -> le a c = true).

Lemma before_total : forall p q, before p q = true \/ before q p = true.
Proof.
  intros [i si] [j sj]. rewrite !before_spec.
  destruct (le si sj) eqn:E1; [|left; left; reflexivity].
  destruct (le sj si) eqn:E2; [|right; left; reflexivity].
  destruct (Nat.le_ge_cases i j); [left|right]; right; auto.
Qed.

Lemma before_ge : forall i si j sj, before (i, si) (j, sj) = true -> le sj si = true.
Proof.
  intros i si j sj H. apply before_spec in H. destruct H as [H|[_ [H _]]]; [|exact H].
  destruct (le_total si sj); congruence.
Qed.

Lemma before_trans : forall p q r,
  before p q = true -> before q r = true -> before p r = true.
Proof.
  intros [i a] [j b] [k c] H1 H2.
  assert (Hba := before_ge _ _ _ _ H1). assert (Hcb := before_ge _ _ _ _ H2).
  apply before_spec. destruct (le a c) eqn:Eac; [right|left; reflexivity].
  split; [reflexivity|]. split; [apply (le_trans c b a); assumption|].
  apply before_spec in H1. apply before_spec in H2.
  destruct H1 as [H1|[_ [_ H1]]]; [rewrite (le_trans a c b Eac Hcb) in H1; discriminate|].
  destruct H2 as [H2|[_ [_ H2]]]; [rewrite (le_trans b a c Hba Eac) in H2; discriminate|].
  lia.
Qed.

Lemma before_antisym : forall i si j sj,
  before (i, si) (j, sj) = true -> before (j, sj) (i, si) = true -> i = j.
Proof.
  intros i si j sj H1 H2. apply before_spec in H1. apply before_spec in H2.
  destruct H1 as [H1|[H1a [H1b H1c]]], H2 as [H2|[H2a [H2b H2c]]];
    try congruence; try lia.
  destruct (le_total si sj); congruence.
Qed.

Lemma sorted_pairs_SS : forall scores,
  StronglySorted (fun p q => before p q = true) (sorted_pairs scores).
Proof.
  intro scores. apply Sorted_StronglySorted.
  - intros p q r. apply before_trans.
  - apply isort_sorted. apply before_total.
Qed.

(* Any index earlier in the full sorted list outranks any later one. *)
Lemma full_order_outranks : forall scores l1 i l2 j si sj,
  full_order scores = l1 ++ i :: l2 -> In j l2 ->
  nth_error scores i = Some si -> nth_error scores j = Some sj -> outranks si i sj j.
Proof.
  intros scores l1 i l2 j si sj Hf Hj Hsi Hsj.
  destruct (SS_fst_app _ _ l1 i l2 j (sorted_pairs_SS scores) Hf Hj)
    as [si' [sj' [Hi' [Hj' Hb]]]].
  apply sorted_pairs_nth in Hi', Hj'.
  rewrite Hsi in Hi'. rewrite Hsj in Hj'. injection Hi' as <-. injection Hj' as <-.
  apply before_strict; [|exact Hb].
  intros <-. pose proof (full_order_NoDup scores) as Hnd. rewrite Hf in Hnd.
  apply NoDup_remove_2 in Hnd. apply Hnd, in_or_app. right. exact Hj.
Qed.

(* ---------------- (3) order ---------------- *)

(* Every output index outranks every later output index. *)
Theorem rerank_order_sorted : forall scores limit l1 i l2 j si sj,
  rerank_order scores limit = l1 ++ i :: l2 -> In j l2 ->
  nth_error scores i = Some si -> nth_error scores j = Some sj -> outranks si i sj j.
Proof.
  intros scores limit l1 i l2 j si sj Hr Hj Hsi Hsj.
  apply (full_order_outranks scores l1 i (l2 ++ skipn limit (full_order scores)));
    [|apply in_or_app; left; exact Hj|exact Hsi|exact Hsj].
  rewrite <- (firstn_skipn limit (full_order scores)) at 1.
  fold (rerank_order scores limit). rewrite Hr, <- app_assoc. reflexivity.
Qed.

(* (3) as stated: consecutive output indices i, j. *)
Theorem rerank_order_consecutive : forall scores limit l1 i j l2 si sj,
  rerank_order scores limit = l1 ++ i :: j :: l2 ->
  nth_error scores i = Some si -> nth_error scores j = Some sj -> outranks si i sj j.
Proof.
  intros scores limit l1 i j l2 si sj Hr.
  apply (rerank_order_sorted scores limit l1 i (j :: l2)); [exact Hr|left; reflexivity].
Qed.

(* ---------------- (4) top-limit optimality ---------------- *)

(* An index left out has a score <= every chosen score, and when the scores
   are equal it comes later than the chosen index. *)
Theorem rerank_order_top : forall scores limit k i sk si,
  ~ In k (rerank_order scores limit) -> In i (rerank_order scores limit) ->
  nth_error scores k = Some sk -> nth_error scores i = Some si ->
  le sk si = true /\ (le si sk = true -> (i < k)%nat).
Proof.
  intros scores limit k i sk si Hk Hi Hsk Hsi.
  assert (Hkf : In k (full_order scores)).
  { apply (Permutation_in _ (Permutation_sym (full_order_perm scores))).
    apply in_seq. split; [lia|]. apply nth_error_Some. congruence. }
  apply in_split in Hi. destruct Hi as [l1 [l2 Hr]].
  assert (Hf : full_order scores = l1 ++ i :: (l2 ++ skipn limit (full_order scores))).
  { rewrite <- (firstn_skipn limit (full_order scores)) at 1.
    fold (rerank_order scores limit). rewrite Hr, <- app_assoc. reflexivity. }
  assert (Hk' : In k (l2 ++ skipn limit (full_order scores))).
  { rewrite <- (firstn_skipn limit (full_order scores)) in Hkf.
    apply in_app_or in Hkf. destruct Hkf as [Hkf|Hkf]; [contradiction|].
    apply in_or_app. right. exact Hkf. }
  destruct (full_order_outranks scores l1 i _ k si sk Hf Hk' Hsi Hsk)
    as [H|[H1 [H2 H3]]].
  - split; [destruct (le_total si sk); congruence|]. intro; congruence.
  - split; [exact H2|]. intros _. exact H3.
Qed.

(* ---------------- uniqueness: this is what sorted() returns ---------------- *)

(* Every permutation of range(len(scores)) that is sorted by the Python key
   gives, after [:limit], exactly rerank_order: the result does not depend on
   the sorting algorithm or on its stability. *)
Theorem rerank_order_unique : forall scores limit l,
  Permutation l (seq 0 (length scores)) ->
  Sorted (fun i j => idx_before scores i j = true) l ->
  firstn limit l = rerank_order scores limit.
Proof.
  intros scores limit l Hp Hs. unfold rerank_order. f_equal.
  assert (Tr : forall i j k, idx_before scores i j = true -> idx_before scores j k = true ->
                             idx_before scores i k = true).
  { intros i j k. unfold idx_before.
    destruct (nth_error scores i), (nth_error scores j), (nth_error scores k);
      try discriminate; apply before_trans. }
  apply (strongly_sorted_unique (fun i j => idx_before scores i j = true)).
  - intros i j. unfold idx_before.
    destruct (nth_error scores i), (nth_error scores j); try discriminate.
    apply before_antisym.
  - rewrite Hp. symmetry. apply full_order_perm.
  - apply Sorted_StronglySorted; [exact Tr|exact Hs].
  - apply SS_map with (R1 := fun p q => before p q = true); [|apply sorted_pairs_SS].
    intros [i si] [j sj] Hi Hj Hb. simpl. unfold idx_before.
    rewrite (sorted_pairs_nth _ _ _ Hi), (sorted_pairs_nth _ _ _ Hj). exact Hb.
Qed.

End Preorder.

(* ---------------- (5) and (6): already ordered input is kept ---------------- *)

Lemma indexed_from_sorted : forall l k,
  Sorted (fun s t => le t s = true) l -> Sorted (fun p q => before p q = true) (indexed_from k l).
Proof.
  induction l as [|s l IH]; intros k Hs; simpl; [constructor|].
  inversion Hs as [|? ? Hl Hhd]; subst. constructor; [apply IH; exact Hl|].
  destruct l as [|t l']; simpl; constructor.
  inversion Hhd as [|? ? Hts]; subst. apply before_spec.
  destruct (le s t); [right; repeat split; auto|left; reflexivity].
Qed.

(* Scores that never increase along the list keep vector order. *)
Theorem rerank_order_nonincreasing : forall scores limit,
  Sorted (fun s t => le t s = true) scores ->
  rerank_order scores limit = seq 0 (Nat.min limit (length scores)).
Proof.
  intros scores limit Hs. unfold rerank_order, full_order, sorted_pairs.
  rewrite isort_id by (apply indexed_from_sorted; exact Hs).
  rewrite indexed_from_fst. apply firstn_seq'.
Qed.

(* (5) Stability: all scores equal -> [0; 1; ...; min(limit, len) - 1]. *)
Theorem rerank_order_all_equal : forall scores limit,
  (forall s t, In s scores -> In t scores -> le s t = true) ->
  rerank_order scores limit = seq 0 (Nat.min limit (length scores)).
Proof.
  intros scores limit H. apply rerank_order_nonincreasing.
  apply Sorted_of_all. intros s t Hs Ht. apply H; assumption.
Qed.

(* (6) Strictly decreasing scores -> the first [limit] indices in order. *)
Theorem rerank_order_strictly_decreasing :
  (forall a b, le a b = true \/ le b a = true) ->
  forall scores limit,
  Sorted (fun s t => le s t = false) scores ->
  rerank_order scores limit = seq 0 (Nat.min limit (length scores)).
Proof.
  intros Htot scores limit Hs. apply rerank_order_nonincreasing.
  apply (Sorted_weaken (fun s t => le s t = false)); [|exact Hs].
  intros a b H. destruct (Htot a b); congruence.
Qed.

End Rerank.

(* ---------------- instance: exact rationals ---------------- *)

Lemma Qle_bool_total : forall a b, Qle_bool a b = true \/ Qle_bool b a = true.
Proof.
  intros a b. rewrite !Qle_bool_iff. destruct (Qlt_le_dec a b); [left; lra|right; lra].
Qed.

Lemma Qle_bool_trans : forall a b c,
  Qle_bool a b = true -> Qle_bool b c = true -> Qle_bool a c = true.
Proof. intros a b c. rewrite !Qle_bool_iff. apply Qle_trans. Qed.

Lemma Qle_bool_false : forall a b, Qle_bool a b = false <-> b < a.
Proof.
  intros a b. split; intro H.
  - destruct (Qlt_le_dec b a) as [Hl|Hl]; [exact Hl|].
    apply Qle_bool_iff in Hl. congruence.
  - destruct (Qle_bool a b) eqn:E; [|reflexivity]. apply Qle_bool_iff in E. lra.
Qed.

Definition rerank_order_Q : list Q -> nat -> list nat := rerank_order Qle_bool.

Lemma outranks_Q : forall si i sj j,
  outranks Qle_bool si i sj j <-> sj < si \/ (si == sj /\ (i < j)%nat).
Proof.
  intros si i sj j. unfold outranks. rewrite Qle_bool_false, !Qle_bool_iff.
  split; (intros [H|H]; [left; exact H|right]).
  - destruct H as [H1 [H2 H3]]. split; [apply Qle_antisym|]; assumption.
  - destruct H as [H1 H2]. repeat split; [lra|lra|exact H2].
Qed.

(* (3) over Q: an earlier output index has a strictly higher score, or an
   equal score and a smaller index. *)
Theorem rerank_Q_sorted : forall scores limit l1 i l2 j si sj,
  rerank_order_Q scores limit = l1 ++ i :: l2 -> In j l2 ->
  nth_error scores i = Some si -> nth_error scores j = Some sj ->
  sj < si \/ (si == sj /\ (i < j)%nat).
Proof.
  intros. apply outranks_Q.
  eapply rerank_order_sorted; eauto using Qle_bool_total, Qle_bool_trans.
Qed.

(* (4) over Q. *)
Theorem rerank_Q_top : forall scores limit k i sk si,
  ~ In k (rerank_order_Q scores limit) -> In i (rerank_order_Q scores limit) ->
  nth_error scores k = Some sk -> nth_error scores i = Some si ->
  sk <= si /\ (si == sk -> (i < k)%nat).
Proof.
  intros scores limit k i sk si Hk Hi Hsk Hsi.
  destruct (rerank_order_top Qle_bool Qle_bool_total Qle_bool_trans
              scores limit k i sk si Hk Hi Hsk Hsi) as [H1 H2].
  split; [apply Qle_bool_iff; exact H1|].
  intro Heq. apply H2, Qle_bool_iff. lra.
Qed.

(* (5) over Q. *)
Theorem rerank_Q_all_equal : forall scores limit,
  (forall s t, In s scores -> In t scores -> s == t) ->
  rerank_order_Q scores limit = seq 0 (Nat.min limit (length scores)).
Proof.
  intros scores limit H. apply rerank_order_all_equal.
  intros s t Hs Ht. apply Qle_bool_iff. rewrite (H s t Hs Ht). apply Qle_refl.
Qed.

(* (6) over Q. *)
Theorem rerank_Q_strictly_decreasing : forall scores limit,
  Sorted (fun s t => t < s) scores ->
  rerank_order_Q scores limit = seq 0 (Nat.min limit (length scores)).
Proof.
  intros scores limit Hs. apply rerank_order_strictly_decreasing; [apply Qle_bool_total|].
  apply (Sorted_weaken (fun s t => t < s)); [|exact Hs].
  intros a b H. apply Qle_bool_false. exact H.
Qed.

(* Cross-checks against Python (values captured from rerank_order in the
   project venv):
     rerank_order([0.5, 0.75, 0.5, 2.0], 3)  == [3, 1, 0]
     rerank_order([0.5, 0.75, 0.5, 2.0], 10) == [3, 1, 0, 2]
     rerank_order([0.5, 0.5, 0.5], 2)        == [0, 1]
     rerank_order([], 5)                     == []
   1#2 and 2#4 are different terms of Q but equal numbers; they tie. *)
Example rerank_Q_example1 :
  rerank_order_Q [1#2; 3#4; 2#4; 2] 3 = [3; 1; 0]%nat.
Proof. vm_compute. reflexivity. Qed.

Example rerank_Q_example2 :
  rerank_order_Q [1#2; 3#4; 2#4; 2] 10 = [3; 1; 0; 2]%nat.
Proof. vm_compute. reflexivity. Qed.

Example rerank_Q_example3 : rerank_order_Q [1#2; 1#2; 1#2] 2 = [0; 1]%nat.
Proof. vm_compute. reflexivity. Qed.

Example rerank_Q_example4 : rerank_order_Q [] 5 = [].
Proof. vm_compute. reflexivity. Qed.

(* ---------------- instance: rationals with NaN ranked last ---------------- *)

(* [None] stands for NaN.  rerank.py's key maps NaN to +inf (after negation),
   so NaN ranks below every finite number; NaNs tie with each other and fall
   to the index.  Python also ties NaN with -inf (rerank_order([nan, -inf], 2)
   == [0, 1]); Q has no infinities, so that tie is outside this instance.
   Cross-check: rerank_order([nan, 0.5, nan, 2.0], 4) == [3, 1, 0, 2]. *)
Definition le_nan (a b : option Q) : bool :=
  match a, b with
  | None, _ => true
  | Some _, None => false
  | Some x, Some y => Qle_bool x y
  end.

Lemma le_nan_total : forall a b, le_nan a b = true \/ le_nan b a = true.
Proof.
  intros [x|] [y|]; simpl; auto. apply Qle_bool_total.
Qed.

Lemma le_nan_trans : forall a b c, le_nan a b = true -> le_nan b c = true -> le_nan a c = true.
Proof.
  intros [x|] [y|] [z|]; simpl; try discriminate; auto. apply Qle_bool_trans.
Qed.

(* Every index after a NaN-scored index is also NaN-scored and later: NaN
   scores sort last, in candidate order. *)
Theorem rerank_nan_last : forall scores limit l1 i l2 j sj,
  rerank_order le_nan scores limit = l1 ++ i :: l2 -> In j l2 ->
  nth_error scores i = Some None -> nth_error scores j = Some sj ->
  sj = None /\ (i < j)%nat.
Proof.
  intros scores limit l1 i l2 j sj Hr Hj Hi Hsj.
  destruct (rerank_order_sorted le_nan le_nan_total le_nan_trans
              scores limit l1 i l2 j None sj Hr Hj Hi Hsj) as [H|[_ [H2 H3]]];
    [discriminate|].
  destruct sj; [discriminate|]. split; [reflexivity|exact H3].
Qed.

Example rerank_nan_example :
  rerank_order le_nan [None; Some (1#2); None; Some 2] 4 = [3; 1; 0; 2]%nat.
Proof. vm_compute. reflexivity. Qed.

Print Assumptions rerank_order_in_range.
Print Assumptions rerank_order_NoDup.
Print Assumptions rerank_order_length.
Print Assumptions rerank_order_subset.
Print Assumptions rerank_order_sorted.
Print Assumptions rerank_order_consecutive.
Print Assumptions rerank_order_top.
Print Assumptions rerank_order_unique.
Print Assumptions rerank_order_all_equal.
Print Assumptions rerank_order_strictly_decreasing.
Print Assumptions rerank_order_nonincreasing.
Print Assumptions rerank_Q_sorted.
Print Assumptions rerank_Q_top.
Print Assumptions rerank_Q_all_equal.
Print Assumptions rerank_Q_strictly_decreasing.
Print Assumptions rerank_nan_last.

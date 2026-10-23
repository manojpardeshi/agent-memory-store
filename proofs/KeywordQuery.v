(* Formal model of [keyword_query] in src/llm_memory_store/store.py.

     terms = [token for token in _KEYWORD_TOKEN.findall(text.lower())
              if token not in KEYWORD_STOPWORDS and len(token) > 1]
     unique = list(dict.fromkeys(terms))[:MAX_KEYWORD_QUERY_TERMS]
     return ' OR '.join(DQ + term + DQ for term in unique) if unique else None

   (written here with DQ for the double-quote character, which Rocq comments
   cannot contain unbalanced; the source uses an f-string), 

   with _KEYWORD_TOKEN = re.compile(r'[^\W_]+') and MAX_KEYWORD_QUERY_TERMS = 64.

   Characters are an abstract type [A] (Python code points).  The regex
   character class [^\W_] is an abstract decidable predicate [word_char]; the
   only fact used about it is that it rejects the double quote, which holds
   for Python's Unicode \w minus underscore; the separator characters (space,
   O, R) are assumed to differ from the double quote.  [str.lower] is an
   arbitrary function [lower] (it may change length, e.g. 'I WITH DOT' lowers
   to two code points), and the stopword set is an arbitrary decidable
   predicate.  Every theorem is universally quantified over all of these, so
   it holds for the concrete Python choices in particular.  At the end the
   model is instantiated with ASCII, an ASCII [lower] and the exact stopword
   list, and checked against outputs produced by the Python function. *)

From Stdlib Require Import Ascii String.
From Stdlib Require Import List Bool Arith Lia.
Import ListNotations.

Section KeywordQuery.

Context {A : Type}.
Context (eq_dec : forall x y : A, {x = y} + {x <> y}).
Context (word_char : A -> bool).
Context (dquote space o_chr r_chr : A).
(* [^\W_] never matches the double quote *)
Context (dquote_not_word : word_char dquote = false).
(* the separator ' OR ' contains no double quote *)
Context (space_not_dquote : space <> dquote).
Context (o_not_dquote : o_chr <> dquote).
Context (r_not_dquote : r_chr <> dquote).
Context (is_stopword : list A -> bool).
Context (lower : list A -> list A).

Definition max_terms : nat := 64.

Definition WordRun (t : list A) : Prop :=
  t <> [] /\ Forall (fun c => word_char c = true) t.

(* ------------------------------------------------------------------ *)
(* re.findall(r'[^\W_]+', s): the maximal runs of word characters.    *)

Fixpoint tokens_acc (cur : list A) (s : list A) : list (list A) :=
  match s with
  | [] => match cur with [] => [] | _ => [rev cur] end
  | c :: s' =>
      if word_char c then tokens_acc (c :: cur) s'
      else match cur with
           | [] => tokens_acc [] s'
           | _ => rev cur :: tokens_acc [] s'
           end
  end.

Definition tokens (s : list A) : list (list A) := tokens_acc [] s.

Lemma tokens_acc_wordrun : forall s cur,
  Forall (fun c => word_char c = true) cur ->
  Forall WordRun (tokens_acc cur s).
Proof.
  induction s as [|c s IH]; intros cur Hcur; simpl.
  - destruct cur as [|x cur'].
    + constructor.
    + constructor; [|constructor]. split.
      * intro H. apply (f_equal (@length A)) in H.
        rewrite length_rev in H. simpl in H. discriminate.
      * apply Forall_rev. exact Hcur.
  - destruct (word_char c) eqn:Hc.
    + apply IH. constructor; assumption.
    + destruct cur as [|x cur'].
      * apply IH. constructor.
      * constructor.
        -- split.
           ++ intro H. apply (f_equal (@length A)) in H.
              rewrite length_rev in H. simpl in H. discriminate.
           ++ apply Forall_rev. exact Hcur.
        -- apply IH. constructor.
Qed.

Theorem tokens_are_word_runs : forall s, Forall WordRun (tokens s).
Proof. intro s. apply tokens_acc_wordrun. constructor. Qed.

(* Tokenisation keeps every word character, in order, and nothing else. *)
Lemma tokens_acc_concat : forall s cur,
  concat (tokens_acc cur s) = rev cur ++ filter word_char s.
Proof.
  induction s as [|c s IH]; intro cur; simpl.
  - destruct cur; simpl; [reflexivity|]. rewrite app_nil_r. reflexivity.
  - destruct (word_char c) eqn:Hc.
    + rewrite IH. simpl. rewrite <- app_assoc. reflexivity.
    + destruct cur as [|x cur'].
      * rewrite IH. reflexivity.
      * simpl. rewrite IH. reflexivity.
Qed.

Theorem tokens_concat : forall s, concat (tokens s) = filter word_char s.
Proof. intro s. unfold tokens. rewrite tokens_acc_concat. reflexivity. Qed.

(* Splitting at any non-word character splits the token list: tokens never
   span a separator. *)
Lemma tokens_acc_split : forall u cur c v,
  word_char c = false ->
  tokens_acc cur (u ++ c :: v) = tokens_acc cur u ++ tokens_acc [] v.
Proof.
  induction u as [|x u IH]; intros cur c v Hc; simpl.
  - rewrite Hc. destruct cur; reflexivity.
  - destruct (word_char x).
    + apply IH. exact Hc.
    + destruct cur as [|y cur'].
      * apply IH. exact Hc.
      * simpl. rewrite IH by exact Hc. reflexivity.
Qed.

Theorem tokens_split : forall u c v,
  word_char c = false -> tokens (u ++ c :: v) = tokens u ++ tokens v.
Proof. intros. unfold tokens. apply tokens_acc_split. assumption. Qed.

Lemma tokens_acc_run : forall t cur,
  Forall (fun c => word_char c = true) t ->
  tokens_acc cur t = tokens_acc (rev t ++ cur) [].
Proof.
  induction t as [|x t IH]; intros cur Ht; simpl; [reflexivity|].
  inversion Ht; subst. rewrite H1. rewrite IH by assumption.
  rewrite <- app_assoc. reflexivity.
Qed.

(* A nonempty run of word characters is exactly one token (maximal munch). *)
Theorem tokens_run : forall t, WordRun t -> tokens t = [t].
Proof.
  intros t [Hne Ht]. unfold tokens. rewrite tokens_acc_run by assumption.
  rewrite app_nil_r. simpl.
  destruct (rev t) eqn:E.
  - exfalso. apply Hne. rewrite <- (rev_involutive t), E. reflexivity.
  - rewrite <- E, rev_involutive. reflexivity.
Qed.

(* ------------------------------------------------------------------ *)
(* Filter: token not in KEYWORD_STOPWORDS and len(token) > 1.         *)

Definition eligible (t : list A) : bool := negb (is_stopword t) && (1 <? length t).

(* list(dict.fromkeys(terms)): de-duplicate keeping first occurrences. *)
Definition list_eq_dec' := list_eq_dec eq_dec.

Fixpoint dedup_acc (seen : list (list A)) (l : list (list A)) : list (list A) :=
  match l with
  | [] => []
  | x :: l' =>
      if in_dec list_eq_dec' x seen then dedup_acc seen l'
      else x :: dedup_acc (x :: seen) l'
  end.

Definition dedup (l : list (list A)) := dedup_acc [] l.

Lemma dedup_acc_In : forall l seen y,
  In y (dedup_acc seen l) <-> In y l /\ ~ In y seen.
Proof.
  induction l as [|x l IH]; intros seen y; simpl.
  - tauto.
  - destruct (in_dec list_eq_dec' x seen) as [Hin|Hnin].
    + rewrite IH. split.
      * tauto.
      * intros [[Heq|Hl] Hns]; [subst; contradiction|tauto].
    + simpl. rewrite IH. simpl. split.
      * intros [Heq|[Hl Hns]]; [subst; tauto|tauto].
      * intros [[Heq|Hl] Hns]; [left; exact Heq|].
        destruct (list_eq_dec' x y); [left; assumption|right; split; [assumption|]].
        intros [H|H]; [contradiction|contradiction].
Qed.

Lemma dedup_acc_NoDup : forall l seen, NoDup (dedup_acc seen l).
Proof.
  induction l as [|x l IH]; intro seen; simpl.
  - constructor.
  - destruct (in_dec list_eq_dec' x seen).
    + apply IH.
    + constructor; [|apply IH].
      rewrite dedup_acc_In. simpl. tauto.
Qed.

Lemma dedup_In : forall l y, In y (dedup l) <-> In y l.
Proof. intros. unfold dedup. rewrite dedup_acc_In. simpl. tauto. Qed.

Lemma dedup_nil : forall l, dedup l = [] <-> l = [].
Proof.
  intros [|x l]; unfold dedup; simpl; [tauto|].
  split; intro H; discriminate.
Qed.

(* [:MAX_KEYWORD_QUERY_TERMS] *)
Lemma firstn_In' : forall (B : Type) n (l : list B) x, In x (firstn n l) -> In x l.
Proof.
  induction n as [|n IH]; intros l x H; [destruct H|].
  destruct l as [|y l]; [destruct H|]. simpl in *. destruct H; [left; assumption|right; eauto].
Qed.

Lemma firstn_NoDup' : forall (B : Type) n (l : list B), NoDup l -> NoDup (firstn n l).
Proof.
  induction n as [|n IH]; intros l Hl; simpl; [constructor|].
  destruct l as [|y l]; [constructor|]. inversion Hl; subst.
  constructor; [|auto]. intro H. apply H1. eapply firstn_In'. exact H.
Qed.

Lemma firstn_length_le' : forall (B : Type) n (l : list B), length (firstn n l) <= n.
Proof.
  induction n as [|n IH]; intros l; simpl; [lia|]. destruct l; simpl; [lia|].
  specialize (IH l). lia.
Qed.

Lemma firstn_all' : forall (B : Type) n (l : list B), length l <= n -> firstn n l = l.
Proof.
  induction n as [|n IH]; intros l H; [destruct l; [reflexivity|simpl in H; lia]|].
  destruct l; simpl in *; [reflexivity|]. rewrite IH by lia. reflexivity.
Qed.

(* ' OR '.join(DQ + term + DQ for term in unique) *)
Definition quote (t : list A) : list A := dquote :: t ++ [dquote].
Definition sep : list A := [space; o_chr; r_chr; space].

Fixpoint join (ts : list (list A)) : list A :=
  match ts with
  | [] => []
  | [t] => quote t
  | t :: ts' => quote t ++ sep ++ join ts'
  end.

Definition terms_of (text : list A) : list (list A) :=
  firstn max_terms (dedup (filter eligible (tokens (lower text)))).

Definition keyword_query (text : list A) : option (list A) :=
  match terms_of text with
  | [] => None
  | ts => Some (join ts)
  end.

(* ------------------------------------------------------------------ *)
(* The FTS5 query grammar   Q (' OR ' Q)*   with Q = DQ word_char+ DQ    *)

Inductive phrase : list A -> Prop :=
| phrase_intro : forall t, WordRun t -> phrase (dquote :: t ++ [dquote]).

Inductive or_query : list A -> Prop :=
| or_one : forall p, phrase p -> or_query p
| or_more : forall p q, phrase p -> or_query q -> or_query (p ++ sep ++ q).

Lemma join_grammar : forall ts, ts <> [] -> Forall WordRun ts -> or_query (join ts).
Proof.
  induction ts as [|t ts IH]; intros Hne Hall; [contradiction|].
  inversion Hall; subst.
  destruct ts as [|t' ts'].
  - simpl. apply or_one. constructor. assumption.
  - change (join (t :: t' :: ts')) with (quote t ++ sep ++ join (t' :: ts')).
    apply or_more; [constructor; assumption|].
    apply IH; [discriminate|assumption].
Qed.

(* ------------------------------------------------------------------ *)
(* Unique decoding: splitting the query string at double quotes gives  *)
(* back exactly the term list, so no input can create extra phrases,   *)
(* operators or column filters.                                        *)

Fixpoint split_dq_acc (cur : list A) (s : list A) : list (list A) :=
  match s with
  | [] => [rev cur]
  | c :: s' =>
      if eq_dec c dquote then rev cur :: split_dq_acc [] s'
      else split_dq_acc (c :: cur) s'
  end.

Fixpoint evens (l : list (list A)) : list (list A) :=
  match l with
  | x :: _ :: l' => x :: evens l'
  | [x] => [x]
  | [] => []
  end.

Definition decode (s : list A) : list (list A) :=
  match split_dq_acc [] s with
  | _ :: r => evens r
  | [] => []
  end.

Lemma split_no_dq : forall u cur v,
  ~ In dquote u ->
  split_dq_acc cur (u ++ dquote :: v) = (rev cur ++ u) :: split_dq_acc [] v.
Proof.
  induction u as [|x u IH]; intros cur v Hu; simpl.
  - destruct (eq_dec dquote dquote) as [_|n]; [|contradiction].
    rewrite app_nil_r. reflexivity.
  - destruct (eq_dec x dquote) as [e|n].
    + exfalso. apply Hu. left. exact e.
    + rewrite IH by (intro H; apply Hu; right; exact H).
      simpl. rewrite <- app_assoc. reflexivity.
Qed.

Lemma wordrun_no_dq : forall t, WordRun t -> ~ In dquote t.
Proof.
  intros t [_ Ht] Hin. rewrite Forall_forall in Ht.
  specialize (Ht _ Hin). rewrite dquote_not_word in Ht. discriminate.
Qed.

Lemma sep_no_dq : ~ In dquote sep.
Proof.
  unfold sep. simpl. intros [H|[H|[H|[H|[]]]]]; contradiction.
Qed.

Fixpoint interleave (ts : list (list A)) : list (list A) :=
  match ts with
  | [] => []
  | [t] => [t; []]
  | t :: ts' => t :: sep :: interleave ts'
  end.

Lemma split_join : forall ts, ts <> [] -> Forall WordRun ts ->
  exists rest, join ts = dquote :: rest /\ split_dq_acc [] rest = interleave ts.
Proof.
  induction ts as [|t ts IH]; intros Hne Hall; [contradiction|].
  inversion Hall; subst.
  destruct ts as [|t' ts'].
  - exists (t ++ [dquote]). split; [reflexivity|].
    rewrite split_no_dq by (apply wordrun_no_dq; assumption).
    reflexivity.
  - destruct (IH ltac:(discriminate) H2) as [rest' [Hj Hs]].
    exists (t ++ dquote :: sep ++ join (t' :: ts')). split.
    + change (join (t :: t' :: ts')) with (quote t ++ sep ++ join (t' :: ts')).
      unfold quote. simpl. rewrite <- app_assoc. reflexivity.
    + rewrite split_no_dq by (apply wordrun_no_dq; assumption).
      rewrite Hj. rewrite split_no_dq by exact sep_no_dq.
      rewrite Hs. reflexivity.
Qed.

Lemma evens_interleave : forall ts, evens (interleave ts) = ts.
Proof.
  induction ts as [|t ts IH]; [reflexivity|].
  destruct ts as [|t' ts']; [reflexivity|].
  change (interleave (t :: t' :: ts')) with (t :: sep :: interleave (t' :: ts')).
  change (evens (t :: sep :: interleave (t' :: ts'))) with (t :: evens (interleave (t' :: ts'))).
  rewrite IH. reflexivity.
Qed.

Theorem decode_join : forall ts, ts <> [] -> Forall WordRun ts -> decode (join ts) = ts.
Proof.
  intros ts Hne Hall. destruct (split_join ts Hne Hall) as [rest [Hj Hs]].
  unfold decode. rewrite Hj. simpl.
  destruct (eq_dec dquote dquote) as [_|n]; [|contradiction].
  rewrite Hs. apply evens_interleave.
Qed.

(* ------------------------------------------------------------------ *)
(* Main theorems                                                       *)

Definition GoodTerm (text t : list A) : Prop :=
  WordRun t /\ ~ In dquote t /\ 1 < length t /\ is_stopword t = false
  /\ In t (tokens (lower text)).

Lemma terms_of_good : forall text, Forall (GoodTerm text) (terms_of text).
Proof.
  intro text. apply Forall_forall. intros t Ht.
  unfold terms_of in Ht. apply firstn_In' in Ht. rewrite dedup_In in Ht.
  rewrite filter_In in Ht. destruct Ht as [Hin Hel].
  unfold eligible in Hel. apply andb_prop in Hel. destruct Hel as [Hs Hl].
  apply negb_true_iff in Hs. apply Nat.ltb_lt in Hl.
  pose proof (tokens_are_word_runs (lower text)) as Hw.
  rewrite Forall_forall in Hw. specialize (Hw t Hin).
  unfold GoodTerm. repeat split; try assumption.
  - apply Hw.
  - apply Hw.
  - apply wordrun_no_dq. exact Hw.
Qed.

Lemma terms_of_NoDup : forall text, NoDup (terms_of text).
Proof. intro. unfold terms_of. apply firstn_NoDup'. apply dedup_acc_NoDup. Qed.

Lemma terms_of_length : forall text, length (terms_of text) <= max_terms.
Proof. intro. apply firstn_length_le'. Qed.

(* (a)+(b)+(c)+(d): every result is a well-formed disjunction of quoted
   word runs, decodes back to exactly its term list, has at most 64
   distinct terms, and every term is an eligible token of the lowered text. *)
Theorem keyword_query_sound : forall text s,
  keyword_query text = Some s ->
  exists ts,
    s = join ts /\ ts = terms_of text /\ ts <> [] /\
    or_query s /\ decode s = ts /\
    length ts <= max_terms /\ NoDup ts /\ Forall (GoodTerm text) ts.
Proof.
  intros text s H. unfold keyword_query in H.
  destruct (terms_of text) as [|t ts] eqn:E; [discriminate|].
  injection H as <-. exists (t :: ts).
  pose proof (terms_of_good text) as Hg. rewrite E in Hg.
  assert (Hw : Forall WordRun (t :: ts)).
  { eapply Forall_impl; [|exact Hg]. intros x Hx. apply Hx. }
  split; [reflexivity|]. split; [reflexivity|]. split; [discriminate|].
  split; [exact (join_grammar (t :: ts) ltac:(discriminate) Hw)|].
  split; [exact (decode_join (t :: ts) ltac:(discriminate) Hw)|].
  split; [rewrite <- E; apply terms_of_length|].
  split; [rewrite <- E; apply terms_of_NoDup|].
  exact Hg.
Qed.

Lemma join_quote_count : forall ts, ts <> [] -> Forall WordRun ts ->
  count_occ eq_dec (join ts) dquote = 2 * length ts.
Proof.
  assert (Hs : count_occ eq_dec sep dquote = 0)
    by (apply count_occ_not_In; exact sep_no_dq).
  induction ts as [|t ts IH]; intros Hne Hw; [contradiction|].
  inversion Hw as [|t0 ts0 Ht Hts]; subst.
  assert (Ht0 : count_occ eq_dec t dquote = 0).
  { apply count_occ_not_In. apply wordrun_no_dq. assumption. }
  assert (Hq : count_occ eq_dec (quote t) dquote = 2).
  { unfold quote. simpl. destruct (eq_dec dquote dquote) as [_|n]; [|contradiction].
    rewrite count_occ_app, Ht0. simpl.
    destruct (eq_dec dquote dquote) as [_|n]; [|contradiction]. reflexivity. }
  destruct ts as [|t' ts'].
  - exact Hq.
  - change (join (t :: t' :: ts')) with (quote t ++ sep ++ join (t' :: ts')).
    rewrite !count_occ_app, Hq, Hs.
    rewrite (IH ltac:(discriminate) Hts). simpl length. lia.
Qed.

(* (b) restated on the output string: the only double quotes in the query
   are the 2 * (number of terms) phrase delimiters. *)
Theorem keyword_query_quote_count : forall text s,
  keyword_query text = Some s ->
  count_occ eq_dec s dquote = 2 * length (decode s).
Proof.
  intros text s H. destruct (keyword_query_sound text s H)
    as [ts [-> [_ [Hne [_ [Hd [_ [_ Hg]]]]]]]].
  rewrite Hd. apply join_quote_count; [exact Hne|].
  eapply Forall_impl; [|exact Hg]. intros x Hx. apply Hx.
Qed.

(* (e) None exactly when no token survives the stopword and length filter. *)
Theorem keyword_query_none_iff : forall text,
  keyword_query text = None <->
  ~ exists t, In t (tokens (lower text)) /\ is_stopword t = false /\ 1 < length t.
Proof.
  intro text. unfold keyword_query, terms_of.
  set (l := dedup (filter eligible (tokens (lower text)))).
  assert (Hl : firstn max_terms l = [] <-> l = []).
  { destruct l; simpl; split; intro; congruence. }
  split.
  - intros H [t [Hin [Hs Hlen]]].
    assert (E : firstn max_terms l = [])
      by (destruct (firstn max_terms l); [reflexivity|discriminate]).
    apply Hl in E. unfold l in E. rewrite dedup_nil in E.
    assert (Hf : In t (filter eligible (tokens (lower text)))).
    { apply filter_In. split; [exact Hin|]. unfold eligible.
      rewrite Hs. apply Nat.ltb_lt in Hlen. rewrite Hlen. reflexivity. }
    rewrite E in Hf. destruct Hf.
  - intro Hno. destruct (firstn max_terms l) as [|y ys] eqn:E; [reflexivity|].
    exfalso. assert (Hne : l <> []) by (intro Hc; subst l; rewrite Hc in E; destruct max_terms; discriminate).
    destruct l as [|t l'] eqn:El; [contradiction|].
    assert (Ht : In t (dedup (filter eligible (tokens (lower text))))).
    { fold l. rewrite El. left. reflexivity. }
    rewrite dedup_In, filter_In in Ht. destruct Ht as [Hin Hel].
    unfold eligible in Hel. apply andb_prop in Hel. destruct Hel as [Hs Hlen].
    apply Hno. exists t. split; [exact Hin|]. split.
    + apply negb_true_iff. exact Hs.
    + apply Nat.ltb_lt. exact Hlen.
Qed.

(* Completeness under the cap: when there are at most 64 distinct eligible
   tokens, every one of them appears in the query. *)
Theorem keyword_query_complete_under_cap : forall text t,
  length (dedup (filter eligible (tokens (lower text)))) <= max_terms ->
  In t (tokens (lower text)) -> is_stopword t = false -> 1 < length t ->
  In t (terms_of text).
Proof.
  intros text t Hcap Hin Hs Hlen. unfold terms_of. rewrite firstn_all' by exact Hcap.
  apply dedup_In, filter_In. split; [exact Hin|]. unfold eligible.
  rewrite Hs. apply Nat.ltb_lt in Hlen. rewrite Hlen. reflexivity.
Qed.

End KeywordQuery.

(* ------------------------------------------------------------------ *)
(* Concrete ASCII instance: word_char = [A-Za-z0-9] (Python's [^\W_]   *)
(* restricted to ASCII), lower = ASCII lowercase, and the exact        *)
(* KEYWORD_STOPWORDS list.  The examples below are outputs of the       *)
(* Python function, checked by computation.                            *)

Definition ascii_word_char (c : ascii) : bool :=
  let n := nat_of_ascii c in
  ((48 <=? n) && (n <=? 57)) || ((65 <=? n) && (n <=? 90)) || ((97 <=? n) && (n <=? 122)).

Definition ascii_lower (c : ascii) : ascii :=
  let n := nat_of_ascii c in
  if (65 <=? n) && (n <=? 90) then ascii_of_nat (n + 32) else c.

Definition stopword_strings : list string :=
  ["a"; "about"; "after"; "again"; "all"; "am"; "an"; "and"; "any"; "are"; "as"; "at";
   "be"; "been"; "before"; "being"; "both"; "but"; "by"; "can"; "could"; "did"; "do";
   "does"; "doing"; "during"; "each"; "few"; "for"; "from"; "had"; "has"; "have";
   "having"; "he"; "her"; "here"; "hers"; "him"; "his"; "how"; "i"; "if"; "in"; "into";
   "is"; "it"; "its"; "itself"; "just"; "me"; "more"; "most"; "my"; "myself"; "no";
   "nor"; "not"; "now"; "of"; "off"; "on"; "once"; "only"; "or"; "other"; "our"; "ours";
   "out"; "over"; "own"; "same"; "she"; "should"; "so"; "some"; "such"; "than"; "that";
   "the"; "their"; "theirs"; "them"; "then"; "there"; "these"; "they"; "this"; "those";
   "through"; "to"; "too"; "under"; "until"; "up"; "very"; "was"; "we"; "were"; "what";
   "when"; "where"; "which"; "while"; "who"; "whom"; "why"; "will"; "with"; "would";
   "you"; "your"; "yours"; "yourself"; "tell"; "remind"; "know"; "recall"; "remember";
   "mentioned"]%string.

Definition ascii_is_stopword (t : list ascii) : bool :=
  existsb (fun w => if list_eq_dec ascii_dec t (list_ascii_of_string w) then true else false)
    stopword_strings.

Definition ascii_keyword_query (text : string) : option string :=
  option_map string_of_list_ascii
    (keyword_query ascii_dec ascii_word_char "034"%char " "%char "O"%char "R"%char
       ascii_is_stopword (map ascii_lower) (list_ascii_of_string text)).

Example py_case_1 :
  ascii_keyword_query "What did Alice say about the Paris trip_plan?" =
  Some """alice"" OR ""say"" OR ""paris"" OR ""trip"" OR ""plan"""%string.
Proof. vm_compute. reflexivity. Qed.

Example py_case_2 :
  ascii_keyword_query "foo"" OR bar NEAR(x) * col:umn" =
  Some """foo"" OR ""bar"" OR ""near"" OR ""col"" OR ""umn"""%string.
Proof. vm_compute. reflexivity. Qed.

Example py_case_3 : ascii_keyword_query "the a I" = None.
Proof. vm_compute. reflexivity. Qed.

Example py_case_4 :
  ascii_keyword_query "Go go GO gone 42 4" = Some """go"" OR ""gone"" OR ""42"""%string.
Proof. vm_compute. reflexivity. Qed.

Example py_case_5 : ascii_keyword_query "" = None.
Proof. vm_compute. reflexivity. Qed.

(* The abstract hypotheses are satisfiable: the main theorem instantiated
   to the concrete ASCII model with every side condition discharged. *)
Corollary ascii_keyword_query_sound : forall text s,
  keyword_query ascii_dec ascii_word_char "034"%char " "%char "O"%char "R"%char
    ascii_is_stopword (map ascii_lower) text = Some s ->
  exists ts,
    s = join "034"%char " "%char "O"%char "R"%char ts /\
    decode ascii_dec "034"%char s = ts /\ ts <> [] /\
    length ts <= 64 /\ NoDup ts /\
    Forall (fun t => t <> [] /\ Forall (fun c => ascii_word_char c = true) t
                     /\ ~ In "034"%char t) ts.
Proof.
  intros text s H.
  destruct (keyword_query_sound ascii_dec ascii_word_char "034"%char " "%char "O"%char "R"%char
              eq_refl ltac:(discriminate) ltac:(discriminate) ltac:(discriminate)
              ascii_is_stopword (map ascii_lower) text s H)
    as [ts [Hj [_ [Hne [_ [Hd [Hl [Hn Hg]]]]]]]].
  exists ts. repeat (split; [assumption|]).
  eapply Forall_impl; [|exact Hg]. intros t [[Hw1 Hw2] [Hq _]]. auto.
Qed.

Print Assumptions keyword_query_sound.
Print Assumptions ascii_keyword_query_sound.
Print Assumptions keyword_query_quote_count.
Print Assumptions keyword_query_none_iff.
Print Assumptions keyword_query_complete_under_cap.
Print Assumptions tokens_concat.
Print Assumptions tokens_split.
Print Assumptions tokens_run.

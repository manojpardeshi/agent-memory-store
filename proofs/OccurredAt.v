(* Formal model of MemoryStore._validate_occurred_at and
   OCCURRED_AT_CLOCK_SKEW in src/llm_memory_store/store.py:

     if occurred_at is None: return None
     value = datetime.fromisoformat(occurred_at.replace('Z', '+00:00'))
     if value.tzinfo is None: raise ValueError(...)
     if value > datetime.now(UTC) + OCCURRED_AT_CLOCK_SKEW: raise ValueError(...)
     return value.astimezone(UTC).isoformat(timespec='microseconds')

   A parsed datetime is its wall-clock reading [local] in microseconds on a
   proleptic epoch scale plus an optional fixed UTC offset in microseconds
   (None = naive).  Its instant is local - offset.  String parsing (the Z
   replacement followed by fromisoformat) is an arbitrary function [parse]
   returning None on ValueError; ISO formatting of the result is not
   modelled, the result is the normalised value itself.  [now] is the
   instant read from datetime.now(UTC).  Python compares two aware datetimes
   by instant (or by wall clock when both share one tzinfo, which then gives
   the same answer), so the future check is a comparison of instants. *)

From Stdlib Require Import ZArith Lia.
Open Scope Z_scope.

(* timedelta(minutes=5) in microseconds *)
Definition skew_us : Z := 5 * 60 * 1000000.

Example skew_is_five_minutes : skew_us = 300000000.
Proof. reflexivity. Qed.

Record dt := mkDt { local : Z; offset : option Z }.

Definition instant (v : dt) : option Z :=
  match offset v with Some off => Some (local v - off) | None => None end.

(* value.astimezone(UTC) for an aware value with offset [off] *)
Definition to_utc (v : dt) (off : Z) : dt := mkDt (local v - off) (Some 0).

Inductive outcome := Accepted (r : option dt) | Rejected.

Section Validate.
Context {Str : Type} (parse : Str -> option dt).

Definition validate (now : Z) (input : option Str) : outcome :=
  match input with
  | None => Accepted None
  | Some s =>
      match parse s with
      | None => Rejected                                (* ValueError from fromisoformat *)
      | Some v =>
          match offset v with
          | None => Rejected                            (* naive: no timezone *)
          | Some off =>
              if now + skew_us <? local v - off then Rejected   (* in the future *)
              else Accepted (Some (to_utc v off))
          end
      end
  end.

(* Main theorem: every accepted value carries a timezone (UTC, offset 0),
   is no later than now + 5 minutes, and denotes the same instant as the
   parsed input. *)
Theorem accepted_sound : forall now s w,
  validate now (Some s) = Accepted (Some w) ->
  exists v off,
    parse s = Some v /\ offset v = Some off /\
    offset w = Some 0 /\
    instant w = instant v /\
    local w <= now + skew_us /\
    (forall t, instant w = Some t -> t <= now + skew_us).
Proof.
  intros now s w H. unfold validate in H.
  destruct (parse s) as [v|] eqn:P; [|discriminate].
  destruct (offset v) as [off|] eqn:O; [|discriminate].
  destruct (now + skew_us <? local v - off) eqn:F; [discriminate|].
  injection H as <-. apply Z.ltb_ge in F.
  exists v, off. unfold instant, to_utc. simpl. rewrite O.
  repeat split; try reflexivity.
  - f_equal. lia.
  - lia.
  - intros t Ht. injection Ht as <-. lia.
Qed.

(* Naive timestamps are rejected. *)
Theorem naive_rejected : forall now s v,
  parse s = Some v -> offset v = None -> validate now (Some s) = Rejected.
Proof. intros now s v P O. simpl. rewrite P, O. reflexivity. Qed.

(* Timestamps more than five minutes ahead of the clock are rejected. *)
Theorem future_rejected : forall now s v off,
  parse s = Some v -> offset v = Some off -> now + skew_us < local v - off ->
  validate now (Some s) = Rejected.
Proof.
  intros now s v off P O F. simpl. rewrite P, O.
  apply Z.ltb_lt in F. rewrite F. reflexivity.
Qed.

(* Completeness: every aware value within the bound is accepted. *)
Theorem within_bound_accepted : forall now s v off,
  parse s = Some v -> offset v = Some off -> local v - off <= now + skew_us ->
  validate now (Some s) = Accepted (Some (to_utc v off)).
Proof.
  intros now s v off P O F. simpl. rewrite P, O.
  apply Z.ltb_ge in F. rewrite F. reflexivity.
Qed.

Theorem none_passes : forall now, validate now None = Accepted None.
Proof. reflexivity. Qed.

(* Normalisation preserves the instant and is idempotent. *)
Theorem to_utc_preserves_instant : forall v off,
  offset v = Some off -> instant (to_utc v off) = instant v.
Proof. intros v off O. unfold instant, to_utc. simpl. rewrite O. f_equal. lia. Qed.

Theorem to_utc_idempotent : forall v off, to_utc (to_utc v off) 0 = to_utc v off.
Proof. intros v off. unfold to_utc. simpl. f_equal. lia. Qed.

(* A stored value stays valid: if the stored string parses back to the
   normalised value, validating it again at any later clock reading accepts
   it unchanged. *)
Theorem revalidation_stable : forall now now' s w s',
  validate now (Some s) = Accepted (Some w) -> now <= now' -> parse s' = Some w ->
  validate now' (Some s') = Accepted (Some w).
Proof.
  intros now now' s w s' H Le P.
  destruct (accepted_sound now s w H) as [v [off [_ [_ [Ow [_ [Lw _]]]]]]].
  simpl. rewrite P, Ow.
  assert (F : (now' + skew_us <? local w - 0) = false) by (apply Z.ltb_ge; lia).
  rewrite F. f_equal. f_equal. destruct w as [lw ow]. unfold to_utc. simpl in *.
  rewrite Ow. f_equal. lia.
Qed.

End Validate.

Print Assumptions accepted_sound.
Print Assumptions naive_rejected.
Print Assumptions future_rejected.
Print Assumptions within_bound_accepted.
Print Assumptions to_utc_preserves_instant.
Print Assumptions to_utc_idempotent.
Print Assumptions revalidation_stable.

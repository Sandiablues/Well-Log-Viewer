"""Backend-owned canonical Curve Fill persistence and commands."""
from __future__ import annotations

from hashlib import sha256
import json

from app.curve_fill_v2.commands import (
    CreateCurveFillRuleCommand,
    RemoveCurveFillRuleCommand,
    ReorderCurveFillRulesCommand,
    UpdateCurveFillRuleCommand,
)
from app.curve_fill_v2.models import (
    CanonicalCurveFillRule,
    CurveFillRuleState,
    RuleType,
)
from app.curve_fill_v2.policy import CurveFillPolicyRegistry
from app.identity import new_uuid7_str
from app.identity.wdv_contract_v2 import WdvCanonicalSession
from app.wdv_session.canonical_service import CanonicalWdvSessionService


class CanonicalCurveFillCommandError(ValueError):
    pass


class CanonicalCurveFillService:
    def __init__(self, session_service: CanonicalWdvSessionService | None = None) -> None:
        self.session_service = session_service or CanonicalWdvSessionService()

    @staticmethod
    def _fingerprint(command_name: str, payload: dict) -> str:
        return sha256(
            json.dumps(
                {"command": command_name, "payload": payload},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    def _execute(self, managed_well_uid: str, command, mutation) -> WdvCanonicalSession:
        payload = command.model_dump(mode="json", exclude={"expected_revision", "command_id"})
        command_id = None if command.command_id is None else str(command.command_id)
        return self.session_service.mutate_session_transactionally(
            managed_well_uid,
            expected_revision=command.expected_revision,
            mutation=mutation,
            command_id=command_id,
            command_fingerprint=(
                None
                if command_id is None
                else self._fingerprint(command.__class__.__name__, payload)
            ),
        )

    @staticmethod
    def _track_and_assignments(session: WdvCanonicalSession, track_uid: str):
        track = next((item for item in session.tracks if item.track_uid == track_uid), None)
        if track is None:
            raise CanonicalCurveFillCommandError(f"Unknown track_uid: {track_uid}")
        if track.track_type != "curve":
            raise CanonicalCurveFillCommandError("Curve Fill rules require a curve track")
        return track, {item.assignment_uid: item for item in track.assignments}

    @staticmethod
    def _normalize(rules: list[CanonicalCurveFillRule], track_uid: str):
        index = 0
        normalized = []
        for rule in rules:
            if rule.track_uid == track_uid:
                rule = rule.model_copy(update={"order": index})
                index += 1
            normalized.append(rule)
        return tuple(normalized)

    def create_rule(self, managed_well_uid: str, command: CreateCurveFillRuleCommand) -> WdvCanonicalSession:
        def mutate(session: WdvCanonicalSession) -> WdvCanonicalSession:
            track, assignments = self._track_and_assignments(session, command.track_uid)
            assignment_a = assignments.get(command.curve_a_assignment_uid)
            if assignment_a is None:
                raise CanonicalCurveFillCommandError("Curve A assignment is not in the target track")
            assignment_b = None
            if command.curve_b_assignment_uid is not None:
                assignment_b = assignments.get(command.curve_b_assignment_uid)
                if assignment_b is None:
                    raise CanonicalCurveFillCommandError("Curve B assignment is not in the target track")
            if command.rule_type == RuleType.CONDITIONAL and assignment_b is not None:
                unit_a = (assignment_a.unit or "").strip().lower()
                unit_b = (assignment_b.unit or "").strip().lower()
                if unit_a and unit_b and unit_a != unit_b:
                    raise CanonicalCurveFillCommandError(
                        "Conditional fill requires compatible engineering units"
                    )
            if command.rule_type == RuleType.CROSSOVER:
                policy = CurveFillPolicyRegistry.require(
                    command.overlay_policy_uid or "",
                    command.overlay_policy_revision or "",
                )
                family_a = (assignment_a.curve_family or "").strip().lower()
                family_b = (assignment_b.curve_family or "").strip().lower() if assignment_b else ""
                if family_a not in policy.primary_families or family_b not in policy.comparison_families:
                    raise CanonicalCurveFillCommandError(
                        "Curve assignments are incompatible with the governed crossover policy"
                    )
            track_rules = [rule for rule in session.curve_fills if rule.track_uid == track.track_uid]
            target = len(track_rules) if command.target_order is None else command.target_order
            if target > len(track_rules):
                raise CanonicalCurveFillCommandError("target_order exceeds the track rule count")
            created = CanonicalCurveFillRule(
                rule_uid=new_uuid7_str(),
                managed_well_uid=managed_well_uid,
                track_uid=track.track_uid,
                curve_a_assignment_uid=command.curve_a_assignment_uid,
                curve_b_assignment_uid=command.curve_b_assignment_uid,
                order=target,
                enabled=command.enabled,
                rule_type=command.rule_type,
                comparison=command.comparison,
                boundary=command.boundary,
                overlay_policy_uid=command.overlay_policy_uid,
                overlay_policy_revision=command.overlay_policy_revision,
                deadband=command.deadband,
                minimum_interval=command.minimum_interval,
                style=command.style,
                state=(
                    CurveFillRuleState.PENDING_GEOMETRY
                    if command.enabled
                    else CurveFillRuleState.DISABLED
                ),
                state_reason=None if command.enabled else "disabled_by_user",
            )
            rules = list(session.curve_fills)
            insertion = next(
                (i for i, rule in enumerate(rules) if rule.track_uid == track.track_uid and rule.order >= target),
                len(rules),
            )
            rules.insert(insertion, created)
            return session.model_copy(update={"curve_fills": self._normalize(rules, track.track_uid)})
        return self._execute(managed_well_uid, command, mutate)

    def update_rule(self, managed_well_uid: str, command: UpdateCurveFillRuleCommand) -> WdvCanonicalSession:
        def mutate(session: WdvCanonicalSession) -> WdvCanonicalSession:
            found = False
            rules = []
            for rule in session.curve_fills:
                if rule.rule_uid != command.rule_uid:
                    rules.append(rule)
                    continue
                found = True
                patch = command.model_dump(
                    mode="json",
                    exclude={"expected_revision", "command_id", "rule_uid"},
                    exclude_none=True,
                )
                enabled = patch.get("enabled", rule.enabled)
                patch.update(
                    {
                        "state": CurveFillRuleState.PENDING_GEOMETRY if enabled else CurveFillRuleState.DISABLED,
                        "state_reason": None if enabled else "disabled_by_user",
                        "geometry_revision": None,
                    }
                )
                rule = rule.model_copy(update=patch)
                # Revalidate the full model after patching.
                rule = CanonicalCurveFillRule.model_validate(rule.model_dump(mode="json"))
                rules.append(rule)
            if not found:
                raise CanonicalCurveFillCommandError(f"Unknown rule_uid: {command.rule_uid}")
            return session.model_copy(update={"curve_fills": tuple(rules)})
        return self._execute(managed_well_uid, command, mutate)

    def remove_rule(self, managed_well_uid: str, command: RemoveCurveFillRuleCommand) -> WdvCanonicalSession:
        def mutate(session: WdvCanonicalSession) -> WdvCanonicalSession:
            target = next((rule for rule in session.curve_fills if rule.rule_uid == command.rule_uid), None)
            if target is None:
                raise CanonicalCurveFillCommandError(f"Unknown rule_uid: {command.rule_uid}")
            kept = [rule for rule in session.curve_fills if rule.rule_uid != command.rule_uid]
            return session.model_copy(update={"curve_fills": self._normalize(kept, target.track_uid)})
        return self._execute(managed_well_uid, command, mutate)

    def reorder_rules(self, managed_well_uid: str, command: ReorderCurveFillRulesCommand) -> WdvCanonicalSession:
        def mutate(session: WdvCanonicalSession) -> WdvCanonicalSession:
            self._track_and_assignments(session, command.track_uid)
            existing = {rule.rule_uid: rule for rule in session.curve_fills if rule.track_uid == command.track_uid}
            if set(command.rule_uids) != set(existing):
                raise CanonicalCurveFillCommandError(
                    "rule_uids must exactly match the target track rules"
                )
            ordered = [existing[uid].model_copy(update={"order": i}) for i, uid in enumerate(command.rule_uids)]
            iterator = iter(ordered)
            rules = tuple(next(iterator) if rule.track_uid == command.track_uid else rule for rule in session.curve_fills)
            return session.model_copy(update={"curve_fills": rules})
        return self._execute(managed_well_uid, command, mutate)

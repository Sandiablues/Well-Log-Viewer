"""Canonical Curve Fill mutation workflows with incremental geometry deltas."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.curve_fill_v2.canonical_service import CanonicalCurveFillService
from app.curve_fill_v2.commands import (
    CreateCurveFillRuleCommand,
    RemoveCurveFillRuleCommand,
    ReorderCurveFillRulesCommand,
    UpdateCurveFillRuleCommand,
)
from app.curve_fill_v2.geometry_service import (
    CanonicalCurveFillGeometryService,
    CurveFillGeometryCommandError,
    CurveFillGeometryDelta,
    ResolveCurveFillGeometryCommand,
)
from app.identity.wdv_contract_v2 import WdvCanonicalSession


class HydrateCurveFillRulesCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    expected_revision: int = Field(ge=0)
    max_samples: int = Field(default=100000, ge=2, le=100000)


class CurveFillCommandResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    contract_version: str = "wdv_curve_fill_command_result_v2"
    session: WdvCanonicalSession
    geometry_delta: CurveFillGeometryDelta


class CanonicalCurveFillWorkflowService:
    def __init__(
        self,
        *,
        command_service: CanonicalCurveFillService | None = None,
        geometry_service: CanonicalCurveFillGeometryService | None = None,
    ) -> None:
        self.command_service = command_service or CanonicalCurveFillService()
        self.geometry_service = geometry_service or CanonicalCurveFillGeometryService(
            session_service=self.command_service.session_service
        )

    @staticmethod
    def _empty_delta(session: WdvCanonicalSession) -> CurveFillGeometryDelta:
        return CurveFillGeometryDelta(
            managed_well_uid=session.managed_well_uid,
            session_revision=session.revision,
        )

    def _promote_receipt(self, managed_well_uid: str, command, final_session: WdvCanonicalSession) -> None:
        if command.command_id is None:
            return
        payload = command.model_dump(mode="json", exclude={"expected_revision", "command_id"})
        fingerprint = self.command_service._fingerprint(command.__class__.__name__, payload)
        self.command_service.session_service.promote_command_receipt_session(
            managed_well_uid,
            command_id=str(command.command_id),
            command_fingerprint=fingerprint,
            session=final_session,
        )

    def _resolve_or_return_state(self, session: WdvCanonicalSession, rule_uid: str) -> CurveFillCommandResult:
        rule = next(rule for rule in session.curve_fills if rule.rule_uid == rule_uid)
        if not rule.enabled:
            return CurveFillCommandResult(
                session=session,
                geometry_delta=CurveFillGeometryDelta(
                    managed_well_uid=session.managed_well_uid,
                    session_revision=session.revision,
                    remove=(rule_uid,),
                ),
            )
        try:
            delta = self.geometry_service.resolve_rule(
                session.managed_well_uid,
                ResolveCurveFillGeometryCommand(
                    expected_revision=session.revision,
                    rule_uid=rule_uid,
                ),
            )
            final_session = self.command_service.session_service.get_session(session.managed_well_uid)
            return CurveFillCommandResult(session=final_session, geometry_delta=delta)
        except CurveFillGeometryCommandError:
            # Geometry service atomically records INVALID. Mutation remains durable.
            final_session = self.command_service.session_service.get_session(session.managed_well_uid)
            return CurveFillCommandResult(
                session=final_session,
                geometry_delta=CurveFillGeometryDelta(
                    managed_well_uid=session.managed_well_uid,
                    session_revision=final_session.revision,
                    remove=(rule_uid,),
                ),
            )

    def create_rule(self, managed_well_uid: str, command: CreateCurveFillRuleCommand) -> CurveFillCommandResult:
        before = self.command_service.session_service.get_session(managed_well_uid)
        existing = {rule.rule_uid for rule in before.curve_fills}
        session = self.command_service.create_rule(managed_well_uid, command)
        created = next((rule for rule in session.curve_fills if rule.rule_uid not in existing), None)
        if created is None:
            # Canonical command replay returns the promoted final session.
            return CurveFillCommandResult(session=session, geometry_delta=self._empty_delta(session))
        result = self._resolve_or_return_state(session, created.rule_uid)
        self._promote_receipt(managed_well_uid, command, result.session)
        return result

    def update_rule(self, managed_well_uid: str, command: UpdateCurveFillRuleCommand) -> CurveFillCommandResult:
        session = self.command_service.update_rule(managed_well_uid, command)
        result = self._resolve_or_return_state(session, command.rule_uid)
        self._promote_receipt(managed_well_uid, command, result.session)
        return result

    def remove_rule(self, managed_well_uid: str, command: RemoveCurveFillRuleCommand) -> CurveFillCommandResult:
        session = self.command_service.remove_rule(managed_well_uid, command)
        result = CurveFillCommandResult(
            session=session,
            geometry_delta=CurveFillGeometryDelta(
                managed_well_uid=managed_well_uid,
                session_revision=session.revision,
                remove=(str(command.rule_uid),),
            ),
        )
        self._promote_receipt(managed_well_uid, command, result.session)
        return result

    def reorder_rules(self, managed_well_uid: str, command: ReorderCurveFillRulesCommand) -> CurveFillCommandResult:
        session = self.command_service.reorder_rules(managed_well_uid, command)
        result = CurveFillCommandResult(session=session, geometry_delta=self._empty_delta(session))
        self._promote_receipt(managed_well_uid, command, result.session)
        return result

    def hydrate_rules(
        self, managed_well_uid: str, command: HydrateCurveFillRulesCommand
    ) -> CurveFillCommandResult:
        session = self.command_service.session_service.get_session(managed_well_uid)
        if session.revision != command.expected_revision:
            from app.wdv_session.canonical_service import CanonicalSessionRevisionConflict
            raise CanonicalSessionRevisionConflict(
                f"Expected revision {command.expected_revision}, found {session.revision}"
            )
        upsert, remove = [], []
        current = session
        for rule in sorted(current.curve_fills, key=lambda item: item.order):
            if not rule.enabled:
                remove.append(rule.rule_uid)
                continue
            try:
                delta = self.geometry_service.resolve_rule(
                    managed_well_uid, ResolveCurveFillGeometryCommand(
                        expected_revision=current.revision,
                        rule_uid=rule.rule_uid,
                        max_samples=command.max_samples,
                    )
                )
                upsert.extend(delta.upsert)
                remove.extend(delta.remove)
            except CurveFillGeometryCommandError:
                remove.append(rule.rule_uid)
            current = self.command_service.session_service.get_session(managed_well_uid)
        return CurveFillCommandResult(
            session=current,
            geometry_delta=CurveFillGeometryDelta(
                managed_well_uid=managed_well_uid,
                session_revision=current.revision,
                upsert=tuple(upsert),
                remove=tuple(dict.fromkeys(remove)),
            ),
        )

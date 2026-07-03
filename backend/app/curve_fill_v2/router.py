"""Canonical backend-owned Curve Fill APIs."""
import os
from fastapi import APIRouter, Depends, HTTPException, Query

from app.curve_fill_v2.canonical_service import (
    CanonicalCurveFillCommandError,
    CanonicalCurveFillService,
)
from app.curve_fill_v2.capabilities import (
    CanonicalCurveFillCapabilityService,
    CurveFillCapabilities,
    CurveFillCapabilityError,
)
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
from app.curve_fill_v2.workflow_service import (
    CanonicalCurveFillWorkflowService,
    CurveFillCommandResult,
    HydrateCurveFillRulesCommand,
)
from app.identity.wdv_contract_v2 import WdvCanonicalSession
from pydantic import BaseModel, ConfigDict
from app.wdv_session.canonical_service import (
    CanonicalSessionCommandReplayConflict,
    CanonicalSessionRevisionConflict,
)

router = APIRouter(prefix="/api/wlv/v2/wdv/curve-fill-commands", tags=["wlv-curve-fill-v2"])


def get_service() -> CanonicalCurveFillService:
    return CanonicalCurveFillService()


def get_geometry_service() -> CanonicalCurveFillGeometryService:
    return CanonicalCurveFillGeometryService()


def get_workflow_service() -> CanonicalCurveFillWorkflowService:
    return CanonicalCurveFillWorkflowService()


def get_capability_service() -> CanonicalCurveFillCapabilityService:
    return CanonicalCurveFillCapabilityService()


class CurveFillFeatureStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    contract_version: str = "wdv_curve_fill_feature_status_v2"
    enabled: bool


def curve_fill_feature_enabled() -> bool:
    return os.getenv("WLV_CURVE_FILL_V2_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}


@router.get("/feature-status", response_model=CurveFillFeatureStatus)
def feature_status():
    return CurveFillFeatureStatus(enabled=curve_fill_feature_enabled())


def _translate(call):
    try:
        return call()
    except (CanonicalSessionRevisionConflict, CanonicalSessionCommandReplayConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (
        CanonicalCurveFillCommandError,
        CurveFillGeometryCommandError,
        CurveFillCapabilityError,
        ValueError,
    ) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# Stable canonical mutation endpoints retained for existing backend consumers.
@router.post("/{managed_well_uid}/rules", response_model=WdvCanonicalSession)
def create_rule(managed_well_uid: str, command: CreateCurveFillRuleCommand, service: CanonicalCurveFillService = Depends(get_service)):
    return _translate(lambda: service.create_rule(managed_well_uid, command))


@router.post("/{managed_well_uid}/rules/update", response_model=WdvCanonicalSession)
def update_rule(managed_well_uid: str, command: UpdateCurveFillRuleCommand, service: CanonicalCurveFillService = Depends(get_service)):
    return _translate(lambda: service.update_rule(managed_well_uid, command))


@router.post("/{managed_well_uid}/rules/remove", response_model=WdvCanonicalSession)
def remove_rule(managed_well_uid: str, command: RemoveCurveFillRuleCommand, service: CanonicalCurveFillService = Depends(get_service)):
    return _translate(lambda: service.remove_rule(managed_well_uid, command))


@router.post("/{managed_well_uid}/rules/reorder", response_model=WdvCanonicalSession)
def reorder_rules(managed_well_uid: str, command: ReorderCurveFillRulesCommand, service: CanonicalCurveFillService = Depends(get_service)):
    return _translate(lambda: service.reorder_rules(managed_well_uid, command))


@router.post("/{managed_well_uid}/geometry/resolve", response_model=CurveFillGeometryDelta)
def resolve_geometry(managed_well_uid: str, command: ResolveCurveFillGeometryCommand, service: CanonicalCurveFillGeometryService = Depends(get_geometry_service)):
    return _translate(lambda: service.resolve_rule(managed_well_uid, command))


# Preferred mutation workflow: canonical state plus only the affected geometry delta.
@router.post("/{managed_well_uid}/workflow/rules", response_model=CurveFillCommandResult)
def workflow_create_rule(managed_well_uid: str, command: CreateCurveFillRuleCommand, service: CanonicalCurveFillWorkflowService = Depends(get_workflow_service)):
    return _translate(lambda: service.create_rule(managed_well_uid, command))


@router.post("/{managed_well_uid}/workflow/rules/update", response_model=CurveFillCommandResult)
def workflow_update_rule(managed_well_uid: str, command: UpdateCurveFillRuleCommand, service: CanonicalCurveFillWorkflowService = Depends(get_workflow_service)):
    return _translate(lambda: service.update_rule(managed_well_uid, command))


@router.post("/{managed_well_uid}/workflow/rules/remove", response_model=CurveFillCommandResult)
def workflow_remove_rule(managed_well_uid: str, command: RemoveCurveFillRuleCommand, service: CanonicalCurveFillWorkflowService = Depends(get_workflow_service)):
    return _translate(lambda: service.remove_rule(managed_well_uid, command))


@router.post("/{managed_well_uid}/workflow/rules/reorder", response_model=CurveFillCommandResult)
def workflow_reorder_rules(managed_well_uid: str, command: ReorderCurveFillRulesCommand, service: CanonicalCurveFillWorkflowService = Depends(get_workflow_service)):
    return _translate(lambda: service.reorder_rules(managed_well_uid, command))


@router.get("/{managed_well_uid}/capabilities", response_model=CurveFillCapabilities)
def capabilities(
    managed_well_uid: str,
    track_uid: str = Query(min_length=1),
    curve_a_assignment_uid: str = Query(min_length=1),
    service: CanonicalCurveFillCapabilityService = Depends(get_capability_service),
):
    return _translate(
        lambda: service.get_capabilities(
            managed_well_uid,
            track_uid=track_uid,
            curve_a_assignment_uid=curve_a_assignment_uid,
        )
    )

@router.post("/{managed_well_uid}/workflow/hydrate", response_model=CurveFillCommandResult)
def workflow_hydrate_rules(
    managed_well_uid: str,
    command: HydrateCurveFillRulesCommand,
    service: CanonicalCurveFillWorkflowService = Depends(get_workflow_service),
):
    return _translate(lambda: service.hydrate_rules(managed_well_uid, command))

"""Canonical governed-template application command API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.identity.wdv_contract_v2 import WdvCanonicalSession
from app.inventory.canonical_identity_resolver import (
    CanonicalIdentityResolutionError,
)
from app.inventory.repository import ManagedWellNotFoundError
from app.knowledge.api_managed_knowledge import get_managed_repository
from app.knowledge.managed_repository import ManagedKRRepository
from app.wdv_session.canonical_service import (
    CanonicalSessionCommandReplayConflict,
    CanonicalSessionRevisionConflict,
)
from app.wdv_workspace.models import WdvWorkspaceInvariantError
from app.wdv_templates.application_plan_service import (
    WdvTemplateApplicationPlanNotFoundError,
    WdvTemplateApplicationPlanService,
)
from app.wdv_templates.canonical_apply_service import (
    ApplyGovernedTemplateCommand,
    CanonicalTemplateApplyBlockedError,
    CanonicalTemplateApplyError,
    CanonicalWdvTemplateApplyService,
)

router = APIRouter(
    prefix="/api/wlv/v2/wdv/template-commands",
    tags=["wlv-wdv-canonical-template-commands"],
)


def get_service(
    repo: ManagedKRRepository = Depends(get_managed_repository),
) -> CanonicalWdvTemplateApplyService:
    return CanonicalWdvTemplateApplyService(
        plan_service=WdvTemplateApplicationPlanService(repository=repo),
    )


@router.post(
    "/{managed_well_uid}/apply",
    response_model=WdvCanonicalSession,
)
def apply_governed_template(
    managed_well_uid: str,
    command: ApplyGovernedTemplateCommand,
    service: CanonicalWdvTemplateApplyService = Depends(get_service),
) -> WdvCanonicalSession:
    try:
        return service.apply(managed_well_uid, command)
    except ManagedWellNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WdvTemplateApplicationPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CanonicalSessionRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CanonicalSessionCommandReplayConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CanonicalTemplateApplyBlockedError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "canonical_template_application_blocked",
                "template_key": exc.template_key,
                "blocking_issues": exc.blocking_issues,
            },
        ) from exc
    except (
        CanonicalTemplateApplyError,
        CanonicalIdentityResolutionError,
        WdvWorkspaceInvariantError,
        ValueError,
    ) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

"""Transactional mutation boundary for the canonical WDV workspace.

Every authoritative WDV mutation passes through this service.  It combines
revision guarding, optional idempotency, atomic persistence and full workspace
validation before the updated session is written.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

from app.identity import parse_uuid7
from app.identity.wdv_contract_v2 import WdvCanonicalSession
from app.wdv_session.canonical_service import (
    CanonicalSessionCommandReplayConflict,
    CanonicalWdvSessionService,
)

from .models import WdvCanonicalWorkspace
from .service import CanonicalWdvWorkspaceService


CanonicalWorkspaceCommandReplayConflict = CanonicalSessionCommandReplayConflict


class CanonicalWdvWorkspaceTransactionService:
    """Execute one validated, atomic mutation for one managed well."""

    def __init__(
        self,
        *,
        session_service: CanonicalWdvSessionService | None = None,
        workspace_service: CanonicalWdvWorkspaceService | None = None,
    ) -> None:
        self.session_service = session_service or CanonicalWdvSessionService()
        self.workspace_service = workspace_service

    def execute(
        self,
        managed_well_uid: str,
        *,
        expected_revision: int,
        command_name: str,
        command_payload: dict[str, Any],
        command_id: str | None,
        mutation: Callable[[WdvCanonicalSession], WdvCanonicalSession],
    ) -> WdvCanonicalSession:
        well_uid = str(parse_uuid7(managed_well_uid))
        normalized_command_id = (
            str(parse_uuid7(command_id)) if command_id is not None else None
        )
        fingerprint = (
            self.command_fingerprint(
                managed_well_uid=well_uid,
                command_name=command_name,
                command_payload=command_payload,
            )
            if normalized_command_id is not None
            else None
        )

        validator = None
        if self.workspace_service is not None:
            def validate(candidate: WdvCanonicalSession) -> WdvCanonicalWorkspace:
                return self.workspace_service.validate_session(well_uid, candidate)
            validator = validate

        return self.session_service.mutate_session_transactionally(
            well_uid,
            expected_revision=expected_revision,
            mutation=mutation,
            validator=validator,
            command_id=normalized_command_id,
            command_fingerprint=fingerprint,
        )

    @staticmethod
    def command_fingerprint(
        *,
        managed_well_uid: str,
        command_name: str,
        command_payload: dict[str, Any],
    ) -> str:
        canonical = json.dumps(
            {
                "managed_well_uid": managed_well_uid,
                "command_name": command_name,
                "command_payload": command_payload,
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

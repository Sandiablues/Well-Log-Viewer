"""Shared canvas profile domain service.

Depends on SharedCanvasProfileRepository only.
Does not access JSON files, paths, or any storage directly.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.identity import new_uuid7_str

from .models import (
    ProfileStatus,
    SharedCanvasActivation,
    SharedCanvasAuditRecord,
    SharedCanvasProfile,
    SharedCanvasProfileRevision,
    SharedCanvasTrack,
)
from .repository import (
    LocalJsonSharedCanvasRepository,
    SharedCanvasProfileNotFound,
    SharedCanvasProfileRepository,
    SharedCanvasRevisionConflict,
)


class SharedCanvasArchivedError(ValueError):
    """Raised when attempting to mutate or activate an archived profile."""


__all__ = [
    "SharedCanvasArchivedError",
    "SharedCanvasProfileService",
    "SharedCanvasRevisionConflict",
    "SharedCanvasProfileNotFound",
]


class SharedCanvasProfileService:
    """Domain service for shared canvas profile lifecycle.

    Operations:
      create_profile       — new profile + initial immutable revision
      append_revision      — new immutable revision (optimistic concurrency guard)
      get_profile          — retrieve profile header
      get_revision         — retrieve a specific immutable revision
      list_profiles        — list headers (active only, or including archived)
      list_revisions       — list all revisions for a profile
      archive_profile      — soft-delete; blocks further mutations and activation
      activate_revision    — set one revision as active for a scope
      get_active_revision  — retrieve the currently active revision for a scope
      list_activations     — retrieve all activation records
    """

    def __init__(
        self,
        repository: SharedCanvasProfileRepository | None = None,
    ) -> None:
        self._repo = repository or LocalJsonSharedCanvasRepository()

    # ----------------------------------------------------------------- create

    def create_profile(
        self,
        *,
        profile_name: str,
        tracks: tuple[SharedCanvasTrack, ...] = (),
        created_by: str = "system",
        source_template_key: str | None = None,
        change_reason: str | None = None,
    ) -> tuple[SharedCanvasProfile, SharedCanvasProfileRevision]:
        """Create a new profile and its first immutable revision atomically.

        Returns the profile header and the initial revision.
        """
        now = self._now()
        profile_uid = new_uuid7_str()
        revision_uid = new_uuid7_str()

        profile = SharedCanvasProfile(
            profile_uid=profile_uid,
            profile_name=profile_name,
            status=ProfileStatus.ACTIVE,
            created_at=now,
            created_by=created_by,
        )
        revision = SharedCanvasProfileRevision(
            profile_revision_uid=revision_uid,
            profile_uid=profile_uid,
            revision_number=0,
            tracks=tracks,
            source_template_key=source_template_key,
            previous_revision_uid=None,
            created_at=now,
            created_by=created_by,
            change_reason=change_reason,
        )
        audit = SharedCanvasAuditRecord(
            audit_uid=new_uuid7_str(),
            actor=created_by,
            timestamp=now,
            operation="create_profile",
            profile_uid=profile_uid,
            previous_revision_uid=None,
            resulting_revision_uid=revision_uid,
            reason=change_reason,
        )
        self._repo.create_profile(profile, revision, audit)
        return profile, revision

    # ---------------------------------------------------------------- revise

    def append_revision(
        self,
        *,
        profile_uid: str,
        expected_revision_number: int,
        tracks: tuple[SharedCanvasTrack, ...],
        created_by: str = "system",
        change_reason: str | None = None,
    ) -> SharedCanvasProfileRevision:
        """Append an immutable revision to an active profile.

        expected_revision_number must equal the current latest revision_number.
        Raises SharedCanvasRevisionConflict on mismatch.
        Raises SharedCanvasArchivedError if the profile is archived.
        """
        self._require_active_profile(profile_uid)
        revisions = self._repo.list_revisions(profile_uid)
        if not revisions:
            raise SharedCanvasProfileNotFound(
                f"No revisions found for profile {profile_uid}"
            )
        previous = revisions[-1]

        now = self._now()
        new_revision_uid = new_uuid7_str()

        revision = SharedCanvasProfileRevision(
            profile_revision_uid=new_revision_uid,
            profile_uid=profile_uid,
            revision_number=previous.revision_number + 1,
            tracks=tracks,
            source_template_key=previous.source_template_key,
            previous_revision_uid=previous.profile_revision_uid,
            created_at=now,
            created_by=created_by,
            change_reason=change_reason,
        )
        audit = SharedCanvasAuditRecord(
            audit_uid=new_uuid7_str(),
            actor=created_by,
            timestamp=now,
            operation="append_revision",
            profile_uid=profile_uid,
            previous_revision_uid=previous.profile_revision_uid,
            resulting_revision_uid=new_revision_uid,
            reason=change_reason,
        )
        # Concurrency check and write occur atomically inside the repository.
        self._repo.append_revision(revision, expected_revision_number, audit)
        return revision

    # ------------------------------------------------------------------ read

    def get_profile(self, profile_uid: str) -> SharedCanvasProfile:
        profile = self._repo.get_profile(profile_uid)
        if profile is None:
            raise SharedCanvasProfileNotFound(
                f"Shared canvas profile not found: {profile_uid}"
            )
        return profile

    def get_revision(
        self, profile_revision_uid: str
    ) -> SharedCanvasProfileRevision:
        revision = self._repo.get_revision(profile_revision_uid)
        if revision is None:
            raise SharedCanvasProfileNotFound(
                f"Shared canvas revision not found: {profile_revision_uid}"
            )
        return revision

    def list_profiles(
        self, include_archived: bool = False
    ) -> list[SharedCanvasProfile]:
        return self._repo.list_profiles(include_archived=include_archived)

    def list_revisions(
        self, profile_uid: str
    ) -> list[SharedCanvasProfileRevision]:
        return self._repo.list_revisions(profile_uid)

    # --------------------------------------------------------------- archive

    def archive_profile(
        self,
        profile_uid: str,
        *,
        archived_by: str = "system",
        reason: str | None = None,
    ) -> SharedCanvasProfile:
        """Soft-delete a profile.  Archived profiles cannot be mutated or activated."""
        profile = self.get_profile(profile_uid)
        if profile.status == ProfileStatus.ARCHIVED:
            return profile
        now = self._now()
        archived = profile.model_copy(
            update={
                "status": ProfileStatus.ARCHIVED,
                "archived_at": now,
                "archived_by": archived_by,
            }
        )
        audit = SharedCanvasAuditRecord(
            audit_uid=new_uuid7_str(),
            actor=archived_by,
            timestamp=now,
            operation="archive_profile",
            profile_uid=profile_uid,
            previous_revision_uid=None,
            resulting_revision_uid=None,
            reason=reason,
        )
        self._repo.update_profile_header(archived, audit)
        return archived

    # ----------------------------------------------------------- activation

    def activate_revision(
        self,
        profile_revision_uid: str,
        *,
        scope_type: str,
        scope_uid: str,
        activated_by: str = "system",
    ) -> SharedCanvasActivation:
        """Set one immutable revision as active for a scope.

        Replaces any previously active revision for the same (scope_type, scope_uid).
        Raises SharedCanvasArchivedError if the profile is archived.
        """
        revision = self.get_revision(profile_revision_uid)
        profile = self.get_profile(revision.profile_uid)
        if profile.status == ProfileStatus.ARCHIVED:
            raise SharedCanvasArchivedError(
                f"Cannot activate a revision of archived profile {revision.profile_uid}"
            )
        now = self._now()
        activation = SharedCanvasActivation(
            activation_uid=new_uuid7_str(),
            activation_scope_type=scope_type,
            activation_scope_uid=scope_uid,
            profile_uid=revision.profile_uid,
            profile_revision_uid=profile_revision_uid,
            activated_at=now,
            activated_by=activated_by,
        )
        self._repo.set_activation(activation)
        return activation

    def get_active_revision(
        self, *, scope_type: str, scope_uid: str
    ) -> SharedCanvasProfileRevision | None:
        """Return the currently active profile revision for a scope, or None."""
        activation = self._repo.get_activation(scope_type, scope_uid)
        if activation is None:
            return None
        return self._repo.get_revision(activation.profile_revision_uid)

    def list_activations(self) -> list[SharedCanvasActivation]:
        return self._repo.list_activations()

    # ---------------------------------------------------------------- helpers

    def _require_active_profile(self, profile_uid: str) -> SharedCanvasProfile:
        profile = self.get_profile(profile_uid)
        if profile.status == ProfileStatus.ARCHIVED:
            raise SharedCanvasArchivedError(
                f"Profile {profile_uid} is archived and cannot be modified"
            )
        return profile

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

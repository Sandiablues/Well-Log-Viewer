from __future__ import annotations

from .repository import MSIRepository
from .schemas import DatasetLifecycleSummary, ManagedRepresentation


class MSILifecycleService:
    """
    Backend-owned lifecycle summary service.

    Frontend panels should consume this instead of inferring readiness from
    folders, filenames, dropdown state, or button visibility.
    """

    def __init__(self, repo: MSIRepository | None = None) -> None:
        self.repo = repo or MSIRepository()

    def list_datasets(self):
        return self.repo.list_datasets()

    def get_dataset(self, dataset_id: str):
        return self.repo.get_dataset(dataset_id)

    def list_representations(self, dataset_id: str):
        return self.repo.list_representations(dataset_id)

    def lifecycle(self, dataset_id: str) -> DatasetLifecycleSummary | None:
        dataset = self.repo.get_dataset(dataset_id)
        if not dataset:
            return None

        representations = self.repo.list_representations(dataset_id)
        loaded = self.repo.list_loaded_states(dataset_id)
        preferred = self._preferred_representation(representations)

        return DatasetLifecycleSummary(
            dataset=dataset,
            representations=representations,
            loaded_representations=loaded,
            viewer_ready=preferred is not None,
            preferred_representation_id=preferred.representation_id if preferred else None,
            available_actions=self._available_actions(dataset.dataset_type, representations),
        )

    def load_representation(self, representation_id: str):
        return self.repo.set_loaded(representation_id, True)

    def unload_representation(self, representation_id: str):
        return self.repo.set_loaded(representation_id, False)

    @staticmethod
    def _preferred_representation(
        representations: list[ManagedRepresentation],
        preferred_mode: str | None = None,
    ) -> ManagedRepresentation | None:
        ready = [
            r for r in representations
            if r.viewer_ready and r.lifecycle_state == "viewer_ready"
        ]

        if preferred_mode in ("2d", "3d"):
            ready = [r for r in ready if r.viewer_mode == preferred_mode]

        if not ready:
            return None

        def rank(r: ManagedRepresentation) -> tuple[int, int, int]:
            # Higher is better.
            type_rank = {
                "zarr_3d": 40,
                "zarr_2d": 30,
                "indexed_segy_2d": 20,
                "metadata_bundle": 5,
                "unknown": 0,
            }.get(r.representation_type, 0)

            return (
                1 if r.is_preferred else 0,
                type_rank,
                1 if r.storage_uri else 0,
            )

        return sorted(ready, key=rank, reverse=True)[0]

    @staticmethod
    def _available_actions(dataset_type: str, representations: list[ManagedRepresentation]) -> list[str]:
        ready_types = {
            r.representation_type
            for r in representations
            if r.viewer_ready and r.lifecycle_state == "viewer_ready"
        }

        actions: list[str] = []

        if dataset_type == "2d_line":
            if "indexed_segy_2d" not in ready_types:
                actions.append("create_index")
            if "zarr_2d" not in ready_types:
                actions.append("convert_to_zarr")
        elif dataset_type == "3d_volume":
            if "zarr_3d" not in ready_types:
                actions.append("convert_to_zarr")
        else:
            actions.extend(["classify_dataset", "prepare_representation"])

        return actions

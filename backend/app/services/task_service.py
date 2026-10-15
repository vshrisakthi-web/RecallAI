"""Task service for approved agent task drafts (Module 8, Task 79).

Plain English: a thin service over :class:`TaskRepository`. The approval agent
depends on this, not on the repository directly, mirroring how the ingestion
service depends on the repository interface. It performs **no validation** —
the approval agent validates drafts (limits, source references) before calling
``persist_drafts``. This service's only job is the durable write, and it
delegates atomicity to the repository.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.repositories.task_repo import TaskRepository


class TaskService:
    """Persist approved task drafts; the sole durable task-write path."""

    def __init__(self, repository: TaskRepository) -> None:
        self._repository = repository

    def persist_drafts(
        self, drafts: List[Dict[str, Any]], run_id: str
    ) -> List[str]:
        """Persist validated drafts for ``run_id``; return the new task ids.

        Raises ``StorageError`` on failure (the repository rolls back the whole
        batch), so a partial approval can never leave half the drafts saved.
        """
        return self._repository.create_many(drafts, run_id)

"""Repository abstraction (Module 3, Task 3.13).

The ingestion service depends on this interface, never on a concrete storage
backend. That keeps persistence details out of route handlers and lets tests
substitute an isolated store (or an in-memory one).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from app.schemas.common import CanonicalRecord


class IngestionRepository(ABC):
    """Storage for canonical ingestion records."""

    @abstractmethod
    def save_or_get(self, record: CanonicalRecord) -> Tuple[CanonicalRecord, bool]:
        """Persist ``record`` unless an equivalent one already exists.

        Returns ``(stored_record, duplicate)``. When ``duplicate`` is True the
        returned record is the pre-existing one and nothing new is written.
        """

    @abstractmethod
    def get_by_id(self, record_id: str) -> Optional[CanonicalRecord]:
        ...

    @abstractmethod
    def list_recent(self, limit: int = 50) -> List[CanonicalRecord]:
        ...

    @abstractmethod
    def count(self) -> int:
        ...


class StorageError(RuntimeError):
    """Raised by a repository when persistence fails."""

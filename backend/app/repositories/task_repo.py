"""Task persistence repository for approved agent task drafts (Task 79).

Plain English: this is the *only* place durable ``tasks`` rows are created.
It is called by the approval service **after** a valid, explicit user
approval — never by the workflow, the agents, or any model output.

Design decisions:

* No migration and no schema change: the draft is stored verbatim in the
  existing ``tasks.input_reference`` JSON column with
  ``task_type="agent_task_draft"`` and ``status="todo"``. Title, description,
  priority, source ids, and kind are all preserved inside that JSON.
* All drafts for one approval are written in a **single transaction**. If any
  row fails, the whole batch rolls back (no partial persistence) and a
  ``StorageError`` is raised, matching the existing repository convention.
* The caller (approval service) has already validated the drafts; this layer
  only persists. It never invents ids — ``new_id("task")`` is server-side.
"""

from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import Task
from app.repositories.base import StorageError
from app.services.hashing import new_id

# The one task_type this module writes. Drafts from the agent harness are
# clearly distinguishable from any other future task kinds.
AGENT_DRAFT_TASK_TYPE = "agent_task_draft"


class TaskRepository:
    """Durable task persistence over the existing ``tasks`` table."""

    def __init__(self, sessions: sessionmaker) -> None:
        self._sessions = sessions

    def create_many(
        self, drafts: List[Dict[str, Any]], run_id: str
    ) -> List[str]:
        """Persist approved drafts atomically; return the new task ids.

        Args:
            drafts: validated draft dicts, each with keys ``title``,
                ``description``, ``priority``, ``source_ids``, ``kind``.
            run_id: the workflow run these drafts came from, recorded on every
                row for provenance.

        Raises:
            StorageError: any database failure; nothing is committed, so a
                failed batch leaves no partial rows.
        """
        if not drafts:
            return []
        session: Session = self._sessions()
        try:
            ids: List[str] = []
            for draft in drafts:
                task_id = new_id("task")
                reference = {
                    "title": draft.get("title"),
                    "description": draft.get("description"),
                    "priority": draft.get("priority"),
                    "source_ids": list(draft.get("source_ids") or []),
                    "kind": draft.get("kind"),
                    "run_id": run_id,
                }
                session.add(
                    Task(
                        id=task_id,
                        task_type=AGENT_DRAFT_TASK_TYPE,
                        status="todo",
                        input_reference=reference,
                    )
                )
                ids.append(task_id)
            session.commit()
            return ids
        except IntegrityError as exc:
            session.rollback()
            raise StorageError("database constraint rejected the approved task") from exc
        except SQLAlchemyError as exc:
            session.rollback()
            raise StorageError("database write failed while saving approved tasks") from exc
        finally:
            session.close()

    def get_by_id(self, task_id: str) -> Dict[str, Any] | None:
        """Return a stored task's reference dict, or ``None`` (for tests)."""
        session: Session = self._sessions()
        try:
            task = session.get(Task, task_id)
            if task is None:
                return None
            return {
                "id": task.id,
                "task_type": task.task_type,
                "status": task.status,
                "input_reference": task.input_reference,
            }
        finally:
            session.close()

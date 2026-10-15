"""Harness policies: limits and budgets for every workflow run (Task 71).

Plain English: before any agent runs, the harness decides how much it is
allowed to do — how long the question may be, how much evidence may enter a
prompt, how many tasks may be drafted, how long one stage may take, how long
the whole run may take, and how many attempts a stage gets after a
recoverable error. All of it lives here as one frozen value object so tests
can assert the exact limits instead of hunting for magic numbers.

Every field is backed by a RECALLAI_AGENT_* setting in
``app.core.config.Settings`` (same environment-variable conventions as the
Module 6 RAG settings).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings, settings

_POLICY_FIELDS = (
    "max_query_chars",
    "max_evidence_items",
    "max_evidence_chars",
    "max_tasks",
    "max_task_title_chars",
    "max_task_description_chars",
    "stage_timeout_seconds",
    "total_budget_seconds",
    "max_attempts",
    "max_errors",
)


@dataclass(frozen=True)
class HarnessPolicy:
    """Bounds for one workflow run.

    Attributes:
        max_query_chars: maximum length of the question text.
        max_evidence_items: maximum evidence passages passed to analysis.
        max_evidence_chars: total evidence characters allowed into a prompt.
        max_tasks: maximum number of task drafts per run.
        max_task_title_chars / max_task_description_chars: per-draft text caps.
        stage_timeout_seconds: wall-clock budget for a single stage operation.
        total_budget_seconds: wall-clock budget for the whole run.
        max_attempts: attempts per stage (initial try plus bounded repairs of
            recoverable format errors; never retries for invalid input).
        max_errors: user-facing errors retained on the run (oldest dropped).
    """

    max_query_chars: int
    max_evidence_items: int
    max_evidence_chars: int
    max_tasks: int
    max_task_title_chars: int
    max_task_description_chars: int
    stage_timeout_seconds: int
    total_budget_seconds: int
    max_attempts: int
    max_errors: int

    def __post_init__(self) -> None:
        for name in _POLICY_FIELDS:
            if getattr(self, name) < 1:
                raise ValueError(f"Harness policy field {name} must be at least 1.")
        if self.total_budget_seconds < self.stage_timeout_seconds:
            raise ValueError(
                "Harness policy requires total_budget_seconds >= stage_timeout_seconds "
                "so one stage call can never exceed the whole run budget."
            )

    @classmethod
    def from_settings(cls, config: Settings = settings) -> "HarnessPolicy":
        """Build the policy from application settings (env-overridable)."""
        return cls(
            max_query_chars=config.agent_max_query_chars,
            max_evidence_items=config.agent_max_evidence_items,
            max_evidence_chars=config.agent_max_evidence_chars,
            max_tasks=config.agent_max_tasks,
            max_task_title_chars=config.agent_max_task_title_chars,
            max_task_description_chars=config.agent_max_task_description_chars,
            stage_timeout_seconds=config.agent_stage_timeout_seconds,
            total_budget_seconds=config.agent_total_budget_seconds,
            max_attempts=config.agent_max_attempts,
            max_errors=config.agent_max_errors,
        )

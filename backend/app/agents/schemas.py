"""Shared structured schemas for the agent harness (Module 8, Task 77).

Plain English: this module is the single validation boundary for data
that crosses trust lines in the workflow — router results, model output
already validated by the agents, and the orchestrator response served to
the API/UI. Every model here is strict (``extra="forbid"``): unknown
fields are rejected, never absorbed.

What lives here versus the agent modules:

* Analysis/task *model-output* schemas stay where they are
  (``AnalysisResult`` in ``analysis_agent.py``, ``TaskDraft`` /
  ``TaskDraftList`` in ``task_agent.py``) and are reused, not duplicated.
* This module adds what was missing: the router result schema, the
  response-side evidence/error/trace items, the full ``WorkflowResponse``
  envelope, and cross-field consistency (refs ⊆ evidence, clarification
  exclusivity, empty-evidence honesty, server-field protection).
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.agents.contracts import validate_evidence_refs
from app.agents.state import Objective, RunStatus, TraceStatus
from app.agents.task_agent import TaskDraft

_SAFE_ID_PATTERN = r"^[A-Za-z0-9._-]{1,64}$"
_MAX_CLARIFICATION_CHARS = 500
_MAX_STATEMENT_CHARS = 1000
_MAX_PASSAGE_CHARS = 10000
_MAX_ERROR_MESSAGE_CHARS = 300
_MAX_ITEMS = 20

__all__ = [
    "RoutingResult",
    "WorkflowEvidenceItem",
    "WorkflowErrorItem",
    "WorkflowTraceItem",
    "WorkflowResponse",
    "validate_routing_result",
    "validate_workflow_response",
]


class RoutingResult(BaseModel):
    """Validated router output: exactly one of objective/clarification."""

    model_config = ConfigDict(extra="forbid")

    objective: Optional[Objective] = None
    clarification: Optional[str] = Field(default=None, max_length=_MAX_CLARIFICATION_CHARS)
    confidence: float = Field(ge=0.0, le=1.0)
    ambiguity_score: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _exactly_one_outcome(self) -> "RoutingResult":
        has_objective = self.objective is not None
        has_clarification = self.clarification is not None and self.clarification.strip() != ""
        if has_objective == has_clarification:
            raise ValueError(
                "A routing result must carry either an objective or a "
                "non-empty clarification, never both or neither."
            )
        return self


class AnalysisFindingItem(BaseModel):
    """Response-side finding: statement plus cited chunk ids."""

    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1, max_length=_MAX_STATEMENT_CHARS)
    evidence_refs: List[str] = Field(min_length=1, max_length=10)


class WorkflowEvidenceItem(BaseModel):
    """One grounded evidence passage in a workflow response."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(min_length=1, max_length=64)
    memory_id: str = Field(min_length=1, max_length=64)
    source_title: Optional[str] = Field(default=None, max_length=500)
    source_url: Optional[str] = Field(default=None, max_length=2000)
    passage: str = Field(min_length=1, max_length=_MAX_PASSAGE_CHARS)


class WorkflowErrorItem(BaseModel):
    """One safe user-facing workflow error (no internals, ever)."""

    model_config = ConfigDict(extra="forbid")

    stage: str = Field(min_length=1, max_length=64)
    category: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=_MAX_ERROR_MESSAGE_CHARS)


class WorkflowTraceItem(BaseModel):
    """One sanitized stage-trace record (timing only, no content)."""

    model_config = ConfigDict(extra="forbid")

    stage: str = Field(min_length=1, max_length=64)
    status: TraceStatus
    duration_ms: int = Field(ge=0)
    attempts: int = Field(ge=1)
    error_category: Optional[str] = Field(default=None, max_length=64)


class WorkflowResponse(BaseModel):
    """The validated workflow result served to the API/UI.

    Mirrors ``build_response`` exactly: ``run_id, objective, status,
    clarification, findings, evidence, task_drafts, errors, trace``.
    Cross-field rules: clarification runs carry no objective, evidence,
    findings, or drafts; every finding ref and draft source id must name
    a retrieved ``chunk_id``; every draft stays ``status="draft"``.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=64, pattern=_SAFE_ID_PATTERN)
    objective: Optional[Objective] = None
    status: RunStatus
    clarification: Optional[str] = Field(default=None, max_length=_MAX_CLARIFICATION_CHARS)
    findings: List[AnalysisFindingItem] = Field(default_factory=list, max_length=_MAX_ITEMS)
    evidence: List[WorkflowEvidenceItem] = Field(default_factory=list, max_length=_MAX_ITEMS)
    task_drafts: List[TaskDraft] = Field(default_factory=list, max_length=_MAX_ITEMS)
    errors: List[WorkflowErrorItem] = Field(default_factory=list, max_length=100)
    trace: List[WorkflowTraceItem] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def _check_consistency(self) -> "WorkflowResponse":
        if self.clarification is not None:
            if self.objective is not None:
                raise ValueError("A clarification response must not carry an objective.")
            if self.evidence or self.findings or self.task_drafts:
                raise ValueError(
                    "A clarification response must not contain results from "
                    "stages that never ran."
                )
            return self
        available = [item.chunk_id for item in self.evidence]
        claimed: List[str] = []
        for finding in self.findings:
            claimed.extend(finding.evidence_refs)
        for draft in self.task_drafts:
            claimed.extend(draft.source_ids)
        validate_evidence_refs(claimed, available)
        return self


def validate_routing_result(result: dict) -> dict:
    """Validate a router result dict; return its python-mode (enum-safe) dump."""
    validated = RoutingResult.model_validate(result)
    return validated.model_dump(mode="python")


def validate_workflow_response(payload: dict) -> WorkflowResponse:
    """Validate an orchestrator response payload into ``WorkflowResponse``."""
    return WorkflowResponse.model_validate(payload)


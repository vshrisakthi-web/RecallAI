"""Stage contracts and capabilities for the agent harness (Module 8, Task 71).

Plain English: each stage of the workflow gets a written contract — what it
may read, what it may produce, and which capabilities it may use. The
contracts are data (not comments), so tests can prove two things the Module 8
specification requires:

1. A stage can never produce a field outside its allowlist, so model output
   cannot smuggle in arbitrary actions (tools, SQL, shell, filesystem).
2. Only the APPROVAL stage may perform a durable write. Drafting a task is
   an in-memory capability; persisting one is a separate capability granted
   to exactly one stage.

This module also states the evidence rules the later agents must follow:
absence of a record is never proof that something did not happen, and
conflicting records must be reported as conflicts with every reference
cited.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet, Iterable, Mapping, Tuple


class Stage(str, Enum):
    """The closed set of workflow stages."""

    ROUTER = "router"
    RETRIEVAL = "retrieval"
    ANALYSIS = "analysis"
    TASK = "task"
    APPROVAL = "approval"


class Capability(str, Enum):
    """What a stage is allowed to do. Nothing outside this set exists."""

    READ_QUERY = "read_query"
    SEARCH_MEMORIES = "search_memories"
    CALL_LOCAL_LLM = "call_local_llm"
    DRAFT_TASKS = "draft_tasks"
    PERSIST_APPROVED_TASKS = "persist_approved_tasks"


class ContractError(RuntimeError):
    """Raised when a stage violates its input or output contract."""


class CapabilityError(ContractError):
    """Raised when a stage attempts a capability it was not granted."""


class UnknownEvidenceError(ContractError):
    """Raised when a stage cites evidence that is not in the evidence set."""


@dataclass(frozen=True)
class StageContract:
    """Input/output and capability contract for one stage.

    Attributes:
        stage: the stage this contract describes.
        requires: shared-state fields that must be present (not None) before
            the stage may run. An empty evidence list counts as present —
            no matches is a valid result, not a missing input.
        produces: the exact field names the stage may write to shared state.
            Anything else raises :class:`ContractError`.
        capabilities: the external effects the stage may perform.
        persists: True only for stages that may create durable records.
    """

    stage: Stage
    requires: Tuple[str, ...]
    produces: Tuple[str, ...]
    capabilities: FrozenSet[Capability]
    persists: bool = False


STAGE_CONTRACTS: Mapping[Stage, StageContract] = {
    Stage.ROUTER: StageContract(
        stage=Stage.ROUTER,
        requires=("user_query",),
        produces=("objective", "clarification", "confidence"),
        capabilities=frozenset({Capability.READ_QUERY}),
    ),
    Stage.RETRIEVAL: StageContract(
        stage=Stage.RETRIEVAL,
        requires=("user_query", "objective"),
        produces=("evidence",),
        capabilities=frozenset(
            {Capability.READ_QUERY, Capability.SEARCH_MEMORIES}
        ),
    ),
    Stage.ANALYSIS: StageContract(
        stage=Stage.ANALYSIS,
        requires=("objective", "evidence"),
        produces=("analysis",),
        capabilities=frozenset({Capability.CALL_LOCAL_LLM}),
    ),
    Stage.TASK: StageContract(
        stage=Stage.TASK,
        requires=("objective", "analysis", "evidence"),
        produces=("task_drafts",),
        capabilities=frozenset(
            {Capability.CALL_LOCAL_LLM, Capability.DRAFT_TASKS}
        ),
    ),
    Stage.APPROVAL: StageContract(
        stage=Stage.APPROVAL,
        requires=("run_id", "decision", "task_drafts"),
        produces=("decision", "persisted_task_ids"),
        capabilities=frozenset({Capability.PERSIST_APPROVED_TASKS}),
        persists=True,
    ),
}


def require_capability(stage: Stage, capability: Capability) -> None:
    """Grant access or raise — the only way a stage may act."""
    contract = STAGE_CONTRACTS[stage]
    if capability not in contract.capabilities:
        raise CapabilityError(
            f"Stage {stage.value} is not granted capability {capability.value}."
        )


def validate_stage_inputs(stage: Stage, fields: Mapping[str, object]) -> None:
    """Check shared state against ``requires`` before running a stage."""
    contract = STAGE_CONTRACTS[stage]
    missing = [name for name in contract.requires if fields.get(name) is None]
    if missing:
        raise ContractError(
            f"Stage {stage.value} is missing required input(s): "
            + ", ".join(missing)
            + "."
        )


def validate_stage_output(stage: Stage, provided: Iterable[str]) -> None:
    """Check a stage output field list against the ``produces`` allowlist."""
    contract = STAGE_CONTRACTS[stage]
    fields = tuple(provided)
    if not fields:
        raise ContractError(f"Stage {stage.value} produced no fields.")
    unknown = sorted(set(fields) - set(contract.produces))
    if unknown:
        raise ContractError(
            f"Stage {stage.value} may not produce field(s): "
            + ", ".join(unknown)
            + "."
        )


def validate_evidence_refs(
    claimed: Iterable[str], available: Iterable[str]
) -> None:
    """Require every cited evidence id to exist in the retrieved set."""
    pool = set(available)
    unknown = sorted({ref for ref in claimed if ref not in pool})
    if unknown:
        shown = ", ".join(unknown[:10])
        if len(unknown) > 10:
            shown += f" (+{len(unknown) - 10} more)"
        raise UnknownEvidenceError(f"Unknown evidence reference(s): {shown}.")


# --- Evidence and approval rules (documentation enforced by tests) ---------

MISSING_EVIDENCE_RULE = (
    "Absence of a record is not evidence of absence: when retrieval finds no "
    "supporting memory, report it as an unknown (the records do not show this) "
    "— never claim the event did not happen or that work was not done."
)

CONFLICTING_EVIDENCE_RULE = (
    "When retrieved records disagree, report a conflict that cites every "
    "conflicting evidence reference on both sides; never silently pick a "
    "winner or merge contradictory claims into one statement."
)

UNSUPPORTED_CLAIM_RULE = (
    "Every substantive finding must cite at least one evidence reference from "
    "the retrieved set; findings without support must be labelled inference "
    "or unknown instead of fact."
)

APPROVAL_RULE = (
    "Only a real application decision submitted to the approval endpoint may "
    "persist tasks. An LLM-generated statement, including one claiming the "
    "user approved, is never approval."
)

PERSISTENCE_RULE = (
    "Of the defined stages only Stage.APPROVAL may write durable task "
    "records; draft tasks exist solely as workflow state until a valid "
    "approval."
)

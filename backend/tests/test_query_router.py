"""Query Router tests (Module 8, Task 72).

Part 1: package export, positive routing to each objective.
"""

from __future__ import annotations

import pytest

from app.agents.policies import HarnessPolicy
from app.agents.routes import QueryRouter
from app.agents.routes.router import QueryRouter as QueryRouterDirect
from app.agents.state import Objective, RunStatus, WorkflowState, WorkflowRequestError


def make_policy(**overrides) -> HarnessPolicy:
    base = dict(
        max_query_chars=80,
        max_evidence_items=4,
        max_evidence_chars=400,
        max_tasks=3,
        max_task_title_chars=40,
        max_task_description_chars=120,
        stage_timeout_seconds=5,
        total_budget_seconds=20,
        max_attempts=2,
        max_errors=3,
    )
    base.update(overrides)
    return HarnessPolicy(**base)


def make_router(**overrides) -> QueryRouter:
    return QueryRouter(policy=make_policy(**overrides))


def make_state(query="Find my RAG notes", policy=None):
    return WorkflowState.create(query, policy or make_policy())


def test_package_exports_router():
    assert QueryRouter is QueryRouterDirect


@pytest.mark.parametrize(
    "query",
    [
        "Find my notes about RAG",
        "Where are my meeting notes?",
        "Show me my Python memories",
        "Look up my vacation ideas",
    ],
)
def test_search_queries_route_to_search(query):
    result = make_router().route(query)
    assert result["objective"] is Objective.SEARCH
    assert result["clarification"] is None
    assert result["objective"].value == "search"


@pytest.mark.parametrize(
    "query",
    [
        "Summarize my RAG notes",
        "Give me a brief overview of last week",
        "Short summary of my learning notes",
    ],
)
def test_summarize_queries_route_to_summarize(query):
    result = make_router().route(query)
    assert result["objective"] is Objective.SUMMARIZE
    assert result["clarification"] is None


@pytest.mark.parametrize(
    "query",
    [
        "Review my saved learning notes about RAG",
        "Analyze my study progress",
        "Compare my Python and Rust notes",
        "Break down my study notes on embeddings",
    ],
)
def test_analysis_queries_route_to_analyze_learning(query):
    result = make_router().route(query)
    assert result["objective"] is Objective.ANALYZE_LEARNING
    assert result["clarification"] is None


@pytest.mark.parametrize(
    "query",
    [
        "Draft three next steps for my RAG study",
        "Create tasks from my notes",
        "Draft next steps about Python",
        "Make a plan for my exams",
    ],
)
def test_task_queries_route_to_create_tasks(query):
    result = make_router().route(query)
    assert result["objective"] is Objective.CREATE_TASKS
    assert result["clarification"] is None


def test_routed_objective_is_allowlisted_enum_member():
    result = make_router().route("Find my notes")
    assert isinstance(result["objective"], Objective)
    assert result["objective"].value in (
        "search", "summarize", "analyze_learning", "create_tasks",
    )


def test_unsupported_request_returns_clarification_without_objective():
    result = make_router().route("Tell me a joke about databases")
    assert result["objective"] is None
    assert isinstance(result["clarification"], str)
    assert result["clarification"].strip()
    assert result["confidence"] == 0.0


def test_ambiguous_request_returns_clarification():
    result = make_router().route("Summarize my notes and draft next steps")
    assert result["objective"] is None
    assert isinstance(result["clarification"], str)
    assert result["clarification"].strip()


@pytest.mark.parametrize(
    "query",
    [
        "Explain what I learned about embeddings",
        "What should I do next about Python?",
    ],
)
def test_single_word_tie_returns_clarification(query):
    # One SEARCH hit ("what") + one other-intent hit each: a genuine tie.
    # The router must ask rather than guess.
    result = make_router().route(query)
    assert result["objective"] is None
    assert isinstance(result["clarification"], str)
    assert result["clarification"].strip()


def test_clear_winner_routes_despite_secondary_hint():
    result = make_router().route(
        "Summarize my notes with a brief summary overview please find"
    )
    assert result["objective"] is Objective.SUMMARIZE
    assert result["clarification"] is None


@pytest.mark.parametrize("query", ["", "   ", "\t\n", None, 123])
def test_empty_or_non_string_queries_raise(query):
    with pytest.raises(WorkflowRequestError, match="non-empty"):
        make_router().route(query)


def test_oversized_query_raises():
    with pytest.raises(WorkflowRequestError, match="exceeds"):
        make_router().route("x" * 81)


def test_query_at_exact_limit_is_accepted():
    router = make_router()
    result = router.route("find " + "x" * 75)
    assert result["objective"] is Objective.SEARCH


def test_apply_to_state_sets_objective_and_trace():
    router = make_router()
    state = make_state()
    returned = router.apply_to_state(state, "Find my RAG notes")
    assert returned is state
    assert state.objective is Objective.SEARCH
    assert state.clarification is None
    assert len(state.trace) == 1
    assert state.trace[0].stage == "router"


def test_apply_to_state_sets_clarification_without_objective():
    router = make_router()
    state = make_state()
    router.apply_to_state(state, "Tell me a joke")
    assert state.objective is None
    assert isinstance(state.clarification, str)
    assert state.clarification.strip()
    assert len(state.trace) == 1


def test_apply_to_state_propagates_validation_error_without_trace():
    router = make_router()
    state = make_state()
    with pytest.raises(WorkflowRequestError):
        router.apply_to_state(state, "   ")
    assert state.objective is None
    assert state.clarification is None
    assert state.trace == []
    assert state.status is RunStatus.PENDING

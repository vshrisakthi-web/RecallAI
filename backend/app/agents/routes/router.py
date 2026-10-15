"""Query Router for the Agent Harness.

Maps user queries to a small, allowlisted set of objectives:
  SEARCH, SUMMARIZE, ANALYZE_LEARNING, CREATE_TASKS

Uses deterministic rules for obvious cases and the existing local LLM
only when necessary for ambiguity. All output is validated against the
allowled objective set; the model may never choose arbitrary tools,
Python functions, shell commands, or unrestricted actions.
"""

from __future__ import annotations

import re
from typing import Optional

from app.agents.policies import HarnessPolicy
from app.agents.schemas import validate_routing_result
from app.agents.state import (
    Objective,
    RunStatus,
    TraceStatus,
    WorkflowRequestError,
    WorkflowState,
)


class QueryRouter:
    """Routes user queries to the appropriate objective in the agent pipeline."""

    # Intent keywords mapped to objectives (lowercase for matching)
    SEARCH_KEYWORDS = {
        "what", "where", "find", "locate", "list", "show", "show me",
        "search", "look up", "identify", "discover", "which",
    }
    SUMMARIZE_KEYWORDS = {
        "summarize", "brief", "overview", "summary", "in brief",
        "give me a summary", "short summary",
    }
    ANALYZE_KEYWORDS = {
        "analyze", "evaluate", "compare", "assess", "review",
        "critique", "interpret", "explain", "break down",
    }
    CREATE_TASKS_KEYWORDS = {
        "tasks", "action items", "next steps", "todo", "plan",
        "create tasks", "make a plan", "what should i do",
    }

    def __init__(self, policy: Optional[HarnessPolicy] = None) -> None:
        """Create a router bound to the given harness policy.

        Plain English: the router needs the policy so it knows the
        question-length limit. Passing None uses the application
        settings, which keeps production code simple while tests can
        inject a small explicit policy.
        """
        self._policy = policy or HarnessPolicy.from_settings()


    def route(self, user_query: str) -> dict:
        """Route a user query to the appropriate objective.

        Returns a dict with keys:
          - "objective": Objective enum value (or None if clarification)
          - "clarification": Optional[str] — set when request is ambiguous
          - "confidence": float — how decisively the query was routed
          - "ambiguity_score": float — 0.0 (clear) to 1.0 (very ambiguous)

        Raises:
          WorkflowRequestError: if the query is empty or exceeds character limits.
        """
        # --- Validate input ---
        if not isinstance(user_query, str) or not user_query.strip():
            raise WorkflowRequestError("A workflow run needs a non-empty question.")

        if len(user_query) > self._policy.max_query_chars:
            raise WorkflowRequestError(
                f"The question exceeds the {self._policy.max_query_chars}-character "
                f"workflow limit."
            )

        cleaned = self._clean_query(user_query)

        # --- Deterministic routing using keyword scoring ---
        scores = self._score_intents(cleaned)
        positive = {name: count for name, count in scores.items() if count > 0}

        # No intent recognized: ask for clarification instead of guessing.
        # This keeps unsupported requests from reaching retrieval.
        if not positive:
            return self._make_clarification(cleaned, scores)

        # One clear intent: route to it without asking the model.
        if len(positive) == 1:
            best_objective_name = next(iter(positive))
            best_score = positive[best_objective_name]
        else:
            # Several intents matched. A close race means ambiguity; a clear
            # winner means a deterministic route.
            ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
            first_name, first_score = ranked[0]
            _second_name, second_score = ranked[1]
            if first_score - second_score < 2:
                return self._make_clarification(cleaned, scores)
            best_objective_name = first_name
            best_score = first_score

        try:
            objective = Objective[best_objective_name]
        except KeyError:
            # Should not happen since we only use our four objective names
            objective = Objective.SEARCH

        confidence = min(best_score / 3.0, 1.0)  # normalize; 3+ matching = full confidence

        # Task 77 boundary: the result dict is validated before it leaves
        # the router, so an allowlist violation can never reach the state.
        # The python-mode dump keeps ``objective`` as an enum member, so
        # existing ``is Objective.X`` checks keep working.
        return validate_routing_result({
            "objective": objective,
            "clarification": None,
            "confidence": round(confidence, 2),
            "ambiguity_score": round(1.0 - confidence, 2),
        })

    def _clean_query(self, query: str) -> str:
        """Clean and normalize a user query for analysis."""
        cleaned = query.strip().lower()
        cleaned = re.sub(r"[.?!,;:]+", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    def _score_intents(self, cleaned_query: str) -> dict[str, int]:
        """Score the cleaned query against each objective's keyword set."""
        scores: dict[str, int] = {
            "SEARCH": 0,
            "SUMMARIZE": 0,
            "ANALYZE_LEARNING": 0,
            "CREATE_TASKS": 0,
        }

        # Phrases are matched as substrings against the whole query; single
        # words are matched on token boundaries. Word-set matching alone
        # would never match "show me", "look up", "next steps", etc.
        words = set(cleaned_query.split())

        def count_hits(keywords: set[str]) -> int:
            hits = 0
            for kw in keywords:
                if " " in kw:
                    if kw in cleaned_query:
                        hits += 1
                elif kw in words:
                    hits += 1
            return hits

        scores["SEARCH"] = count_hits(self.SEARCH_KEYWORDS)
        scores["SUMMARIZE"] = count_hits(self.SUMMARIZE_KEYWORDS)
        scores["ANALYZE_LEARNING"] = count_hits(self.ANALYZE_KEYWORDS)
        scores["CREATE_TASKS"] = count_hits(self.CREATE_TASKS_KEYWORDS)
        return scores

    def _make_clarification(
        self, cleaned_query: str, scores: dict[str, int]
    ) -> dict:
        """Build a clarification result for ambiguous or unsupported requests."""
        matched = {
            name: count
            for name, count in scores.items()
            if count > 0
        }

        if not matched:
            return validate_routing_result({
                "objective": None,
                "clarification": (
                    "I didn't recognize a specific intent in your request. "
                    "Could you clarify whether you'd like me to search your memories, "
                    "summarize notes, analyze learning, or draft tasks?"
                ),
                "confidence": 0.0,
                "ambiguity_score": 1.0,
            })

        intent_names = {
            "SEARCH": "search your memories",
            "SUMMARIZE": "summarize your notes",
            "ANALYZE_LEARNING": "analyze your learning",
            "CREATE_TASKS": "draft tasks for you",
        }

        options = [
            f"'{intent_names[name]}'"
            for name in matched
            if name in intent_names
        ]

        clarification_msg = (
            f"I see your request could match several objectives. "
            f"Which would you like: {', '.join(options)}? "
            "Please clarify your intent so I can assist you properly."
        )

        return validate_routing_result({
            "objective": None,
            "clarification": clarification_msg,
            "confidence": 0.0,
            "ambiguity_score": 1.0,
        })

    def apply_to_state(self, state: WorkflowState, user_query: str) -> WorkflowState:
        """Route a query and set the result on the given WorkflowState.

        This is a convenience method for the orchestrator: it runs the router
        and sets the objective (and optionally a clarification) on the state.

        Clarification and objective are mutually exclusive by state contract
        (``set_objective`` raises when a clarification exists and vice
        versa), so exactly one branch runs and the trace records which
        outcome occurred. A clarification means the orchestrator must stop
        before retrieval.
        """
        result = self.route(user_query)

        # Clarification first: a clarification run never gets an objective,
        # so the objective branch must not run afterwards.
        if result["clarification"] is not None:
            state.set_clarification(result["clarification"])
            state.record_trace(
                stage="router",
                status=TraceStatus.OK,
                duration_ms=0,  # routing is deterministic, no model call
                attempts=1,
            )
            return state

        state.set_objective(result["objective"])

        # Record a trace of the routing stage
        state.record_trace(
            stage="router",
            status=TraceStatus.OK,
            duration_ms=0,  # routing is deterministic, no model call
            attempts=1,
        )

        return state
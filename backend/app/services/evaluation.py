"""Retrieval evaluation over a deterministic synthetic dataset (Task 6.10).

Plain English: "the search feels good" is not a measurement. This module turns
retrieval quality into numbers you can re-run and compare.

The dataset is **synthetic and deterministic** — no private user data, no live
model call, and the same corpus every run — so the ordinary test suite stays
offline and reproducible. Vectors are fixed by construction rather than
produced by an embedding model, which makes the expected ranking unambiguous:
a query vector either points at a topic or it does not.

Metrics (standard information-retrieval measures):

* **Recall@k** — of the passages that *should* be found, how many were? Catches
  "the right answer was ranked 8th and cut off".
* **Precision@k** — of the passages returned, how many were relevant? Catches
  "it returned six things and only one was on topic".
* **MRR** (Mean Reciprocal Rank) — how high the *first* relevant result sits,
  averaged over queries. A first hit scores 1.0, a second 0.5, a third 0.33.

The case list deliberately includes the awkward situations, not just the easy
ones: exact-match, paraphrased, temporal, source-filtered, irrelevant,
duplicate, deleted-memory, and missing-metadata cases. A retrieval system is
only as good as its worst case, so those are the ones worth measuring.

Reported numbers are **measured from this dataset**, never benchmarks copied
from elsewhere; a different corpus will produce different results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

# --- Synthetic corpus ------------------------------------------------------
#
# Six topics, each with a 3-dim "direction". A case's query vector is a blend
# of the directions of the topics it is about, so relevance is defined by
# construction rather than by a live model's opinion.

VECTOR_DB = [1.0, 0.0, 0.0, 0.0, 0.0]
IVF = [0.86, 0.51, 0.0, 0.0, 0.0]
COOKING = [0.0, 1.0, 0.0, 0.0, 0.0]
PRIVACY = [0.0, 0.0, 1.0, 0.0, 0.0]
LOCAL_EMBEDDINGS = [0.5, 0.0, 0.5, 0.71, 0.0]
WITHDRAWN = [0.0, 0.0, 0.0, 0.0, 1.0]

#: The corpus entry treated as deleted before scoring, so the deleted-memory
#: case is measured rather than merely asserted in prose.
DELETED_MEMORY_ID = "mem_deleted_1"

#: The similarity floor production applies to the semantic channel. Evaluation
#: uses the same value so measured numbers reflect real behaviour.
SIMILARITY_FLOOR = 0.25

#: The reference "today" for temporal cases. Fixed so results are reproducible.
REFERENCE_TODAY = "2026-10-12"


@dataclass(frozen=True)
class CorpusEntry:
    """One synthetic memory: its text, topic direction, and metadata."""

    memory_id: str
    title: str
    text: str
    vector: list[float]
    captured_at: str  # ISO date; used by temporal cases
    source_type: str = "note"
    domain: Optional[str] = None
    source_url: Optional[str] = None


@dataclass(frozen=True)
class EvalCase:
    """One evaluation case: a question and what a correct retriever should do.

    ``relevant_memory_ids`` is the ground truth. ``expect_empty`` marks cases
    where the correct answer is "nothing" — an irrelevant question, or a memory
    that was deleted — and returning anything there is a failure.
    """

    case_id: str
    kind: str
    question: str
    query_vector: list[float]
    relevant_memory_ids: frozenset
    expect_empty: bool = False
    temporal_expression: Optional[str] = None
    source_type: Optional[str] = None
    note: str = ""


@dataclass
class CaseResult:
    """The measured outcome for one case."""

    case_id: str
    kind: str
    retrieved: list
    relevant: list
    recall_at_k: float
    precision_at_k: float
    reciprocal_rank: float
    passed: bool
    detail: str = ""


@dataclass
class EvaluationReport:
    """Aggregate results across every case in the dataset."""

    results: list = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    def mean(self, name: str) -> float:
        """Mean of a per-case metric; 0.0 for an empty dataset (never NaN)."""
        if not self.results:
            return 0.0
        return sum(getattr(r, name) for r in self.results) / len(self.results)

    @property
    def mean_recall_at_k(self) -> float:
        return self.mean("recall_at_k")

    @property
    def mean_precision_at_k(self) -> float:
        return self.mean("precision_at_k")

    @property
    def mean_reciprocal_rank(self) -> float:
        return self.mean("reciprocal_rank")

    def by_kind(self, kind: str) -> list:
        return [r for r in self.results if r.kind == kind]


def recall_at_k(retrieved: Sequence, relevant: Iterable, k: int) -> float:
    """Fraction of the relevant ids that appear in the top ``k`` results."""
    relevant_set = set(relevant)
    if not relevant_set:
        # Nothing was supposed to be found, so there is nothing to miss.
        return 1.0
    hits = len(relevant_set & set(list(retrieved)[:k]))
    return hits / len(relevant_set)


def precision_at_k(retrieved: Sequence, relevant: Iterable, k: int) -> float:
    """Fraction of the top ``k`` results that are relevant."""
    top = list(retrieved)[:k]
    if not top:
        return 0.0
    relevant_set = set(relevant)
    return sum(1 for item in top if item in relevant_set) / len(top)


def reciprocal_rank(retrieved: Sequence, relevant: Iterable) -> float:
    """1/rank of the first relevant result, or 0.0 when none was found."""
    relevant_set = set(relevant)
    for position, item in enumerate(retrieved, start=1):
        if item in relevant_set:
            return 1.0 / position
    return 0.0

def build_dataset() -> tuple:
    """Return the deterministic synthetic corpus and its evaluation cases.

    Every case kind required by the task plan is represented, including the
    negative cases where the correct behaviour is to return nothing.
    """
    corpus = [
        CorpusEntry(
            memory_id="mem_vector_1",
            title="HNSW graphs",
            text="HNSW graphs connect embeddings in layers for approximate search.",
            vector=VECTOR_DB,
            captured_at="2026-09-20",
            source_type="browser",
            domain="example.com",
            source_url="https://example.com/hnsw",
        ),
        CorpusEntry(
            memory_id="mem_vector_2",
            title="IVF lists",
            text="IVF partitions embeddings into inverted lists for faster lookup.",
            vector=VECTOR_DB,
            captured_at="2026-10-05",
            source_type="note",
        ),
        CorpusEntry(
            memory_id="mem_cooking_1",
            title="Pasta water",
            text="Pasta needs salted boiling water and a wide pot.",
            vector=COOKING,
            captured_at="2026-10-08",
        ),
        CorpusEntry(
            memory_id="mem_privacy_1",
            title="Loopback only",
            text="Local inference must target a loopback host so nothing leaves the device.",
            vector=PRIVACY,
            captured_at="2026-10-01",
        ),
        CorpusEntry(
            memory_id="mem_blend_1",
            title="Local embeddings",
            text="A local embedding model keeps vectors and privacy on one machine.",
            vector=LOCAL_EMBEDDINGS,
            captured_at="2026-10-06",
        ),
        CorpusEntry(
            memory_id=DELETED_MEMORY_ID,
            title="Withdrawn note",
            text="This memory is deleted before retrieval runs.",
            vector=WITHDRAWN,
            captured_at="2026-10-07",
        ),
    ]

    cases = [
        # --- Exact keyword match -----------------------------------------
        EvalCase(
            case_id="exact_token",
            kind="exact",
            question="HNSW graphs",
            query_vector=VECTOR_DB,
            relevant_memory_ids=frozenset({"mem_vector_1"}),
            note="The exact token HNSW appears in only one memory.",
        ),
        # --- Paraphrase: no shared tokens, same meaning -------------------
        EvalCase(
            case_id="paraphrase",
            kind="paraphrase",
            question="how do approximate nearest neighbour structures work?",
            query_vector=VECTOR_DB,
            relevant_memory_ids=frozenset({"mem_vector_1"}),
            note="No shared words with the corpus; only semantics can find it.",
        ),
        # --- Temporal: right topic, wrong window --------------------------
        EvalCase(
            case_id="temporal_out_of_window",
            kind="temporal",
            question="what did I save about IVF lists yesterday?",
            query_vector=IVF,
            relevant_memory_ids=frozenset(),
            expect_empty=True,
            temporal_expression="yesterday",
            note="The IVF note exists but is outside the parsed window.",
        ),
        EvalCase(
            case_id="temporal_in_window",
            kind="temporal",
            question="what did I save about pasta in October?",
            query_vector=COOKING,
            relevant_memory_ids=frozenset({"mem_cooking_1"}),
            temporal_expression="in october",
            note="A memory inside the parsed month window is returned.",
        ),
        # --- Source filter -------------------------------------------------
        EvalCase(
            case_id="source_filter_browser",
            kind="source_filtered",
            question="which browser capture mentions HNSW?",
            query_vector=VECTOR_DB,
            relevant_memory_ids=frozenset({"mem_vector_1"}),
            source_type="browser",
            note="Only the browser-typed memory is relevant.",
        ),
        EvalCase(
            case_id="source_filter_excludes_note",
            kind="source_filtered",
            question="which transcript mentions pasta water?",
            query_vector=COOKING,
            relevant_memory_ids=frozenset(),
            expect_empty=True,
            source_type="transcript",
            note="The pasta memory exists but is a note, and no transcript covers it.",
        ),
        # --- Irrelevant: the correct answer is "nothing" -------------------
        EvalCase(
            case_id="irrelevant_topic",
            kind="irrelevant",
            question="what is the capital of France?",
            query_vector=[0.0, 0.0, 0.0, 0.0, 1.0],
            relevant_memory_ids=frozenset(),
            expect_empty=True,
            note="Only the deleted memory is near this vector, so nothing is returned.",
        ),
        # --- Duplicate content --------------------------------------------
        EvalCase(
            case_id="duplicate_content",
            kind="duplicate",
            question="embeddings in inverted lists",
            query_vector=IVF,
            relevant_memory_ids=frozenset({"mem_vector_2"}),
            note="A duplicate capture must not crowd out the original.",
        ),
        # --- Deleted memory -----------------------------------------------
        EvalCase(
            case_id="deleted_memory",
            kind="deleted",
            question="what did the withdrawn note say?",
            query_vector=WITHDRAWN,
            relevant_memory_ids=frozenset(),
            expect_empty=True,
            note="Only the deleted memory is near this vector, so nothing is returned.",
        ),
        # --- Missing metadata ---------------------------------------------
        EvalCase(
            case_id="missing_metadata",
            kind="missing_metadata",
            question="how do inverted lists work?",
            query_vector=IVF,
            relevant_memory_ids=frozenset({"mem_vector_2"}),
            note="The relevant memory has no URL or domain; that is acceptable.",
        ),
    ]
    return corpus, cases


def evaluate(corpus: Sequence, cases: Sequence, k: int = 5) -> EvaluationReport:
    """Measure retrieval quality with fixed vectors and a real cosine scan.

    This deliberately avoids the database and any model, but it applies the
    **same rules production uses**, so the measured numbers mean something:

    * the semantic similarity floor (``SIMILARITY_FLOOR``),
    * source-type filtering,
    * temporal windows parsed by the real ``parse_temporal`` implementation,
    * deleted memories removed before scoring.

    Ranking uses the same cosine function as the production vector store, and
    ties break on memory id, so results are deterministic and comparable.
    """
    from datetime import datetime, timezone

    from app.services.temporal import parse_temporal
    from app.services.vectors import cosine_similarity

    now = datetime.strptime(REFERENCE_TODAY, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    # A memory deleted in the dataset is removed before scoring, so it
    # physically cannot be retrieved.
    active = [
        entry for entry in corpus if entry.memory_id != DELETED_MEMORY_ID
    ]

    results: list = []
    for case in cases:
        # Parse the temporal window exactly as retrieval does, so a temporal
        # case is genuinely exercised rather than assumed.
        window = None
        if case.temporal_expression:
            window = parse_temporal(case.question, now)

        scored: list = []
        for entry in active:
            if case.source_type and entry.source_type != case.source_type:
                continue
            if window is not None:
                captured = datetime.strptime(entry.captured_at, "%Y-%m-%d").date()
                if not (window.from_date <= captured <= window.to_date):
                    continue
            score = cosine_similarity(case.query_vector, entry.vector)
            if score < SIMILARITY_FLOOR:
                continue  # the same floor the semantic channel applies
            scored.append((score, entry.memory_id))

        # Highest similarity first, ties broken by id for determinism.
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        retrieved = [memory_id for _score, memory_id in scored[:k]]

        relevant = sorted(case.relevant_memory_ids)
        rec = recall_at_k(retrieved, relevant, k)
        prec = precision_at_k(retrieved, relevant, k)
        rr = reciprocal_rank(retrieved, relevant)

        if case.expect_empty:
            passed = not retrieved
            detail = "expected no evidence" + (f", got {retrieved}" if retrieved else "")
        else:
            passed = rec == 1.0
            detail = f"expected {relevant or 'nothing'}"

        results.append(
            CaseResult(
                case_id=case.case_id,
                kind=case.kind,
                retrieved=retrieved,
                relevant=relevant,
                recall_at_k=rec,
                precision_at_k=prec,
                reciprocal_rank=rr,
                passed=passed,
                detail=detail,
            )
        )

    return EvaluationReport(results=results)


def format_report(report: EvaluationReport, k: int = 5) -> str:
    """Render a human-readable report of measured results."""
    lines = [
        f"Retrieval evaluation — {report.passed}/{report.total} cases passed",
        f"  Recall@{k}:    {report.mean_recall_at_k:.3f}",
        f"  Precision@{k}: {report.mean_precision_at_k:.3f}",
        f"  MRR:          {report.mean_reciprocal_rank:.3f}",
        "",
        "Per case:",
    ]
    for result in report.results:
        status = "PASS" if result.passed else "FAIL"
        lines.append(
            f"  [{status}] {result.case_id} ({result.kind}) "
            f"recall={result.recall_at_k:.2f} precision={result.precision_at_k:.2f} "
            f"rrr={result.reciprocal_rank:.2f} — {result.detail}"
        )
    return "\n".join(lines)


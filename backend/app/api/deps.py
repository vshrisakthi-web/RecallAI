"""Dependency wiring for the SQLite-backed ingestion and memory APIs."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import sessionmaker

from app.database.session import get_session_local
from app.repositories.base import IngestionRepository
from app.repositories.chunk_store import ChunkRepository
from app.repositories.sqlite_store import MemoryRepository
from app.repositories.vector_store import VectorStore
from app.services.hybrid import HybridRetrievalService
from app.services.indexing import IndexingService
from app.services.ingestion import IngestionService
from app.services.keyword_search import KeywordSearchService
from app.services.stt import TranscriptionService
from app.services.summarization import OllamaSummarizationService


def get_repository() -> IngestionRepository:
    """Return a repository backed by the configured local SQLite database."""
    return MemoryRepository(get_session_local())


def get_service(repo: IngestionRepository = Depends(get_repository)) -> IngestionService:
    return IngestionService(repo)


def get_summarization_service() -> OllamaSummarizationService:
    """Return the local Ollama summarization service (Task 5.6).

    The default provider is loopback-only and credential-free, so no memory
    text can leave the device. Exposed as a dependency so tests can substitute
    the provider boundary without any network access or a running model.
    """
    return OllamaSummarizationService()


def get_retrieval_service() -> HybridRetrievalService:
    """Return the hybrid retrieval service (Module 6, Tasks 6.5-6.6).

    Reads only the local SQLite database and calls the loopback-only embedding
    model; nothing is sent off-device. Exposed as a dependency so tests can
    substitute the whole retrieval boundary without a running model.
    """
    sessions = get_session_local()
    return HybridRetrievalService(
        memories=MemoryRepository(sessions),
        chunks=ChunkRepository(sessions),
        vectors=VectorStore(sessions),
        keywords=KeywordSearchService(sessions),
        sessions=sessions,
    )


def get_indexing_service() -> IndexingService:
    """Return the indexing service that builds chunks and vectors (Task 6.1-6.3).

    Exposed as a dependency so tests can substitute the embedding boundary.
    Indexing is deliberately separate from ingestion: it needs the local model,
    and saving a memory must never fail because the model is not installed.
    """
    sessions = get_session_local()
    return IndexingService(
        memories=MemoryRepository(sessions),
        chunks=ChunkRepository(sessions),
        vectors=VectorStore(sessions),
    )


def get_orchestrator(
    retrieval: HybridRetrievalService = Depends(get_retrieval_service),
):
    """Build the Task 76 workflow orchestrator with production deps.

    The analysis/task models default to loopback Ollama inside the
    agents; the router uses application settings. Exposed as a
    dependency so tests can substitute the whole orchestrator (or its
    retrieval boundary) without a running model.
    """
    from app.agents.orchestrator import Orchestrator
    from app.agents.routes.router import QueryRouter

    return Orchestrator(router=QueryRouter(), retrieval=retrieval)


def get_transcription_service() -> TranscriptionService:
    """Return the speech-to-text service (Module 9, Task 82).

    The service shells out to the isolated ``.venv-voice`` interpreter; its
    ``runner`` is injectable so tests substitute the subprocess entirely —
    no model is downloaded and no worker process is started in tests.
    """
    return TranscriptionService()


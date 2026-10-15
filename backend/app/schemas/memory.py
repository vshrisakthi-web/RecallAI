"""Response models for listing memories and inspecting their sources."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from app.schemas.common import CanonicalRecord


class MemoryListResponse(BaseModel):
    items: list[CanonicalRecord]
    page: int
    page_size: int
    total: int
    total_pages: int


class SourceResponse(BaseModel):
    id: str
    source_type: str
    url: Optional[str]
    domain: Optional[str]
    title: str
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    memory_count: int


class MemoryDetailResponse(BaseModel):
    memory: CanonicalRecord
    source: SourceResponse

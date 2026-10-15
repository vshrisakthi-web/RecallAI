"""Validated response shape for a generated memory summary."""

from pydantic import BaseModel, Field


class SummaryResult(BaseModel):
    summary: str = Field(min_length=1, max_length=4000)
    model: str


class MemorySummaryResponse(BaseModel):
    """Summary generated for one stored memory (Module 5, Task 5.5)."""

    memory_id: str
    summary: str
    model: str
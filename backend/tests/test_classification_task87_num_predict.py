"""Task 90 regression test: Task 87 output-contract fix (num_predict).

The frozen Task 87 baseline was generated with ``OllamaBackend.infer``
hard-coding ``options.num_predict = 8``. That value truncated the model
response before a single label token could be emitted, contributing to the
12/12 ``invalid_format`` results recorded in Task 87.

The verified defect is fixed by making the generation budget configurable via
``OllamaBackend(max_new_tokens=...)`` with a non-truncating default of 32.
These tests confirm the outgoing Ollama request carries the configured value
and that the default is no longer 8. They are fully offline: ``httpx.post`` is
monkeypatched, so no network, model, or Ollama server is required.

Scope note: a larger budget lets the model *finish* its response but does not
by itself make ``llama3.2:1b`` obey the prompt. This test only locks in the
config-plumbing fix; it does not re-run or replace the frozen Task 87 result.
"""

from __future__ import annotations

import httpx
import pytest

from app.services.classification import OllamaBackend


class _FakeResponse:
    """Minimal stand-in for an httpx response carrying an Ollama chat body."""

    def __init__(self, content: str = "BUG") -> None:
        self._content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"message": {"content": self._content}}


def _capture_post(monkeypatch, content: str = "BUG"):
    """Monkeypatch ``httpx.post`` to capture outgoing JSON and return a stub."""
    captured: dict = {}

    def fake_post(url, json=None, timeout=None):  # noqa: A002 - mirrors httpx API
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return _FakeResponse(content)

    monkeypatch.setattr(httpx, "post", fake_post)
    return captured


def test_default_max_new_tokens_is_not_truncating(monkeypatch):
    captured = _capture_post(monkeypatch)
    backend = OllamaBackend()
    assert backend.max_new_tokens == 32
    backend.infer("classify this")
    assert captured["json"]["options"]["num_predict"] == 32


def test_default_num_predict_is_no_longer_eight():
    # Regression guard: the old hard-coded truncating value must not return.
    assert OllamaBackend().max_new_tokens != 8


def test_configured_max_new_tokens_is_honored(monkeypatch):
    captured = _capture_post(monkeypatch)
    backend = OllamaBackend(max_new_tokens=128)
    backend.infer("classify this")
    assert captured["json"]["options"]["num_predict"] == 128


def test_request_shape_preserved(monkeypatch):
    captured = _capture_post(monkeypatch, content="TASK")
    backend = OllamaBackend(model="llama3.2:1b", timeout_seconds=45)
    out = backend.infer("hello")
    assert out == "TASK"
    assert captured["json"]["model"] == "llama3.2:1b"
    assert captured["json"]["stream"] is False
    assert captured["json"]["messages"] == [{"role": "user", "content": "hello"}]
    assert captured["json"]["options"]["temperature"] == 0
    assert captured["url"].endswith("/api/chat")
    assert captured["timeout"] == 45


def test_empty_response_raises(monkeypatch):
    _capture_post(monkeypatch, content="")
    backend = OllamaBackend()
    with pytest.raises(ValueError):
        backend.infer("classify this")

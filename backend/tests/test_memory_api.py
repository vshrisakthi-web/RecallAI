from datetime import datetime, timezone


def _browser(title, body, captured_at, url="https://docs.example/guide"):
    return {
        "id": title.lower().replace(" ", "-"),
        "title": title,
        "url": url,
        "domain": "docs.example" if "docs.example" in url else "audio.example",
        "capturedAt": captured_at.isoformat(),
        "captureType": "full-page",
        "extractedText": body,
        "status": "ok",
    }


def test_ingest_types_are_listed_searchable_and_paginated(client):
    captured = datetime(2026, 10, 10, 8, tzinfo=timezone.utc)
    browser = client.post(
        "/api/v1/ingest/browser",
        json=_browser("Searchable browser", "quartz indexing browser body", captured),
    )
    transcript = client.post(
        "/api/v1/ingest/transcript",
        json={
            "title": "Searchable transcript",
            "transcript": "quartz indexing transcript body",
            "source_url": "https://audio.example/episode",
            "captured_at": captured.isoformat(),
        },
    )
    note = client.post(
        "/api/v1/ingest/notes",
        json={"title": "Searchable note", "note": "quartz indexing personal body"},
    )

    assert [browser.status_code, transcript.status_code, note.status_code] == [201, 201, 201]
    all_records = client.get("/api/v1/memories").json()["items"]
    assert {record["source_type"] for record in all_records} == {"browser", "transcript", "note"}
    page_one = client.get(
        "/api/v1/memories",
        params={
            "q": "quartz",
            "from_date": "2026-10-10",
            "to_date": "2026-10-10",
            "domain": "DOCS.EXAMPLE.",
            "source_type": "browser",
            "page": 1,
            "page_size": 1,
        },
    )
    page_two = client.get(
        "/api/v1/memories", params={"q": "quartz", "source_type": "browser", "page": 2, "page_size": 1}
    )

    assert page_one.status_code == 200
    assert page_one.json()["total"] == 1
    assert page_one.json()["items"][0]["title"] == "Searchable browser"
    assert page_one.json()["total_pages"] == 1
    assert page_two.json()["items"] == []


def test_detail_source_and_safe_delete(client):
    created = client.post(
        "/api/v1/ingest/browser",
        json=_browser(
            "Page version one",
            "source inspection text",
            datetime(2026, 10, 10, 8, tzinfo=timezone.utc),
        ),
    )
    memory_id = created.json()["record_id"]
    source_id = created.json()["record"]["source_id"]

    detail = client.get(f"/api/v1/memories/{memory_id}")
    source = client.get(f"/api/v1/sources/{source_id}")
    assert detail.status_code == 200
    assert detail.json()["memory"]["normalized_text"] == "source inspection text"
    assert detail.json()["source"]["url"] == "https://docs.example/guide"
    assert source.json()["memory_count"] == 1

    deleted = client.delete(f"/api/v1/memories/{memory_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert deleted.headers["X-Request-ID"] == deleted.json()["request_id"]
    assert client.get("/api/v1/memories", params={"q": "inspection"}).json()["total"] == 0
    assert client.get(f"/api/v1/sources/{source_id}").json()["memory_count"] == 0


def test_same_source_can_be_used_by_multiple_memories(client):
    timestamp = datetime(2026, 10, 10, 8, tzinfo=timezone.utc)
    first = client.post("/api/v1/ingest/browser", json=_browser("First", "first body", timestamp))
    second = client.post("/api/v1/ingest/browser", json=_browser("Second", "second body", timestamp))
    source_id = first.json()["record"]["source_id"]

    assert first.status_code == second.status_code == 201
    assert second.json()["record"]["source_id"] == source_id
    assert client.get(f"/api/v1/sources/{source_id}").json()["memory_count"] == 2


def test_missing_memory_source_and_invalid_filters_use_error_envelope(client):
    missing_memory = client.get("/api/v1/memories/does-not-exist")
    missing_source = client.get("/api/v1/sources/does-not-exist")
    invalid_date_range = client.get(
        "/api/v1/memories", params={"from_date": "2026-10-11", "to_date": "2026-10-10"}
    )
    invalid_domain = client.get("/api/v1/memories", params={"domain": "https://example.com"})
    invalid_source_type = client.get("/api/v1/memories", params={"source_type": "unknown"})
    invalid_page_size = client.get("/api/v1/memories", params={"page_size": 0})

    assert missing_memory.status_code == 404
    assert missing_source.status_code == 404
    assert missing_memory.json()["error"]["code"] == "NOT_FOUND"
    assert invalid_date_range.status_code == 422
    assert invalid_domain.status_code == 422
    assert invalid_source_type.status_code == 422
    assert invalid_page_size.status_code == 422
    for response in (
        missing_memory,
        missing_source,
        invalid_date_range,
        invalid_domain,
        invalid_source_type,
        invalid_page_size,
    ):
        assert response.headers["X-Request-ID"]
        assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]

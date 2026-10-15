"""Unit tests for the JSON-file repository (Module 3, Tasks 3.6, 3.13)."""

from app.repositories.json_store import JsonFileRepository, dedup_key_of
from tests._factories import make_record


def new_repo(tmp_path):
    return JsonFileRepository(str(tmp_path / "store.json"))


def test_save_new_record(tmp_path):
    repo = new_repo(tmp_path)
    rec, duplicate = repo.save_or_get(make_record(id="a", _text="alpha body"))
    assert duplicate is False
    assert rec.id == "a"
    assert repo.count() == 1


def test_identical_content_is_duplicate(tmp_path):
    repo = new_repo(tmp_path)
    repo.save_or_get(make_record(id="a", _text="same body"))
    rec2, duplicate = repo.save_or_get(make_record(id="b", _text="same body"))
    assert duplicate is True
    assert repo.count() == 1
    # The pre-existing record is returned.
    assert rec2.id == "a"


def test_changed_content_same_url_is_not_duplicate(tmp_path):
    repo = new_repo(tmp_path)
    repo.save_or_get(
        make_record(id="a", _text="first body", source_url="https://x.test/p", source_type="browser", capture_type="full-page")
    )
    rec2, duplicate = repo.save_or_get(
        make_record(id="b", _text="second body", source_url="https://x.test/p", source_type="browser", capture_type="full-page")
    )
    assert duplicate is False
    assert repo.count() == 2


def test_selection_vs_full_page_are_distinct(tmp_path):
    repo = new_repo(tmp_path)
    repo.save_or_get(
        make_record(id="a", _text="same", source_url="https://x.test/p", source_type="browser", capture_type="full-page")
    )
    rec2, duplicate = repo.save_or_get(
        make_record(id="b", _text="same", source_url="https://x.test/p", source_type="browser", capture_type="selection")
    )
    assert duplicate is False
    assert repo.count() == 2


def test_persists_across_restart(tmp_path):
    path = str(tmp_path / "store.json")
    JsonFileRepository(path).save_or_get(make_record(id="a", _text="persisted body"))
    # A brand-new repository instance on the same file (simulates a restart).
    repo2 = JsonFileRepository(path)
    assert repo2.count() == 1
    assert repo2.get_by_id("a") is not None


def test_id_collision_with_different_content_gets_new_id(tmp_path):
    repo = new_repo(tmp_path)
    repo.save_or_get(make_record(id="dup", _text="body one"))
    rec2, duplicate = repo.save_or_get(make_record(id="dup", _text="body two"))
    assert duplicate is False
    assert rec2.id != "dup"  # minted a fresh id rather than clobbering
    assert repo.count() == 2


def test_get_by_id_missing(tmp_path):
    repo = new_repo(tmp_path)
    assert repo.get_by_id("nope") is None


def test_list_recent_is_newest_first(tmp_path):
    repo = new_repo(tmp_path)
    repo.save_or_get(make_record(id="old", _text="old body"))
    repo.save_or_get(make_record(id="new", _text="new body"))
    recent = repo.list_recent(10)
    assert [r.id for r in recent] == ["new", "old"]


def test_dedup_key_ignores_title(tmp_path):
    a = make_record(id="a", _text="body", title="Title A")
    b = make_record(id="b", _text="body", title="Title B")
    # Same source_type/url/capture_type/hash (title excluded) -> same key.
    assert dedup_key_of(a) == dedup_key_of(b)

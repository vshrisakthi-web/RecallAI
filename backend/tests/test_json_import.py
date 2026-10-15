import json

import pytest

from app.scripts.import_json import import_json_file
from tests._factories import make_record


def test_json_import_reports_invalid_duplicates_and_preserves_source(tmp_path, repository):
    first = make_record(id="legacy-one", _text="legacy import body")
    retry = make_record(id="legacy-two", _text="legacy import body")
    source_path = tmp_path / "legacy.json"
    source_path.write_text(
        json.dumps(
            {
                "records": [
                    first.model_dump(mode="json"),
                    retry.model_dump(mode="json"),
                    {"id": "invalid"},
                ]
            }
        ),
        encoding="utf-8",
    )
    original = source_path.read_bytes()

    result = import_json_file(str(source_path), repository)
    rerun = import_json_file(str(source_path), repository)

    assert result == {"read": 3, "imported": 1, "duplicates": 1, "skipped": 1}
    assert rerun == {"read": 3, "imported": 0, "duplicates": 2, "skipped": 1}
    assert source_path.read_bytes() == original
    assert repository.count() == 1


def test_json_import_rejects_unexpected_top_level_shape(tmp_path, repository):
    source_path = tmp_path / "invalid.json"
    source_path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="records array"):
        import_json_file(str(source_path), repository)

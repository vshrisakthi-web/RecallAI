"""Explicit, repeatable import of Module 3 JSON records into SQLite."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from app.core.config import settings
from app.database.session import get_session_local
from app.repositories.base import StorageError
from app.repositories.sqlite_store import MemoryRepository
from app.schemas.common import CanonicalRecord


def import_json_file(path: str, repository: MemoryRepository) -> dict[str, int]:
    """Import valid records without changing or deleting the JSON source file."""
    source_path = Path(path)
    with source_path.open("r", encoding="utf-8") as source_file:
        payload = json.load(source_file)
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise ValueError("JSON store must contain a top-level records array")

    result = {"read": len(payload["records"]), "imported": 0, "duplicates": 0, "skipped": 0}
    for raw_record in payload["records"]:
        try:
            record = CanonicalRecord.model_validate(raw_record)
        except Exception:
            result["skipped"] += 1
            continue
        try:
            _, duplicate = repository.save_or_get(record)
        except StorageError:
            raise
        if duplicate:
            result["duplicates"] += 1
        else:
            result["imported"] += 1
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json-file",
        default=settings.storage_path,
        help="JSON source path (defaults to RECALLAI_STORAGE_PATH)",
    )
    args = parser.parse_args()
    repository = MemoryRepository(get_session_local())
    try:
        result = import_json_file(args.json_file, repository)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

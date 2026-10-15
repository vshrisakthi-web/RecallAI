import pytest

from app.core.config import Settings, _non_empty_env, _positive_int_env


def test_gemini_configuration_uses_model_and_bounds_without_requiring_a_key():
    settings = Settings(
        gemini_api_key=None,
        gemini_model="gemini-3.8-flash",
        gemini_timeout_seconds=30,
        max_summary_input_chars=30_000,
    )

    assert settings.gemini_model == "gemini-3.8-flash"
    assert settings.gemini_timeout_seconds == 30
    assert settings.max_summary_input_chars == 30_000
    with pytest.raises(RuntimeError, match="RECALLAI_GEMINI_API_KEY"):
        settings.require_gemini_api_key()


def test_gemini_key_is_available_only_from_backend_settings_and_redacted():
    test_key = "test-key-not-a-real-credential"
    settings = Settings(gemini_api_key=test_key)

    assert settings.require_gemini_api_key() == test_key
    assert test_key not in repr(settings)


def test_gemini_values_are_read_from_backend_environment(monkeypatch):
    monkeypatch.setenv("RECALLAI_GEMINI_API_KEY", "test-env-key")
    monkeypatch.setenv("RECALLAI_GEMINI_MODEL", "gemini-3.8-flash")
    monkeypatch.setenv("RECALLAI_GEMINI_TIMEOUT_SECONDS", "45")

    settings = Settings()

    assert settings.gemini_api_key == "test-env-key"
    assert settings.gemini_model == "gemini-3.8-flash"
    assert settings.gemini_timeout_seconds == 45


def test_empty_model_is_rejected(monkeypatch):
    monkeypatch.setenv("RECALLAI_GEMINI_MODEL", "   ")

    with pytest.raises(ValueError, match="RECALLAI_GEMINI_MODEL must not be empty"):
        _non_empty_env("RECALLAI_GEMINI_MODEL", "gemini-3.8-flash")


@pytest.mark.parametrize(
    ("raw_value", "maximum"),
    [("not-a-number", 120), ("0", 120), ("121", 120)],
)
def test_positive_summarization_limits_reject_invalid_values(monkeypatch, raw_value, maximum):
    monkeypatch.setenv("RECALLAI_TEST_LIMIT", raw_value)

    with pytest.raises(ValueError, match="RECALLAI_TEST_LIMIT must be an integer"):
        _positive_int_env("RECALLAI_TEST_LIMIT", 30, maximum)

from jamescore.presentation.presenter import ResponsePresenter
from jamescore.settings import Settings


def test_presenter_model_prefers_presenter_then_deepseek(monkeypatch):
    monkeypatch.setattr("jamescore.settings._hydrate_presenter_secrets", lambda: None)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-flash")
    monkeypatch.delenv("PRESENTER_MODEL", raising=False)
    monkeypatch.delenv("PRESENTER_API_KEY", raising=False)
    settings = Settings.from_env()
    assert settings.presenter_model == "deepseek-flash"
    assert settings.presenter_api_key == "sk-test"


def test_presenter_model_explicit_override(monkeypatch):
    monkeypatch.setattr("jamescore.settings._hydrate_presenter_secrets", lambda: None)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-flash")
    monkeypatch.setenv("PRESENTER_MODEL", "deepseek-chat")
    settings = Settings.from_env()
    assert settings.presenter_model == "deepseek-chat"


def test_health_snapshot_reports_config_without_llm_call(monkeypatch):
    monkeypatch.setattr("jamescore.settings._hydrate_presenter_secrets", lambda: None)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-flash")
    monkeypatch.delenv("PRESENTER_MODEL", raising=False)
    settings = Settings.from_env()
    presenter = ResponsePresenter.from_settings(settings)
    snap = presenter.health_snapshot()
    assert snap["credentials_present"] is True
    assert snap["model"] == "deepseek-flash"
    assert snap["configured"] is True
    assert snap["available"] is True


def test_health_snapshot_detects_missing_credentials():
    presenter = ResponsePresenter(
        None,
        enabled=False,
        model="deepseek-flash",
        base_url="https://api.deepseek.com",
        credentials_present=False,
    )
    snap = presenter.health_snapshot()
    assert snap["available"] is False
    assert snap["credentials_present"] is False
    assert snap["model"] == "deepseek-flash"
    assert snap["configured"] is False

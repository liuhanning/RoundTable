import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web.app import create_app  # noqa: E402
from web.services.attachment_service import AttachmentService  # noqa: E402
from web.services.config_store import ConfigStore  # noqa: E402
from engine.session_store import SessionStore  # noqa: E402


class DummyTaskRunner:
    def __init__(self):
        self.started = []

    def start_session(self, manifest):
        self.started.append(manifest.session_id)

    def is_running(self, session_id):
        return False


def build_client(tmp_path):
    config_store = ConfigStore(
        env_path=str(tmp_path / ".env"),
        settings_path=str(tmp_path / "settings.json"),
    )
    session_store = SessionStore(base_dir=str(tmp_path / "sessions"))
    app = create_app(
        config_store=config_store,
        session_store=session_store,
        attachment_service=AttachmentService(base_dir=str(tmp_path / "uploads")),
        task_runner=DummyTaskRunner(),
    )
    return TestClient(app), config_store


def test_get_settings_returns_provider_states_and_models(tmp_path):
    client, _ = build_client(tmp_path)

    response = client.get("/api/settings")

    assert response.status_code == 200
    payload = response.json()
    assert "providers" in payload
    assert "enabled_models" in payload


def test_save_secret_masks_return_value(tmp_path):
    client, _ = build_client(tmp_path)

    response = client.post("/api/settings/secrets", json={"provider": "gemini", "api_key": "sk-1234567890"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is True
    assert payload["masked_value"].startswith("sk-1")
    assert "1234567890" not in payload["masked_value"]


def test_save_enabled_models_updates_settings(tmp_path):
    client, config_store = build_client(tmp_path)

    response = client.post(
        "/api/settings/models",
        json={"enabled_models": {"gemini-2.5-flash": False, "custom-model": True}},
    )

    assert response.status_code == 200
    settings = config_store.load_settings()
    assert settings["enabled_models"]["gemini-2.5-flash"] is False
    assert settings["enabled_models"]["custom-model"] is True

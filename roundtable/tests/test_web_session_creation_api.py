import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.session_store import SessionStore  # noqa: E402
from web.app import create_app  # noqa: E402
from web.services.attachment_service import AttachmentService  # noqa: E402
from web.services.config_store import ConfigStore  # noqa: E402


class DummyTaskRunner:
    def start_session(self, manifest):
        return manifest.session_id

    def is_running(self, session_id):
        return False


def build_client(tmp_path):
    config_store = ConfigStore(
        env_path=str(tmp_path / ".env"),
        settings_path=str(tmp_path / "settings.json"),
    )
    config_store.update_enabled_models(
        {
            "gemini-2.5-flash": True,
            "openrouter/deepseek/deepseek-chat-v3-0324:free": True,
        }
    )
    app = create_app(
        config_store=config_store,
        session_store=SessionStore(base_dir=str(tmp_path / "sessions")),
        attachment_service=AttachmentService(base_dir=str(tmp_path / "uploads")),
        task_runner=DummyTaskRunner(),
    )
    return TestClient(app)


def test_create_draft_session_persists_manifest_and_status(tmp_path):
    client = build_client(tmp_path)

    response = client.post(
        "/api/sessions",
        json={
            "title": "Transport Review",
            "project_name": "Guizhou",
            "task_description": "Assess transport priorities",
            "roles": [
                {
                    "role_id": "planner",
                    "enabled": True,
                    "display_name": "Planner",
                    "responsibility": "Plan",
                    "instruction": "Be structured",
                    "model": "gemini-2.5-flash",
                }
            ],
            "attachment_ids": [],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "draft"
    assert payload["session_id"]


def test_create_session_rejects_disabled_model(tmp_path):
    client = build_client(tmp_path)

    response = client.post(
        "/api/sessions",
        json={
            "title": "Transport Review",
            "project_name": "Guizhou",
            "task_description": "Assess transport priorities",
            "roles": [
                {
                    "role_id": "planner",
                    "enabled": True,
                    "display_name": "Planner",
                    "responsibility": "Plan",
                    "instruction": "Be structured",
                    "model": "disabled-model",
                }
            ],
            "attachment_ids": [],
        },
    )

    assert response.status_code == 400
    assert "disabled" in response.json()["detail"]

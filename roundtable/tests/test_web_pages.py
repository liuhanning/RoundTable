import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.session_store import SessionStore  # noqa: E402
from engine.structures import SessionManifest, SessionStatus, SessionStatusType  # noqa: E402
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
    session_store = SessionStore(base_dir=str(tmp_path / "sessions"))
    app = create_app(
        config_store=config_store,
        session_store=session_store,
        attachment_service=AttachmentService(base_dir=str(tmp_path / "uploads")),
        task_runner=DummyTaskRunner(),
    )
    return TestClient(app), session_store


def test_settings_page_is_reachable(tmp_path):
    client, _ = build_client(tmp_path)

    response = client.get("/settings")

    assert response.status_code == 200
    assert "Provider 密钥" in response.text
    assert "启用模型" in response.text


def test_new_session_page_contains_form_fields(tmp_path):
    client, _ = build_client(tmp_path)

    response = client.get("/sessions/new")

    assert response.status_code == 200
    assert "会话标题" in response.text
    assert "任务描述" in response.text
    assert "角色模板" in response.text


def test_session_detail_page_renders_status_and_report(tmp_path):
    client, session_store = build_client(tmp_path)
    report_path = tmp_path / "output" / "report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("# Ready", encoding="utf-8")

    session_store.save_manifest(
        SessionManifest(
            session_id="session-001",
            title="Transport Review",
            project_name="Guizhou",
            task_description="Assess transport priorities",
        )
    )
    session_store.save_status(
        SessionStatus(
            session_id="session-001",
            status=SessionStatusType.FAILED,
            current_stage="summary",
            error_summary="provider offline",
            next_action="retry",
            report_path=str(report_path),
        )
    )

    response = client.get("/sessions/session-001")

    assert response.status_code == 200
    assert "执行状态" in response.text
    assert "provider offline" in response.text
    assert "# Ready" in response.text

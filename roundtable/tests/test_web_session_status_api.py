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
    def is_running(self, session_id):
        return False

    def start_session(self, manifest):
        return manifest.session_id


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


def seed_session(session_store, tmp_path, session_id="session-001", status_value=SessionStatusType.COMPLETED):
    manifest = SessionManifest(
        session_id=session_id,
        title="Transport Review",
        project_name="Guizhou",
        task_description="Assess transport priorities",
    )
    report_path = tmp_path / "output" / "report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("# Report", encoding="utf-8")
    status = SessionStatus(
        session_id=session_id,
        status=status_value,
        current_stage=None,
        completed_stages=["independent", "blue_team"],
        report_path=str(report_path),
    )
    session_store.save_manifest(manifest)
    session_store.save_status(status)


def test_list_sessions_returns_summary_fields_only(tmp_path):
    client, session_store = build_client(tmp_path)
    seed_session(session_store, tmp_path)

    response = client.get("/api/sessions")

    assert response.status_code == 200
    payload = response.json()[0]
    assert set(payload.keys()) == {
        "session_id",
        "title",
        "status",
        "current_stage",
        "last_stage",
        "updated_at",
        "report_path",
    }


def test_get_session_detail_returns_manifest_status_and_report(tmp_path):
    client, session_store = build_client(tmp_path)
    seed_session(session_store, tmp_path, session_id="session-abc")

    response = client.get("/api/sessions/session-abc")

    assert response.status_code == 200
    payload = response.json()
    assert payload["manifest"]["title"] == "Transport Review"
    assert payload["status"]["status"] == "completed"
    assert "# Report" in payload["report_markdown"]

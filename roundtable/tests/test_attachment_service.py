import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.session_store import SessionStore  # noqa: E402
from utils.file_validator import FileUploadValidationError  # noqa: E402
from web.app import create_app  # noqa: E402
from web.services.attachment_service import AttachmentService  # noqa: E402
from web.services.config_store import ConfigStore  # noqa: E402


class DummyTaskRunner:
    def start_session(self, manifest):
        return manifest.session_id

    def is_running(self, session_id):
        return False


class TestAttachmentService:
    def test_txt_attachment_is_embedded_with_safe_context(self, tmp_path):
        service = AttachmentService(base_dir=str(tmp_path / "uploads"))

        record = service.save_upload("notes.txt", "hello world".encode("utf-8"))

        assert record.injection_mode == "embedded"
        assert record.extraction_status == "ready"
        context_path = tmp_path / "uploads" / record.attachment_id / "context.txt"
        assert context_path.exists()
        assert "hello world" in context_path.read_text(encoding="utf-8")

    def test_xlsx_attachment_is_listed_only(self, tmp_path):
        service = AttachmentService(base_dir=str(tmp_path / "uploads"))
        xlsx_bytes = b"PK\x03\x04fake-xlsx"

        record = service.save_upload("sheet.xlsx", xlsx_bytes)

        assert record.injection_mode == "listed_only"
        assert record.extraction_status == "skipped"

    def test_invalid_attachment_type_is_rejected(self, tmp_path):
        service = AttachmentService(base_dir=str(tmp_path / "uploads"))

        with pytest.raises(FileUploadValidationError):
            service.save_upload("malware.exe", b"MZ")


def test_attachment_api_returns_400_for_invalid_magic_bytes(tmp_path):
    config_store = ConfigStore(
        env_path=str(tmp_path / ".env"),
        settings_path=str(tmp_path / "settings.json"),
    )
    app = create_app(
        config_store=config_store,
        session_store=SessionStore(base_dir=str(tmp_path / "sessions")),
        attachment_service=AttachmentService(base_dir=str(tmp_path / "uploads")),
        task_runner=DummyTaskRunner(),
    )
    client = TestClient(app)

    response = client.post(
        "/api/attachments",
        files={
            "file": (
                "broken.xlsx",
                io.BytesIO(b"not-a-real-xlsx"),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 400
    assert "内容验证失败" in response.json()["detail"]

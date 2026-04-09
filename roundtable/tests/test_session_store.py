import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.session_store import SessionStore  # noqa: E402
from engine.structures import (  # noqa: E402
    AttachmentRecord,
    RoleConfig,
    SessionManifest,
    SessionStatus,
    SessionStatusType,
)


def build_manifest(session_id: str, title: str) -> SessionManifest:
    return SessionManifest(
        session_id=session_id,
        title=title,
        project_name="贵州十五五",
        task_description="请分析重点方向",
        roles=[
            RoleConfig(
                role_id="planner",
                display_name="规划师",
                responsibility="负责规划",
                instruction="请给出结构化建议",
                model="gemini-2.5-flash",
            )
        ],
        attachments=[
            AttachmentRecord(
                attachment_id=f"att-{session_id}",
                filename="report.pdf",
                extension=".pdf",
                size_bytes=1024,
                stored_path=f"data/sessions/{session_id}/attachments/report.pdf",
                injection_mode="embedded",
                extraction_status="ready",
            )
        ],
    )


def build_status(session_id: str, status: SessionStatusType, updated_at: str) -> SessionStatus:
    return SessionStatus(
        session_id=session_id,
        status=status,
        current_stage="blue_team" if status != SessionStatusType.DRAFT else None,
        completed_stages=["independent"] if status != SessionStatusType.DRAFT else [],
        stage_summaries={"independent": {"summary": "阶段完成"}} if status != SessionStatusType.DRAFT else {},
        updated_at=updated_at,
    )


class TestSessionStore:
    def test_save_and_load_manifest(self, tmp_path):
        store = SessionStore(base_dir=str(tmp_path / "sessions"))
        manifest = build_manifest("session-001", "交通规划讨论")

        store.save_manifest(manifest)
        loaded = store.load_manifest("session-001")

        assert loaded is not None
        assert loaded.session_id == "session-001"
        assert loaded.title == "交通规划讨论"
        assert loaded.roles[0].display_name == "规划师"

    def test_save_and_load_status(self, tmp_path):
        store = SessionStore(base_dir=str(tmp_path / "sessions"))
        status = build_status(
            "session-001",
            SessionStatusType.RUNNING,
            "2026-04-01T10:00:00+00:00",
        )

        store.save_status(status)
        loaded = store.load_status("session-001")

        assert loaded is not None
        assert loaded.status == SessionStatusType.RUNNING
        assert loaded.current_stage == "blue_team"

    def test_load_session_returns_manifest_and_status(self, tmp_path):
        store = SessionStore(base_dir=str(tmp_path / "sessions"))
        manifest = build_manifest("session-001", "交通规划讨论")
        status = build_status(
            "session-001",
            SessionStatusType.COMPLETED,
            "2026-04-01T12:00:00+00:00",
        )

        store.save_manifest(manifest)
        store.save_status(status)
        session = store.load_session("session-001")

        assert session["manifest"] is not None
        assert session["status"] is not None
        assert session["status"].status == SessionStatusType.COMPLETED

    def test_list_sessions_sorted_by_updated_at_desc(self, tmp_path):
        store = SessionStore(base_dir=str(tmp_path / "sessions"))

        store.save_manifest(build_manifest("session-001", "较早会话"))
        store.save_status(build_status(
            "session-001",
            SessionStatusType.COMPLETED,
            "2026-04-01T09:00:00+00:00",
        ))

        store.save_manifest(build_manifest("session-002", "较晚会话"))
        store.save_status(build_status(
            "session-002",
            SessionStatusType.RUNNING,
            "2026-04-01T10:00:00+00:00",
        ))

        sessions = store.list_sessions()
        assert len(sessions) == 2
        assert sessions[0]["session_id"] == "session-002"
        assert sessions[1]["session_id"] == "session-001"
        assert sessions[0]["title"] == "较晚会话"

    def test_list_sessions_skips_incomplete_session_files(self, tmp_path):
        store = SessionStore(base_dir=str(tmp_path / "sessions"))
        store.save_manifest(build_manifest("session-001", "只有 manifest"))

        sessions = store.list_sessions()
        assert sessions == []

    def test_missing_files_return_none(self, tmp_path):
        store = SessionStore(base_dir=str(tmp_path / "sessions"))

        assert store.load_manifest("missing") is None
        assert store.load_status("missing") is None

    def test_mark_interrupted_sessions_updates_running_and_queued(self, tmp_path):
        store = SessionStore(base_dir=str(tmp_path / "sessions"))

        store.save_manifest(build_manifest("running-session", "运行中会话"))
        store.save_status(build_status(
            "running-session",
            SessionStatusType.RUNNING,
            "2026-04-01T09:00:00+00:00",
        ))

        store.save_manifest(build_manifest("queued-session", "排队会话"))
        store.save_status(build_status(
            "queued-session",
            SessionStatusType.QUEUED,
            "2026-04-01T09:30:00+00:00",
        ))

        store.save_manifest(build_manifest("completed-session", "已完成会话"))
        store.save_status(build_status(
            "completed-session",
            SessionStatusType.COMPLETED,
            "2026-04-01T10:00:00+00:00",
        ))

        updated = store.mark_interrupted_sessions()

        assert sorted(updated) == ["queued-session", "running-session"]
        assert store.load_status("running-session").status == SessionStatusType.INTERRUPTED
        assert store.load_status("queued-session").status == SessionStatusType.INTERRUPTED
        assert store.load_status("completed-session").status == SessionStatusType.COMPLETED

    def test_mark_interrupted_sets_next_action_when_missing(self, tmp_path):
        store = SessionStore(base_dir=str(tmp_path / "sessions"))
        store.save_manifest(build_manifest("running-session", "运行中会话"))
        store.save_status(build_status(
            "running-session",
            SessionStatusType.RUNNING,
            "2026-04-01T09:00:00+00:00",
        ))

        store.mark_interrupted_sessions()
        loaded = store.load_status("running-session")

        assert loaded is not None
        assert loaded.next_action is not None
        assert "中断" in loaded.next_action

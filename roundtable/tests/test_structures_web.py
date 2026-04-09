import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.structures import (  # noqa: E402
    AttachmentRecord,
    ProviderSecretState,
    RoleConfig,
    SessionManifest,
    SessionStatus,
    SessionStatusType,
)


class TestWebStructures:
    def test_role_config_round_trip(self):
        role = RoleConfig(
            role_id="planner",
            enabled=True,
            display_name="规划师",
            responsibility="负责结构化分析",
            instruction="先总结后判断",
            model="gemini-2.5-flash",
        )

        restored = RoleConfig.from_dict(role.to_dict())
        assert restored.role_id == "planner"
        assert restored.display_name == "规划师"
        assert restored.model == "gemini-2.5-flash"

    def test_attachment_record_round_trip(self):
        attachment = AttachmentRecord(
            attachment_id="att-001",
            filename="report.pdf",
            extension=".pdf",
            size_bytes=1024,
            stored_path="data/sessions/s1/attachments/report.pdf",
            injection_mode="embedded",
            extraction_status="ready",
        )

        restored = AttachmentRecord.from_dict(attachment.to_dict())
        assert restored.attachment_id == "att-001"
        assert restored.injection_mode == "embedded"
        assert restored.extraction_status == "ready"

    def test_provider_secret_state_round_trip(self):
        provider = ProviderSecretState(
            provider="gemini",
            configured=True,
            masked_value="sk-****abcd",
            connection_status="ok",
            last_checked_at="2026-04-01T10:00:00+00:00",
        )

        restored = ProviderSecretState.from_dict(provider.to_dict())
        assert restored.provider == "gemini"
        assert restored.configured is True
        assert restored.masked_value == "sk-****abcd"

    def test_session_manifest_round_trip(self):
        manifest = SessionManifest(
            session_id="session-001",
            title="交通规划讨论",
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
                    attachment_id="att-001",
                    filename="report.pdf",
                    extension=".pdf",
                    size_bytes=1024,
                    stored_path="data/sessions/session-001/attachments/report.pdf",
                    injection_mode="embedded",
                    extraction_status="ready",
                )
            ],
            model_snapshot={"gemini-2.5-flash": True},
            settings_snapshot={"enabled_models": {"gemini-2.5-flash": True}},
            execution_snapshot={"providers": {"gemini": {"configured": True}}},
        )

        restored = SessionManifest.from_dict(manifest.to_dict())
        assert restored.session_id == "session-001"
        assert len(restored.roles) == 1
        assert restored.roles[0].role_id == "planner"
        assert len(restored.attachments) == 1
        assert restored.attachments[0].filename == "report.pdf"
        assert restored.execution_snapshot["providers"]["gemini"]["configured"] is True

    def test_session_status_round_trip(self):
        status = SessionStatus(
            session_id="session-001",
            status=SessionStatusType.RUNNING,
            current_stage="blue_team",
            completed_stages=["independent"],
            stage_summaries={"independent": {"summary": "阶段完成"}},
            report_path="output/guizhou/final_report.md",
        )

        restored = SessionStatus.from_dict(status.to_dict())
        assert restored.session_id == "session-001"
        assert restored.status == SessionStatusType.RUNNING
        assert restored.current_stage == "blue_team"
        assert restored.completed_stages == ["independent"]

    def test_session_status_invalid_value_falls_back_to_draft(self):
        restored = SessionStatus.from_dict({
            "session_id": "session-001",
            "status": "unknown-status",
        })
        assert restored.status == SessionStatusType.DRAFT

    def test_session_status_enum_values(self):
        assert SessionStatusType.DRAFT.value == "draft"
        assert SessionStatusType.QUEUED.value == "queued"
        assert SessionStatusType.RUNNING.value == "running"
        assert SessionStatusType.COMPLETED.value == "completed"
        assert SessionStatusType.FAILED.value == "failed"
        assert SessionStatusType.INTERRUPTED.value == "interrupted"

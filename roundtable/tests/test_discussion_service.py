import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.discussion_service import DiscussionService  # noqa: E402
from engine.models import ModelProvider, ModelResponse  # noqa: E402
from engine.session_store import SessionStore  # noqa: E402


class FakeModelClient:
    def __init__(self):
        self.fallback_chain = [ModelProvider.GEMINI, ModelProvider.OPENROUTER]
        self.retry_config = type(
            "RetryConfig",
            (),
            {
                "max_retries": 3,
                "initial_delay": 1.0,
                "backoff_multiplier": 2.0,
                "max_delay": 30.0,
            },
        )()

    async def call_parallel(self, prompts):
        return [
            ModelResponse(
                content=f"Independent opinion {index + 1}",
                model=prompt["provider"],
                provider=ModelProvider(prompt["provider"]),
                tokens_in=10,
                tokens_out=20,
                cost_usd=0.01,
            )
            for index, prompt in enumerate(prompts)
        ]

    async def call(self, prompt):
        return ModelResponse(
            content=f"Summary response for: {prompt[:20]}",
            model="gemini-2.5-flash",
            provider=ModelProvider.GEMINI,
            tokens_in=12,
            tokens_out=34,
            cost_usd=0.02,
        )


class FakeBlueTeam:
    async def challenge(self, independent_outputs, session_id):
        class Report:
            critical_issues = [{"id": "C1"}]
            high_risks = []
            medium_assumptions = []

            def to_dict(self):
                return {
                    "session_id": session_id,
                    "stage": "blue_team_challenge",
                    "critical_issues": self.critical_issues,
                    "high_risks": self.high_risks,
                    "medium_assumptions": self.medium_assumptions,
                    "passed": True,
                    "recommendations": [],
                    "total_issues": 1,
                }

        return Report()


class FakeCostTracker:
    def __init__(self):
        self.records = []

    def record_call(self, **kwargs):
        self.records.append(kwargs)
        return self.get_budget_status(kwargs["session_id"])

    def get_budget_status(self, session_id):
        spent = sum(item["cost_usd"] for item in self.records if item["session_id"] == session_id)
        return {
            "session_id": session_id,
            "total_budget": 0.50,
            "spent": spent,
            "remaining": 0.50 - spent,
            "usage_percent": spent / 0.50 * 100 if spent else 0,
        }


@pytest.mark.asyncio
async def test_run_discussion_persists_manifest_status_and_outputs(tmp_path):
    session_store = SessionStore(base_dir=str(tmp_path / "sessions"))
    from engine.checkpoint import CheckpointManager

    service = DiscussionService(
        checkpoint_manager=CheckpointManager(base_dir=str(tmp_path / "checkpoints")),
        cost_tracker=FakeCostTracker(),
        model_client=FakeModelClient(),
        blue_team=FakeBlueTeam(),
        session_store=session_store,
        output_root=str(tmp_path / "output"),
    )

    result = await service.run_discussion(
        topic="贵州交通规划",
        project_name="guizhou-project",
        session_id="session-001",
        created_from="cli",
    )

    manifest = session_store.load_manifest("session-001")
    status = session_store.load_status("session-001")

    assert result.session_id == "session-001"
    assert manifest is not None
    assert manifest.project_name == "guizhou-project"
    assert manifest.execution_snapshot["fallback_chain"] == ["gemini", "openrouter"]
    assert status is not None
    assert status.status.value == "completed"
    assert status.completed_stages == ["independent", "blue_team", "summary", "report"]
    assert Path(result.report_path).exists()
    assert Path(result.report_json_path).exists()
    assert session_store.list_sessions()[0]["report_path"] == result.report_path


@pytest.mark.asyncio
async def test_run_discussion_marks_failed_status_when_stage_errors(tmp_path):
    class FailingModelClient(FakeModelClient):
        async def call_parallel(self, prompts):
            raise RuntimeError("provider offline")

    session_store = SessionStore(base_dir=str(tmp_path / "sessions"))
    from engine.checkpoint import CheckpointManager

    service = DiscussionService(
        checkpoint_manager=CheckpointManager(base_dir=str(tmp_path / "checkpoints")),
        cost_tracker=FakeCostTracker(),
        model_client=FailingModelClient(),
        blue_team=FakeBlueTeam(),
        session_store=session_store,
        output_root=str(tmp_path / "output"),
    )

    with pytest.raises(RuntimeError, match="provider offline"):
        await service.run_discussion(
            topic="故障演练",
            project_name="failure-case",
            session_id="session-failed",
        )

    status = session_store.load_status("session-failed")
    assert status is not None
    assert status.status.value == "failed"
    assert status.error_summary == "provider offline"
    assert status.next_action is not None


def test_clean_session_removes_checkpoints_and_session_snapshots(tmp_path):
    session_store = SessionStore(base_dir=str(tmp_path / "sessions"))
    from engine.checkpoint import CheckpointManager
    from engine.structures import SessionManifest, SessionStatus

    checkpoint_manager = CheckpointManager(base_dir=str(tmp_path / "checkpoints"))
    service = DiscussionService(
        checkpoint_manager=checkpoint_manager,
        cost_tracker=FakeCostTracker(),
        model_client=FakeModelClient(),
        blue_team=FakeBlueTeam(),
        session_store=session_store,
        output_root=str(tmp_path / "output"),
    )

    session_store.save_manifest(
        SessionManifest(
            session_id="session-clean",
            title="cleanup",
            project_name="cleanup",
            task_description="cleanup",
        )
    )
    session_store.save_status(SessionStatus(session_id="session-clean"))
    checkpoint_manager.save(
        __import__("engine.structures", fromlist=["Checkpoint"]).Checkpoint(
            session_id="session-clean",
            current_round=1,
            stage="independent",
        )
    )

    assert service.clean_session("session-clean") is True
    assert session_store.load_manifest("session-clean") is None
    assert checkpoint_manager.load("session-clean", "independent") is None

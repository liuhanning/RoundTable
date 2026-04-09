import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.checkpoint import CheckpointManager  # noqa: E402
from engine.cost_tracker import CostTracker  # noqa: E402
from engine.discussion_service import DiscussionService  # noqa: E402
from engine.models import ModelProvider, ModelResponse  # noqa: E402
from engine.session_store import SessionStore  # noqa: E402
from web.app import create_app  # noqa: E402
from web.services.attachment_service import AttachmentService  # noqa: E402
from web.services.config_store import ConfigStore  # noqa: E402


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
            content="Summary result",
            model="gemini-2.5-flash",
            provider=ModelProvider.GEMINI,
            tokens_in=10,
            tokens_out=20,
            cost_usd=0.01,
        )


class FakeBlueTeam:
    async def challenge(self, independent_outputs, session_id):
        class Report:
            critical_issues = [{"id": "C1", "description": "Risk", "impact": "Medium"}]
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
    session_store = SessionStore(base_dir=str(tmp_path / "sessions"))
    discussion_service = DiscussionService(
        checkpoint_manager=CheckpointManager(base_dir=str(tmp_path / "checkpoints")),
        cost_tracker=CostTracker(),
        model_client=FakeModelClient(),
        blue_team=FakeBlueTeam(),
        session_store=session_store,
        output_root=str(tmp_path / "output"),
    )
    class SyncTaskRunner:
        def start_session(self, manifest):
            import asyncio

            asyncio.run(
                discussion_service.run_discussion(
                    topic=manifest.task_description,
                    project_name=manifest.project_name,
                    session_id=manifest.session_id,
                    created_from=manifest.created_from,
                    manifest=manifest,
                )
            )
            return manifest.session_id

        def is_running(self, session_id):
            return False

    task_runner = SyncTaskRunner()
    app = create_app(
        config_store=config_store,
        session_store=session_store,
        discussion_service=discussion_service,
        attachment_service=AttachmentService(base_dir=str(tmp_path / "uploads")),
        task_runner=task_runner,
    )
    return TestClient(app)


def test_web_e2e_create_start_and_complete_session(tmp_path):
    client = build_client(tmp_path)

    create_response = client.post(
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
    assert create_response.status_code == 200
    session_id = create_response.json()["session_id"]

    start_response = client.post(f"/api/sessions/{session_id}/start")
    assert start_response.status_code == 200

    deadline = time.time() + 5
    detail_payload = None
    while time.time() < deadline:
        detail_response = client.get(f"/api/sessions/{session_id}")
        detail_payload = detail_response.json()
        if detail_payload["status"]["status"] == "completed":
            break
        time.sleep(0.1)

    assert detail_payload is not None
    assert detail_payload["status"]["status"] == "completed"
    assert detail_payload["report_markdown"]

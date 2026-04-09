import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.session_store import SessionStore  # noqa: E402
from engine.structures import SessionManifest, SessionStatus, SessionStatusType  # noqa: E402
from web.services.task_runner import TaskRunner  # noqa: E402


class DummyDiscussionService:
    def __init__(self):
        self.calls = []

    async def run_discussion(self, **kwargs):
        self.calls.append(kwargs)


def test_task_runner_marks_interrupted_sessions_on_init(tmp_path):
    session_store = SessionStore(base_dir=str(tmp_path / "sessions"))
    session_store.save_manifest(
        SessionManifest(
            session_id="session-running",
            title="Running",
            project_name="Project",
            task_description="Task",
        )
    )
    session_store.save_status(
        SessionStatus(session_id="session-running", status=SessionStatusType.RUNNING)
    )

    TaskRunner(discussion_service=DummyDiscussionService(), session_store=session_store)

    status = session_store.load_status("session-running")
    assert status is not None
    assert status.status == SessionStatusType.INTERRUPTED


def test_task_runner_reports_thread_liveness(tmp_path):
    session_store = SessionStore(base_dir=str(tmp_path / "sessions"))
    runner = TaskRunner(discussion_service=DummyDiscussionService(), session_store=session_store)

    assert runner.is_running("missing-session") is False

"""
In-process task runner for Web MVP.
"""
import asyncio
import threading
from typing import Dict, Optional

from engine.discussion_service import DiscussionService
from engine.session_store import SessionStore
from engine.structures import SessionManifest


class TaskRunner:
    """Manage background discussion tasks inside one process."""

    def __init__(self, discussion_service: DiscussionService, session_store: SessionStore):
        self.discussion_service = discussion_service
        self.session_store = session_store
        self._threads: Dict[str, threading.Thread] = {}
        self.session_store.mark_interrupted_sessions()

    def start_session(self, manifest: SessionManifest) -> str:
        """Start a background discussion for an existing manifest."""
        thread = threading.Thread(
            target=self._run_session,
            args=(manifest,),
            daemon=True,
            name=f"rt-session-{manifest.session_id}",
        )
        self._threads[manifest.session_id] = thread
        thread.start()
        return manifest.session_id

    def is_running(self, session_id: str) -> bool:
        """Return whether a session thread is still alive."""
        thread = self._threads.get(session_id)
        return bool(thread and thread.is_alive())

    def _run_session(self, manifest: SessionManifest) -> None:
        asyncio.run(
            self.discussion_service.run_discussion(
                topic=manifest.task_description,
                project_name=manifest.project_name,
                session_id=manifest.session_id,
                created_from=manifest.created_from,
                manifest=manifest,
            )
        )

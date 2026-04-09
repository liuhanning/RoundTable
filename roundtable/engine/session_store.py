"""
Web 会话快照与状态存储

职责：
1. 保存和读取会话 manifest/status
2. 提供最近会话列表摘要
3. 与 Checkpoint 分离，专注页面读模型
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.structures import SessionManifest, SessionStatus, SessionStatusType
from utils.logger import get_sensitive_logger


logger = get_sensitive_logger(__name__)


class SessionStore:
    """会话存储层"""

    def __init__(self, base_dir: str = "data/sessions"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _session_dir(self, session_id: str) -> Path:
        path = self.base_dir / session_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _manifest_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "manifest.json"

    def _status_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "status.json"

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        temp_path = path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        temp_path.replace(path)

    def save_manifest(self, manifest: SessionManifest) -> None:
        path = self._manifest_path(manifest.session_id)
        self._write_json(path, manifest.to_dict())
        logger.info(f"会话 manifest 已保存：session={manifest.session_id}")

    def load_manifest(self, session_id: str) -> Optional[SessionManifest]:
        path = self._manifest_path(session_id)
        if not path.exists():
            return None

        try:
            with open(path, "r", encoding="utf-8") as handle:
                return SessionManifest.from_dict(json.load(handle))
        except Exception as exc:
            logger.error(f"读取 manifest 失败：session={session_id}, error={exc}")
            return None

    def save_status(self, status: SessionStatus) -> None:
        path = self._status_path(status.session_id)
        self._write_json(path, status.to_dict())
        logger.info(
            f"会话 status 已保存：session={status.session_id}, status={status.status.value}"
        )

    def load_status(self, session_id: str) -> Optional[SessionStatus]:
        path = self._status_path(session_id)
        if not path.exists():
            return None

        try:
            with open(path, "r", encoding="utf-8") as handle:
                return SessionStatus.from_dict(json.load(handle))
        except Exception as exc:
            logger.error(f"读取 status 失败：session={session_id}, error={exc}")
            return None

    def load_session(self, session_id: str) -> Dict[str, Optional[object]]:
        return {
            "manifest": self.load_manifest(session_id),
            "status": self.load_status(session_id),
        }

    def list_sessions(self) -> List[Dict[str, Any]]:
        sessions: List[Dict[str, Any]] = []
        if not self.base_dir.exists():
            return sessions

        for session_dir in self.base_dir.iterdir():
            if not session_dir.is_dir():
                continue

            session_id = session_dir.name
            manifest = self.load_manifest(session_id)
            status = self.load_status(session_id)
            if manifest is None or status is None:
                continue

            sessions.append({
                "session_id": session_id,
                "title": manifest.title,
                "status": status.status.value,
                "current_stage": status.current_stage,
                "last_stage": status.completed_stages[-1] if status.completed_stages else None,
                "updated_at": status.updated_at,
                "report_path": status.report_path,
            })

        return sorted(sessions, key=lambda item: item["updated_at"], reverse=True)

    def mark_interrupted_sessions(self) -> List[str]:
        """将残留 running/queued 会话标记为 interrupted。"""
        updated: List[str] = []
        for entry in self.list_sessions():
            if entry["status"] not in (
                SessionStatusType.RUNNING.value,
                SessionStatusType.QUEUED.value,
            ):
                continue

            status = self.load_status(entry["session_id"])
            if status is None:
                continue

            status.status = SessionStatusType.INTERRUPTED
            if status.next_action is None:
                status.next_action = "会话因服务重启中断，请重新发起或进入恢复流程。"
            self.save_status(status)
            updated.append(entry["session_id"])

        return updated


_session_store: Optional[SessionStore] = None


def get_session_store(base_dir: Optional[str] = None) -> SessionStore:
    """获取会话存储单例。"""
    global _session_store
    if _session_store is None or base_dir is not None:
        _session_store = SessionStore(base_dir or "data/sessions")
    return _session_store

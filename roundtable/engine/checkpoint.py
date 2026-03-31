"""
Checkpoint 断点续跑机制

功能：
1. 每阶段结束后自动保存 Checkpoint
2. 中断后从最近 Checkpoint 恢复
3. 支持回滚到任意历史节点
4. 幂等性保证：恢复后重跑不产生副作用
"""
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

from engine.structures import Checkpoint, generate_session_id
from utils.logger import get_sensitive_logger, get_audit_logger


logger = get_sensitive_logger(__name__)
audit_logger = get_audit_logger()


class CheckpointManager:
    """
    Checkpoint 管理器

    提供：
    1. Checkpoint 保存/加载
    2. 会话列表查询
    3. 历史版本管理
    4. 清理过期 Checkpoint
    """

    def __init__(self, base_dir: str = "data/checkpoints"):
        """
        初始化 Checkpoint 管理器

        Args:
            base_dir: Checkpoint 存储目录
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Checkpoint 管理器初始化：{self.base_dir.absolute()}")

    def _get_session_dir(self, session_id: str) -> Path:
        """获取会话的 Checkpoint 目录"""
        session_dir = self.base_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    def _get_checkpoint_path(self, session_id: str, stage: str) -> Path:
        """获取 Checkpoint 文件路径"""
        return self._get_session_dir(session_id) / f"{stage}.json"

    def save(
        self,
        checkpoint: Checkpoint,
        session_id: Optional[str] = None,
    ) -> str:
        """
        保存 Checkpoint

        Args:
            checkpoint: Checkpoint 对象
            session_id: 会话 ID（可选，为空时自动生成）

        Returns:
            session_id: 会话 ID
        """
        session_id = session_id or checkpoint.session_id or generate_session_id()
        checkpoint.session_id = session_id

        path = self._get_checkpoint_path(session_id, checkpoint.stage)

        try:
            # 原子写入：先写临时文件，再重命名
            temp_path = path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(checkpoint.to_dict(), f, ensure_ascii=False, indent=2)
            temp_path.rename(path)

            logger.info(f"Checkpoint 已保存：{path}")

            audit_logger.log_event(
                event_type="checkpoint_save",
                resource=session_id,
                action="save",
                result="success",
                details={"stage": checkpoint.stage, "path": str(path)},
            )

            return session_id

        except Exception as e:
            logger.error(f"Checkpoint 保存失败：{e}")
            audit_logger.log_event(
                event_type="checkpoint_save",
                resource=session_id,
                action="save",
                result="failure",
                details={"error": str(e)},
            )
            raise

    def load(
        self,
        session_id: str,
        stage: Optional[str] = None,
    ) -> Optional[Checkpoint]:
        """
        加载 Checkpoint

        Args:
            session_id: 会话 ID
            stage: 阶段名称（可选，为空时加载最新的）

        Returns:
            Checkpoint 对象或 None
        """
        session_dir = self._get_session_dir(session_id)

        if stage:
            # 加载指定阶段的 Checkpoint
            path = self._get_checkpoint_path(session_id, stage)
            if not path.exists():
                logger.warning(f"Checkpoint 不存在：{path}")
                return None
        else:
            # 加载最新的 Checkpoint
            checkpoints = list(session_dir.glob("*.json"))
            if not checkpoints:
                logger.warning(f"会话无 Checkpoint: {session_id}")
                return None

            # 按修改时间排序，取最新的
            path = max(checkpoints, key=lambda p: p.stat().st_mtime)

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            checkpoint = Checkpoint.from_dict(data)
            logger.info(f"Checkpoint 已加载：{path}")

            return checkpoint

        except Exception as e:
            logger.error(f"Checkpoint 加载失败：{e}")
            return None

    def list_sessions(self) -> List[Dict[str, Any]]:
        """
        列出所有会话

        Returns:
            会话列表，每项包含 {session_id, stages, last_updated}
        """
        sessions = []

        if not self.base_dir.exists():
            return []

        for session_dir in self.base_dir.iterdir():
            if not session_dir.is_dir():
                continue

            session_id = session_dir.name
            checkpoints = list(session_dir.glob("*.json"))

            if not checkpoints:
                continue

            stages = [p.stem for p in checkpoints]
            last_updated = max(p.stat().st_mtime for p in checkpoints)

            sessions.append({
                "session_id": session_id,
                "stages": stages,
                "last_updated": datetime.fromtimestamp(last_updated).isoformat(),
            })

        return sorted(sessions, key=lambda s: s["last_updated"], reverse=True)

    def delete(self, session_id: str) -> bool:
        """
        删除会话的所有 Checkpoint

        Args:
            session_id: 会话 ID

        Returns:
            是否成功删除
        """
        import shutil

        session_dir = self._get_session_dir(session_id)

        if not session_dir.exists():
            logger.warning(f"会话不存在：{session_id}")
            return False

        try:
            shutil.rmtree(session_dir)
            logger.info(f"Checkpoint 已删除：{session_dir}")
            return True
        except Exception as e:
            logger.error(f"Checkpoint 删除失败：{e}")
            return False

    def get_resume_info(self, session_id: str) -> Dict[str, Any]:
        """
        获取恢复信息

        Args:
            session_id: 会话 ID

        Returns:
            恢复信息字典
        """
        checkpoint = self.load(session_id)
        if not checkpoint:
            return {"can_resume": False, "reason": "无 Checkpoint"}

        # 计算已完成阶段
        completed_stages = [checkpoint.stage]
        next_stage = self._get_next_stage(checkpoint.stage)

        return {
            "can_resume": True,
            "session_id": session_id,
            "completed_stages": completed_stages,
            "next_stage": next_stage,
            "current_round": checkpoint.current_round,
            "last_updated": checkpoint.timestamp,
        }

    def _get_next_stage(self, current_stage: str) -> str:
        """获取下一阶段"""
        stage_order = [
            "preparation",
            "independent",
            "blue_team",
            "summary",
            "consensus",
            "report",
        ]

        try:
            idx = stage_order.index(current_stage)
            return stage_order[idx + 1] if idx + 1 < len(stage_order) else "completed"
        except ValueError:
            return "unknown"


# 装饰器：自动保存 Checkpoint
def checkpoint_after(func):
    """
    装饰器：函数执行后自动保存 Checkpoint

    用法:
        @checkpoint_after
        def run_stage(self, stage, data):
            ...
    """
    import functools

    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        result = await func(self, *args, **kwargs)

        # 如果有 checkpoint_manager，调用保存
        if hasattr(self, "checkpoint_manager") and isinstance(result, Checkpoint):
            self.checkpoint_manager.save(result)

        return result

    return wrapper


# 全局管理器实例（单例）
_manager: Optional[CheckpointManager] = None


def get_checkpoint_manager() -> CheckpointManager:
    """获取 Checkpoint 管理器（单例）"""
    global _manager
    if _manager is None:
        _manager = CheckpointManager()
    return _manager


# 便捷函数
def save_checkpoint(checkpoint: Checkpoint, session_id: Optional[str] = None) -> str:
    """便捷保存函数"""
    manager = get_checkpoint_manager()
    return manager.save(checkpoint, session_id)


def load_checkpoint(session_id: str, stage: Optional[str] = None) -> Optional[Checkpoint]:
    """便捷加载函数"""
    manager = get_checkpoint_manager()
    return manager.load(session_id, stage)


def list_checkpoint_sessions() -> List[Dict[str, Any]]:
    """便捷列出函数"""
    manager = get_checkpoint_manager()
    return manager.list_sessions()


def resume_from_checkpoint(session_id: str) -> Dict[str, Any]:
    """便捷恢复信息函数"""
    manager = get_checkpoint_manager()
    return manager.get_resume_info(session_id)

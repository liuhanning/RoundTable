"""
成本追踪与告警

功能：
1. 实时追踪每份报告的成本
2. 预算 80% 时预警
3. 达到预算上限时降级到免费模型
"""
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from config import get_cost_config
from utils.logger import get_sensitive_logger, get_audit_logger


logger = get_sensitive_logger(__name__)
audit_logger = get_audit_logger()


@dataclass
class CostRecord:
    """单次调用成本记录"""
    timestamp: str
    session_id: str
    stage: str
    model: str
    provider: str
    tokens_in: int
    tokens_out: int
    cost_usd: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "stage": self.stage,
            "model": self.model,
            "provider": self.provider,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": self.cost_usd,
        }


@dataclass
class SessionBudget:
    """会话预算状态"""
    session_id: str
    total_budget: float
    spent: float
    call_count: int = 0
    warning_threshold: float = 0.8  # 80% 预警
    is_exceeded: bool = False
    warning_triggered: bool = False

    @property
    def remaining(self) -> float:
        return max(0, self.total_budget - self.spent)

    @property
    def usage_percent(self) -> float:
        if self.total_budget <= 0:
            return 0
        return (self.spent / self.total_budget) * 100

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "total_budget": self.total_budget,
            "spent": self.spent,
            "remaining": self.remaining,
            "usage_percent": self.usage_percent,
            "call_count": self.call_count,
            "is_exceeded": self.is_exceeded,
            "warning_triggered": self.warning_triggered,
        }


class CostTracker:
    """
    成本追踪器

    提供：
    1. 实时成本追踪
    2. 预算预警
    3. 降级策略
    4. 成本报告
    """

    def __init__(
        self,
        total_budget: float = 0.50,
        warning_threshold: float = 0.8,
    ):
        """
        初始化成本追踪器

        Args:
            total_budget: 总预算（美元）
            warning_threshold: 预警阈值（0-1）
        """
        self.config = get_cost_config()
        self.total_budget = total_budget or self.config.TOTAL_BUDGET_USD
        self.warning_threshold = warning_threshold or self.config.BUDGET_WARNING_THRESHOLD

        # 会话预算映射
        self.budgets: Dict[str, SessionBudget] = {}

        # 成本记录历史
        self.records: List[CostRecord] = []

        # 模型成本表（每 1k tokens）
        self.model_costs = {
            "gemini": {"in": 0.0, "out": 0.0},  # 免费
            "claude-sonnet": {"in": 0.003, "out": 0.015},
            "claude-opus": {"in": 0.015, "out": 0.075},
            "gpt-4": {"in": 0.005, "out": 0.015},
            "gpt-5": {"in": 0.005, "out": 0.015},
            "deepseek": {"in": 0.001, "out": 0.002},
        }

        logger.info(f"成本追踪器初始化：预算=${self.total_budget:.2f}, 预警阈值={self.warning_threshold*100:.0f}%")

    def get_or_create_budget(self, session_id: str) -> SessionBudget:
        """获取或创建会话预算"""
        if session_id not in self.budgets:
            self.budgets[session_id] = SessionBudget(
                session_id=session_id,
                total_budget=self.total_budget,
                spent=0,
                warning_threshold=self.warning_threshold,
            )
        return self.budgets[session_id]

    def record_call(
        self,
        session_id: str,
        stage: str,
        model: str,
        provider: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: Optional[float] = None,
    ) -> SessionBudget:
        """
        记录模型调用成本

        Args:
            session_id: 会话 ID
            stage: 阶段名称
            model: 模型名称
            provider: 提供商
            tokens_in: 输入 token 数
            tokens_out: 输出 token 数
            cost_usd: 实际成本（可选，为空时估算）

        Returns:
            更新后的预算状态
        """
        budget = self.get_or_create_budget(session_id)

        # 计算成本
        if cost_usd is None:
            cost_usd = self._estimate_cost(model, tokens_in, tokens_out)

        # 更新预算
        budget.spent += cost_usd
        budget.call_count += 1

        # 检查是否超出预算
        if budget.spent >= budget.total_budget:
            budget.is_exceeded = True
            logger.warning(f"预算已用尽：session={session_id}, spent=${budget.spent:.4f}")

        # 检查是否触发预警
        if (budget.spent >= budget.total_budget * budget.warning_threshold and
                not budget.warning_triggered):
            budget.warning_triggered = True
            logger.warning(f"预算预警：session={session_id}, 已用{budget.usage_percent:.1f}%")

            audit_logger.log_event(
                event_type="budget_warning",
                resource=session_id,
                action="warning",
                result="warning",
                details={
                    "spent": budget.spent,
                    "total": budget.total_budget,
                    "percent": budget.usage_percent,
                },
            )

        # 记录历史
        record = CostRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id=session_id,
            stage=stage,
            model=model,
            provider=provider,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
        )
        self.records.append(record)

        return budget

    def _estimate_cost(self, model: str, tokens_in: int, tokens_out: int) -> float:
        """估算调用成本"""
        # 查找匹配的模型成本
        rates = self.model_costs.get("deepseek", {"in": 0.001, "out": 0.002})

        model_lower = model.lower()
        for key, rate in self.model_costs.items():
            if key in model_lower:
                rates = rate
                break

        return (tokens_in / 1000) * rates["in"] + (tokens_out / 1000) * rates["out"]

    def get_budget_status(self, session_id: str) -> Dict[str, Any]:
        """获取预算状态"""
        budget = self.get_or_create_budget(session_id)
        return budget.to_dict()

    def should_downgrade(self, session_id: str, model: str) -> bool:
        """
        判断是否应该降级到免费模型

        Args:
            session_id: 会话 ID
            model: 当前模型

        Returns:
            是否应该降级
        """
        budget = self.get_or_create_budget(session_id)

        # 预算已用尽，且当前不是免费模型
        if budget.is_exceeded and "gemini" not in model.lower():
            logger.info(f"预算已用尽，降级到免费模型：{model} -> gemini")
            return True

        return False

    def get_downgrade_model(self) -> str:
        """获取降级后的模型（免费）"""
        return "gemini-2.5-flash"

    def get_cost_report(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        生成成本报告

        Args:
            session_id: 会话 ID（可选，为空时返回全部）

        Returns:
            成本报告字典
        """
        if session_id:
            records = [r for r in self.records if r.session_id == session_id]
            budget = self.budgets.get(session_id)
        else:
            records = self.records
            budget = None

        total_cost = sum(r.cost_usd for r in records)
        total_tokens_in = sum(r.tokens_in for r in records)
        total_tokens_out = sum(r.tokens_out for r in records)

        # 按模型分组统计
        by_model: Dict[str, Dict[str, Any]] = {}
        for r in records:
            if r.model not in by_model:
                by_model[r.model] = {"cost": 0, "calls": 0, "tokens_in": 0, "tokens_out": 0}
            by_model[r.model]["cost"] += r.cost_usd
            by_model[r.model]["calls"] += 1
            by_model[r.model]["tokens_in"] += r.tokens_in
            by_model[r.model]["tokens_out"] += r.tokens_out

        return {
            "session_id": session_id or "all",
            "total_cost_usd": total_cost,
            "total_tokens_in": total_tokens_in,
            "total_tokens_out": total_tokens_out,
            "total_calls": len(records),
            "by_model": by_model,
            "budget": budget.to_dict() if budget else None,
        }

    def save_report(self, session_id: str, output_dir: str = "output") -> str:
        """
        保存成本报告到文件

        Args:
            session_id: 会话 ID
            output_dir: 输出目录

        Returns:
            文件路径
        """
        report = self.get_cost_report(session_id)
        output_path = Path(output_dir) / session_id / "cost_report.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info(f"成本报告已保存：{output_path}")
        return str(output_path)


# 全局追踪器实例（单例）
_tracker: Optional[CostTracker] = None


def get_cost_tracker() -> CostTracker:
    """获取成本追踪器（单例）"""
    global _tracker
    if _tracker is None:
        _tracker = CostTracker()
    return _tracker


# 便捷函数
def record_model_call(
    session_id: str,
    stage: str,
    model: str,
    provider: str,
    tokens_in: int,
    tokens_out: int,
    cost_usd: Optional[float] = None,
) -> SessionBudget:
    """便捷记录函数"""
    tracker = get_cost_tracker()
    return tracker.record_call(session_id, stage, model, provider, tokens_in, tokens_out, cost_usd)


def check_budget_status(session_id: str) -> Dict[str, Any]:
    """便捷查询函数"""
    tracker = get_cost_tracker()
    return tracker.get_budget_status(session_id)

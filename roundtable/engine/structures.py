"""
RoundTable 数据结构定义

统一的数据流结构，支持：
- 轮间传递（结构化知识提取）
- Checkpoint 恢复
- 事件审计
"""
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum


class StageType(Enum):
    """阶段类型枚举"""
    PREPARATION = "preparation"       # 阶段 0: 项目准备
    PROBLEM_DEFINE = "problem_define" # 阶段 1: 问题定义
    RESEARCH = "research"             # 阶段 2: 资料研究
    ANALYSIS = "analysis"             # 阶段 3: 分析研判
    DESIGN = "design"                 # 阶段 4: 方案设计
    CONSENSUS = "consensus"           # 阶段 5: 共识形成
    REPORT = "report"                 # 阶段 6: 报告撰写
    REVIEW = "review"                 # 阶段 7: 质检审核


class EventType(Enum):
    """事件类型枚举"""
    STAGE_START = "stage_start"
    STAGE_END = "stage_end"
    MODEL_CALL = "model_call"
    BLUE_TEAM_CHALLENGE = "blue_team_challenge"
    BLUE_TEAM_VETO = "blue_team_veto"
    CONSENSUS_REACHED = "consensus_reached"
    CHECKPOINT_SAVE = "checkpoint_save"
    ERROR = "error"
    RETRY = "retry"


@dataclass
class RoundOutput:
    """
    每轮每个模型的输出（简化版）

    用于 Stage 1 独立输出阶段
    """
    session_id: str
    round: int
    stage: str
    participant: str  # 模型标识
    content: str      # 输出正文
    position: str = ""  # 核心立场（1-2 句话）
    key_points: List[str] = field(default_factory=list)  # 关键论点
    confidence: float = 0.8  # 自评置信度 0-1
    sources: List[str] = field(default_factory=list)  # 引用的知识库来源

    # 元数据
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    cost_usd: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "round": self.round,
            "stage": self.stage,
            "participant": self.participant,
            "content": self.content,
            "position": self.position,
            "key_points": self.key_points,
            "confidence": self.confidence,
            "sources": self.sources,
            "metadata": {
                "tokens_in": self.tokens_in,
                "tokens_out": self.tokens_out,
                "latency_ms": self.latency_ms,
                "cost_usd": self.cost_usd,
            },
            "timestamp": self.timestamp,
        }

    def to_markdown(self) -> str:
        """输出 Markdown 格式"""
        md = f"### {self.participant} 的观点\n\n"
        if self.position:
            md += f"**立场**: {self.position}\n\n"
        if self.key_points:
            md += "**关键论点**:\n"
            for point in self.key_points:
                md += f"- {point}\n"
        md += f"\n{self.content}\n"
        if self.sources:
            md += f"\n**引用来源**: {', '.join(self.sources)}\n"
        return md


@dataclass
class ChallengeReport:
    """
    蓝军质询报告

    用于 Stage 2 蓝军质询阶段
    """
    session_id: str
    stage: str  # "blue_team_challenge" | "blue_team_final"
    critical_issues: List[Dict[str, Any]] = field(default_factory=list)
    high_risks: List[Dict[str, Any]] = field(default_factory=list)
    medium_assumptions: List[Dict[str, Any]] = field(default_factory=list)
    passed: bool = True  # 仅终审使用
    recommendations: List[str] = field(default_factory=list)

    @property
    def total_issues(self) -> int:
        return len(self.critical_issues) + len(self.high_risks) + len(self.medium_assumptions)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "stage": self.stage,
            "critical_issues": self.critical_issues,
            "high_risks": self.high_risks,
            "medium_assumptions": self.medium_assumptions,
            "passed": self.passed,
            "recommendations": self.recommendations,
            "total_issues": self.total_issues,
        }

    def to_markdown(self) -> str:
        """输出 Markdown 格式"""
        md = f"## 蓝军质询报告\n\n"
        md += f"**阶段**: {self.stage}\n"
        md += f"**问题总数**: {self.total_issues}\n\n"

        if self.critical_issues:
            md += "### 🔴 致命漏洞 (Critical)\n\n"
            for item in self.critical_issues:
                md += f"**{item.get('id', 'N/A')}**: {item.get('description', '')}\n"
                md += f"- 影响：{item.get('impact', '')}\n"
                if item.get('evidence'):
                    md += f"- 证据：{item.get('evidence')}\n"
                md += "\n"

        if self.high_risks:
            md += "### 🟠 重大风险 (High)\n\n"
            for item in self.high_risks:
                md += f"**{item.get('id', 'N/A')}**: {item.get('description', '')}\n"
                md += f"- 影响：{item.get('impact', '')}\n"
                if item.get('evidence'):
                    md += f"- 证据：{item.get('evidence')}\n"
                md += "\n"

        if self.medium_assumptions:
            md += "### 🟡 待澄清假设 (Medium)\n\n"
            for item in self.medium_assumptions:
                md += f"**{item.get('id', 'N/A')}**: {item.get('description', '')}\n"
                md += f"- 风险：{item.get('impact', '')}\n"
                if item.get('validation'):
                    md += f"- 验证方式：{item.get('validation')}\n"
                md += "\n"

        if self.recommendations:
            md += "### 💡 建议\n\n"
            for rec in self.recommendations:
                md += f"- {rec}\n"

        return md


@dataclass
class RoundSummary:
    """
    阶段汇总

    用于轮间传递，不传完整对话历史
    """
    session_id: str
    round: int
    stage: str
    consensus_points: List[str] = field(default_factory=list)  # 共识点
    disagreements: List[Dict[str, Any]] = field(default_factory=list)  # 分歧点
    blue_team_challenges: List[Dict[str, Any]] = field(default_factory=list)  # 蓝军质疑
    action_items: List[str] = field(default_factory=list)  # 待决事项
    next_stage: str = ""  # 下一阶段
    quality_score: float = 0.0  # 质量评分 0-1
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "round": self.round,
            "stage": self.stage,
            "consensus_points": self.consensus_points,
            "disagreements": self.disagreements,
            "blue_team_challenges": self.blue_team_challenges,
            "action_items": self.action_items,
            "next_stage": self.next_stage,
            "quality_score": self.quality_score,
            "timestamp": self.timestamp,
        }

    def to_markdown(self) -> str:
        """输出 Markdown 格式"""
        md = f"## 阶段汇总：{self.stage}\n\n"

        if self.consensus_points:
            md += "### ✅ 已达成共识\n\n"
            for point in self.consensus_points:
                md += f"- {point}\n"
            md += "\n"

        if self.disagreements:
            md += "### ⚠️ 未解决的分歧\n\n"
            for item in self.disagreements:
                md += f"- **{item.get('topic', 'N/A')}**: {item.get('positions', {})}\n"
            md += "\n"

        if self.blue_team_challenges:
            md += "### 🛡️ 蓝军质疑\n\n"
            for item in self.blue_team_challenges:
                md += f"- {item.get('issue', '')}\n"
            md += "\n"

        if self.action_items:
            md += "### 📋 待决事项\n\n"
            for item in self.action_items:
                md += f"- {item}\n"
            md += "\n"

        md += f"**下一步**: {self.next_stage}\n"
        md += f"**质量评分**: {self.quality_score:.1f}/10\n"

        return md


@dataclass
class DiscussionEvent:
    """
    讨论事件（用于审计和回放）

    每个关键动作记录为事件
    """
    event_id: str
    session_id: str
    event_type: EventType
    actor: str  # 哪个模型或系统
    stage: str
    round: int = 0
    detail: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "event_type": self.event_type.value,
            "actor": self.actor,
            "stage": self.stage,
            "round": self.round,
            "detail": self.detail,
            "timestamp": self.timestamp,
        }


@dataclass
class Checkpoint:
    """
    Checkpoint 数据结构

    用于断点续跑，每阶段结束后保存
    """
    session_id: str
    current_round: int
    stage: str
    round_outputs: List[Dict[str, Any]] = field(default_factory=list)
    challenge_report: Optional[Dict[str, Any]] = None
    summary: Optional[Dict[str, Any]] = None
    participants_state: Dict[str, Any] = field(default_factory=dict)
    event_log: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "current_round": self.current_round,
            "stage": self.stage,
            "round_outputs": self.round_outputs,
            "challenge_report": self.challenge_report,
            "summary": self.summary,
            "participants_state": self.participants_state,
            "event_log": self.event_log,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Checkpoint":
        """从字典创建 Checkpoint"""
        return cls(
            session_id=data.get("session_id", ""),
            current_round=data.get("current_round", 0),
            stage=data.get("stage", ""),
            round_outputs=data.get("round_outputs", []),
            challenge_report=data.get("challenge_report"),
            summary=data.get("summary"),
            participants_state=data.get("participants_state", {}),
            event_log=data.get("event_log", []),
            timestamp=data.get("timestamp", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class FinalReport:
    """
    最终报告输出

    完整的咨询报告
    """
    session_id: str
    title: str
    sections: List[Dict[str, Any]] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    participants_summary: Dict[str, Any] = field(default_factory=dict)
    blue_team_report: Optional[Dict[str, Any]] = None
    total_cost: float = 0.0
    total_tokens: int = 0
    quality_score: float = 0.0
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "title": self.title,
            "sections": self.sections,
            "sources": self.sources,
            "participants_summary": self.participants_summary,
            "blue_team_report": self.blue_team_report,
            "total_cost": self.total_cost,
            "total_tokens": self.total_tokens,
            "quality_score": self.quality_score,
            "generated_at": self.generated_at,
        }

    def to_markdown(self) -> str:
        """输出 Markdown 格式"""
        md = f"# {self.title}\n\n"
        md += f"**生成时间**: {self.generated_at}\n"
        md += f"**质量评分**: {self.quality_score:.1f}/10\n"
        md += f"**总成本**: ${self.total_cost:.4f}\n"
        md += f"**Token 消耗**: {self.total_tokens}\n\n"

        for section in self.sections:
            md += f"## {section.get('title', '无标题')}\n\n"
            md += section.get('content', '') + "\n\n"

        if self.sources:
            md += "## 数据来源\n\n"
            for source in self.sources:
                md += f"- {source}\n"

        return md


# 便捷函数
def generate_event_id() -> str:
    """生成事件 ID"""
    import uuid
    return str(uuid.uuid4())[:8]


def generate_session_id() -> str:
    """生成会话 ID"""
    import uuid
    return str(uuid.uuid4())[:12]

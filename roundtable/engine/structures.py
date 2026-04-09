"""
RoundTable 数据结构定义

统一的数据流结构，支持：
- 轮间传递（结构化知识提取）
- Checkpoint 恢复
- 事件审计
- Web 会话快照与状态持久化
"""
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from enum import Enum


def utc_now_iso() -> str:
    """返回 UTC ISO 时间戳。"""
    return datetime.now(timezone.utc).isoformat()


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


class SessionStatusType(Enum):
    """Web 会话状态枚举"""
    DRAFT = "draft"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


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
    timestamp: str = field(default_factory=utc_now_iso)

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
    timestamp: str = field(default_factory=utc_now_iso)

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
    timestamp: str = field(default_factory=utc_now_iso)

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
    timestamp: str = field(default_factory=utc_now_iso)
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
    generated_at: str = field(default_factory=utc_now_iso)

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


@dataclass
class RoleConfig:
    """一次会话中的角色配置快照"""
    role_id: str
    enabled: bool = True
    display_name: str = ""
    responsibility: str = ""
    instruction: str = ""
    model: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_id": self.role_id,
            "enabled": self.enabled,
            "display_name": self.display_name,
            "responsibility": self.responsibility,
            "instruction": self.instruction,
            "model": self.model,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RoleConfig":
        return cls(
            role_id=data.get("role_id", ""),
            enabled=data.get("enabled", True),
            display_name=data.get("display_name", ""),
            responsibility=data.get("responsibility", ""),
            instruction=data.get("instruction", ""),
            model=data.get("model", ""),
        )


@dataclass
class AttachmentRecord:
    """一次会话中的附件状态"""
    attachment_id: str
    filename: str
    extension: str
    size_bytes: int
    stored_path: str
    classification: str = "internal"
    injection_mode: str = "listed_only"
    extraction_status: str = "pending"
    extraction_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attachment_id": self.attachment_id,
            "filename": self.filename,
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "stored_path": self.stored_path,
            "classification": self.classification,
            "injection_mode": self.injection_mode,
            "extraction_status": self.extraction_status,
            "extraction_error": self.extraction_error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AttachmentRecord":
        return cls(
            attachment_id=data.get("attachment_id", ""),
            filename=data.get("filename", ""),
            extension=data.get("extension", ""),
            size_bytes=data.get("size_bytes", 0),
            stored_path=data.get("stored_path", ""),
            classification=data.get("classification", "internal"),
            injection_mode=data.get("injection_mode", "listed_only"),
            extraction_status=data.get("extraction_status", "pending"),
            extraction_error=data.get("extraction_error"),
        )


@dataclass
class ProviderSecretState:
    """设置页展示用 provider secret 状态"""
    provider: str
    configured: bool = False
    masked_value: str = ""
    connection_status: str = "unknown"
    last_checked_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "configured": self.configured,
            "masked_value": self.masked_value,
            "connection_status": self.connection_status,
            "last_checked_at": self.last_checked_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProviderSecretState":
        return cls(
            provider=data.get("provider", ""),
            configured=data.get("configured", False),
            masked_value=data.get("masked_value", ""),
            connection_status=data.get("connection_status", "unknown"),
            last_checked_at=data.get("last_checked_at"),
        )


@dataclass
class SessionManifest:
    """会话启动前后的不可变输入快照"""
    session_id: str
    title: str
    project_name: str
    task_description: str
    created_at: str = field(default_factory=utc_now_iso)
    created_from: str = "web"
    roles: List[RoleConfig] = field(default_factory=list)
    attachments: List[AttachmentRecord] = field(default_factory=list)
    model_snapshot: Dict[str, Any] = field(default_factory=dict)
    settings_snapshot: Dict[str, Any] = field(default_factory=dict)
    execution_snapshot: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "title": self.title,
            "project_name": self.project_name,
            "task_description": self.task_description,
            "created_at": self.created_at,
            "created_from": self.created_from,
            "roles": [role.to_dict() for role in self.roles],
            "attachments": [attachment.to_dict() for attachment in self.attachments],
            "model_snapshot": self.model_snapshot,
            "settings_snapshot": self.settings_snapshot,
            "execution_snapshot": self.execution_snapshot,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionManifest":
        return cls(
            session_id=data.get("session_id", ""),
            title=data.get("title", ""),
            project_name=data.get("project_name", ""),
            task_description=data.get("task_description", ""),
            created_at=data.get("created_at", utc_now_iso()),
            created_from=data.get("created_from", "web"),
            roles=[RoleConfig.from_dict(item) for item in data.get("roles", [])],
            attachments=[AttachmentRecord.from_dict(item) for item in data.get("attachments", [])],
            model_snapshot=data.get("model_snapshot", {}),
            settings_snapshot=data.get("settings_snapshot", {}),
            execution_snapshot=data.get("execution_snapshot", {}),
        )


@dataclass
class SessionStatus:
    """会话运行态读模型"""
    session_id: str
    status: SessionStatusType = SessionStatusType.DRAFT
    current_stage: Optional[str] = None
    completed_stages: List[str] = field(default_factory=list)
    stage_summaries: Dict[str, Any] = field(default_factory=dict)
    error_summary: Optional[str] = None
    next_action: Optional[str] = None
    report_path: Optional[str] = None
    cost_summary: Dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status.value,
            "current_stage": self.current_stage,
            "completed_stages": self.completed_stages,
            "stage_summaries": self.stage_summaries,
            "error_summary": self.error_summary,
            "next_action": self.next_action,
            "report_path": self.report_path,
            "cost_summary": self.cost_summary,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionStatus":
        status_value = data.get("status", SessionStatusType.DRAFT.value)
        try:
            status = SessionStatusType(status_value)
        except ValueError:
            status = SessionStatusType.DRAFT

        return cls(
            session_id=data.get("session_id", ""),
            status=status,
            current_stage=data.get("current_stage"),
            completed_stages=data.get("completed_stages", []),
            stage_summaries=data.get("stage_summaries", {}),
            error_summary=data.get("error_summary"),
            next_action=data.get("next_action"),
            report_path=data.get("report_path"),
            cost_summary=data.get("cost_summary", {}),
            updated_at=data.get("updated_at", utc_now_iso()),
        )


# 便捷函数
def generate_event_id() -> str:
    """生成事件 ID"""
    import uuid
    return str(uuid.uuid4())[:8]


def generate_session_id() -> str:
    """生成会话 ID"""
    import uuid
    return str(uuid.uuid4())[:12]

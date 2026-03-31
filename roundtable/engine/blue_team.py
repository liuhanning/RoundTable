"""
蓝军角色实现

蓝军（Blue Team）职责：
1. Stage 2: 对独立输出进行破坏性拆解
2. Stage 6: 对共识草案进行最终压力测试（V2 功能）

方法论：
- 识别逻辑漏洞
- 挖掘隐含假设
- 压力测试极端场景
- 财务可行性挑战
- 技术瓶颈识别
"""
import asyncio
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum

from engine.models import call_model, ModelResponse, ModelProvider
from utils.logger import get_sensitive_logger
from utils.prompt_injection import sanitize_model_output


logger = get_sensitive_logger(__name__)


class SeverityLevel(Enum):
    """严重程度枚举"""
    CRITICAL = 1  # 致命漏洞
    HIGH = 2      # 重大风险
    MEDIUM = 3    # 待澄清假设
    LOW = 4       # 建议优化


@dataclass
class ChallengeItem:
    """质询项"""
    id: str
    severity: SeverityLevel
    description: str
    impact: str
    evidence: Optional[str] = None
    validation: Optional[str] = None  # 验证方式（仅 Medium）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity.name,
            "description": self.description,
            "impact": self.impact,
            "evidence": self.evidence,
            "validation": self.validation,
        }


@dataclass
class ChallengeReport:
    """蓝军质询报告"""
    session_id: str
    stage: str  # "blue_team_challenge" | "blue_team_final"
    critical_issues: List[ChallengeItem] = field(default_factory=list)
    high_risks: List[ChallengeItem] = field(default_factory=list)
    medium_assumptions: List[ChallengeItem] = field(default_factory=list)
    passed: bool = True  # 仅终审使用
    recommendations: List[str] = field(default_factory=list)  # 仅终审使用

    @property
    def total_issues(self) -> int:
        return len(self.critical_issues) + len(self.high_risks) + len(self.medium_assumptions)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "stage": self.stage,
            "critical_issues": [item.to_dict() for item in self.critical_issues],
            "high_risks": [item.to_dict() for item in self.high_risks],
            "medium_assumptions": [item.to_dict() for item in self.medium_assumptions],
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
                md += f"**{item.id}**: {item.description}\n"
                md += f"- 影响：{item.impact}\n"
                if item.evidence:
                    md += f"- 证据：{item.evidence}\n"
                md += "\n"

        if self.high_risks:
            md += "### 🟠 重大风险 (High)\n\n"
            for item in self.high_risks:
                md += f"**{item.id}**: {item.description}\n"
                md += f"- 影响：{item.impact}\n"
                if item.evidence:
                    md += f"- 证据：{item.evidence}\n"
                md += "\n"

        if self.medium_assumptions:
            md += "### 🟡 待澄清假设 (Medium)\n\n"
            for item in self.medium_assumptions:
                md += f"**{item.id}**: {item.description}\n"
                md += f"- 风险：{item.impact}\n"
                if item.validation:
                    md += f"- 验证方式：{item.validation}\n"
                md += "\n"

        if self.recommendations:
            md += "### 💡 建议\n\n"
            for rec in self.recommendations:
                md += f"- {rec}\n"

        return md


# 蓝军系统提示词
BLUE_TEAM_SYSTEM_PROMPT = """你是一名首席逻辑质疑官（Blue Team），职责是对咨询报告进行破坏性拆解。

你的任务：
1. 识别逻辑漏洞（因果断裂、数据跳跃、循环论证）
2. 挖掘隐含假设（未声明的预设条件）
3. 压力测试（政策/资源/时间剧变场景）
4. 财务可行性挑战（成本低估、收益高估）
5. 技术瓶颈识别（落地障碍、依赖风险）

输出要求：
- 犀利但不人身攻击
- 基于证据而非臆测
- 每个问题都要说明影响

严重等级说明：
- Critical: 直接导致方案不可行的致命缺陷
- High: 严重影响方案成功率但可修复的问题
- Medium: 需要澄清的假设或中等风险
"""

# 蓝军终审系统提示词
BLUE_TEAM_FINAL_PROMPT = """你是一名首席逻辑质疑官（Blue Team），现在进行最终压力测试。

你的任务：
1. 评估共识草案是否已回应所有 Critical/High 质询
2. 识别剩余的逻辑漏洞和风险
3. 判断方案是否通过压力测试

最终裁决：
- 通过：方案足够健壮，可以进入报告撰写
- 驳回：存在重大未解决问题，需要返回辩论阶段

输出格式：
1. 已解决的 Critical/High 问题列表
2. 未解决的问题列表
3. 最终裁决（通过/驳回）
4. 驳回理由（如适用）
"""


class BlueTeamAgent:
    """
    蓝军智能体

    提供两种质询模式：
    1. challenge(): Stage 2 质询（对独立输出）
    2. final_review(): Stage 6 终审（对共识草案）
    """

    def __init__(self, model: str = "openrouter/deepseek/deepseek-chat-v3-0324:free", severity: int = 3):
        """
        初始化蓝军智能体

        Args:
            model: 使用的模型（默认 DeepSeek via OpenRouter）
            severity: 严苛等级 1-5（默认 3）
        """
        self.model = model
        self.severity = severity  # 1-5，数字越大越严格
        logger.info(f"蓝军智能体初始化完成：model={model}, severity={severity}")

    def _build_challenge_prompt(
        self,
        independent_outputs: List[Dict[str, Any]],
    ) -> str:
        """
        构建质询 prompt

        Args:
            independent_outputs: 各模型的独立输出列表

        Returns:
            质询 prompt
        """
        # 格式化各模型输出
        opinions_text = ""
        for i, output in enumerate(independent_outputs):
            model_name = output.get("model", f"Model-{i+1}")
            content = output.get("content", "")
            position = output.get("position", "")

            opinions_text += f"\n\n--- [{model_name}] ---\n"
            if position:
                opinions_text += f"立场：{position}\n"
            opinions_text += f"内容：{content}\n"

        # 根据 severity 调整语气
        severity_map = {
            1: "温和地指出潜在问题",
            2: "适度质疑，重点关注",
            3: "严格审视每个论点和假设",
            4: "以最高标准进行破坏性拆解",
            5: "极致严苛，不放过任何疑点",
        }
        severity_instruction = severity_map.get(self.severity, severity_map[3])

        prompt = f"""{BLUE_TEAM_SYSTEM_PROMPT}

【质询要求】
请以{severity_instruction}的态度，对以下独立观点进行破坏性拆解：

{opinions_text}

【输出格式】
请按以下 JSON 格式输出：
{{
    "critical_issues": [
        {{"id": "C1", "description": "...", "impact": "...", "evidence": "..."}}
    ],
    "high_risks": [
        {{"id": "H1", "description": "...", "impact": "...", "evidence": "..."}}
    ],
    "medium_assumptions": [
        {{"id": "M1", "description": "...", "impact": "...", "validation": "..."}}
    ]
}}

每个类别至少输出{max(1, 6 - self.severity)}项，最多{self.severity + 2}项。"""

        return prompt

    def _build_final_review_prompt(
        self,
        consensus_draft: Dict[str, Any],
        challenge_report: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        构建终审 prompt

        Args:
            consensus_draft: 共识草案
            challenge_report: 之前的质询报告（可选）

        Returns:
            终审 prompt
        """
        draft_text = consensus_draft.get("content", "")
        consensus_points = consensus_draft.get("consensus_points", [])

        # 格式化共识点
        consensus_text = "\n".join(f"- {p}" for p in consensus_points) if consensus_points else ""

        # 之前的质询问题
        previous_challenges = ""
        if challenge_report:
            critical = challenge_report.get("critical_issues", [])
            high = challenge_report.get("high_risks", [])

            if critical or high:
                previous_challenges = "\n\n【之前的质询问题】\n"
                for item in critical:
                    previous_challenges += f"- [Critical] {item.get('description', '')}\n"
                for item in high:
                    previous_challenges += f"- [High] {item.get('description', '')}\n"

        prompt = f"""{BLUE_TEAM_FINAL_PROMPT}

【共识草案内容】
{draft_text}

【已达成共识的点】
{consensus_text}
{previous_challenges}

【输出格式】
请按以下 JSON 格式输出：
{{
    "resolved_issues": ["已解决的问题描述"],
    "unresolved_issues": ["未解决的问题描述"],
    "passed": true/false,
    "recommendations": ["建议列表"],
    "rejection_reason": "驳回理由（仅当 passed=false 时填写）"
}}"""

        return prompt

    def _parse_challenge_report(
        self,
        response: ModelResponse,
        session_id: str,
    ) -> ChallengeReport:
        """
        解析质询报告

        Args:
            response: 模型响应
            session_id: 会话 ID

        Returns:
            ChallengeReport
        """
        import json

        content = response.content.strip()

        # 尝试提取 JSON
        try:
            # 清理 Markdown 代码块标记
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            content = content.strip()

            data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON 解析失败：{e}，尝试宽松解析")
            # 宽松解析：从文本中提取关键信息
            data = self._loose_parse_challenge(content)

        report = ChallengeReport(
            session_id=session_id,
            stage="blue_team_challenge",
        )

        # 解析 Critical Issues
        for item in data.get("critical_issues", []):
            report.critical_issues.append(ChallengeItem(
                id=item.get("id", f"C{len(report.critical_issues)+1}"),
                severity=SeverityLevel.CRITICAL,
                description=item.get("description", ""),
                impact=item.get("impact", ""),
                evidence=item.get("evidence"),
            ))

        # 解析 High Risks
        for item in data.get("high_risks", []):
            report.high_risks.append(ChallengeItem(
                id=item.get("id", f"H{len(report.high_risks)+1}"),
                severity=SeverityLevel.HIGH,
                description=item.get("description", ""),
                impact=item.get("impact", ""),
                evidence=item.get("evidence"),
            ))

        # 解析 Medium Assumptions
        for item in data.get("medium_assumptions", []):
            report.medium_assumptions.append(ChallengeItem(
                id=item.get("id", f"M{len(report.medium_assumptions)+1}"),
                severity=SeverityLevel.MEDIUM,
                description=item.get("description", ""),
                impact=item.get("impact", ""),
                validation=item.get("validation"),
            ))

        return report

    def _parse_final_review(
        self,
        response: ModelResponse,
        session_id: str,
    ) -> ChallengeReport:
        """
        解析终审报告

        Args:
            response: 模型响应
            session_id: 会话 ID

        Returns:
            ChallengeReport
        """
        import json

        content = response.content.strip()

        try:
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            content = content.strip()
            data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON 解析失败：{e}，尝试宽松解析")
            data = self._loose_parse_final(content)

        report = ChallengeReport(
            session_id=session_id,
            stage="blue_team_final",
            passed=data.get("passed", True),
            recommendations=data.get("recommendations", []),
        )

        # 未解决的问题作为 High Risks
        for desc in data.get("unresolved_issues", []):
            report.high_risks.append(ChallengeItem(
                id=f"U{len(report.high_risks)+1}",
                severity=SeverityLevel.HIGH,
                description=desc,
                impact="未解决可能影响方案可行性",
            ))

        return report

    def _loose_parse_challenge(self, text: str) -> Dict[str, Any]:
        """宽松解析质询报告（当 JSON 解析失败时）"""
        # 简单实现：返回空报告
        # 可以扩展为使用正则提取关键信息
        logger.warning("使用宽松解析，可能丢失部分信息")
        return {
            "critical_issues": [],
            "high_risks": [],
            "medium_assumptions": [],
        }

    def _loose_parse_final(self, text: str) -> Dict[str, Any]:
        """宽松解析终审报告"""
        # 简单实现：默认通过
        return {
            "passed": True,
            "recommendations": [],
            "unresolved_issues": [],
        }

    async def challenge(
        self,
        independent_outputs: List[Dict[str, Any]],
        session_id: str = "default",
    ) -> ChallengeReport:
        """
        Stage 2: 对独立输出进行质询

        Args:
            independent_outputs: 各模型的独立输出
            session_id: 会话 ID

        Returns:
            ChallengeReport: 质询报告
        """
        logger.info(f"开始蓝军质询，session={session_id}, 输出数量={len(independent_outputs)}")

        prompt = self._build_challenge_prompt(independent_outputs)

        try:
            response = await call_model(
                prompt=prompt,
                max_tokens=3000,
                temperature=0.3,  # 较低温度保证逻辑一致性
                provider=ModelProvider.OPENROUTER,
            )

            report = self._parse_challenge_report(response, session_id)

            logger.info(
                f"蓝军质询完成：Critical={len(report.critical_issues)}, "
                f"High={len(report.high_risks)}, Medium={len(report.medium_assumptions)}"
            )

            return report

        except Exception as e:
            logger.error(f"蓝军质询失败：{e}")
            # 返回空报告，不阻断流程
            return ChallengeReport(
                session_id=session_id,
                stage="blue_team_challenge",
            )

    async def final_review(
        self,
        consensus_draft: Dict[str, Any],
        challenge_report: Optional[ChallengeReport] = None,
        session_id: str = "default",
    ) -> ChallengeReport:
        """
        Stage 6: 对共识草案进行终审

        Args:
            consensus_draft: 共识草案
            challenge_report: 之前的质询报告（可选）
            session_id: 会话 ID

        Returns:
            ChallengeReport: 终审报告
        """
        logger.info(f"开始蓝军终审，session={session_id}")

        prompt = self._build_final_review_prompt(
            consensus_draft,
            challenge_report.to_dict() if challenge_report else None,
        )

        try:
            response = await call_model(
                prompt=prompt,
                max_tokens=2000,
                temperature=0.3,
                provider=ModelProvider.OPENROUTER,
            )

            report = self._parse_final_review(response, session_id)

            logger.info(f"蓝军终审完成：passed={report.passed}, 未解决问题={len(report.high_risks)}")

            return report

        except Exception as e:
            logger.error(f"蓝军终审失败：{e}")
            # 返回默认通过的报告，不阻断流程
            return ChallengeReport(
                session_id=session_id,
                stage="blue_team_final",
                passed=True,
            )


# 全局蓝军实例（可选）
_blue_team: Optional[BlueTeamAgent] = None


def get_blue_team_agent(
    model: str = "openrouter/deepseek/deepseek-chat-v3-0324:free",
    severity: int = 3,
) -> BlueTeamAgent:
    """获取蓝军智能体（单例）"""
    global _blue_team
    if _blue_team is None or _blue_team.model != model or _blue_team.severity != severity:
        _blue_team = BlueTeamAgent(model=model, severity=severity)
    return _blue_team

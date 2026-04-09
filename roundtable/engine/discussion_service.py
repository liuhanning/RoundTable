"""
Discussion service shared by CLI and future Web entrypoints.
"""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from engine.blue_team import BlueTeamAgent, get_blue_team_agent
from engine.checkpoint import CheckpointManager, get_checkpoint_manager
from engine.cost_tracker import CostTracker, get_cost_tracker
from engine.models import ModelClient, get_model_client
from engine.session_store import SessionStore, get_session_store
from engine.structures import (
    Checkpoint,
    FinalReport,
    RoundOutput,
    RoundSummary,
    SessionManifest,
    SessionStatus,
    SessionStatusType,
    generate_session_id,
)
from utils.logger import get_sensitive_logger


logger = get_sensitive_logger(__name__)


@dataclass
class DiscussionResult:
    """Result summary for one discussion run."""
    session_id: str
    project_name: str
    report_path: str
    report_json_path: str
    cost_summary: Dict[str, Any]
    manifest: SessionManifest
    status: SessionStatus


class DiscussionService:
    """Reusable discussion orchestration service."""

    def __init__(
        self,
        checkpoint_manager: Optional[CheckpointManager] = None,
        cost_tracker: Optional[CostTracker] = None,
        model_client: Optional[ModelClient] = None,
        blue_team: Optional[BlueTeamAgent] = None,
        session_store: Optional[SessionStore] = None,
        output_root: str = "output",
    ):
        self.checkpoint_manager = checkpoint_manager or get_checkpoint_manager()
        self.cost_tracker = cost_tracker or get_cost_tracker()
        self.model_client = model_client or get_model_client()
        self.blue_team = blue_team or get_blue_team_agent()
        self.session_store = session_store or get_session_store()
        self.output_root = Path(output_root)

    async def run_discussion(
        self,
        topic: str,
        project_name: str,
        session_id: Optional[str] = None,
        created_from: str = "cli",
        manifest: Optional[SessionManifest] = None,
    ) -> DiscussionResult:
        """Run the full discussion pipeline and persist session state."""
        session_id = session_id or (manifest.session_id if manifest else None) or generate_session_id()
        manifest = manifest or self._build_manifest(
            session_id=session_id,
            topic=topic,
            project_name=project_name,
            created_from=created_from,
        )
        self.session_store.save_manifest(manifest)

        queued_status = SessionStatus(
            session_id=session_id,
            status=SessionStatusType.QUEUED,
            next_action="等待开始执行 Stage 1",
        )
        self.session_store.save_status(queued_status)

        try:
            running_status = SessionStatus(
                session_id=session_id,
                status=SessionStatusType.RUNNING,
                current_stage="independent",
                next_action="执行中",
            )
            self.session_store.save_status(running_status)

            await self._run_stage_1_independent(topic, session_id)
            self._update_stage_status(
                session_id=session_id,
                current_stage="blue_team",
                completed_stage="independent",
                stage_summary={
                    "output_count": len(
                        self.checkpoint_manager.load(session_id, "independent").round_outputs
                    )
                },
                next_action="进入蓝军质询",
            )

            await self._run_stage_2_blue_team(session_id)
            checkpoint = self.checkpoint_manager.load(session_id, "blue_team")
            self._update_stage_status(
                session_id=session_id,
                current_stage="summary",
                completed_stage="blue_team",
                stage_summary={
                    "total_issues": checkpoint.challenge_report.get("total_issues", 0)
                    if checkpoint and checkpoint.challenge_report
                    else 0
                },
                next_action="进入共识汇总",
            )

            await self._run_stage_3_summary(session_id)
            checkpoint = self.checkpoint_manager.load(session_id, "summary")
            summary = checkpoint.summary if checkpoint and checkpoint.summary else {}
            self._update_stage_status(
                session_id=session_id,
                current_stage="report",
                completed_stage="summary",
                stage_summary={
                    "consensus_points": summary.get("consensus_points", []),
                    "disagreements": summary.get("disagreements", []),
                },
                next_action="生成最终报告",
            )

            report_paths = self._run_stage_4_report(session_id, project_name)
            cost_summary = self.cost_tracker.get_budget_status(session_id)
            completed_status = self._update_stage_status(
                session_id=session_id,
                current_stage=None,
                completed_stage="report",
                stage_summary={"report_path": report_paths["report_path"]},
                next_action="可查看结果",
                report_path=report_paths["report_path"],
                status=SessionStatusType.COMPLETED,
                cost_summary=cost_summary,
            )

            return DiscussionResult(
                session_id=session_id,
                project_name=project_name,
                report_path=report_paths["report_path"],
                report_json_path=report_paths["json_path"],
                cost_summary=cost_summary,
                manifest=manifest,
                status=completed_status,
            )
        except Exception as exc:
            logger.error(f"讨论失败: session={session_id}, error={exc}")
            failed_status = self._update_stage_status(
                session_id=session_id,
                current_stage=self._infer_current_stage(session_id),
                completed_stage=None,
                stage_summary=None,
                next_action="修复错误后重试或恢复",
                status=SessionStatusType.FAILED,
                error_summary=str(exc),
                cost_summary=self.cost_tracker.get_budget_status(session_id),
            )
            raise exc

    def get_resume_info(self, session_id: str) -> Dict[str, Any]:
        """Expose checkpoint resume info through the service."""
        return self.checkpoint_manager.get_resume_info(session_id)

    def get_session_status(self, session_id: str) -> Optional[SessionStatus]:
        """Load persisted session status."""
        return self.session_store.load_status(session_id)

    def clean_session(self, session_id: str) -> bool:
        """Delete checkpoint and session snapshot data."""
        checkpoint_dir = self.checkpoint_manager.base_dir / session_id
        checkpoint_deleted = False
        has_checkpoint_data = checkpoint_dir.exists() and any(checkpoint_dir.glob("*.json"))
        if has_checkpoint_data:
            checkpoint_deleted = self.checkpoint_manager.delete(session_id)

        session_dir = self.session_store.base_dir / session_id
        session_deleted = False
        has_session_data = session_dir.exists() and any(session_dir.iterdir())
        if has_session_data:
            import shutil

            shutil.rmtree(session_dir)
            session_deleted = True

        return checkpoint_deleted or session_deleted

    def _build_manifest(
        self,
        session_id: str,
        topic: str,
        project_name: str,
        created_from: str,
    ) -> SessionManifest:
        return SessionManifest(
            session_id=session_id,
            title=topic,
            project_name=project_name,
            task_description=topic,
            created_from=created_from,
            execution_snapshot={
                "fallback_chain": [provider.value for provider in self.model_client.fallback_chain],
                "retry_config": {
                    "max_retries": self.model_client.retry_config.max_retries,
                    "initial_delay": self.model_client.retry_config.initial_delay,
                    "backoff_multiplier": self.model_client.retry_config.backoff_multiplier,
                    "max_delay": self.model_client.retry_config.max_delay,
                },
            },
        )

    def _update_stage_status(
        self,
        session_id: str,
        current_stage: Optional[str],
        completed_stage: Optional[str],
        stage_summary: Optional[Dict[str, Any]],
        next_action: Optional[str],
        status: SessionStatusType = SessionStatusType.RUNNING,
        report_path: Optional[str] = None,
        error_summary: Optional[str] = None,
        cost_summary: Optional[Dict[str, Any]] = None,
    ) -> SessionStatus:
        stored = self.session_store.load_status(session_id) or SessionStatus(session_id=session_id)

        completed_stages = list(stored.completed_stages)
        if completed_stage and completed_stage not in completed_stages:
            completed_stages.append(completed_stage)

        stage_summaries = dict(stored.stage_summaries)
        if completed_stage and stage_summary is not None:
            stage_summaries[completed_stage] = stage_summary

        updated = SessionStatus(
            session_id=session_id,
            status=status,
            current_stage=current_stage,
            completed_stages=completed_stages,
            stage_summaries=stage_summaries,
            error_summary=error_summary,
            next_action=next_action,
            report_path=report_path or stored.report_path,
            cost_summary=cost_summary or stored.cost_summary,
        )
        self.session_store.save_status(updated)
        return updated

    def _infer_current_stage(self, session_id: str) -> Optional[str]:
        checkpoint = self.checkpoint_manager.load(session_id)
        if checkpoint:
            return checkpoint.stage
        return self.session_store.load_status(session_id).current_stage if self.session_store.load_status(session_id) else None

    async def _run_stage_1_independent(self, topic: str, session_id: str) -> None:
        prompts = [
            {"provider": "gemini", "prompt": f"请对以下主题提出你的独立见解：{topic}"},
            {"provider": "openrouter", "prompt": f"请对以下主题提出你的独立见解：{topic}"},
        ]

        responses = await self.model_client.call_parallel(prompts)

        round_outputs = []
        for index, response in enumerate(responses):
            round_outputs.append(
                RoundOutput(
                    session_id=session_id,
                    round=1,
                    stage="independent",
                    participant=f"Model-{index + 1}",
                    content=response.content,
                    tokens_in=response.tokens_in,
                    tokens_out=response.tokens_out,
                    cost_usd=response.cost_usd,
                ).to_dict()
            )
            self.cost_tracker.record_call(
                session_id=session_id,
                stage="independent",
                model=response.model,
                provider=response.provider.value,
                tokens_in=response.tokens_in,
                tokens_out=response.tokens_out,
                cost_usd=response.cost_usd,
            )

        checkpoint = Checkpoint(
            session_id=session_id,
            current_round=1,
            stage="independent",
            round_outputs=round_outputs,
        )
        self.checkpoint_manager.save(checkpoint)

    async def _run_stage_2_blue_team(self, session_id: str) -> None:
        checkpoint = self.checkpoint_manager.load(session_id, "independent")
        if not checkpoint or not checkpoint.round_outputs:
            raise ValueError("Stage 1 输出为空，无法进行蓝军质询")

        report = await self.blue_team.challenge(checkpoint.round_outputs, session_id)
        checkpoint.stage = "blue_team"
        checkpoint.challenge_report = report.to_dict()
        self.checkpoint_manager.save(checkpoint)

        self.cost_tracker.record_call(
            session_id=session_id,
            stage="blue_team",
            model="deepseek",
            provider="openrouter",
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
        )

    async def _run_stage_3_summary(self, session_id: str) -> None:
        checkpoint = self.checkpoint_manager.load(session_id, "blue_team")
        if not checkpoint:
            raise ValueError("Checkpoint 不存在")

        prompt = (
            "请基于以下独立观点和蓝军质询，总结已达成共识和未解决的分歧：\n"
            f"独立观点数量：{len(checkpoint.round_outputs)}\n"
            f"蓝军质询问题数："
            f"{checkpoint.challenge_report.get('total_issues', 0) if checkpoint.challenge_report else 0}\n\n"
            "请输出：\n"
            "1. 已达成共识的点（3-5 条）\n"
            "2. 未解决的分歧（1-3 条）\n"
            "3. 下一步建议"
        )

        response = await self.model_client.call(prompt)
        self.cost_tracker.record_call(
            session_id=session_id,
            stage="summary",
            model=response.model,
            provider=response.provider.value,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            cost_usd=response.cost_usd,
        )

        summary = RoundSummary(
            session_id=session_id,
            round=1,
            stage="summary",
            consensus_points=["共识点 1", "共识点 2"],
            disagreements=[{"topic": "分歧点 1", "positions": {}}],
            next_stage="report",
        )
        checkpoint.stage = "summary"
        checkpoint.summary = summary.to_dict()
        checkpoint.metadata["summary_response"] = response.content
        self.checkpoint_manager.save(checkpoint)

    def _run_stage_4_report(self, session_id: str, project_name: str) -> Dict[str, str]:
        report = FinalReport(
            session_id=session_id,
            title=f"{project_name} 讨论报告",
            sections=[
                {"title": "背景", "content": "讨论背景和目标"},
                {"title": "独立观点", "content": "各模型的独立见解"},
                {"title": "蓝军质询", "content": "关键质疑和风险点"},
                {"title": "共识与建议", "content": "已达成共识和下一步建议"},
            ],
            total_cost=self.cost_tracker.get_budget_status(session_id).get("spent", 0),
            quality_score=0.8,
        )

        output_dir = self.output_root / project_name
        output_dir.mkdir(parents=True, exist_ok=True)

        report_path = output_dir / "final_report.md"
        report_json_path = output_dir / "final_report.json"

        report_path.write_text(report.to_markdown(), encoding="utf-8")
        report_json_path.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return {
            "report_path": str(report_path),
            "json_path": str(report_json_path),
        }


_discussion_service: Optional[DiscussionService] = None


def get_discussion_service() -> DiscussionService:
    """Return singleton discussion service."""
    global _discussion_service
    if _discussion_service is None:
        _discussion_service = DiscussionService()
    return _discussion_service

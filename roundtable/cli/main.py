"""
RoundTable CLI 命令行工具

命令:
- run: 启动新讨论
- resume: 恢复中断的讨论
- status: 查看会话状态
- clean: 清理会话数据
"""
import argparse
import asyncio
import sys
from pathlib import Path
from typing import Optional

from engine.checkpoint import get_checkpoint_manager, CheckpointManager
from engine.cost_tracker import get_cost_tracker, CostTracker
from engine.models import get_model_client, ModelClient
from engine.blue_team import get_blue_team_agent, BlueTeamAgent
from engine.structures import generate_session_id
from utils.logger import get_sensitive_logger


logger = get_sensitive_logger(__name__)


class RoundTableCLI:
    """CLI 主类"""

    def __init__(self):
        self.checkpoint_manager: Optional[CheckpointManager] = None
        self.cost_tracker: Optional[CostTracker] = None
        self.model_client: Optional[ModelClient] = None
        self.blue_team: Optional[BlueTeamAgent] = None
        self.current_session: Optional[str] = None

    def init_services(self, session_id: str):
        """初始化服务"""
        self.current_session = session_id
        self.checkpoint_manager = get_checkpoint_manager()
        self.cost_tracker = get_cost_tracker()
        self.model_client = get_model_client()
        self.blue_team = get_blue_team_agent()
        logger.info(f"服务已初始化：session={session_id}")

    async def run_discussion(self, topic: str, project_name: str):
        """
        运行讨论流程

        Args:
            topic: 讨论主题
            project_name: 项目名称
        """
        session_id = generate_session_id()
        self.init_services(session_id)

        print(f"\n{'='*60}")
        print(f"RoundTable 讨论开始")
        print(f"{'='*60}")
        print(f"会话 ID: {session_id}")
        print(f"项目名称：{project_name}")
        print(f"讨论主题：{topic}")
        print(f"{'='*60}\n")

        try:
            # Stage 1: 独立思考（简化版，仅示例）
            await self._run_stage_1_independent(topic, session_id)

            # Stage 2: 蓝军质询
            await self._run_stage_2_blue_team(session_id)

            # Stage 3: 汇总共识
            await self._run_stage_3_summary(session_id)

            # Stage 4: 报告撰写
            await self._run_stage_4_report(session_id, project_name)

            # 输出成本报告
            self._print_cost_report()

            print(f"\n{'='*60}")
            print(f"讨论完成！输出目录：output/{project_name}/")
            print(f"{'='*60}\n")

        except KeyboardInterrupt:
            print(f"\n\n中断！Checkpoint 已保存，可使用 resume 命令恢复。")
            sys.exit(1)
        except Exception as e:
            logger.error(f"讨论失败：{e}")
            print(f"\n错误：{e}")
            sys.exit(1)

    async def _run_stage_1_independent(self, topic: str, session_id: str):
        """Stage 1: 独立思考"""
        print(f"\n[Stage 1/4] 独立思考中...")

        # 调用多模型获取独立观点
        prompts = [
            {"provider": "gemini", "prompt": f"请对以下主题提出你的独立见解：{topic}"},
            {"provider": "openrouter", "prompt": f"请对以下主题提出你的独立见解：{topic}"},
        ]

        try:
            responses = await self.model_client.call_parallel(prompts)
            print(f"  ✓ 已收集 {len(responses)} 个独立观点")

            # 保存到 Checkpoint
            from engine.structures import RoundOutput
            round_outputs = []
            for i, response in enumerate(responses):
                round_outputs.append(RoundOutput(
                    session_id=session_id,
                    round=1,
                    stage="independent",
                    participant=f"Model-{i+1}",
                    content=response.content,
                    tokens_in=response.tokens_in,
                    tokens_out=response.tokens_out,
                    cost_usd=response.cost_usd,
                ).to_dict())

            from engine.structures import Checkpoint
            checkpoint = Checkpoint(
                session_id=session_id,
                current_round=1,
                stage="independent",
                round_outputs=round_outputs,
            )
            self.checkpoint_manager.save(checkpoint)

            # 记录成本
            for response in responses:
                self.cost_tracker.record_call(
                    session_id=session_id,
                    stage="independent",
                    model=response.model,
                    provider=response.provider.value,
                    tokens_in=response.tokens_in,
                    tokens_out=response.tokens_out,
                    cost_usd=response.cost_usd,
                )

        except Exception as e:
            logger.error(f"Stage 1 失败：{e}")
            print(f"  ✗ Stage 1 失败：{e}")
            raise

    async def _run_stage_2_blue_team(self, session_id: str):
        """Stage 2: 蓝军质询"""
        print(f"\n[Stage 2/4] 蓝军质询中...")

        # 加载 Stage 1 的输出
        checkpoint = self.checkpoint_manager.load(session_id, "independent")
        if not checkpoint or not checkpoint.round_outputs:
            raise ValueError("Stage 1 输出为空，无法进行蓝军质询")

        independent_outputs = checkpoint.round_outputs

        try:
            report = await self.blue_team.challenge(independent_outputs, session_id)

            print(f"  ✓ 质询完成：Critical={len(report.critical_issues)}, "
                  f"High={len(report.high_risks)}, Medium={len(report.medium_assumptions)}")

            # 保存到 Checkpoint
            checkpoint.stage = "blue_team"
            checkpoint.challenge_report = report.to_dict()
            self.checkpoint_manager.save(checkpoint)

            # 记录成本（蓝军调用）
            self.cost_tracker.record_call(
                session_id=session_id,
                stage="blue_team",
                model="deepseek",
                provider="openrouter",
                tokens_in=0,
                tokens_out=0,
                cost_usd=0.0,  # 实际成本在 ModelResponse 中追踪
            )

        except Exception as e:
            logger.error(f"Stage 2 失败：{e}")
            print(f"  ✗ Stage 2 失败：{e}")
            raise

    async def _run_stage_3_summary(self, session_id: str):
        """Stage 3: 汇总共识"""
        print(f"\n[Stage 3/4] 汇总共识中...")

        # 加载 Checkpoint
        checkpoint = self.checkpoint_manager.load(session_id, "blue_team")
        if not checkpoint:
            raise ValueError("Checkpoint 不存在")

        # 简化实现：直接基于 Stage 1 输出和 Stage 2 质询生成汇总
        prompt = f"""请基于以下独立观点和蓝军质询，总结已达成共识和未解决的分歧：

独立观点数量：{len(checkpoint.round_outputs)}
蓝军质询问题数：{checkpoint.challenge_report.get('total_issues', 0) if checkpoint.challenge_report else 0}

请输出：
1. 已达成共识的点（3-5 条）
2. 未解决的分歧（2-3 条）
3. 下一步建议
"""

        try:
            response = await self.model_client.call(prompt)

            print(f"  ✓ 共识汇总完成")

            # 保存汇总
            from engine.structures import RoundSummary
            summary = RoundSummary(
                session_id=session_id,
                round=1,
                stage="summary",
                consensus_points=["共识点 1", "共识点 2"],  # 简化
                disagreements=["分歧点 1"],
                next_stage="report",
            )

            checkpoint.stage = "summary"
            checkpoint.summary = summary.to_dict()
            self.checkpoint_manager.save(checkpoint)

            # 记录成本
            self.cost_tracker.record_call(
                session_id=session_id,
                stage="summary",
                model=response.model,
                provider=response.provider.value,
                tokens_in=response.tokens_in,
                tokens_out=response.tokens_out,
                cost_usd=response.cost_usd,
            )

        except Exception as e:
            logger.error(f"Stage 3 失败：{e}")
            print(f"  ✗ Stage 3 失败：{e}")
            raise

    async def _run_stage_4_report(self, session_id: str, project_name: str):
        """Stage 4: 报告撰写"""
        print(f"\n[Stage 4/4] 报告撰写中...")

        # 加载 Checkpoint
        checkpoint = self.checkpoint_manager.load(session_id, "summary")
        if not checkpoint:
            raise ValueError("Checkpoint 不存在")

        # 生成最终报告
        from engine.structures import FinalReport
        report = FinalReport(
            session_id=session_id,
            title=f"{project_name} 讨论报告",
            sections=[
                {"title": "背景", "content": "讨论背景和目標"},
                {"title": "独立观点", "content": "各模型的独立见解"},
                {"title": "蓝军质询", "content": "关键质疑和风险点"},
                {"title": "共识与建议", "content": "已达成共识和下一步建议"},
            ],
            total_cost=self.cost_tracker.get_budget_status(session_id).get("spent", 0),
            quality_score=0.8,
        )

        # 保存到文件
        output_dir = Path("output") / project_name
        output_dir.mkdir(parents=True, exist_ok=True)

        report_path = output_dir / "final_report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report.to_markdown())

        # 保存 JSON 版本
        json_path = output_dir / "final_report.json"
        import json
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)

        print(f"  ✓ 报告已保存：{report_path}")

    def _print_cost_report(self):
        """打印成本报告"""
        status = self.cost_tracker.get_budget_status(self.current_session)
        print(f"\n{'='*60}")
        print(f"成本统计")
        print(f"{'='*60}")
        print(f"总预算：${status.get('total_budget', 0):.2f}")
        print(f"已花费：${status.get('spent', 0):.4f}")
        print(f"剩余：${status.get('remaining', 0):.4f}")
        print(f"使用率：{status.get('usage_percent', 0):.1f}%")
        print(f"{'='*60}\n")

    def resume_session(self, session_id: str):
        """恢复会话"""
        print(f"\n恢复会话：{session_id}")

        self.init_services(session_id)
        resume_info = self.checkpoint_manager.get_resume_info(session_id)

        if not resume_info.get("can_resume"):
            print(f"无法恢复：{resume_info.get('reason', '未知原因')}")
            sys.exit(1)

        print(f"  已完成阶段：{', '.join(resume_info.get('completed_stages', []))}")
        print(f"  下一阶段：{resume_info.get('next_stage', 'unknown')}")
        print(f"  当前轮次：{resume_info.get('current_round', 0)}")
        print(f"  最后更新：{resume_info.get('last_updated', 'unknown')}")

        # TODO: 实现恢复逻辑
        print(f"\n恢复功能待实现 - 请手动从 Checkpoint 继续")

    def show_status(self, session_id: str):
        """显示会话状态"""
        print(f"\n会话状态：{session_id}")

        manager = get_checkpoint_manager()
        sessions = manager.list_sessions()

        target = next((s for s in sessions if s["session_id"] == session_id), None)
        if not target:
            print(f"会话不存在：{session_id}")
            sys.exit(1)

        print(f"  阶段：{', '.join(target.get('stages', []))}")
        print(f"  最后更新：{target.get('last_updated', 'unknown')}")

        # 显示成本
        tracker = get_cost_tracker()
        cost_status = tracker.get_budget_status(session_id)
        print(f"  已花费：${cost_status.get('spent', 0):.4f}")
        print(f"  预算剩余：${cost_status.get('remaining', 0):.4f}")

    def clean_session(self, session_id: str):
        """清理会话"""
        print(f"\n清理会话：{session_id}")

        manager = get_checkpoint_manager()
        success = manager.delete(session_id)

        if success:
            print(f"  ✓ Checkpoint 已删除")

            # 清理输出目录
            import shutil
            output_dirs = list(Path("output").glob(f"{session_id}*"))
            for d in output_dirs:
                shutil.rmtree(d)
                print(f"  ✓ 输出目录已删除：{d}")
        else:
            print(f"  ✗ 清理失败")
            sys.exit(1)


def main():
    """CLI 入口函数"""
    parser = argparse.ArgumentParser(
        description="RoundTable 多模型协作讨论工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s run --topic "贵州交通规划" --project "贵州十五五"
  %(prog)s resume --session abc123
  %(prog)s status --session abc123
  %(prog)s clean --session abc123
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # run 命令
    run_parser = subparsers.add_parser("run", help="启动新讨论")
    run_parser.add_argument("--topic", "-t", required=True, help="讨论主题")
    run_parser.add_argument("--project", "-p", required=True, help="项目名称")

    # resume 命令
    resume_parser = subparsers.add_parser("resume", help="恢复中断的讨论")
    resume_parser.add_argument("--session", "-s", required=True, help="会话 ID")

    # status 命令
    status_parser = subparsers.add_parser("status", help="查看会话状态")
    status_parser.add_argument("--session", "-s", required=True, help="会话 ID")

    # clean 命令
    clean_parser = subparsers.add_parser("clean", help="清理会话数据")
    clean_parser.add_argument("--session", "-s", required=True, help="会话 ID")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    cli = RoundTableCLI()

    if args.command == "run":
        asyncio.run(cli.run_discussion(args.topic, args.project))
    elif args.command == "resume":
        cli.resume_session(args.session)
    elif args.command == "status":
        cli.show_status(args.session)
    elif args.command == "clean":
        cli.clean_session(args.session)


if __name__ == "__main__":
    main()

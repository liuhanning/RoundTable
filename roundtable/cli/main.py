"""
RoundTable CLI entrypoint.
"""
import argparse
import asyncio
import sys
from pathlib import Path
from typing import Optional

from engine.checkpoint import CheckpointManager, get_checkpoint_manager
from engine.cost_tracker import CostTracker, get_cost_tracker
from engine.discussion_service import DiscussionService, get_discussion_service
from engine.models import ModelClient, get_model_client
from utils.console_encoding import configure_utf8_console
from utils.logger import get_sensitive_logger


configure_utf8_console()

logger = get_sensitive_logger(__name__)


class RoundTableCLI:
    """Thin CLI wrapper over the shared discussion service."""

    def __init__(self):
        self.checkpoint_manager: Optional[CheckpointManager] = None
        self.cost_tracker: Optional[CostTracker] = None
        self.model_client: Optional[ModelClient] = None
        self.discussion_service: Optional[DiscussionService] = None
        self.current_session: Optional[str] = None

    def init_services(self, session_id: str) -> None:
        """Initialize singleton-backed services."""
        self.current_session = session_id
        self.checkpoint_manager = get_checkpoint_manager()
        self.cost_tracker = get_cost_tracker()
        self.model_client = get_model_client()
        self.discussion_service = get_discussion_service()
        logger.info(f"Services initialized: session={session_id}")

    async def run_discussion(self, topic: str, project_name: str) -> None:
        """Run a new discussion session."""
        from engine.structures import generate_session_id

        session_id = generate_session_id()
        self.init_services(session_id)

        print(f"\n{'=' * 60}")
        print("RoundTable discussion started")
        print(f"{'=' * 60}")
        print(f"Session ID: {session_id}")
        print(f"Project: {project_name}")
        print(f"Topic: {topic}")
        print(f"{'=' * 60}\n")

        try:
            result = await self.discussion_service.run_discussion(  # type: ignore[union-attr]
                topic=topic,
                project_name=project_name,
                session_id=session_id,
                created_from="cli",
            )
            self._print_cost_report()

            print(f"\n{'=' * 60}")
            print(f"Discussion finished. Output directory: {Path(result.report_path).parent}")
            print(f"{'=' * 60}\n")
        except KeyboardInterrupt:
            print("\n\nInterrupted. Checkpoint saved, resume can continue later.")
            sys.exit(1)
        except Exception as exc:
            logger.error(f"Discussion failed: {exc}")
            print(f"\nError: {exc}")
            sys.exit(1)

    def _print_cost_report(self) -> None:
        """Print session budget status."""
        status = self.cost_tracker.get_budget_status(self.current_session)  # type: ignore[union-attr]
        print(f"\n{'=' * 60}")
        print("Cost Summary")
        print(f"{'=' * 60}")
        print(f"Budget: ${status.get('total_budget', 0):.2f}")
        print(f"Spent: ${status.get('spent', 0):.4f}")
        print(f"Remaining: ${status.get('remaining', 0):.4f}")
        print(f"Usage: {status.get('usage_percent', 0):.1f}%")
        print(f"{'=' * 60}\n")

    def resume_session(self, session_id: str) -> None:
        """Show checkpoint resume information."""
        print(f"\nResume session: {session_id}")

        self.init_services(session_id)
        resume_info = self.discussion_service.get_resume_info(session_id)  # type: ignore[union-attr]

        if not resume_info.get("can_resume"):
            print(f"Cannot resume: {resume_info.get('reason', 'unknown')}")
            sys.exit(1)

        print(f"  Completed stages: {', '.join(resume_info.get('completed_stages', []))}")
        print(f"  Next stage: {resume_info.get('next_stage', 'unknown')}")
        print(f"  Current round: {resume_info.get('current_round', 0)}")
        print(f"  Last updated: {resume_info.get('last_updated', 'unknown')}")
        print("\nResume execution flow is not implemented yet. Continue from the checkpoint manually.")

    def show_status(self, session_id: str) -> None:
        """Show session checkpoint and cost status."""
        print(f"\nSession status: {session_id}")

        manager = get_checkpoint_manager()
        sessions = manager.list_sessions()
        target = next((session for session in sessions if session["session_id"] == session_id), None)
        if not target:
            print(f"会话不存在: {session_id}")
            sys.exit(1)

        print(f"  Stages: {', '.join(target.get('stages', []))}")
        print(f"  Last updated: {target.get('last_updated', 'unknown')}")

        tracker = get_cost_tracker()
        cost_status = tracker.get_budget_status(session_id)
        print(f"  Spent: ${cost_status.get('spent', 0):.4f}")
        print(f"  Remaining: ${cost_status.get('remaining', 0):.4f}")

    def clean_session(self, session_id: str) -> None:
        """Delete session-related persisted data."""
        print(f"\nClean session: {session_id}")
        self.init_services(session_id)
        success = self.discussion_service.clean_session(session_id)  # type: ignore[union-attr]

        if success:
            print("  Checkpoint/session data removed")
            output_dirs = list(Path("output").glob(f"{session_id}*"))
            for directory in output_dirs:
                import shutil

                shutil.rmtree(directory)
                print(f"  Output directory removed: {directory}")
        else:
            print("  Clean failed")
            sys.exit(1)


def main() -> None:
    """CLI main function."""
    parser = argparse.ArgumentParser(
        description="RoundTable multi-model discussion CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s run --topic "Transport planning" --project "Guizhou"
  %(prog)s resume --session abc123
  %(prog)s status --session abc123
  %(prog)s clean --session abc123
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    run_parser = subparsers.add_parser("run", help="Start a new discussion")
    run_parser.add_argument("--topic", "-t", required=True, help="Discussion topic")
    run_parser.add_argument("--project", "-p", required=True, help="Project name")

    resume_parser = subparsers.add_parser("resume", help="Resume a checkpointed session")
    resume_parser.add_argument("--session", "-s", required=True, help="Session ID")

    status_parser = subparsers.add_parser("status", help="Show session status")
    status_parser.add_argument("--session", "-s", required=True, help="Session ID")

    clean_parser = subparsers.add_parser("clean", help="Clean session data")
    clean_parser.add_argument("--session", "-s", required=True, help="Session ID")

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

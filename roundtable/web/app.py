"""
FastAPI app for the RoundTable Web MVP.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from config import get_config_store, reload_config
from engine.discussion_service import DiscussionService, get_discussion_service
from engine.session_store import SessionStore, get_session_store
from engine.structures import RoleConfig, SessionManifest, SessionStatus, SessionStatusType, generate_session_id
from utils.console_encoding import configure_utf8_console
from utils.file_validator import FileUploadValidationError
from web.role_templates import DEFAULT_ROLE_TEMPLATES
from web.services.attachment_service import AttachmentService
from web.services.task_runner import TaskRunner

configure_utf8_console()

STATUS_LABELS = {
    "draft": "草稿",
    "queued": "排队中",
    "running": "执行中",
    "completed": "已完成",
    "failed": "失败",
    "interrupted": "已中断",
}

STAGE_LABELS = {
    "independent": "独立分析",
    "blue_team": "蓝军质询",
    "summary": "共识汇总",
    "report": "报告生成",
}

PROVIDER_STATUS_LABELS = {
    "unknown": "未检测",
    "ok": "正常",
    "failed": "失败",
}

ATTACHMENT_MODE_LABELS = {
    "embedded": "已注入上下文",
    "listed_only": "仅列表展示",
}

ATTACHMENT_EXTRACTION_LABELS = {
    "ready": "已提取",
    "pending": "待处理",
    "failed": "提取失败",
    "skipped": "未注入",
}


class ProviderSecretPayload(BaseModel):
    provider: str
    api_key: str = ""


class EnabledModelsPayload(BaseModel):
    enabled_models: Dict[str, bool]


class RolePayload(BaseModel):
    role_id: str
    enabled: bool = True
    display_name: str = ""
    responsibility: str = ""
    instruction: str = ""
    model: str = ""


class CreateSessionPayload(BaseModel):
    title: str
    project_name: str
    task_description: str
    roles: List[RolePayload] = Field(default_factory=list)
    attachment_ids: List[str] = Field(default_factory=list)


def create_app(
    config_store=None,
    session_store: Optional[SessionStore] = None,
    discussion_service: Optional[DiscussionService] = None,
    attachment_service: Optional[AttachmentService] = None,
    task_runner: Optional[TaskRunner] = None,
) -> FastAPI:
    """Create the FastAPI app with injectable services for tests."""
    app = FastAPI(title="RoundTable Web MVP")

    root = Path(__file__).resolve().parent
    templates = Jinja2Templates(directory=str(root / "templates"))
    static_dir = root / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    config_store = config_store or get_config_store()
    session_store = session_store or get_session_store()
    discussion_service = discussion_service or get_discussion_service()
    attachment_service = attachment_service or AttachmentService()
    task_runner = task_runner or TaskRunner(discussion_service=discussion_service, session_store=session_store)

    def render_page(template_name: str, request: Request, context: Optional[Dict[str, Any]] = None):
        page_context = {
            "request": request,
            "providers": [state.to_dict() for state in config_store.list_provider_states()],
            "settings": config_store.load_settings(),
            "role_templates": DEFAULT_ROLE_TEMPLATES,
            "recent_sessions": session_store.list_sessions(),
            "status_labels": STATUS_LABELS,
            "stage_labels": STAGE_LABELS,
            "provider_status_labels": PROVIDER_STATUS_LABELS,
            "attachment_mode_labels": ATTACHMENT_MODE_LABELS,
            "attachment_extraction_labels": ATTACHMENT_EXTRACTION_LABELS,
        }
        if context:
            page_context.update(context)
        return templates.TemplateResponse(request, template_name, page_context)

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse(url="/sessions/new", status_code=302)

    @app.get("/api/settings")
    def get_settings():
        return {
            "providers": [state.to_dict() for state in config_store.list_provider_states()],
            **config_store.load_settings(),
        }

    @app.post("/api/settings/secrets")
    def save_secret(payload: ProviderSecretPayload):
        state = config_store.set_provider_secret(payload.provider, payload.api_key)
        reload_config()
        return state.to_dict()

    @app.post("/api/settings/models")
    def save_models(payload: EnabledModelsPayload):
        settings = config_store.update_enabled_models(payload.enabled_models)
        reload_config()
        return settings

    @app.post("/api/attachments")
    async def upload_attachment(file: UploadFile = File(...)):
        content = await file.read()
        try:
            record = attachment_service.save_upload(file.filename, content)
        except FileUploadValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return record.to_dict()

    @app.post("/api/sessions")
    def create_session(payload: CreateSessionPayload):
        settings = config_store.load_settings()
        enabled_models = settings.get("enabled_models", {})

        roles = []
        for role in payload.roles:
            if role.enabled and role.model and not enabled_models.get(role.model, False):
                raise HTTPException(status_code=400, detail=f"Model disabled for role: {role.model}")
            roles.append(
                RoleConfig(
                    role_id=role.role_id,
                    enabled=role.enabled,
                    display_name=role.display_name,
                    responsibility=role.responsibility,
                    instruction=role.instruction,
                    model=role.model,
                )
            )

        provider_states = {
            state.provider: {
                "configured": state.configured,
                "masked_value": state.masked_value,
            }
            for state in config_store.list_provider_states()
        }

        session_id = generate_session_id()
        attachments = []
        for attachment_id in payload.attachment_ids:
            record = attachment_service.promote_to_session(attachment_id, session_id)
            if record is None:
                raise HTTPException(status_code=404, detail=f"Attachment not found: {attachment_id}")
            attachments.append(record)

        manifest = SessionManifest(
            session_id=session_id,
            title=payload.title,
            project_name=payload.project_name,
            task_description=payload.task_description,
            created_from="web",
            roles=roles,
            attachments=attachments,
            settings_snapshot=settings,
            execution_snapshot={"providers": provider_states},
        )
        status = SessionStatus(session_id=session_id, status=SessionStatusType.DRAFT)

        session_store.save_manifest(manifest)
        session_store.save_status(status)
        return {"session_id": session_id, "status": status.status.value}

    @app.post("/api/sessions/{session_id}/start")
    def start_session(session_id: str):
        manifest = session_store.load_manifest(session_id)
        if manifest is None:
            raise HTTPException(status_code=404, detail="Session not found")

        settings = manifest.settings_snapshot or config_store.load_settings()
        enabled_models = settings.get("enabled_models", {})
        if not any(enabled_models.values()):
            raise HTTPException(status_code=400, detail="No enabled models configured")

        task_runner.start_session(manifest)
        return {"session_id": session_id, "status": "queued"}

    @app.get("/api/sessions")
    def list_sessions():
        return session_store.list_sessions()

    @app.get("/api/sessions/{session_id}")
    def session_detail(session_id: str):
        manifest = session_store.load_manifest(session_id)
        status = session_store.load_status(session_id)
        if manifest is None or status is None:
            raise HTTPException(status_code=404, detail="Session not found")

        report_markdown = ""
        if status.report_path and Path(status.report_path).exists():
            report_markdown = Path(status.report_path).read_text(encoding="utf-8")

        return {
            "manifest": manifest.to_dict(),
            "status": status.to_dict(),
            "report_markdown": report_markdown,
            "is_running": task_runner.is_running(session_id),
        }

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request):
        return render_page("settings.html", request)

    @app.get("/sessions/new", response_class=HTMLResponse)
    def session_new_page(request: Request):
        return render_page("session_new.html", request)

    @app.get("/sessions/{session_id}", response_class=HTMLResponse)
    def session_detail_page(session_id: str, request: Request):
        manifest = session_store.load_manifest(session_id)
        status = session_store.load_status(session_id)
        if manifest is None or status is None:
            raise HTTPException(status_code=404, detail="Session not found")

        report_markdown = ""
        if status.report_path and Path(status.report_path).exists():
            report_markdown = Path(status.report_path).read_text(encoding="utf-8")

        return render_page(
            "session_detail.html",
            request,
            {
                "manifest": manifest.to_dict(),
                "manifest_pretty": json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
                "status": status.to_dict(),
                "report_markdown": report_markdown,
            },
        )

    return app


app = create_app()

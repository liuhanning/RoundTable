# RoundTable

RoundTable is a multi-model discussion tool with both CLI and Web MVP entrypoints.

## Current State

- CLI discussion flow is implemented and routed through a shared `DiscussionService`
- Web MVP supports settings, session creation, attachment upload, session start, status/detail view, and report readback
- Session snapshots and runtime status are persisted separately from checkpoints
- The latest DashScope integration regressions have been fixed and the regression suites are green again

## Quick Start

### 1. Install dependencies

```bash
cd roundtable
pip install -r requirements.txt
```

### 2. Configure secrets

Create or update `.env`:

```dotenv
GEMINI_API_KEY=
OPENROUTER_API_KEY=
DASHSCOPE_API_KEY=
```

Web settings will manage these values through `ConfigStore`, but the file format remains plain `.env`.

### 3. Run the CLI

```bash
python main.py run --topic "Guizhou transport planning" --project "Guizhou Project"
python main.py resume --session abc123
python main.py status --session abc123
python main.py clean --session abc123
```

### 4. Run the Web MVP

```bash
uvicorn web.app:app --reload
```

On Windows terminals, the CLI and web entrypoints now attempt to switch the console to UTF-8 automatically.
If you still see garbled Chinese output in PowerShell or CMD, run `chcp 65001` before starting the app.

Then open:

- `http://127.0.0.1:8000/settings`
- `http://127.0.0.1:8000/sessions/new`

## Web MVP Scope

- Provider secret management via `.env`
- Model enable/disable settings via `data/settings.json`
- Draft session creation
- Attachment upload with validation
- Session start and in-process execution
- Session detail page with status and report readback

## Storage Layout

```text
data/
  checkpoints/<session_id>/*.json
  sessions/<session_id>/manifest.json
  sessions/<session_id>/status.json
  settings.json
  uploads/<attachment_id>/*
output/<project_name>/
  final_report.md
  final_report.json
```

## Key Modules

- `engine/discussion_service.py`: shared execution flow for CLI and Web
- `engine/session_store.py`: manifest/status persistence
- `web/services/config_store.py`: `.env` + `settings.json` config management
- `web/services/attachment_service.py`: upload validation and extraction handling
- `web/services/task_runner.py`: in-process task execution
- `web/app.py`: FastAPI app entrypoint

## Testing

Project regression suite:

```bash
cd roundtable
python -m pytest tests/test_e2e.py -q
```

Web MVP suite:

```bash
python -m pytest \
  tests/test_discussion_service.py \
  tests/test_session_store.py \
  tests/test_structures_web.py \
  tests/test_web_config_store.py \
  tests/test_web_task_runner.py \
  tests/test_console_encoding.py \
  tests/test_attachment_service.py \
  tests/test_web_settings_api.py \
  tests/test_web_session_creation_api.py \
  tests/test_web_session_status_api.py \
  tests/test_web_pages.py \
  tests/test_web_e2e.py -q
```

Current verified results:

- `python -m pytest tests/test_e2e.py -q` -> `71 passed`
- `python -m pytest tests/test_discussion_service.py ... tests/test_console_encoding.py ... tests/test_web_e2e.py -q` -> `42 passed`

## Known Remaining Work

- Real provider manual verification is still pending
- Some production-hardening work remains around task durability and richer attachment extraction

## License

MIT

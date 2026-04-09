---
title: RT 可视化 MVP 详细设计
type: feat
status: active
date: 2026-04-01
origin: D:\worksapces\RT\docs\plans\2026-04-01-001-feat-rt-visual-mvp-plan.md
---

# RT 可视化 MVP 详细设计

## Overview

这份文档将实现计划进一步细化为可直接编码的设计约束，重点覆盖三部分：
- 核心模块职责和边界
- 核心数据结构与存储文件
- 页面与 API 契约

它的目标不是替代实现计划，而是把实现前最容易分歧的接口和状态语义定死，减少开发过程中返工。

## Problem Frame

RT 当前的业务流程集中在 CLI 中，Web MVP 要求同一套引擎同时服务于浏览器工作台和现有命令行，同时满足：
- 设置页修改不影响已启动会话
- 附件入口不绕过现有安全边界
- 运行页与结果页基于同一个会话实体
- 服务重启后运行中任务的状态语义清晰可见

因此详细设计的重点不在视觉，而在运行模型、数据快照和读写边界。

## Detailed Decisions

### 1. 模块边界

**`roundtable/engine/discussion_service.py`**
- 负责一次讨论会话的完整生命周期。
- 输入是 `SessionManifest` 与运行时配置快照。
- 输出是阶段状态更新、Checkpoint、最终报告和失败摘要。
- 不能感知 HTML、模板或具体路由。

**`roundtable/engine/session_store.py`**
- 负责保存和读取会话快照与会话状态。
- 为页面层提供最近会话列表和会话详情读模型。
- 不负责执行讨论，也不负责解析附件内容。

**`roundtable/web/services/config_store.py`**
- 负责双层配置存储：
  - `.env`：只存 API Keys 等 secrets
  - `settings.json`：只存模型启用、角色模板默认值、UI 默认选项
- 负责遮蔽输出、原子写入和默认值合并。

**`roundtable/web/services/attachment_service.py`**
- 负责上传文件的安全校验、文本提取、上下文封装和附件元数据写入。
- 不直接决定模型调用逻辑。

**`roundtable/web/services/task_runner.py`**
- 负责进程内任务注册、任务启动、状态登记和中断检测。
- 不负责持久化会话业务字段，持久化仍交给 `SessionStore`。

**`roundtable/web/app.py`**
- 作为独立 ASGI 入口装配 FastAPI app。
- 负责路由注册、模板环境、静态资源和依赖注入。
- 不承载业务流程。

### 2. 运行时原则

- 会话一旦启动，运行中读取的是启动时固化的配置快照，而不是设置页当前值。
- 设置页的修改只影响后续新建会话。
- 运行页和结果页共享同一个会话详情模型，由 `status` 决定展示内容。
- 服务重启时，任务注册表中的运行中任务视为丢失；页面看到的是 `interrupted`，而不是继续假装 `running`。

### 3. 附件处理原则

- 支持上传但不等于支持注入讨论上下文。
- `txt`、`md`、`pdf`、`docx`：
  - 允许上传
  - 尝试文本提取
  - 提取成功后包裹安全上下文进入 prompt
  - 提取失败则阻断创建
- `xlsx`、`pptx`：
  - 允许上传
  - 仅进入附件清单
  - 不参与 prompt 注入
  - 页面显式标明“未进入讨论上下文”

## Data Model

### SessionManifest

用途：会话启动前后的不可变输入快照，供运行态和结果页回看。

建议字段：

```json
{
  "session_id": "string",
  "title": "string",
  "project_name": "string",
  "task_description": "string",
  "created_at": "ISO8601",
  "created_from": "web|cli",
  "roles": [],
  "attachments": [],
  "model_snapshot": {},
  "settings_snapshot": {},
  "execution_snapshot": {}
}
```

字段说明：
- `roles`: 本次启用角色的会前副本，不回读全局模板
- `attachments`: 本次上传的附件清单与注入状态
- `model_snapshot`: 本次允许使用的模型与 provider 状态快照
- `settings_snapshot`: 会前生效的 UI 配置快照
- `execution_snapshot`: 运行时 secrets 与 provider 选择快照，不直接暴露完整 secret 到页面

### SessionStatus

用途：运行态读模型，用于最近会话列表和会话详情页。

建议字段：

```json
{
  "session_id": "string",
  "status": "draft|queued|running|completed|failed|interrupted",
  "current_stage": "string|null",
  "completed_stages": [],
  "stage_summaries": {},
  "error_summary": null,
  "next_action": null,
  "report_path": null,
  "cost_summary": {},
  "updated_at": "ISO8601"
}
```

状态语义：
- `draft`: 已创建但未启动
- `queued`: 已提交给任务注册器，等待开始
- `running`: 至少一个阶段正在执行
- `completed`: 报告已生成
- `failed`: 执行过程中出现明确失败
- `interrupted`: 服务重启或任务丢失导致执行中断

### RoleConfig

用途：一次会话中单个角色的运行配置。

```json
{
  "role_id": "planner",
  "enabled": true,
  "display_name": "规划师",
  "responsibility": "负责提出结构化方案",
  "instruction": "string",
  "model": "gemini-2.0-flash"
}
```

约束：
- `role_id` 来自内置模板
- `display_name`、`responsibility`、`instruction`、`model` 可在会前微调

### AttachmentRecord

用途：描述单个附件的状态。

```json
{
  "attachment_id": "string",
  "filename": "report.pdf",
  "extension": ".pdf",
  "size_bytes": 1024,
  "stored_path": "string",
  "classification": "public|internal|classified",
  "injection_mode": "embedded|listed_only",
  "extraction_status": "pending|ready|failed|skipped",
  "extraction_error": null
}
```

关键语义：
- `embedded`: 已进入讨论上下文
- `listed_only`: 仅在结果页和附件清单中可见，不参与讨论

### ProviderSecretState

用途：设置页显示 provider 状态，不回显明文。

```json
{
  "provider": "gemini",
  "configured": true,
  "masked_value": "sk-****abcd",
  "connection_status": "unknown|ok|failed",
  "last_checked_at": "ISO8601|null"
}
```

## Storage Layout

### `.env`

用途：
- 存储 API Keys 和其他 secrets

示例：

```dotenv
GEMINI_API_KEY=...
OPENROUTER_API_KEY=...
DASHSCOPE_API_KEY=...
```

规则：
- 由 UI 维护，不要求用户手工编辑
- 接口只返回遮蔽值

### `settings.json`

建议位置：
- `roundtable/data/settings.json`

用途：
- 存储 UI 层和产品层配置，不存 secret

示例：

```json
{
  "enabled_models": {
    "gemini-2.0-flash": true,
    "openrouter/deepseek-chat": false
  },
  "default_role_templates": {
    "planner": {
      "display_name": "规划师",
      "responsibility": "负责结构化分析",
      "instruction": "..."
    }
  }
}
```

### Session Files

建议目录：
- `roundtable/data/sessions/<session_id>/manifest.json`
- `roundtable/data/sessions/<session_id>/status.json`
- `roundtable/data/sessions/<session_id>/attachments/*`

阶段产物仍放在：
- `roundtable/data/checkpoints/<session_id>/*.json`

## API Contract

### Settings API

#### `GET /api/settings`

用途：
- 返回设置页初始化数据

响应最小字段：

```json
{
  "providers": [],
  "enabled_models": {},
  "role_template_defaults": {}
}
```

#### `POST /api/settings/secrets`

用途：
- 保存或更新 provider secrets

请求：

```json
{
  "provider": "gemini",
  "api_key": "string"
}
```

响应：

```json
{
  "provider": "gemini",
  "configured": true,
  "masked_value": "sk-****abcd"
}
```

#### `POST /api/settings/models`

用途：
- 更新模型启用状态

请求：

```json
{
  "enabled_models": {
    "gemini-2.0-flash": true,
    "openrouter/deepseek-chat": false
  }
}
```

### Session Creation API

#### `POST /api/sessions`

用途：
- 创建会话草稿

请求：

```json
{
  "title": "贵州交通规划讨论",
  "project_name": "贵州十五五",
  "task_description": "请围绕...",
  "roles": [],
  "attachment_ids": []
}
```

响应：

```json
{
  "session_id": "abc123",
  "status": "draft"
}
```

#### `POST /api/sessions/{session_id}/start`

用途：
- 将草稿会话提交到任务注册器

响应：

```json
{
  "session_id": "abc123",
  "status": "queued"
}
```

### Attachment API

#### `POST /api/attachments`

用途：
- 上传并校验单个附件

响应最小字段：

```json
{
  "attachment_id": "att-001",
  "filename": "report.pdf",
  "injection_mode": "embedded",
  "extraction_status": "ready"
}
```

### Session Detail API

#### `GET /api/sessions`

用途：
- 返回最近会话列表

响应项最小字段：

```json
{
  "session_id": "abc123",
  "title": "string",
  "status": "running",
  "current_stage": "blue_team",
  "updated_at": "ISO8601"
}
```

#### `GET /api/sessions/{session_id}`

用途：
- 返回会话详情页所需全部数据

响应最小字段：

```json
{
  "manifest": {},
  "status": {},
  "report_markdown": "# title",
  "checkpoints": []
}
```

## Page Contract

### 1. 设置页 `/settings`

区块：
- Provider Key 设置区
- 模型启用开关区
- 默认角色模板区

交互：
- 保存 secret
- 测试连接
- 保存模型启用状态

错误反馈：
- provider 保存失败
- 连接测试失败
- 模型配置非法

### 2. 新建会议页 `/sessions/new`

区块：
- 任务基础信息
- 附件上传区
- 角色模板卡片区
- 启动按钮区

交互：
- 上传附件
- 编辑角色名称/职责/指令/模型
- 启用/禁用角色
- 创建草稿
- 启动会议

阻断条件：
- 无可用模型
- 角色绑定了禁用模型
- 可注入附件提取失败
- 缺少必填任务字段

### 3. 会话详情页 `/sessions/{session_id}`

状态区块：
- 顶部状态摘要
- 阶段时间线
- 当前阶段摘要
- 失败/中断提示
- 结果报告区
- 配置回看区
- 附件清单区

状态分支：
- `draft`: 展示启动入口
- `queued/running`: 展示阶段进展与轮询状态
- `completed`: 展示报告与配置回看
- `failed/interrupted`: 展示错误摘要、最后阶段、下一步动作

## Test Design

### First-Wave Tests

优先先写这些服务/API 契约测试，再写页面层测试：

- `roundtable/tests/test_session_store.py`
  - 保存/读取 manifest
  - 保存/读取 status
  - 最近会话列表排序

- `roundtable/tests/test_discussion_service.py`
  - 启动时固化运行时快照
  - 成功完成一次会话
  - 单阶段失败时写入失败状态

- `roundtable/tests/test_web_config_store.py`
  - `.env` secret 保存与遮蔽输出
  - `settings.json` 默认值与覆盖

- `roundtable/tests/test_attachment_service.py`
  - 支持类型与不注入类型分支
  - 提取失败阻断
  - 文件校验失败阻断

- `roundtable/tests/test_web_session_creation_api.py`
  - 创建草稿
  - 角色模型合法性校验
  - 草稿启动

- `roundtable/tests/test_web_session_status_api.py`
  - 最近会话列表
  - 运行态轮询
  - `failed/interrupted` 状态返回

### Later Tests

- `roundtable/tests/test_web_pages.py`
  - 页面路由可达
  - 模板渲染包含关键状态

- `roundtable/tests/test_web_e2e.py`
  - 保存配置 -> 创建会话 -> 启动 -> 完成 -> 查看结果

## Sequencing

推荐执行顺序：

1. `structures.py` + `session_store.py` + `discussion_service.py`
2. `config_store.py` + `config.py` reload/reset
3. `attachment_service.py` + sessions create API
4. `task_runner.py` + session detail/list API
5. `web/app.py` + templates + static assets
6. e2e 测试与文档更新

## Out of Scope Confirmations

- 不设计独立前端状态管理层
- 不设计 WebSocket 事件流协议
- 不设计多用户权限模型
- 不设计会议后二次编辑复跑
- 不设计完整知识库管理页

## Next Step

按这份详细设计开始实现时，第一批代码应从服务层和数据契约入手，而不是先写模板页面。

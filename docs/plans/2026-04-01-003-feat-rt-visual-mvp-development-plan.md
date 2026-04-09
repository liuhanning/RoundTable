---
title: RT 可视化 MVP 开发计划
type: feat
status: active
date: 2026-04-01
origin: D:\worksapces\RT\docs\plans\2026-04-01-002-feat-rt-visual-mvp-detailed-design.md
---

# RT 可视化 MVP 开发计划

## Goal

按“先固化公用基础，再并行开发实现层，最后联调收口”的方式推进 RT 可视化 MVP，降低前后端返工风险。

## Development Strategy

### 总原则

- 先串行做契约层和公共基础。
- 契约层稳定后，再并行做后端实现和前端页面。
- 最后统一联调、补测试和文档。

### 为什么这样安排

这个项目当前最大的风险不是页面难画，而是：
- 会话状态模型还没有真正落地到代码
- 运行态快照和设置页配置之间容易打架
- 进程内任务、中断语义、结果回看都依赖统一的数据契约

如果这些基础不先坐实，前端、API、后端同时开工只会造成反复改接口。

## Phase Plan

## Phase 0: 契约冻结

**目标**
- 把所有并行开发都会依赖的公共契约先固定下来。

**范围**
- `SessionManifest`
- `SessionStatus`
- `RoleConfig`
- `AttachmentRecord`
- 状态枚举：`draft|queued|running|completed|failed|interrupted`
- 设置页、会话列表、会话详情的最小 API 响应结构

**产出**
- 公共数据结构定义
- 详细设计文档确认版
- API shape 确认版

**完成标准**
- 前端和后端对同一份状态模型开发，不再各自发明字段。

## Phase 1: 基础设施串行落地

**目标**
- 先把所有实现层共享的基础模块做稳。

**任务**
1. 实现 `structures.py` 中新增的会话相关结构。
2. 实现 `session_store.py`。
3. 抽离 `discussion_service.py`，让 CLI 复用它。
4. 实现 `config_store.py`。
5. 给 `config.py` 增加 reload/reset。
6. 实现 `task_runner.py` 的基础能力，但先不接页面。

**这一阶段为什么必须串行**
- `SessionStore` 和 `DiscussionService` 会决定 API 能返回什么。
- `ConfigStore` 会决定设置页能提交什么。
- `TaskRunner` 会决定会话详情页如何轮询状态。

**测试**
- `test_session_store.py`
- `test_discussion_service.py`
- `test_web_config_store.py`
- `test_web_task_runner.py`

**完成标准**
- CLI 已切到 `DiscussionService`
- 会话快照与状态文件能稳定落盘
- 配置修改后运行态能正确刷新

## Phase 2: 实现层并行开发

从这一阶段开始，分成两条并行线。

### Track A: 后端/API

**目标**
- 把基础模块接成真正可用的 Web 能力。

**任务**
1. 实现 `attachment_service.py`
2. 实现 `/api/settings`
3. 实现 `/api/attachments`
4. 实现 `/api/sessions`
5. 实现 `/api/sessions/{id}`
6. 实现最近会话列表接口

**重点约束**
- 运行中会话只读启动时快照
- `txt/md/pdf/docx` 可注入
- `xlsx/pptx` 只列出不注入
- 服务重启后会话状态转 `interrupted`

**测试**
- `test_attachment_service.py`
- `test_web_settings_api.py`
- `test_web_session_creation_api.py`
- `test_web_session_status_api.py`

### Track B: 前端/页面

**目标**
- 基于已经冻结的契约实现可用页面，不等待后端全部完成后才开始。

**任务**
1. 实现 `base.html`
2. 实现 `settings.html`
3. 实现 `session_new.html`
4. 实现 `session_detail.html`
5. 实现 `app.css`
6. 实现 `app.js` 的基础交互

**页面只依赖这些稳定契约**
- 设置页初始化数据结构
- 会话创建请求结构
- 会话状态轮询结构
- 最近会话列表最小字段集

**重点约束**
- 不在前端发明新的状态字段
- 不做复杂客户端状态管理
- 不做角色级实时消息流

**测试**
- `test_web_pages.py`

## Phase 3: 联调与收口

**目标**
- 把并行开发的后端和前端接起来，完成完整闭环。

**任务**
1. 接通 `web/app.py`
2. 联调设置页和真实配置存储
3. 联调新建会议页和附件上传
4. 联调会话详情页和状态轮询
5. 联调结果页和 Markdown 报告展示
6. 修复字段命名、错误反馈和状态切换问题

**测试**
- `test_web_e2e.py`

**完成标准**
- 用户能在浏览器中完成：
  - 配置 Key
  - 启用模型
  - 配置角色
  - 上传附件
  - 发起会议
  - 查看阶段进度
  - 查看最终结果

## Phase 4: 文档与验收

**目标**
- 让 MVP 可运行、可说明、可交接。

**任务**
1. 更新 `README.md`
2. 更新 `roundtable/docs/PROGRESS.md`
3. 补运行说明和排障说明
4. 进行一次真实 provider 手工验收

**验收结论分两类**
- 完整验收：界面闭环 + 至少一条真实 provider 跑通
- 部分验收：界面闭环完成，但真实 provider 仍待验证

## Parallelization Rules

### 可以并行的前提

只有在以下内容已经稳定后，前后端才开始并行：
- 会话状态模型
- API 最小响应结构
- 配置存储职责边界
- 附件注入策略

### 不允许过早并行的部分

- `SessionStatus` 未定前，不开始会话详情页真实交互
- `ConfigStore` 未定前，不开始设置页真实保存逻辑
- `AttachmentService` 未定前，不开始附件上传联调

## Deliverables by Phase

### Phase 0-1 完成后
- 后端公共骨架稳定
- CLI 已接新服务层
- 测试覆盖基础契约

### Phase 2 完成后
- API 可用
- 页面骨架可用
- 前后端可以进入联调

### Phase 3 完成后
- 浏览器闭环打通
- MVP 功能完成

### Phase 4 完成后
- 可交付、可演示、可继续迭代

## Execution Order

推荐实际执行顺序：

1. `structures.py`
2. `session_store.py`
3. `discussion_service.py`
4. `config_store.py`
5. `config.py` reload/reset
6. `task_runner.py`
7. 后端 API 与前端页面并行
8. `web/app.py` 联调
9. e2e 与文档

## Next Step

按这份开发计划，下一步应直接开始 Phase 1，也就是先实现公用基础模块，而不是先写页面。

---
title: RT 可视化 MVP 测试计划
type: feat
status: active
date: 2026-04-01
origin: D:\worksapces\RT\docs\plans\2026-04-01-003-feat-rt-visual-mvp-development-plan.md
---

# RT 可视化 MVP 测试计划

## Goal

确保 RT 可视化 MVP 在“基础模块稳定、接口契约稳定、页面闭环稳定”三个层面都可验证，而不是只在最后做一次端到端检查。

## Test Strategy

### 总原则

- 每个开发阶段都有对应测试，不把测试堆到最后。
- 先测契约和状态模型，再测页面和联调。
- 单元测试优先覆盖共享基础模块。
- API 测试优先覆盖前后端共享契约。
- e2e 只验证关键闭环，不替代底层测试。

### 测试层次

1. 单元测试
   - 数据结构
   - 存储层
   - 服务层
   - 配置层
   - 附件处理

2. API/契约测试
   - 设置接口
   - 会话创建接口
   - 会话状态接口
   - 列表接口

3. 页面测试
   - 页面可达
   - 关键状态可见
   - 表单字段存在

4. 端到端测试
   - 从配置到结果查看的闭环

## Phase Test Plan

## Phase 0: 契约冻结测试

**目标**
- 确保状态模型、请求结构、响应结构不含歧义。

**测试内容**
- 结构序列化/反序列化测试
- 状态枚举值测试
- 字段必填/可选项测试

**建议文件**
- `roundtable/tests/test_structures_web.py`

**必须覆盖**
- `SessionManifest`
- `SessionStatus`
- `RoleConfig`
- `AttachmentRecord`
- 状态枚举：`draft|queued|running|completed|failed|interrupted`

**准入标准**
- 所有基础结构都能稳定 `to_dict/from_dict`
- 状态值不依赖页面层临时拼接

## Phase 1: 公用基础模块测试

**目标**
- 确保共享基础层稳定，再开放并行开发。

### 1. `SessionStore`

**测试文件**
- `roundtable/tests/test_session_store.py`

**测试点**
- 保存 `manifest.json`
- 保存 `status.json`
- 读取单个会话详情
- 最近会话列表按更新时间排序
- 缺失文件时优雅降级

### 2. `DiscussionService`

**测试文件**
- `roundtable/tests/test_discussion_service.py`

**测试点**
- 启动时固化运行时快照
- 正常完成一次讨论
- 单阶段失败写入 `failed`
- 全局配置变化不影响运行中会话
- 报告路径和阶段摘要写入正确
- 运行时快照不会把完整 secret 写入 `manifest/status` 或对外 API 可读数据

### 3. `ConfigStore`

**测试文件**
- `roundtable/tests/test_web_config_store.py`

**测试点**
- `.env` secrets 保存与覆盖
- `settings.json` 配置保存与覆盖
- 遮蔽输出不回显完整 Key
- reload/reset 后新配置可读
- secret 和 UI 配置分层读取
- `settings.json` 缺失时能回填默认值
- `settings.json` 损坏时能优雅降级并返回明确错误

### 4. `TaskRunner`

**测试文件**
- `roundtable/tests/test_web_task_runner.py`

**测试点**
- 注册任务
- 查询任务状态
- 任务结束后状态更新
- 模拟重启后运行中任务转 `interrupted`
- 冷启动读取残留运行态时，持久层状态也会被修正为 `interrupted`

**Phase 1 准入标准**
- 共享模块测试通过后，才进入前后端并行开发

## Phase 2A: 后端/API 测试

**目标**
- 确保接口契约稳定，前端可安全接入。

### 设置接口

**测试文件**
- `roundtable/tests/test_web_settings_api.py`

**测试点**
- 获取设置初始化数据
- 保存 provider secret
- 保存模型启用状态
- 非法输入错误返回
- 响应中不泄露 secret

### 附件接口

**测试文件**
- `roundtable/tests/test_attachment_service.py`
- `roundtable/tests/test_web_attachments_api.py`

**测试点**
- `txt/md/pdf/docx` 提取成功后可注入
- `xlsx/pptx` 仅进入清单
- 文件类型非法时拒绝
- 魔法字节不匹配时拒绝
- 文本提取失败时阻断

### 会话创建接口

**测试文件**
- `roundtable/tests/test_web_session_creation_api.py`

**测试点**
- 创建草稿会话
- 角色绑定禁用模型时报错
- 附件元数据正确进入快照
- 启动会话后状态变 `queued`

### 会话状态接口

**测试文件**
- `roundtable/tests/test_web_session_status_api.py`

**测试点**
- 最近会话列表返回最小字段集
- 最近会话列表作为摘要接口，只允许返回 `session_id`、标题、状态、当前/最后阶段、更新时间、结果入口等摘要字段
- 最近会话列表不得返回 `manifest` 全量内容、`execution_snapshot`、完整附件内容、原始 prompt、完整错误堆栈或任何 secret 相关字段
- 详情页返回 manifest/status/report
- 运行中轮询返回当前阶段
- `failed/interrupted` 状态返回错误摘要与下一步动作
- 结果页读取的是启动时快照
- 列表接口和详情接口都不泄露完整 secret

**Phase 2A 准入标准**
- API 字段名、状态值、错误结构不再频繁变动

## Phase 2B: 前端/页面测试

**目标**
- 确保页面骨架与状态展示正确，不等联调后才发现基础问题。

**测试文件**
- `roundtable/tests/test_web_pages.py`

**测试点**
- `/settings` 可访问
- `/sessions/new` 可访问
- `/sessions/{id}` 可访问
- 页面包含关键表单字段和状态区块
- 无脚本场景下关键内容可读
- `failed` 状态时页面显示失败阶段、错误摘要和下一步动作
- `interrupted` 状态时页面显示中断说明和恢复/重试提示

**额外人工检查**
- 设置页能看见 provider 状态和保存入口
- 新建会议页能看见任务字段、附件区、角色卡片
- 会话详情页能看见阶段时间线和结果区

**Phase 2B 准入标准**
- 页面骨架完整
- 不新增未定义字段依赖

## Phase 3: 联调测试

**目标**
- 验证后端接口与前端页面真正连起来后，用户流程仍然正确。

**测试文件**
- `roundtable/tests/test_web_e2e.py`

**测试点**
- 保存设置 -> 创建草稿 -> 启动会话 -> 轮询完成 -> 查看结果
- 附件上传失败时前端能收到可读错误
- 无可用模型时创建页被阻断
- 会话失败时详情页显示失败阶段和下一步动作
- 服务重启后会话显示 `interrupted`

**人工联调检查**
- 轮询不会把页面刷乱
- 报告 Markdown 渲染可读
- 配置回看和附件清单可见

**Phase 3 准入标准**
- 浏览器闭环跑通

## Phase 4: 验收测试

**目标**
- 确认 MVP 具备交付条件。

### 自动化验收

- 全部单元/API/页面/e2e 测试通过

### 手工验收

1. 配置至少一个真实 provider
2. 创建一场最小会议
3. 上传至少一个支持注入的附件
4. 上传至少一个 `xlsx` 或 `pptx`，确认其仅进入附件清单而不进入讨论上下文
5. 观察阶段推进
6. 查看最终结果与配置回看

### 验收结论

- 完整通过：真实 provider 跑通
- 有条件通过：自动化通过，但真实 provider 仍需补验

## Test Commands

详细命令后续可在 README 里补，这里先定义测试分组：

- 基础结构与服务层
- 配置与附件
- API 契约
- 页面
- e2e

## Exit Criteria

只有在以下条件同时满足时，才算测试计划完成：

- Phase 0-3 的测试都已落地
- 关键失败路径都有测试
- `interrupted`、`failed`、配置快照、附件注入状态都有验证
- 至少完成一次手工验收

## Next Step

按这份测试计划，开发实施时应从 Phase 1 的基础模块测试开始，而不是先写页面测试。

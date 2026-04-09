# RoundTable CLI MVP 开发进度记录

**最后更新时间**: 2026-04-07
**当前状态**: RT 可视化 MVP 的 CLI 与 Web 主链路可运行，最近一轮 DashScope 接入引入的回归已修复，当前测试重新转绿；下一步优先补真实 provider 验证与剩余技术债

---

## 已完成工作

### P0 安全修复（100% 完成）
- [x] 配置管理 - API Key 环境变量加载 (`config.py`)
- [x] Prompt 注入防护 (`utils/prompt_injection.py`)
- [x] 文件上传验证 - 白名单 + 魔法字节 (`utils/file_validator.py`)
- [x] 日志脱敏 - 敏感信息过滤 (`utils/logger.py`)
- [x] Qdrant 安全访问控制 (`knowledge/store.py`)
- [x] 数据分级服务 (`knowledge/classifier.py`)

### CLI MVP 核心功能（100% 完成）
- [x] Unit 1: 多模型调用封装 (`engine/models.py`)
  - GeminiClient (Google 直连)
  - OpenRouterClient (GPT/DeepSeek)
  - ModelClient 统一客户端 + 故障切换链
- [x] Unit 2: 蓝军质询 (`engine/blue_team.py`)
  - challenge() 对独立输出进行质询
  - final_review() 对共识草案进行终审
- [x] 数据结构定义 (`engine/structures.py`)
  - RoundOutput, ChallengeReport, RoundSummary, Checkpoint, FinalReport
- [x] Unit 4: Checkpoint 断点续跑 (`engine/checkpoint.py`)
  - 原子写入机制
  - 恢复信息计算
- [x] Unit 5: 成本追踪 (`engine/cost_tracker.py`)
  - 80% 预算预警
  - 100% 降级到免费模型
- [x] Unit 6: CLI 入口 (`cli/main.py`, `main.py`)
  - 命令：run, resume, status, clean

### 测试覆盖（100% 通过）
- [x] 70 个测试用例全部通过
- [x] 覆盖 7 个模块：多模型调用、蓝军质询、Checkpoint、成本追踪、CLI、数据结构、重试机制
- [x] 覆盖类型：Happy Path + 边界条件 + 异常路径 + 集成场景

### 文档与配置
- [x] README.md - 使用说明
- [x] requirements.txt - 依赖配置
- [x] .gitignore - 排除数据目录

---

## 今日完成 (2026-03-31)

### P1-2: 错误重试与降级机制 ✅ 100% 完成
- **实现内容**
  - 新增 `RetryConfig` dataclass（max_retries=3, initial_delay=1s, backoff_multiplier=2.0, max_delay=30s）
  - 在 `ModelClient.call()` 中实现指数退避重试循环
  - 区分三种错误处理策略：
    - `retryable=True` 且 `fallback_model=None` → 重试同一提供商（指数退避）
    - `retryable=True` 且 `fallback_model=xxx` → 立即切换下一提供商
    - `retryable=False` → 直接切换，不重试
  - 添加重试日志和审计事件追踪

- **测试覆盖**（9 个测试用例全部通过）
  - `test_retry_config_default_values` - 默认配置验证
  - `test_retry_config_custom_values` - 自定义配置验证
  - `test_model_client_accepts_retry_config` - 配置注入验证
  - `test_retry_on_timeout` - 超时错误触发重试
  - `test_retry_on_5xx_error` - 5xx 错误触发重试
  - `test_no_retry_on_4xx_error` - 4xx 错误不重试
  - `test_retry_exhausted_then_fallback` - 重试用尽后切换
  - `test_retry_then_success` - 重试后成功
  - `test_fallback_model_immediate_switch` - 有 fallback_model 立即切换

- **文件修改**
  - `engine/models.py`: 新增 `RetryConfig`、`DashScopeClient`，更新 `ModelClient.call()` 重试逻辑
  - `tests/test_e2e.py`: 新增 `TestRetryMechanism` 测试类
  - `config.py`: 新增阿里百炼配置支持

- **测试结果**: 70 个测试用例全部通过

### 真实 API 调用测试 ⚠️ 阻塞
- 尝试使用阿里百炼 API Key (`sk-sp-09c9278443f74017a7bd6b0c6455a19b`)
- 返回错误：`Invalid API-key provided` (401 Unauthorized)
- **原因**: API Key 无效或已过期
- **待办**: 需要获取有效的 API Key（阿里百炼/Gemini/OpenRouter）

---

## 今日完成 (2026-04-01)

### RT 可视化 MVP - Web API / 页面 / 联调 ✅ 已完成
- **已完成内容**
  - 新增 `web/app.py`，提供独立 FastAPI 入口
  - 实现设置相关 API：
    - `GET /api/settings`
    - `POST /api/settings/secrets`
    - `POST /api/settings/models`
  - 实现附件与会话相关 API：
    - `POST /api/attachments`
    - `POST /api/sessions`
    - `POST /api/sessions/{session_id}/start`
    - `GET /api/sessions`
    - `GET /api/sessions/{session_id}`
  - 新增 `AttachmentService`
    - 复用现有 `file_validator`
    - 对 `txt/md/pdf/docx` 做提取并安全包裹
    - 对 `xlsx/pptx` 保持 `listed_only`
  - 新增 `TaskRunner`
    - 提供进程内任务启动能力
    - 启动时自动将残留运行态会话标记为 `interrupted`
  - 新增页面与静态资源：
    - `templates/base.html`
    - `templates/settings.html`
    - `templates/session_new.html`
    - `templates/session_detail.html`
    - `static/app.css`
    - `static/app.js`
  - 新增 `role_templates.py`
  - `requirements.txt` 已补充 `jinja2` 与 `python-multipart`

- **新增测试**
  - `tests/test_attachment_service.py`
  - `tests/test_web_settings_api.py`
  - `tests/test_web_session_creation_api.py`
  - `tests/test_web_session_status_api.py`
  - `tests/test_web_pages.py`
  - `tests/test_web_e2e.py`

- **测试结果**
  - 命令：`cd roundtable && python -m pytest tests/test_e2e.py -q`
  - 结果：`71 passed`
  - 命令：`python -m pytest roundtable/tests/test_discussion_service.py roundtable/tests/test_session_store.py roundtable/tests/test_structures_web.py roundtable/tests/test_web_config_store.py roundtable/tests/test_attachment_service.py roundtable/tests/test_web_settings_api.py roundtable/tests/test_web_session_creation_api.py roundtable/tests/test_web_session_status_api.py roundtable/tests/test_web_pages.py roundtable/tests/test_web_e2e.py -q`
  - 结果：`38 passed`

- **本次修改文件**
  - `web/app.py`
  - `web/role_templates.py`
  - `web/services/attachment_service.py`
  - `web/services/task_runner.py`
  - `web/templates/*`
  - `web/static/*`
  - `tests/test_attachment_service.py`
  - `tests/test_web_settings_api.py`
  - `tests/test_web_session_creation_api.py`
  - `tests/test_web_session_status_api.py`
  - `tests/test_web_pages.py`
  - `tests/test_web_e2e.py`

- **意义**
  - 用户已经可以在浏览器中完成设置、建会话、启动执行、查看详情与结果回看
  - Web MVP 不再只是设计稿或服务层预备，而是具备可运行的最小产品闭环
  - 后续重点已从“搭骨架”转为“真实 provider 验证、附件能力扩展、技术债收口”

## 今日完成 (2026-04-07)

### 回归修复与测试收口（100% 完成）
- **已完成内容**
  - 修复 `config.py` 的 provider secret 读取逻辑
    - 显式置空环境变量时不再回退到 `.env`
    - `get_model_config()` 每次调用都会刷新 env/.env，避免测试与运行时读到旧缓存
  - 修复 `engine/models.py` 的 fallback 行为
    - 默认链路调整为 `gemini -> openrouter -> dashscope`
    - `fallback_model` 不再只是跳出当前 provider，而是会定向切到指定 provider
    - 修正 Gemini / OpenRouter 异常路径中的旧 fallback 目标，避免跳转到已不在主链路中的 provider
  - 修复 `utils/console_encoding.py` 的 Windows 管道输出兼容
    - 仅在交互式终端下切换 UTF-8
    - 避免 CLI 子进程在 `subprocess(..., text=True)` 下触发 `UnicodeDecodeError`
  - 更新 `tests/test_console_encoding.py` 与 `tests/test_e2e.py`
    - 覆盖新的终端判断逻辑
    - 新增 Gemini / OpenRouter 异常 fallback 目标断言

- **修复的回归问题**
  - `test_gemini_client_no_api_key`
  - `test_cli_resume_nonexistent`
  - `test_cli_status_nonexistent`
  - `test_no_retry_on_4xx_error`
  - `test_retry_exhausted_then_fallback`
  - `test_fallback_model_immediate_switch`

- **测试结果**
  - 命令：`cd roundtable && python -m pytest tests/test_e2e.py -q`
  - 结果：`71 passed`
  - 命令：`cd roundtable && python -m pytest tests/test_discussion_service.py tests/test_session_store.py tests/test_structures_web.py tests/test_web_config_store.py tests/test_web_task_runner.py tests/test_attachment_service.py tests/test_web_settings_api.py tests/test_web_session_creation_api.py tests/test_web_session_status_api.py tests/test_web_pages.py tests/test_web_e2e.py tests/test_console_encoding.py -q`
  - 结果：`42 passed`

- **本次修改文件**
  - `config.py`
  - `engine/models.py`
  - `utils/console_encoding.py`
  - `tests/test_e2e.py`
  - `tests/test_console_encoding.py`

- **意义**
  - DashScope 接入后的主干回归已经收口，CLI 与 Web 相关测试重新恢复绿色
  - 当前阻塞项已经从“回归修复”收敛回“真实 provider 验证、附件能力扩展、技术债收口”

### RT 可视化 MVP - Phase 1 配置中心 ✅ 已完成
- **已完成内容**
  - 新增 `web/services/config_store.py`
  - 实现 `.env` 与 `settings.json` 双层配置存储
  - 将 provider secret 管理收口到 `ConfigStore`
  - 支持 provider 状态读取、遮罩显示、定向清除
  - 重写 `config.py`
    - 新增 `get_config_store()`
    - 新增 `set_config_paths()`
    - 新增 `reset_config_cache()`
    - 新增 `reload_config()`
    - `get_model_config()` 改为优先读取进程环境变量，其次读取受管 `.env`
  - 保持现有 `engine/models.py`、`engine/cost_tracker.py` 等调用方接口不变

- **新增测试**
  - `tests/test_web_config_store.py`
    - 覆盖 secret 写入与遮罩输出
    - 覆盖按 provider 定向清理 secret
    - 覆盖 `settings.json` 默认值合并
    - 覆盖 `config.py` 的 reload/path override/env override

- **测试结果**
  - 命令：`python -m pytest roundtable/tests/test_web_config_store.py -q`
  - 结果：`6 passed`
  - 命令：`cd roundtable && python -m pytest tests/test_e2e.py -q`
  - 结果：`70 passed`
  - 命令：`python -m pytest roundtable/tests/test_discussion_service.py roundtable/tests/test_session_store.py roundtable/tests/test_structures_web.py roundtable/tests/test_web_config_store.py -q`
  - 结果：`24 passed`

- **本次修改文件**
  - `web/services/config_store.py`
  - `web/__init__.py`
  - `web/services/__init__.py`
  - `config.py`
  - `tests/test_web_config_store.py`

- **意义**
  - 后续设置页与设置 API 已有稳定的底层读写能力
  - 运行时配置缓存可以安全刷新，不需要通过重启进程才能生效
  - `.env` secret 与 `settings.json` 产品配置职责已经明确分层

### RT 可视化 MVP - Phase 1 服务层抽离 ✅ 已完成
- **已完成内容**
  - 新增 `engine/discussion_service.py`
  - 将 CLI 中的 4 个阶段执行流程下沉到 `DiscussionService`
  - 将 `SessionManifest / SessionStatus` 接入真实执行流程
  - 在服务层统一落盘：
    - `manifest.json`
    - `status.json`
    - `Checkpoint`
    - `final_report.md`
    - `final_report.json`
  - CLI `cli/main.py` 已改为薄封装，仅负责参数解析、输出展示与服务调用
  - `clean_session()` 已统一清理 checkpoint 与 session snapshot，并修复“不存在会话误报成功”的问题

- **新增测试**
  - `tests/test_discussion_service.py`
    - 覆盖成功路径下的 manifest/status/report 持久化
    - 覆盖阶段失败时的 `failed` 状态落盘
    - 覆盖清理 checkpoint 与 session snapshot

- **测试结果**
  - 命令：`cd roundtable && python -m pytest tests/test_e2e.py -q`
  - 结果：`70 passed`
  - 命令：`python -m pytest roundtable/tests/test_discussion_service.py roundtable/tests/test_session_store.py roundtable/tests/test_structures_web.py -q`
  - 结果：`18 passed`

- **本次修改文件**
  - `engine/discussion_service.py`
  - `cli/main.py`
  - `tests/test_discussion_service.py`

- **意义**
  - CLI 与 Web 后续将共享同一条真实执行链路
  - ConfigStore、Web API、页面联调可以直接建立在服务层之上
  - 会话快照与运行状态不再只是设计契约，而是已经进入实际执行路径

### RT 可视化 MVP - Phase 1 基础契约层 ✅ 已开始
- **已完成内容**
  - 完成 Web 会话核心数据结构设计并落地到 `engine/structures.py`
  - 新增 `SessionStatusType` 状态枚举：`draft / queued / running / completed / failed / interrupted`
  - 新增 Web 侧 dataclass：
    - `RoleConfig`
    - `AttachmentRecord`
    - `ProviderSecretState`
    - `SessionManifest`
    - `SessionStatus`
  - 新增 `utc_now_iso()`，开始替换新的 UTC 时间生成方式
  - 新增 `engine/session_store.py`
    - 保存/读取 `manifest.json`
    - 保存/读取 `status.json`
    - 返回最近会话摘要列表
    - 将残留 `running/queued` 会话标记为 `interrupted`

- **新增测试**
  - `tests/test_structures_web.py`
    - 覆盖 Web 会话结构的序列化/反序列化
    - 覆盖 `SessionStatusType` 枚举值
  - `tests/test_session_store.py`
    - 覆盖 manifest/status 保存与读取
    - 覆盖最近会话列表排序
    - 覆盖缺失文件降级
    - 覆盖 `interrupted` 标记逻辑

- **测试结果**
  - 命令：`python -m pytest roundtable/tests/test_structures_web.py roundtable/tests/test_session_store.py -v`
  - 结果：`15 passed`

- **本次修改文件**
  - `engine/structures.py`
  - `engine/session_store.py`
  - `tests/test_structures_web.py`
  - `tests/test_session_store.py`

- **意义**
  - Web MVP 的契约层已开始稳定化
  - 后续 `DiscussionService`、API、前端页面可建立在统一的会话快照和状态模型上
  - 当前仍未进入页面开发，优先继续完成共享基础模块

---

## 待完成工作

### P1 功能（优先级高）
- [x] BGE-M3 本地 Embedding 备选方案
- [x] 错误重试与降级机制

### P2 功能（优先级中）
- [ ] 真实 API 调用验证（阻塞）
  - 需要有效的 API Key
  - 可选平台：阿里百炼、Google Gemini、OpenRouter
- [ ] Web UI 实现
- [ ] 多轮辩论支持
- [ ] 知识库检索集成

### P2 功能（优先级中）
- [ ] Web UI 实现（路线已更新）
  - 独立入口：`web/app.py`
  - FastAPI + Jinja2 模板 + 原生 JS
  - 轮询式阶段进度展示
  - 双层配置：`.env` + `settings.json`
- [ ] 多轮辩论支持
  - 当前仅支持单轮
  - 需要实现轮次循环
- [ ] 知识库检索集成
  - RAG 检索注入到 prompt
  - 当前已有框架但未完全集成

### 技术债务
- [x] 修复 `datetime.utcnow()` 弃用警告
  - 已替换为 `datetime.now(timezone.utc)` 或统一 `utc_now_iso()` 写法
  - 已覆盖 `structures.py`, `logger.py`, `cost_tracker.py`
- [ ] 配置热重载
  - 当前配置加载后不可动态修改
- [ ] 性能优化
  - 并发调用优化
  - 批量向量化

---

## 关键设计决策

### 模型调用故障切换链
```
gemini (免费) → openrouter (付费) → dashscope (备选)
```

### 5 阶段简化流程
```
Stage 0: 项目准备 → 上传资料 → 向量化
Stage 1: 独立思考 → 多模型并发输出
Stage 2: 蓝军质询 → 破坏性拆解
Stage 3: 汇总共识 → 整合观点
Stage 4: 报告撰写 → 最终输出
```

### 成本控制
- 默认预算：$0.50/会话
- 80% 预警：触发日志告警
- 100% 用尽：强制降级到免费模型 (Gemini)

---

## 已知问题

1. **Windows 控制台编码问题** (已基本收口)
   - 仓库文件本身为 UTF-8，乱码主要出现在 Windows GBK 控制台输出链路
   - CLI 与 Web 入口已增加 UTF-8 控制台初始化
   - 如果本地 PowerShell / CMD 仍显示异常，可先执行 `chcp 65001`

2. **Checkpoint 原子写入冲突**
   - 快速连续保存时可能出现文件存在错误
   - 测试中已通过删除后重建规避

3. **ModelError 继承关系**
   - 已从 dataclass 改为继承 Exception
   - 影响：需要用 `raise ModelError(...)` 而非返回

---

## 下一步行动（按优先级）

### 下一步待办
1. **继续 RT 可视化 MVP Phase 1**
   - 已完成 `DiscussionService` 抽离
   - 已完成 CLI 复用服务层
   - 已完成 `SessionManifest / SessionStatus` 接入真实执行流程

2. **实现配置中心基础能力**
   - 已完成 `ConfigStore`
   - 已完成 `.env` / `settings.json` 双层配置存储
   - 已完成 `config.py` reload/reset

3. **获取有效 API Key**（阻塞项）
   - 方案 A: 阿里百炼控制台重新生成 Key https://bailian.console.aliyun.com/
   - 方案 B: 注册 Google Gemini API（免费）https://aistudio.google.com/apikey
   - 方案 C: 注册 OpenRouter API https://openrouter.ai/keys

4. **验证真实 API 调用**
   - 运行完整流程：`python main.py run --topic "贵州十五五综合交通规划"`
   - 验证重试机制在真实网络环境下的行为
   - 验证故障切换链工作正常

5. **P2-1: Web UI 原型**
   - 已完成 API、页面与最小联调
   - 后续重点：真实 provider 验证、附件能力增强、稳定性收口

### 技术债务
- [x] 修复 `datetime.utcnow()` 弃用警告
  - 已替换完成
  - 已覆盖文件：`structures.py`, `logger.py`, `cost_tracker.py`
- [ ] 配置热重载
- [ ] 性能优化

---

## 测试运行命令

```bash
cd D:/worksapces/RT/roundtable

# 运行全部测试（70 个用例）
python -m pytest tests/test_e2e.py -v

# 运行重试机制测试
python -m pytest tests/test_e2e.py::TestRetryMechanism -v

# 真实 API 调用测试（需要有效 API Key）
export GEMINI_API_KEY=你的 key
python main.py run --topic "贵州十五五综合交通规划" --project "贵州省交通运输厅"
```

---

## 环境配置

### API Key 配置
创建 `.env` 文件（已在 `roundtable/.env` 创建）：
```bash
# Gemini API Key (Google) - 免费
GEMINI_API_KEY=

# OpenRouter API Key (GPT, DeepSeek 等) - 有免费额度
OPENROUTER_API_KEY=

# 阿里百炼 API Key (通义千问)
DASHSCOPE_API_KEY=  # ⚠️ 原 Key 已失效，需重新生成
```

### 获取 API Key
| 平台 | 地址 | 费用 |
|------|------|------|
| Google Gemini | https://aistudio.google.com/apikey | 免费 |
| OpenRouter | https://openrouter.ai/keys | 有免费额度 |
| 阿里百炼 | https://bailian.console.aliyun.com/ | 付费 |

---

## 环境要求

- Python 3.10+
- 依赖：`pip install -r requirements.txt`
- 环境变量：`.env` 文件配置 API Key

---

## 会话交接说明

下次继续开发时：
1. 读取本文件了解进度
2. 优先读取以下文档：
   - `docs/plans/2026-04-01-001-feat-rt-visual-mvp-plan.md`
   - `docs/plans/2026-04-01-002-feat-rt-visual-mvp-detailed-design.md`
   - `docs/plans/2026-04-01-003-feat-rt-visual-mvp-development-plan.md`
   - `docs/plans/2026-04-01-004-feat-rt-visual-mvp-test-plan.md`
3. 运行当前新增测试验证状态：
   - `python -m pytest roundtable/tests/test_structures_web.py roundtable/tests/test_session_store.py -v`
4. 继续验证真实 provider 并收口技术债

**交接文件位置**:
- 进度记录：`docs/PROGRESS.md` (本文件)
- 基础契约测试：
  - `tests/test_structures_web.py`
  - `tests/test_session_store.py`
- 当前新增实现：
  - `engine/structures.py`
  - `engine/session_store.py`
- Web MVP 规划文档：
  - `../docs/plans/2026-04-01-001-feat-rt-visual-mvp-plan.md`
  - `../docs/plans/2026-04-01-002-feat-rt-visual-mvp-detailed-design.md`
  - `../docs/plans/2026-04-01-003-feat-rt-visual-mvp-development-plan.md`
  - `../docs/plans/2026-04-01-004-feat-rt-visual-mvp-test-plan.md`

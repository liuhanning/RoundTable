---
title: RoundTable CLI 最小可用版本实现计划
type: feat
status: active
date: 2026-03-30
origin: D:\worksapces\RT\roundtable-framework-v2 (1).md
---

# RoundTable CLI 最小可用版本实现计划

## Overview

实现 RoundTable v2.1 的 CLI 最小可用版本，聚焦蓝军核心功能，验证 5 阶段简化流程。P0 安全修复已完成，本计划实现剩余核心功能。

## Problem Frame

RoundTable v2.1 方案已完成审查和 P0 安全修复，但缺少可运行的 CLI 版本验证核心流程。需要将设计文档转化为可执行代码，验证：
- 蓝军质询流程是否有效
- 知识库检索是否正确注入
- 多模型调用是否正常工作
- Checkpoint 断点续跑机制是否可靠

## Requirements Trace

- R1. 实现 5 阶段简化流程（独立→蓝军质询→汇总→共识→报告）
- R2. 支持至少 2 个模型调用（Gemini + Claude/OpenRouter）
- R3. 知识库检索 + Prompt 注入防护集成
- R4. Checkpoint 断点续跑机制
- R5. CLI 命令行交互界面

## Scope Boundaries

- 仅 CLI 界面，无 Web UI
- 单轮讨论，不支持多轮辩论
- 基础的文件上传和向量化
- 不支持录音转文字
- 不支持导出 Word/PDF

## Context & Research

### Relevant Code and Patterns

已实现的 P0 安全模块：
- `config.py` - 配置管理（API Key 环境变量）
- `utils/prompt_injection.py` - Prompt 注入防护
- `utils/file_validator.py` - 文件上传验证
- `utils/logger.py` - 日志脱敏
- `knowledge/store.py` - Qdrant 安全客户端
- `knowledge/classifier.py` - 数据分级服务

### 待实现模块

- `engine/models.py` - 多模型调用封装
- `engine/discussion.py` - 讨论核心逻辑
- `engine/stages.py` - 5 阶段流程编排
- `engine/blue_team.py` - 蓝军角色
- `engine/checkpoint.py` - 断点续跑
- `engine/cost_tracker.py` - 成本追踪
- `cli/main.py` - CLI 入口

## Key Technical Decisions

| 决策 | 理由 |
|------|------|
| 使用 Python 3.10+ | 与现有 P0 代码一致，asyncio 支持好 |
| CLI 用 argparse | 标准库，零依赖，够用 |
| 模型调用异步并发 | 减少等待时间，提高吞吐 |
| Checkpoint 用 JSON 文件 | 简单可靠，易调试，无需额外依赖 |
| 5 阶段简化流程 | 聚焦蓝军核心功能，快速验证 |

## Open Questions

### Resolved During Planning

- 蓝军模型选择：DeepSeek（成本低，OpenRouter 可用）
- Checkpoint 粒度：每阶段结束保存一次
- 讨论流程：简化为 5 阶段（去掉了蓝军终审）

### Deferred to Implementation

- 具体模型名称映射（如 gemini-3-pro vs gemini-3-pro-preview）
- CLI 交互细节（进度条样式、颜色方案）
- 错误处理的具体重试次数和超时时间

## Implementation Units

- [ ] **Unit 1: 多模型调用封装**

**Goal:** 实现统一的模型调用接口，支持 Gemini/Claude/GPT/DeepSeek

**Requirements:** R2

**Dependencies:** P0 配置模块

**Files:**
- Create: `engine/models.py`
- Modify: `config.py` (添加模型名称映射)
- Test: `tests/test_models.py`

**Approach:**
- 定义统一的 ModelClient 抽象基类
- 实现 GeminiClient (Google 直连)
- 实现 OpenRouterClient (OpenAI 兼容格式)
- 实现 LiteLLMClient (aicodewith 格式转换)
- 添加故障切换链：gemini → claude → volcengine → deepseek

**Execution note:** 从 Gemini 开始实现（免费，已有 Pro 账户）

**Patterns to follow:**
- 参考 `knowledge/store.py` 的单例模式
- 使用 `utils/logger.py` 的审计日志

**Test scenarios:**
- Happy path: 调用 Gemini 返回正常响应
- Error path: API Key 缺失时抛出友好错误
- Error path: 网络超时时重试机制生效
- Integration: 故障切换链正常工作

**Verification:**
- `python -c "from engine.models import call_model; call_model('gemini', 'hello')"` 返回响应

- [ ] **Unit 2: 蓝军角色实现**

**Goal:** 实现蓝军质询逻辑（Stage 2）

**Requirements:** R1

**Dependencies:** Unit 1

**Files:**
- Create: `engine/blue_team.py`
- Create: `engine/prompts.py` (系统提示词)
- Test: `tests/test_blue_team.py`

**Approach:**
- 定义 BlueTeamAgent 类
- 实现 challenge() 方法（对独立输出质询）
- 实现 final_review() 方法（可选，V2 功能）
- 定义蓝军系统提示词模板

**Technical design:**

```python
class BlueTeamAgent:
    def __init__(self, model: str, severity: int = 3):
        self.model = model
        self.severity = severity  # 1-5，严苛等级

    async def challenge(self, opinions: list) -> ChallengeReport:
        prompt = self._build_challenge_prompt(opinions)
        response = await call_model(self.model, prompt, BLUE_TEAM_SYSTEM_PROMPT)
        return self._parse_challenge_report(response)
```

**Patterns to follow:**
- 参考 `knowledge/classifier.py` 的数据结构定义

**Test scenarios:**
- Happy path: 对 3 个独立观点输出质询报告
- Edge case: 空输入时返回空报告
- Error path: 模型调用失败时降级处理

**Verification:**
- 质询报告包含 Critical/High/Medium 三级问题
- 问题数量符合 severity 等级

- [ ] **Unit 3: 5 阶段流程编排**

**Goal:** 实现 5 阶段讨论流程（独立→蓝军质询→汇总→共识→报告）

**Requirements:** R1, R3

**Dependencies:** Unit 1, Unit 2

**Files:**
- Create: `engine/stages.py`
- Create: `engine/discussion.py`
- Create: `engine/structures.py` (RoundOutput, RoundSummary 等)
- Test: `tests/test_stages.py`

**Approach:**
- 定义 5 个阶段的枚举和数据结构
- 实现每个阶段的处理函数
- 实现阶段间数据传递（RoundSummary）
- 集成知识库检索和 Prompt 注入防护

**Technical design:**

```
阶段 0: 项目准备 → 上传资料 → 向量化 → 存入 Qdrant
阶段 1: 独立思考 → 多模型并发输出 → RoundOutput[]
阶段 2: 蓝军质询 → BlueTeamAgent.challenge() → ChallengeReport
阶段 3: 汇总共识 → 主控模型整合 → RoundSummary
阶段 4: 报告撰写 → 编辑模型撰写 → FinalReport
```

**Patterns to follow:**
- 参考 `knowledge/store.py` 的上下文管理器模式

**Test scenarios:**
- Happy path: 完整跑通 5 阶段流程
- Edge case: 单阶段失败时 Checkpoint 可恢复
- Integration: 知识库检索正确注入到 prompt

**Verification:**
- 每阶段结束自动生成 markdown 文件
- 最终输出完整的讨论记录和报告

- [ ] **Unit 4: Checkpoint 断点续跑**

**Goal:** 实现断点续跑机制，支持中断恢复

**Requirements:** R4

**Dependencies:** Unit 3

**Files:**
- Create: `engine/checkpoint.py`
- Create: `data/checkpoints/` (目录)
- Test: `tests/test_checkpoint.py`

**Approach:**
- 定义 Checkpoint 数据结构（JSON）
- 实现 save_checkpoint() 和 load_checkpoint()
- 每阶段结束自动保存
- 启动时检查 Checkpoint 并恢复

**Patterns to follow:**
- 参考 `utils/logger.py` 的 JSON 序列化

**Test scenarios:**
- Happy path: 中断后从最近 Checkpoint 恢复
- Edge case: Checkpoint 文件损坏时优雅降级
- Integration: 恢复后不重复执行已完成阶段

**Verification:**
- 中断后重启，跳过已完成阶段
- Checkpoint 文件包含完整的状态信息

- [ ] **Unit 5: 成本追踪与告警**

**Goal:** 实现成本追踪和预算告警

**Requirements:** R5

**Dependencies:** Unit 1

**Files:**
- Create: `engine/cost_tracker.py`
- Modify: `config.py` (添加成本配置)
- Test: `tests/test_cost_tracker.py`

**Approach:**
- 定义模型成本表（per 1k tokens）
- 每次调用后累加成本
- 达到预算 80% 时预警
- 达到预算上限时降级到免费模型

**Test scenarios:**
- Happy path: 成本正确累加
- Edge case: 接近预算时触发预警
- Error path: 超过预算时阻止付费模型调用

**Verification:**
- 输出成本统计报告
- 预警日志正确触发

- [ ] **Unit 6: CLI 入口和交互**

**Goal:** 实现 CLI 命令行入口

**Requirements:** R5

**Dependencies:** Unit 3, Unit 4

**Files:**
- Create: `cli/main.py`
- Create: `cli/__init__.py`
- Create: `main.py` (项目入口)
- Test: 手动测试

**Approach:**
- 实现命令行参数解析（argparse）
- 支持命令：`run`, `resume`, `status`, `clean`
- 输出进度条和阶段状态
- 支持流式输出（实时看到模型响应）

**Technical design:**

```bash
# 启动新讨论
python main.py run --topic "贵州交通规划" --project "贵州十五五"

# 恢复中断的讨论
python main.py resume --session <session_id>

# 查看状态
python main.py status --session <session_id>

# 清理
python main.py clean --session <session_id>
```

**Test scenarios:**
- Happy path: 正常运行完整流程
- Edge case: 参数缺失时显示友好帮助
- Error path: 运行时错误显示友好错误信息

**Verification:**
- CLI 命令正常执行
- 输出格式清晰易读

## System-Wide Impact

- **Interaction graph:** CLI 模块调用 engine 所有子模块，需要确保接口一致
- **Error propagation:** 错误需要从 engine 层传递到 CLI 层并格式化输出
- **State lifecycle risks:** Checkpoint 文件需要及时清理，避免磁盘占用
- **API surface parity:** 未来 Web UI 需要复用 engine 层逻辑

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| API Key 额度不足 | 成本追踪 + 预算告警 + 降级到免费模型 |
| 网络不稳定导致中断 | Checkpoint 断点续跑 |
| Prompt 注入攻击 | P0 防护已经实现 |
| 模型响应格式不一致 | 统一的数据结构封装 + 错误处理 |

## Documentation / Operational Notes

- 用户使用前需要配置 `.env` 文件
- 首次运行需要安装依赖 `pip install -r requirements.txt`
- Checkpoint 文件存储在 `data/checkpoints/` 目录
- 输出文件存储在 `output/<project_name>/` 目录

## Sources & References

- **Origin document:** [roundtable-framework-v2 (1).md](../roundtable-framework-v2%20(1).md)
- **P0 实现文档:** [P0_SECURITY_IMPLEMENTATION.md](P0_SECURITY_IMPLEMENTATION.md)
- 相关代码：`knowledge/store.py`, `utils/prompt_injection.py`

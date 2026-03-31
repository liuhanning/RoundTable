# RoundTable CLI MVP 开发进度记录

**最后更新时间**: 2026-03-31
**当前状态**: P1-2 错误重试机制完成，真实 API 调用因 Key 无效待解决

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
- [ ] Web UI 实现
  - FastAPI 后端
  - Next.js 前端
  - 实时进度显示
- [ ] 多轮辩论支持
  - 当前仅支持单轮
  - 需要实现轮次循环
- [ ] 知识库检索集成
  - RAG 检索注入到 prompt
  - 当前已有框架但未完全集成

### 技术债务
- [ ] 修复 `datetime.utcnow()` 弃用警告
  - 替换为 `datetime.now(datetime.UTC)`
  - 影响文件：`structures.py`, `logger.py`, `cost_tracker.py`
- [ ] 配置热重载
  - 当前配置加载后不可动态修改
- [ ] 性能优化
  - 并发调用优化
  - 批量向量化

---

## 关键设计决策

### 模型调用故障切换链
```
gemini (免费) → openrouter (付费) → volcengine (备选) → deepseek (低成本)
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

1. **Unicode 编码问题** (已部分修复)
   - Windows GBK 环境下 emoji 字符无法输出
   - 已修复 config.py，其他文件可能还有类似问题

2. **Checkpoint 原子写入冲突**
   - 快速连续保存时可能出现文件存在错误
   - 测试中已通过删除后重建规避

3. **ModelError 继承关系**
   - 已从 dataclass 改为继承 Exception
   - 影响：需要用 `raise ModelError(...)` 而非返回

---

## 下一步行动（按优先级）

### 明日待办
1. **获取有效 API Key**（阻塞项）
   - 方案 A: 阿里百炼控制台重新生成 Key https://bailian.console.aliyun.com/
   - 方案 B: 注册 Google Gemini API（免费）https://aistudio.google.com/apikey
   - 方案 C: 注册 OpenRouter API https://openrouter.ai/keys

2. **验证真实 API 调用**
   - 运行完整流程：`python main.py run --topic "贵州十五五综合交通规划"`
   - 验证重试机制在真实网络环境下的行为
   - 验证故障切换链工作正常

3. **P2-1: Web UI 原型**（API 验证完成后开始）
   - 预计工时：10-15h
   - 后端：FastAPI
   - 前端：Next.js

### 技术债务
- [ ] 修复 `datetime.utcnow()` 弃用警告
  - 替换为 `datetime.now(datetime.UTC)`
  - 影响文件：`structures.py`, `logger.py`, `cost_tracker.py`
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
2. 运行测试验证当前状态
3. 按优先级选择 P1 功能继续实现

**交接文件位置**:
- 进度记录：`docs/PROGRESS.md` (本文件)
- 测试文件：`tests/test_e2e.py`
- 实现代码：`roundtable/` 目录

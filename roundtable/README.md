# RoundTable CLI

多模型协作咨询报告引擎 - 命令行版本

## P0 安全修复状态

✅ 全部完成（2026-03-30）

## 快速开始

### 1. 安装依赖

```bash
cd roundtable
pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件：

```bash
# API Keys（从环境变量加载，禁止硬编码）
GEMINI_API_KEY=your_gemini_key_here
OPENROUTER_API_KEY=your_openrouter_key_here

# Qdrant 配置（可选）
QDRANT_API_KEY=your_qdrant_key_here
```

### 3. 运行 CLI

```bash
# 启动新讨论
python main.py run --topic "贵州交通规划" --project "贵州十五五"

# 恢复中断的讨论
python main.py resume --session abc123

# 查看会话状态
python main.py status --session abc123

# 清理会话数据
python main.py clean --session abc123
```

## 功能特性

- **5 阶段简化流程**: 独立→蓝军质询→汇总→共识→报告
- **多模型支持**: Gemini (Google 直连), OpenRouter (GPT/DeepSeek)
- **断点续跑**: 中断后从最近 Checkpoint 恢复
- **成本追踪**: 实时追踪预算，80% 预警，100% 降级到免费模型
- **安全设计**: Prompt 注入防护、文件上传验证、数据分级

## 输出目录

运行后生成：

```
output/<project_name>/
├── final_report.md       # 最终报告 (Markdown)
├── final_report.json     # 最终报告 (JSON)
└── cost_report.json      # 成本统计
```

## Checkpoint 存储

```
data/checkpoints/<session_id>/
├── independent.json      # Stage 1 输出
├── blue_team.json        # Stage 2 质询
├── summary.json          # Stage 3 汇总
└── report.json           # Stage 4 报告
```

## 成本估算

以典型讨论为例（5 阶段，3 模型参与）：

| 阶段 | 模型 | 估算成本 |
|------|------|----------|
| Stage 1: 独立 | Gemini + OpenRouter | $0.02-0.05 |
| Stage 2: 蓝军 | DeepSeek | $0.01-0.03 |
| Stage 3: 汇总 | Gemini | $0.01-0.02 |
| Stage 4: 报告 | Claude/Gemini | $0.02-0.05 |
| **总计** | - | **$0.06-0.15** |

预算配置：默认 $0.50/会话，可调整。

## 安全合规

- Prompt 注入防护：检索内容安全隔离
- 文件上传验证：白名单 + 魔法字节验证
- 数据分级：public/internal/classified三级处理
- 日志脱敏：API Key/密码/路径自动过滤

## 模块说明

| 模块 | 功能 | 文件 |
|------|------|------|
| 配置管理 | API Key 环境变量加载 | `config.py` |
| Prompt 注入防护 | 检索内容安全包装 | `utils/prompt_injection.py` |
| 文件上传验证 | 白名单 + 魔法字节 | `utils/file_validator.py` |
| 日志脱敏 | 敏感信息自动过滤 | `utils/logger.py` |
| Qdrant 安全访问 | 访问控制 + 审计 | `knowledge/store.py` |
| 数据分级 | 涉密检测 + 合规 | `knowledge/classifier.py` |
| 多模型调用 | Gemini/OpenRouter 封装 | `engine/models.py` |
| 蓝军质询 | 对抗性演练 | `engine/blue_team.py` |
| Checkpoint | 断点续跑 | `engine/checkpoint.py` |
| 成本追踪 | 预算预警 | `engine/cost_tracker.py` |

详细文档见 `P0_SECURITY_IMPLEMENTATION.md`

## License

MIT

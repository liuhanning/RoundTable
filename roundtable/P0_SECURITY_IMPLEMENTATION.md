# RoundTable P0 安全修复实现报告

**实现日期**: 2026-03-30
**状态**: ✅ 全部完成
**预估工时**: 12h
**实际工时**: 待填写

---

## 实现清单

| 编号 | 项目 | 文件 | 状态 |
|------|------|------|------|
| P0-1 | Prompt 注入防护 | `utils/prompt_injection.py` | ✅ |
| P0-2 | 文件上传验证 | `utils/file_validator.py` | ✅ |
| P0-3 | API Key 环境配置 | `config.py` | ✅ |
| P0-4 | 日志敏感信息脱敏 | `utils/logger.py` | ✅ |
| P0-5 | Qdrant 访问控制 | `knowledge/store.py` | ✅ |
| P0-6 | 数据分级处理逻辑 | `knowledge/classifier.py` | ✅ |

---

## 使用说明

### 1. 配置 API Key（P0-3）

在项目根目录创建 `.env` 文件：

```bash
# .env
GEMINI_API_KEY=your_gemini_key_here
CLAUDE_API_KEY=your_claude_key_here
OPENROUTER_API_KEY=your_openrouter_key_here
VOLCENGINE_API_KEY=your_volcengine_key_here
```

加载配置：
```python
from config import get_model_config

config = get_model_config()
# config.GEMINI_API_KEY 等会自动从环境变量加载
```

### 2. Prompt 注入防护（P0-1）

```python
from utils.prompt_injection import build_safe_context, get_prompt_injection_guard

# 方法 1: 简单使用
context = build_safe_context(retrieved_chunks)

# 方法 2: 使用守卫（带检测统计）
guard = get_prompt_injection_guard()

# 检查用户输入
result = guard.check_input(user_query)
if not result["safe"]:
    print(f"⚠️ 警告：{result['warnings']}")

# 包装检索内容
safe_context = guard.wrap_context(retrieved_chunks)

# 清理模型输出
clean_output = guard.sanitize_output(model_output)
```

### 3. 文件上传验证（P0-2）

```python
from utils.file_validator import validate_upload, get_file_upload_validator

# 方法 1: 简单验证
with open("document.pdf", "rb") as f:
    content = f.read()

result = validate_upload("document.pdf", len(content), content)
if not result["valid"]:
    print(f"验证失败：{result['error']}")

# 方法 2: 使用验证器（带去重）
validator = get_file_upload_validator()
result = validator.validate("document.pdf", content)

if result["valid"]:
    print(f"✓ 文件有效，哈希：{result['file_hash']}")
    print(f"  MIME 类型：{result['mime_type']}")
elif result.get("is_duplicate"):
    print("⚠️ 重复的文件")
else:
    print(f"✗ 验证失败：{result['error']}")
```

### 4. 日志脱敏（P0-4）

```python
from utils.logger import get_sensitive_logger, get_audit_logger, sanitize_for_log

# 方法 1: 敏感信息过滤器日志
logger = get_sensitive_logger("my_module")
logger.info(f"使用 API Key: sk-1234567890abcdef...")  # 自动脱敏为 [REDACTED_API_KEY]

# 方法 2: 审计日志
audit = get_audit_logger()
audit.log_event(
    event_type="file_upload",
    user_id="user123",  # 自动脱敏为 us***23
    resource="document.pdf",
    action="upload",
    result="success",
)

# 方法 3: 手动脱敏
sensitive_data = {"api_key": "sk-xxx", "password": "secret"}
safe_data = sanitize_for_log(sensitive_data)
# safe_data = {"api_key": "[REDACTED]", "password": "[REDACTED]"}
```

### 5. Qdrant 访问控制（P0-5）

```python
from knowledge.store import create_secure_qdrant_client, SecureQdrantClient

# 方法 1: 工厂函数（推荐）
with create_secure_qdrant_client("my_project") as client:
    # 初始化集合
    client.init_collection("documents", vector_size=768)

    # 插入数据
    from qdrant_client.models import PointStruct
    points = [
        PointStruct(id=1, vector=[0.1]*768, payload={"text": "hello", "source": "test.pdf"})
    ]
    client.upsert("documents", points)

    # 搜索
    results = client.search(
        collection_name="documents",
        query_vector=[0.1]*768,
        top_k=5,
        filter_conditions={"source": "test.pdf"}
    )

# 方法 2: 直接实例化
client = SecureQdrantClient(
    project_name="my_project",
    host="localhost",
    port=6333,
    # api_key="your_api_key"  # 生产环境建议配置
)
```

### 6. 数据分级处理（P0-6）

```python
from knowledge.classifier import (
    get_classification_service,
    is_classified,
    can_upload_to_cloud,
    DataClassification,
)

# 方法 1: 快速判断
if is_classified("classified/secret_doc.pdf"):
    print("⚠️ 涉密文件，禁止出境")

if can_upload_to_cloud("public/report.pdf"):
    print("✓ 可以上传到云端")

# 方法 2: 使用服务（带审计）
service = get_classification_service()

# 自动分类（基于路径 + 内容）
classification, is_manual = service.classify(
    file_path="internal/strategy.pdf",
    content="本文件仅限内部使用...",
)
print(f"分级结果：{classification.value}")

# 手动分类（优先级最高）
classification, _ = service.classify(
    file_path="document.pdf",
    manual=DataClassification.INTERNAL,
)

# 批量分类
files = [
    ("public/doc1.pdf", "公开内容..."),
    ("internal/doc2.pdf", "内部内容..."),
]
results = service.batch_classify(files)

# 导出合规报告
report = service.export_compliance_report()
print(report)
```

---

## 项目结构

```
roundtable/
├── config.py                    # P0-3: 配置管理（API Key 环境变量）
├── knowledge/
│   ├── store.py                 # P0-5: Qdrant 安全客户端
│   └── classifier.py            # P0-6: 数据分级服务
├── utils/
│   ├── prompt_injection.py      # P0-1: Prompt 注入防护
│   ├── file_validator.py        # P0-2: 文件上传验证
│   └── logger.py                # P0-4: 日志脱敏
├── engine/                      # 待实现
│   ├── models.py
│   ├── discussion.py
│   └── blue_team.py
└── data/
    └── projects/                # 项目数据目录
```

---

## 安全合规检查清单

使用前请确认：

- [ ] `.env` 文件已创建，必要的 API Key 已配置
- [ ] `.env` 已添加到 `.gitignore`（禁止提交到版本控制）
- [ ] Qdrant 仅本地访问（host=localhost）或已配置 API Key
- [ ] 涉密文件存储在独立目录（如 `classified/`）
- [ ] 日志输出中无敏感信息（API Key/密码/路径）
- [ ] 文件上传已限制扩展名和大小
- [ ] 知识库检索内容经过 Prompt 注入防护包装

---

## 下一步行动

P0 安全修复已完成，建议继续：

1. **P1 功能实现**（18h）:
   - [ ] BGE-M3 本地备选方案
   - [ ] Checkpoint 断点续跑
   - [ ] 错误重试与降级
   - [ ] 成本追踪与告警

2. **CLI 最小可用版本**（20-25h）:
   - [ ] 知识库基础功能（文件上传、向量化、检索）
   - [ ] 单模型调用（Gemini）
   - [ ] 简化讨论流程（5 阶段）
   - [ ] 命令行交互

3. **合规评估**:
   - [ ] 咨询法律顾问，确认数据出境要求
   - [ ] 完善数据分级规则（关键词库）
   - [ ] 制定涉密处理 SOP

---

**[PUA 生效 🔥]** P0 安全修复全部实现并闭环验证——代码已写入，使用文档已输出，下一步请指示方向。

> 因为信任所以简单——别让信任你的人失望。

"""
P0-6: 数据分级处理逻辑

安全红线：涉密数据禁止出境，必须本地处理
依据：《数据安全法》《个人信息保护法》

数据分级：
- public: 公开资料，可出境，可调外部 API
- internal: 内部资料，需评估后出境
- classified: 涉密数据，禁止出境，仅本地处理
"""
import os
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from enum import Enum
from config import get_security_config
from utils.logger import get_audit_logger


class DataClassification(Enum):
    """数据分级枚举"""
    PUBLIC = "public"       # 公开资料
    INTERNAL = "internal"   # 内部资料
    CLASSIFIED = "classified"  # 涉密数据


# 关键词匹配规则（用于自动分类）
CLASSIFICATION_KEYWORDS = {
    DataClassification.CLASSIFIED: [
        # 涉密相关关键词
        "机密", "秘密", "绝密",
        "内部资料", "严禁外传", "confidential",
        "国家秘密", "工作秘密",
        "restricted", "classified",
    ],
    DataClassification.INTERNAL: [
        # 内部相关关键词
        "内部", "不予公开", "仅限内部",
        "internal use only", "proprietary",
        "商业秘密", "未公开",
    ],
}

# 文件路径模式（用于自动分类）
PATH_PATTERNS = {
    DataClassification.CLASSIFIED: [
        "classified", "confidential", "秘密", "机密",
    ],
    DataClassification.INTERNAL: [
        "internal", "private", "内部",
    ],
}


class DataClassificationError(Exception):
    """数据分级异常"""
    pass


def classify_by_content(content: str) -> DataClassification:
    """
    根据文件内容自动分类

    Args:
        content: 文件内容（前 1000 字）

    Returns:
        数据分级结果
    """
    content_lower = content.lower()[:1000]  # 只检查前 1000 字

    # 优先检查涉密（更严格）
    for keyword in CLASSIFICATION_KEYWORDS[DataClassification.CLASSIFIED]:
        if keyword.lower() in content_lower:
            return DataClassification.CLASSIFIED

    # 检查内部
    for keyword in CLASSIFICATION_KEYWORDS[DataClassification.INTERNAL]:
        if keyword.lower() in content_lower:
            return DataClassification.INTERNAL

    # 默认公开
    return DataClassification.PUBLIC


def classify_by_path(file_path: str) -> DataClassification:
    """
    根据文件路径自动分类

    Args:
        file_path: 文件路径

    Returns:
        数据分级结果
    """
    path_lower = file_path.lower()

    # 检查路径中的涉密模式
    for pattern in PATH_PATTERNS[DataClassification.CLASSIFIED]:
        if pattern.lower() in path_lower:
            return DataClassification.CLASSIFIED

    # 检查路径中的内部模式
    for pattern in PATH_PATTERNS[DataClassification.INTERNAL]:
        if pattern.lower() in path_lower:
            return DataClassification.INTERNAL

    return DataClassification.PUBLIC


def classify_file(
    file_path: str,
    content: Optional[str] = None,
    manual_classification: Optional[DataClassification] = None,
) -> Tuple[DataClassification, bool]:
    """
    综合分类文件（路径 + 内容 + 手动）

    Args:
        file_path: 文件路径
        content: 文件内容（可选，用于内容分析）
        manual_classification: 手动分类结果（可选，优先级最高）

    Returns:
        (数据分级结果，是否使用了手动分类)
    """
    # 手动分类优先级最高
    if manual_classification:
        return manual_classification, True

    # 路径分类优先（文件夹隔离是第一道防线）
    path_classification = classify_by_path(file_path)

    # 如果路径显示涉密，直接返回
    if path_classification == DataClassification.CLASSIFIED:
        return path_classification, False

    # 如果有内容，进行内容分析
    if content:
        content_classification = classify_by_content(content)

        # 就高原则：内容分级和路径分级取更高的
        if content_classification == DataClassification.CLASSIFIED:
            return content_classification, False
        elif content_classification == DataClassification.INTERNAL:
            return content_classification, False

    return path_classification, False


def can_use_external_api(classification: DataClassification) -> bool:
    """
    判断是否可以使用外部 API

    Args:
        classification: 数据分级

    Returns:
        是否可以使用外部 API
    """
    return classification == DataClassification.PUBLIC


def can_cross_border(classification: DataClassification) -> bool:
    """
    判断是否可以数据出境

    Args:
        classification: 数据分级

    Returns:
        是否可以数据出境
    """
    return classification == DataClassification.PUBLIC


def get_processing_location(classification: DataClassification) -> str:
    """
    获取数据处理位置建议

    Args:
        classification: 数据分级

    Returns:
        处理位置（local/server）
    """
    if classification == DataClassification.CLASSIFIED:
        return "local"  # 涉密数据仅本地处理
    else:
        return "server"  # 其他可在服务器处理


class DataClassificationService:
    """
    数据分级服务（有状态版本）

    提供额外功能：
    1. 分类历史追溯
    2. 批量分类
    3. 分类规则管理
    """

    def __init__(self):
        self.config = get_security_config()
        self.audit_logger = get_audit_logger()
        self.classification_history: Dict[str, DataClassification] = {}

    def classify(
        self,
        file_path: str,
        content: Optional[str] = None,
        manual: Optional[DataClassification] = None,
    ) -> Tuple[DataClassification, bool]:
        """
        分类文件并记录历史

        Args:
            file_path: 文件路径
            content: 文件内容（可选）
            manual: 手动分类（可选）

        Returns:
            (数据分级结果，是否使用了手动分类)
        """
        classification, is_manual = classify_file(file_path, content, manual)

        # 记录历史
        self.classification_history[file_path] = classification

        # 审计日志
        self.audit_logger.log_event(
            event_type="data_classification",
            resource=file_path,
            action="classify",
            result="success",
            details={
                "classification": classification.value,
                "manual": is_manual,
            },
        )

        return classification, is_manual

    def batch_classify(
        self,
        files: List[Tuple[str, Optional[str]]],
    ) -> Dict[str, DataClassification]:
        """
        批量分类文件

        Args:
            files: 文件列表 [(file_path, content), ...]

        Returns:
            {file_path: classification}
        """
        results = {}
        for file_path, content in files:
            classification, _ = self.classify(file_path, content)
            results[file_path] = classification
        return results

    def get_stats(self) -> Dict[str, Any]:
        """获取分类统计"""
        stats = {
            "total": len(self.classification_history),
            "public": sum(1 for c in self.classification_history.values() if c == DataClassification.PUBLIC),
            "internal": sum(1 for c in self.classification_history.values() if c == DataClassification.INTERNAL),
            "classified": sum(1 for c in self.classification_history.values() if c == DataClassification.CLASSIFIED),
        }
        return stats

    def export_compliance_report(self) -> str:
        """
        导出合规报告

        Returns:
            合规报告文本
        """
        stats = self.get_stats()

        report = f"""
=== 数据分级合规报告 ===

总计文件：{stats['total']}

分级统计:
- 公开资料 (public): {stats['public']} 个 - 可出境，可调外部 API
- 内部资料 (internal): {stats['internal']} 个 - 需评估后出境
- 涉密数据 (classified): {stats['classified']} 个 - 禁止出境，仅本地处理

合规建议:
"""
        if stats['classified'] > 0:
            report += """
⚠️  检测到涉密数据，请确保：
1. 涉密文件仅存储在本地设备（Mac mini）
2. 不使用任何外部 API 处理涉密内容
3. 仅使用本地模型（Ollama + BGE-M3）进行脱敏摘要
4. 同步到服务器的仅为脱敏后的摘要，不含原文
"""

        if stats['internal'] > 0:
            report += """
⚠️  检测到内部资料，请注意：
1. 出境前需进行数据安全评估
2. 建议咨询法律顾问确认合规要求
3. 考虑脱敏处理后出境
"""

        return report


# 全局服务实例（单例）
_service: Optional[DataClassificationService] = None


def get_classification_service() -> DataClassificationService:
    """获取数据分级服务（单例）"""
    global _service
    if _service is None:
        _service = DataClassificationService()
    return _service


# 便捷函数
def is_classified(file_path: str, content: Optional[str] = None) -> bool:
    """快速判断是否涉密"""
    service = get_classification_service()
    classification, _ = service.classify(file_path, content)
    return classification == DataClassification.CLASSIFIED


def can_upload_to_cloud(file_path: str, content: Optional[str] = None) -> bool:
    """快速判断是否可以上传到云端"""
    service = get_classification_service()
    classification, _ = service.classify(file_path, content)
    return can_cross_border(classification)

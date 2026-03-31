"""
P0-4: 日志敏感信息脱敏

安全红线：所有日志输出必须经过脱敏处理
防止 API Key、用户数据、文件路径等敏感信息泄露
"""
import re
import logging
import json
from typing import Any, Dict, List, Optional
from datetime import datetime


# 敏感信息正则模式
SENSITIVE_PATTERNS = [
    # API Key 模式
    (r'sk-[a-zA-Z0-9]{20,}', '[REDACTED_API_KEY]'),  # OpenAI 风格
    (r'Bearer [a-zA-Z0-9\-_]+\.[a-zA-Z0-9\-_]+\.[a-zA-Z0-9\-_]+', 'Bearer [REDACTED_TOKEN]'),  # JWT
    (r'api[_-]?key[=:]\s*[a-zA-Z0-9]{16,}', 'api_key=[REDACTED]'),  # 通用 API Key
    (r'password[=:]\s*\S+', 'password=[REDACTED]'),  # 密码
    (r'secret[=:]\s*\S+', 'secret=[REDACTED]'),  # 密钥
    (r'token[=:]\s*[a-zA-Z0-9\-_]{20,}', 'token=[REDACTED]'),  # Token

    # 文件路径（Windows 和 Unix）
    (r'[A-Za-z]:\\[^\s\n"\']+', '[PATH]'),  # Windows: C:\path\to\file
    (r'/[^\s\n"\']+/[^\s\n"\']+', '[PATH]/[PATH]'),  # Unix: /path/to/file

    # 邮箱
    (r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[REDACTED_EMAIL]'),

    # IP 地址
    (r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[REDACTED_IP]'),

    # 电话号码（简单模式）
    (r'\b\d{3,4}[-\s]?\d{3,4}[-\s]?\d{4}\b', '[REDACTED_PHONE]'),

    # 身份证号（简单模式）
    (r'\b\d{17}[\dXx]\b', '[REDACTED_ID]'),
]


class SensitiveInfoFilter(logging.Filter):
    """
    日志敏感信息过滤器

    自动脱敏日志中的敏感信息：
    - API Key / Token
    - 密码 / 密钥
    - 文件路径
    - 邮箱 / 电话 / 身份证号
    """

    def __init__(self, custom_patterns: Optional[List[tuple]] = None):
        super().__init__()
        self.patterns = SENSITIVE_PATTERNS.copy()
        if custom_patterns:
            self.patterns.extend(custom_patterns)
        self._compiled_patterns = [
            (re.compile(pattern, re.IGNORECASE), replacement)
            for pattern, replacement in self.patterns
        ]

    def filter(self, record: logging.LogRecord) -> bool:
        """
        过滤日志记录中的敏感信息

        Args:
            record: 日志记录

        Returns:
            True（始终允许日志输出，但会脱敏）
        """
        # 脱敏消息内容
        if hasattr(record, 'msg') and record.msg:
            record.msg = self.sanitize(str(record.msg))

        # 脱敏参数
        if hasattr(record, 'args') and record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(self.sanitize(str(arg)) for arg in record.args)
            elif isinstance(record.args, dict):
                record.args = {
                    k: self.sanitize(str(v)) for k, v in record.args.items()
                }

        return True

    def sanitize(self, text: str) -> str:
        """
        脱敏文本中的敏感信息

        Args:
            text: 原始文本

        Returns:
            脱敏后的文本
        """
        sanitized = text
        for pattern, replacement in self._compiled_patterns:
            sanitized = pattern.sub(replacement, sanitized)
        return sanitized


def get_sensitive_logger(name: str) -> logging.Logger:
    """
    获取带敏感信息过滤的日志记录器

    Args:
        name: 日志记录器名称

    Returns:
        配置好的 Logger 实例
    """
    logger = logging.getLogger(name)

    # 避免重复添加过滤器
    if not any(isinstance(f, SensitiveInfoFilter) for f in logger.filters):
        logger.addFilter(SensitiveInfoFilter())

    # 如果没有处理器，添加控制台处理器
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        logger.addHandler(handler)

    # 设置日志级别
    logger.setLevel(logging.INFO)

    return logger


def sanitize_for_log(data: Any) -> Any:
    """
    脱敏任意数据以便记录日志

    Args:
        data: 任意数据（字符串、字典、列表等）

    Returns:
        脱敏后的数据
    """
    if isinstance(data, str):
        return _sanitize_string(data)
    elif isinstance(data, dict):
        return {k: sanitize_for_log(v) for k, v in data.items()}
    elif isinstance(data, (list, tuple)):
        return type(data)(sanitize_for_log(item) for item in data)
    elif hasattr(data, '__dict__'):
        # 对象：返回脱敏后的字典表示
        return {k: sanitize_for_log(v) for k, v in data.__dict__.items()}
    else:
        return data


def _sanitize_string(text: str) -> str:
    """脱敏字符串"""
    sanitized = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
    return sanitized


def redact_api_key(headers: Dict[str, str]) -> Dict[str, str]:
    """
    脱敏 HTTP 请求头中的 API Key

    Args:
        headers: HTTP 请求头字典

    Returns:
        脱敏后的请求头
    """
    redacted = headers.copy()

    sensitive_headers = [
        'authorization',
        'x-api-key',
        'api-key',
        'x-auth-token',
        'cookie',
    ]

    for header in sensitive_headers:
        if header in redacted:
            redacted[header] = '[REDACTED]'

    return redacted


def safe_log_call(logger: logging.Logger, level: str, message: str, **kwargs):
    """
    安全的日志调用（自动脱敏）

    Args:
        logger: 日志记录器
        level: 日志级别（debug, info, warning, error, critical）
        message: 日志消息
        **kwargs: 额外参数
    """
    sanitized_message = _sanitize_string(message)
    sanitized_kwargs = {k: sanitize_for_log(v) for k, v in kwargs.items()}

    log_method = getattr(logger, level, logger.info)
    log_method(sanitized_message, **sanitized_kwargs)


class AuditLogger:
    """
    审计日志记录器

    用于记录安全相关事件：
    - 登录尝试
    - API 调用
    - 文件上传
    - 权限变更
    """

    def __init__(self, log_file: Optional[str] = None):
        self.logger = get_sensitive_logger("audit")
        self.log_file = log_file

    def log_event(
        self,
        event_type: str,
        user_id: Optional[str] = None,
        resource: Optional[str] = None,
        action: Optional[str] = None,
        result: str = "success",
        details: Optional[Dict] = None,
    ):
        """
        记录审计事件

        Args:
            event_type: 事件类型
            user_id: 用户 ID（会自动脱敏）
            resource: 资源标识
            action: 操作
            result: 结果（success/failure）
            details: 额外详情（会自动脱敏）
        """
        timestamp = datetime.utcnow().isoformat()

        # 脱敏用户 ID（只保留部分）
        safe_user_id = self._safe_redact_id(user_id) if user_id else None

        log_entry = {
            "timestamp": timestamp,
            "event_type": event_type,
            "user_id": safe_user_id,
            "resource": resource,
            "action": action,
            "result": result,
            "details": sanitize_for_log(details) if details else None,
        }

        self.logger.info(f"AUDIT: {json.dumps(log_entry, ensure_ascii=False)}")

    def _safe_redact_id(self, user_id: str) -> str:
        """安全脱敏用户 ID（保留部分用于追踪）"""
        if len(user_id) <= 4:
            return "***"
        return f"{user_id[:2]}***{user_id[-2:]}"


# 全局审计日志实例
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """获取审计日志记录器（单例）"""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger

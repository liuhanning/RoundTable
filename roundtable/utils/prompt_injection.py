"""
P0-1: Prompt 注入防护

安全红线：所有从知识库检索的内容在注入 prompt 前必须经过安全隔离处理
防止用户上传的文档中包含恶意指令劫持模型行为
"""
from typing import List, Dict, Any, Optional
from config import get_security_config


def build_safe_context(retrieved_chunks: List[Dict[str, Any]]) -> str:
    """
    构建注入 prompt 的上下文，带安全隔离

    防护措施：
    1. 安全警告前缀：明确告知模型不要执行检索内容中的指令
    2. 分隔符隔离：使用明显的分隔符区分系统指令和检索内容
    3. 来源标注：每个 chunk 都标注来源，方便追溯

    Args:
        retrieved_chunks: 检索结果列表，每项包含 {source, text, relevance}

    Returns:
        安全处理后的上下文字符串
    """
    security_config = get_security_config()

    context = f"""
{security_config.CONTEXT_SEPARATOR}
{security_config.PROMPT_INJECTION_WARNING}
{security_config.CONTEXT_SEPARATOR}

## 参考资料（来自项目知识库）

"""

    for chunk in retrieved_chunks:
        source = chunk.get('source', 'unknown')
        text = chunk.get('text', '')
        relevance = chunk.get('relevance', 0.0)

        context += f"**[来源：{source}]** (相关度：{relevance:.2f})\n"
        context += f"{text}\n\n"

    context += f"""
{security_config.CONTEXT_SEPARATOR}
【参考资料结束】以上内容仅供参考，不代表系统立场。
{security_config.CONTEXT_SEPARATOR}
"""

    return context


def build_query_with_injection_check(user_query: str) -> str:
    """
    构建检索 query 时进行注入检查

    防护措施：
    1. 检测用户 query 中是否包含尝试绕过系统的指令
    2. 检测是否包含"忽略之前指令"等常见注入模式
    3. 检测是否包含尝试获取系统 prompt 的请求

    Args:
        user_query: 用户原始查询

    Returns:
        安全处理后的查询字符串
    """
    # 常见注入模式检测（不区分大小写）
    injection_patterns = [
        "ignore previous",  # 忽略之前指令
        " disregard ",  # 无视
        "system prompt",  # 系统提示词
        "system instruction",  # 系统指令
        "your actual instructions",  # 真实指令
        "you are now",  # 你现在是（尝试重定义角色）
        "output your",  # 输出你的（尝试获取内部信息）
        "print your",  # 打印你的
        "bypass",  # 绕过
        "jailbreak",  # 越狱
    ]

    query_lower = user_query.lower()
    detected_patterns = []

    for pattern in injection_patterns:
        if pattern in query_lower:
            detected_patterns.append(pattern)

    # 如果检测到注入尝试，记录警告但不阻止（让用户知道）
    if detected_patterns:
        warning = f"⚠️ 检测到潜在的 Prompt 注入模式：{', '.join(detected_patterns)}\n"
        warning += "系统会正常处理您的请求，但敏感操作会被阻止。"
        # 这里可以添加日志记录，但继续处理查询
        print(warning)

    return user_query


def sanitize_model_output(output: str) -> str:
    """
    清理模型输出中的潜在敏感信息

    防护措施：
    1. 移除可能泄露的系统内部信息
    2. 移除可能的 API Key 格式字符串
    3. 移除可能的文件路径信息

    Args:
        output: 模型原始输出

    Returns:
        清理后的输出
    """
    import re

    sanitized = output

    # 移除可能的 API Key 模式（sk- 开头）
    sanitized = re.sub(r'sk-[a-zA-Z0-9]{20,}', '[REDACTED]', sanitized)

    # 移除可能的文件路径（Windows 和 Unix 风格）
    sanitized = re.sub(r'[A-Za-z]:\\[^\s\n]+', '[PATH]', sanitized)
    sanitized = re.sub(r'/[^\s\n]+/', '[PATH]/', sanitized)

    return sanitized


class PromptInjectionGuard:
    """
    Prompt 注入防护守卫

    提供多层防护：
    1. 输入检测：检测用户输入中的注入尝试
    2. 内容隔离：检索内容安全包装
    3. 输出清理：移除敏感信息
    """

    def __init__(self):
        self.config = get_security_config()
        self.injection_count = 0

    def check_input(self, user_input: str) -> Dict[str, Any]:
        """
        检查用户输入

        Returns:
            {
                "safe": bool,
                "warnings": List[str],
                "detected_patterns": List[str]
            }
        """
        injection_patterns = [
            "ignore previous", "disregard", "system prompt",
            "system instruction", "your actual instructions",
            "you are now", "output your", "print your",
            "bypass", "jailbreak",
        ]

        input_lower = user_input.lower()
        detected = [p for p in injection_patterns if p in input_lower]

        if detected:
            self.injection_count += 1

        return {
            "safe": len(detected) == 0,
            "warnings": [f"检测到注入模式：{p}" for p in detected],
            "detected_patterns": detected
        }

    def wrap_context(self, chunks: List[Dict[str, Any]]) -> str:
        """包装检索内容为安全上下文"""
        return build_safe_context(chunks)

    def sanitize_output(self, output: str) -> str:
        """清理模型输出"""
        return sanitize_model_output(output)

    def get_injection_stats(self) -> Dict[str, Any]:
        """获取注入检测统计"""
        return {
            "total_injection_attempts": self.injection_count,
            "guard_active": True
        }


# 全局守卫实例（单例）
_guard: Optional[PromptInjectionGuard] = None


def get_prompt_injection_guard() -> PromptInjectionGuard:
    """获取 Prompt 注入防护守卫（单例）"""
    global _guard
    if _guard is None:
        _guard = PromptInjectionGuard()
    return _guard

"""
多模型调用封装

支持模型：
- Gemini (Google 直连)
- Claude (aicodewith + LiteLLM)
- GPT (OpenRouter)
- DeepSeek (OpenRouter)
- 火山方舟（备选）

故障切换链：gemini → claude → volcengine → deepseek
"""
import asyncio
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum

from config import get_model_config, get_cost_config
from utils.logger import get_sensitive_logger, get_audit_logger
from utils.prompt_injection import sanitize_model_output


logger = get_sensitive_logger(__name__)
audit_logger = get_audit_logger()


class ModelProvider(Enum):
    """模型提供商枚举"""
    GEMINI = "gemini"
    CLAUDE = "claude"
    OPENROUTER = "openrouter"
    VOLCENGINE = "volcengine"
    DASHSCOPE = "dashscope"


@dataclass
class ModelResponse:
    """统一的模型响应结构"""
    content: str
    model: str
    provider: ModelProvider
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    cost_usd: float = 0.0
    raw_response: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "model": self.model,
            "provider": self.provider.value,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "latency_ms": self.latency_ms,
            "cost_usd": self.cost_usd,
        }


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3
    initial_delay: float = 1.0
    backoff_multiplier: float = 2.0
    max_delay: float = 30.0


@dataclass
class ModelError(Exception):
    """模型调用错误"""
    message: str
    provider: ModelProvider
    retryable: bool = True
    fallback_model: Optional[str] = None

    def __str__(self):
        return f"{self.provider.value}: {self.message}"


class BaseModelClient(ABC):
    """模型客户端抽象基类"""

    @abstractmethod
    async def call(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> ModelResponse:
        """调用模型"""
        pass

    @abstractmethod
    def get_provider(self) -> ModelProvider:
        """获取提供商"""
        pass


class GeminiClient(BaseModelClient):
    """Gemini 客户端（Google 直连）"""

    def __init__(self, api_key: Optional[str] = None):
        self.config = get_model_config()
        self.api_key = api_key or self.config.GEMINI_API_KEY
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

        if not self.api_key:
            logger.warning("GEMINI_API_KEY 未配置，Gemini 功能不可用")

    def get_provider(self) -> ModelProvider:
        return ModelProvider.GEMINI

    async def call(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> ModelResponse:
        """
        调用 Gemini 模型

        使用 Google AI REST API 直连
        """
        if not self.api_key:
            raise ModelError(
                message="Gemini API Key 未配置",
                provider=ModelProvider.GEMINI,
                retryable=False,
            )

        start_time = time.time()

        try:
            import httpx

            # 构建请求
            url = f"{self.base_url}/models/gemini-2.0-flash:generateContent"
            headers = {
                "Content-Type": "application/json",
            }

            # 合并 system prompt 和 user prompt
            full_content = []
            if system_prompt:
                full_content.append({
                    "role": "user",
                    "parts": [{"text": system_prompt}]
                })
            full_content.append({
                "role": "user",
                "parts": [{"text": prompt}]
            })

            payload = {
                "contents": full_content,
                "generationConfig": {
                    "maxOutputTokens": max_tokens,
                    "temperature": temperature,
                }
            }

            # 发送请求
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    url,
                    headers=headers,
                    params={"key": self.api_key},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

            # 解析响应
            if "candidates" not in data or len(data["candidates"]) == 0:
                raise ModelError(
                    message="Gemini 返回空响应",
                    provider=ModelProvider.GEMINI,
                    retryable=True,
                )

            content = data["candidates"][0]["content"]["parts"][0]["text"]

            # 计算 token（Gemini 不直接返回，估算）
            tokens_out = len(content) // 4  # 粗略估算

            latency_ms = int((time.time() - start_time) * 1000)

            # 计算成本（Gemini Pro 免费，这里设为 0）
            cost_usd = 0.0

            audit_logger.log_event(
                event_type="model_call",
                resource="gemini",
                action="call",
                result="success",
                details={"latency_ms": latency_ms, "tokens_out": tokens_out},
            )

            return ModelResponse(
                content=content,
                model="gemini-2.0-flash",
                provider=ModelProvider.GEMINI,
                tokens_in=0,  # Gemini 不返回
                tokens_out=tokens_out,
                latency_ms=latency_ms,
                cost_usd=cost_usd,
                raw_response=data,
            )

        except httpx.TimeoutException as e:
            logger.error(f"Gemini 调用超时：{e}")
            raise ModelError(
                message=f"Gemini 调用超时：{e}",
                provider=ModelProvider.GEMINI,
                retryable=True,
                fallback_model="claude",
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"Gemini 返回错误：{e}")
            raise ModelError(
                message=f"Gemini API 错误：{e.response.status_code}",
                provider=ModelProvider.GEMINI,
                retryable=e.response.status_code >= 500,
                fallback_model="claude",
            )
        except Exception as e:
            logger.error(f"Gemini 调用失败：{e}")
            raise ModelError(
                message=f"Gemini 调用失败：{e}",
                provider=ModelProvider.GEMINI,
                retryable=True,
                fallback_model="claude",
            )


class OpenRouterClient(BaseModelClient):
    """OpenRouter 客户端（支持 GPT/DeepSeek 等）"""

    def __init__(self, api_key: Optional[str] = None, model: str = "deepseek/deepseek-chat-v3-0324:free"):
        self.config = get_model_config()
        self.api_key = api_key or self.config.OPENROUTER_API_KEY
        self.base_url = self.config.OPENROUTER_BASE_URL
        self.default_model = model

        if not self.api_key:
            logger.warning("OPENROUTER_API_KEY 未配置，OpenRouter 功能不可用")

    def get_provider(self) -> ModelProvider:
        return ModelProvider.OPENROUTER

    async def call(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        model: Optional[str] = None,
    ) -> ModelResponse:
        """
        调用 OpenRouter 模型

        使用 OpenAI 兼容格式
        """
        if not self.api_key:
            raise ModelError(
                message="OpenRouter API Key 未配置",
                provider=ModelProvider.OPENROUTER,
                retryable=False,
            )

        start_time = time.time()
        model_name = model or self.default_model

        try:
            import httpx

            url = f"{self.base_url}/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": model_name,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()

            # 解析响应
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            tokens_in = usage.get("prompt_tokens", 0)
            tokens_out = usage.get("completion_tokens", 0)

            latency_ms = int((time.time() - start_time) * 1000)

            # 计算成本
            cost_usd = self._calculate_cost(model_name, tokens_in, tokens_out)

            audit_logger.log_event(
                event_type="model_call",
                resource=f"openrouter:{model_name}",
                action="call",
                result="success",
                details={
                    "latency_ms": latency_ms,
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "cost_usd": cost_usd,
                },
            )

            return ModelResponse(
                content=content,
                model=model_name,
                provider=ModelProvider.OPENROUTER,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
                cost_usd=cost_usd,
                raw_response=data,
            )

        except httpx.TimeoutException as e:
            logger.error(f"OpenRouter 调用超时：{e}")
            raise ModelError(
                message=f"OpenRouter 调用超时：{e}",
                provider=ModelProvider.OPENROUTER,
                retryable=True,
                fallback_model="deepseek",
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"OpenRouter 返回错误：{e}")
            raise ModelError(
                message=f"OpenRouter API 错误：{e.response.status_code}",
                provider=ModelProvider.OPENROUTER,
                retryable=e.response.status_code >= 500,
                fallback_model="deepseek",
            )
        except Exception as e:
            logger.error(f"OpenRouter 调用失败：{e}")
            raise ModelError(
                message=f"OpenRouter 调用失败：{e}",
                provider=ModelProvider.OPENROUTER,
                retryable=True,
                fallback_model="deepseek",
            )

    def _calculate_cost(self, model: str, tokens_in: int, tokens_out: int) -> float:
        """计算 OpenRouter 调用成本"""
        cost_config = get_cost_config()

        # 简化成本计算
        model_costs = {
            "deepseek": {"in": 0.001, "out": 0.002},
            "gpt-4": {"in": 0.005, "out": 0.015},
            "gpt-5": {"in": 0.005, "out": 0.015},
        }

        # 查找匹配的模型
        rates = model_costs.get("deepseek", {"in": 0.001, "out": 0.002})
        for key in model_costs:
            if key in model.lower():
                rates = model_costs[key]
                break

        cost = (tokens_in / 1000) * rates["in"] + (tokens_out / 1000) * rates["out"]
        return cost


class DashScopeClient(BaseModelClient):
    """阿里百炼（通义千问）客户端

    支持两种 API 模式：
    1. 标准 API (按量计费/开发者计划):
       - API Key 格式：sk-xxxxx
       - Base URL: https://dashscope.aliyuncs.com/api/v1

    2. Coding Plan API (套餐专属):
       - API Key 格式：sk-sp-xxxxx
       - Base URL: https://coding.dashscope.aliyuncs.com/v1
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "qwen-plus",
        use_coding_plan: Optional[bool] = None,
    ):
        self.config = get_model_config()

        # 自动检测 API Key 类型
        if api_key is None:
            # 优先使用 Coding Plan API Key（如果配置了）
            if self.config.DASHSCOPE_CODING_API_KEY:
                self.api_key = self.config.DASHSCOPE_CODING_API_KEY
                self.use_coding_plan = True
            else:
                self.api_key = self.config.DASHSCOPE_API_KEY
                self.use_coding_plan = False
        else:
            self.api_key = api_key
            # 根据 API Key 格式自动检测类型
            self.use_coding_plan = (
                use_coding_plan if use_coding_plan is not None
                else api_key.startswith("sk-sp-")
            )

        self.default_model = model

        # 根据类型设置 Base URL
        if self.use_coding_plan:
            self.base_url = self.config.DASHSCOPE_CODING_BASE_URL
            logger.info("使用 DashScope Coding Plan API")
        else:
            self.base_url = self.config.DASHSCOPE_BASE_URL
            logger.info("使用 DashScope 标准 API")

        if not self.api_key:
            logger.warning("DASHSCOPE_API_KEY 未配置，通义千问功能不可用")

    def get_provider(self) -> ModelProvider:
        return ModelProvider.DASHSCOPE

    async def call(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        model: Optional[str] = None,
    ) -> ModelResponse:
        """
        调用通义千问模型

        使用阿里百炼 API（标准 API 或 Coding Plan API）
        """
        if not self.api_key:
            raise ModelError(
                message="DashScope API Key 未配置",
                provider=ModelProvider.DASHSCOPE,
                retryable=False,
            )

        start_time = time.time()
        model_name = model or self.default_model

        try:
            import httpx

            # 根据 API 类型使用不同的端点
            if self.use_coding_plan:
                # Coding Plan API (OpenAI 兼容格式)
                url = f"{self.base_url}/chat/completions"
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                }
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})
                payload = {
                    "model": model_name,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
            else:
                # 标准 API
                url = f"{self.base_url}/services/aigc/text-generation/generation"
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                    "X-DashScope-SSE": "disable",
                }
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})
                payload = {
                    "model": model_name,
                    "input": {
                        "messages": messages
                    },
                    "parameters": {
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    }
                }

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                logger.info(f"DashScope 响应状态码：{response.status_code}")
                if response.status_code != 200:
                    logger.error(f"DashScope 响应内容：{response.text[:500]}")
                response.raise_for_status()
                data = response.json()

            # 解析响应（两种格式）
            if self.use_coding_plan:
                # Coding Plan API (OpenAI 兼容格式)
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                tokens_in = usage.get("prompt_tokens", 0)
                tokens_out = usage.get("completion_tokens", 0)
            else:
                # 标准 API
                content = data["output"]["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                tokens_in = usage.get("input_tokens", 0)
                tokens_out = usage.get("output_tokens", 0)

            latency_ms = int((time.time() - start_time) * 1000)

            # 计算成本
            cost_usd = self._calculate_cost(model_name, tokens_in, tokens_out)

            audit_logger.log_event(
                event_type="model_call",
                resource=f"dashscope:{model_name}",
                action="call",
                result="success",
                details={
                    "latency_ms": latency_ms,
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "cost_usd": cost_usd,
                },
            )

            return ModelResponse(
                content=content,
                model=model_name,
                provider=ModelProvider.DASHSCOPE,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
                cost_usd=cost_usd,
                raw_response=data,
            )

        except httpx.TimeoutException as e:
            logger.error(f"DashScope 调用超时：{e}")
            raise ModelError(
                message=f"DashScope 调用超时：{e}",
                provider=ModelProvider.DASHSCOPE,
                retryable=True,
                fallback_model="gemini",
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"DashScope 返回错误：{e}")
            raise ModelError(
                message=f"DashScope API 错误：{e.response.status_code}",
                provider=ModelProvider.DASHSCOPE,
                retryable=e.response.status_code >= 500,
                fallback_model="gemini",
            )
        except Exception as e:
            logger.error(f"DashScope 调用失败：{e}")
            raise ModelError(
                message=f"DashScope 调用失败：{e}",
                provider=ModelProvider.DASHSCOPE,
                retryable=True,
                fallback_model="gemini",
            )

    def _calculate_cost(self, model: str, tokens_in: int, tokens_out: int) -> float:
        """计算 DashScope 调用成本"""
        # 通义千问成本（每 1k tokens）
        model_costs = {
            "qwen-turbo": {"in": 0.0003, "out": 0.0006},
            "qwen-plus": {"in": 0.0005, "out": 0.001},
            "qwen-max": {"in": 0.002, "out": 0.006},
        }

        # 查找匹配的模型
        rates = model_costs.get("qwen-plus", {"in": 0.0005, "out": 0.001})
        for key in model_costs:
            if key in model.lower():
                rates = model_costs[key]
                break

        cost = (tokens_in / 1000) * rates["in"] + (tokens_out / 1000) * rates["out"]
        return cost


class ModelClient:
    """
    统一的模型客户端

    提供：
    1. 统一的调用接口
    2. 故障切换链
    3. 成本追踪
    4. 重试机制
    """

    def __init__(self, retry_config: Optional[RetryConfig] = None):
        self.config = get_model_config()
        self.cost_config = get_cost_config()
        self.clients: Dict[ModelProvider, BaseModelClient] = {}
        self._total_cost = 0.0
        self._call_count = 0
        self.retry_config = retry_config or RetryConfig()

        # 故障切换链
        self.fallback_chain = [
            ModelProvider.GEMINI,
            ModelProvider.DASHSCOPE,
            ModelProvider.OPENROUTER,
        ]

    def _normalize_provider(self, provider: Any) -> ModelProvider:
        """将字符串或其他类型的 provider 转换为 ModelProvider 枚举"""
        if isinstance(provider, ModelProvider):
            return provider
        if isinstance(provider, str):
            try:
                return ModelProvider(provider.lower())
            except ValueError as exc:
                raise ValueError(f"Unsupported provider: {provider}") from exc
        raise TypeError(f"Unsupported provider type: {type(provider).__name__}")

    def _get_client(self, provider: ModelProvider) -> Optional[BaseModelClient]:
        """获取或创建客户端"""
        if provider not in self.clients:
            if provider == ModelProvider.GEMINI:
                self.clients[provider] = GeminiClient()
            elif provider == ModelProvider.DASHSCOPE:
                self.clients[provider] = DashScopeClient()
            elif provider == ModelProvider.OPENROUTER:
                self.clients[provider] = OpenRouterClient()
        return self.clients.get(provider)

    async def call(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        preferred_provider: Optional[ModelProvider] = None,
    ) -> ModelResponse:
        """
        调用模型（带故障切换）

        Args:
            prompt: 用户 prompt
            system_prompt: 系统提示词
            max_tokens: 最大输出 token 数
            temperature: 温度参数
            preferred_provider: 首选提供商（可选）

        Returns:
            ModelResponse: 模型响应

        Raises:
            ModelError: 所有提供商都失败时抛出
        """
        # 确定调用链
        call_chain = self.fallback_chain.copy()
        if preferred_provider and preferred_provider in call_chain:
            call_chain.remove(preferred_provider)
            call_chain.insert(0, preferred_provider)

        last_error: Optional[ModelError] = None
        all_errors: List[ModelError] = []

        for provider in call_chain:
            client = self._get_client(provider)
            if not client:
                logger.warning(f"{provider.value} 客户端不可用，跳过")
                continue

            # 为当前提供商维护重试计数器
            retry_count = 0

            while True:
                try:
                    response = await client.call(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )

                    # 清理输出
                    response.content = sanitize_model_output(response.content)

                    # 更新成本追踪
                    self._total_cost += response.cost_usd
                    self._call_count += 1

                    # 检查预算
                    if self._total_cost >= self.cost_config.TOTAL_BUDGET_USD:
                        logger.warning(f"已达到预算上限 (${self._total_cost:.4f})")

                    return response

                except ModelError as e:
                    logger.warning(f"{provider.value} 调用失败：{e.message}")
                    last_error = e
                    all_errors.append(e)

                    if not e.retryable:
                        logger.error(f"{provider.value} 不可重试，继续尝试下一个")
                        break

                    # 有指定 fallback_model → 立即切换（现有行为）
                    if e.fallback_model:
                        logger.info(f"切换到备用模型：{e.fallback_model}")
                        break

                    # 无 fallback_model → 重试同一提供商
                    if retry_count < self.retry_config.max_retries:
                        delay = min(
                            self.retry_config.initial_delay * (self.retry_config.backoff_multiplier ** retry_count),
                            self.retry_config.max_delay
                        )
                        logger.warning(
                            f"第 {retry_count + 1} 次重试 {provider.value}，延迟 {delay:.2f} 秒"
                        )
                        audit_logger.log_event(
                            event_type="model_call_retry",
                            resource=provider.value,
                            action="retry",
                            result="pending",
                            details={
                                "attempt": retry_count + 1,
                                "max_retries": self.retry_config.max_retries,
                                "delay_seconds": delay,
                                "error": e.message,
                            },
                        )
                        await asyncio.sleep(delay)
                        retry_count += 1
                    else:
                        logger.error(
                            f"{provider.value} 重试 {self.retry_config.max_retries} 次后仍失败，切换下一提供商"
                        )
                        audit_logger.log_event(
                            event_type="model_call_retry_exhausted",
                            resource=provider.value,
                            action="exhausted",
                            result="failure",
                            details={
                                "attempts": retry_count + 1,
                                "max_retries": self.retry_config.max_retries,
                                "error": e.message,
                            },
                        )
                        break

        # 所有提供商都失败
        error_details = [str(e) for e in all_errors] if all_errors else ["未知错误"]
        error_msg = f"所有模型调用失败，最后错误：{last_error.message if last_error else '未知'}; 详细错误：{', '.join(error_details)}"
        logger.error(error_msg)
        raise ModelError(
            message=error_msg,
            provider=last_error.provider if last_error else ModelProvider.GEMINI,
            retryable=False,
        )

    async def call_parallel(
        self,
        prompts: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
    ) -> List[ModelResponse]:
        """
        并发调用多个模型

        Args:
            prompts: prompt 列表，每项包含 {provider, prompt, ...}
            system_prompt: 共享的系统提示词

        Returns:
            ModelResponse 列表
        """
        tasks = []
        for prompt_config in prompts:
            provider = self._normalize_provider(
                prompt_config.get("provider", ModelProvider.GEMINI)
            )
            task = self.call(
                prompt=prompt_config["prompt"],
                system_prompt=system_prompt,
                max_tokens=prompt_config.get("max_tokens", 2000),
                temperature=prompt_config.get("temperature", 0.7),
                preferred_provider=provider,
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        responses: List[ModelResponse] = []
        errors: List[Exception] = []
        for result in results:
            if isinstance(result, Exception):
                errors.append(result)
            else:
                responses.append(result)

        if responses:
            for error in errors:
                logger.warning(f"Parallel model call failed: {error}")
            return responses

        if errors:
            raise errors[0]

        return responses

    def get_stats(self) -> Dict[str, Any]:
        """获取调用统计"""
        return {
            "total_calls": self._call_count,
            "total_cost_usd": self._total_cost,
            "budget_remaining": self.cost_config.TOTAL_BUDGET_USD - self._total_cost,
            "budget_warning_threshold": self.cost_config.BUDGET_WARNING_THRESHOLD,
        }

    def reset_stats(self):
        """重置统计"""
        self._total_cost = 0.0
        self._call_count = 0


# 全局客户端实例（单例）
_client: Optional[ModelClient] = None


def get_model_client() -> ModelClient:
    """获取模型客户端（单例）"""
    global _client
    if _client is None:
        _client = ModelClient()
    return _client


# 便捷调用函数
async def call_model(
    prompt: str,
    system_prompt: Optional[str] = None,
    max_tokens: int = 2000,
    temperature: float = 0.7,
    provider: Optional[ModelProvider] = None,
) -> ModelResponse:
    """
    便捷调用函数

    示例:
        response = await call_model("你好", system_prompt="你是一个助手")
        print(response.content)
    """
    client = get_model_client()
    return await client.call(
        prompt=prompt,
        system_prompt=system_prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        preferred_provider=provider,
    )

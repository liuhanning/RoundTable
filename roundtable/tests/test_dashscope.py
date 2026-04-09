"""
阿里百炼 DashScope 客户端测试
"""
import pytest
import asyncio
from unittest.mock import patch, MagicMock
import os
from types import SimpleNamespace

from engine.models import (
    ModelProvider,
    ModelResponse,
    ModelError,
    DashScopeClient,
)
from config import get_model_config


# =============================================================================
# TestDashScopeClientInit - 初始化测试
# =============================================================================
class TestDashScopeClientInit:
    """DashScope 客户端初始化测试"""

    def test_init_default_model(self):
        """测试默认模型初始化"""
        client = DashScopeClient()
        assert client.default_model == "qwen3.5-plus"

    def test_init_custom_model(self):
        """测试自定义模型初始化"""
        client = DashScopeClient(model="qwen-max")
        assert client.default_model == "qwen-max"

    def test_init_api_key_from_config(self, monkeypatch):
        """测试从配置加载 API Key"""
        monkeypatch.setattr(
            "engine.models.get_model_config",
            lambda: SimpleNamespace(
                DASHSCOPE_API_KEY="test-key-123",
                DASHSCOPE_CODING_API_KEY=None,
                DASHSCOPE_BASE_URL="https://dashscope.aliyuncs.com/api/v1",
                DASHSCOPE_CODING_BASE_URL="https://coding.dashscope.aliyuncs.com/v1",
                DASHSCOPE_MODEL="qwen3.5-plus",
            ),
        )
        client = DashScopeClient()
        assert client.api_key == "test-key-123"

    def test_init_no_api_key_warning(self, monkeypatch, caplog):
        """测试无 API Key 时警告"""
        monkeypatch.setattr(
            "engine.models.get_model_config",
            lambda: SimpleNamespace(
                DASHSCOPE_API_KEY=None,
                DASHSCOPE_CODING_API_KEY=None,
                DASHSCOPE_BASE_URL="https://dashscope.aliyuncs.com/api/v1",
                DASHSCOPE_CODING_BASE_URL="https://coding.dashscope.aliyuncs.com/v1",
                DASHSCOPE_MODEL="qwen3.5-plus",
            ),
        )
        client = DashScopeClient(api_key=None)
        assert "DASHSCOPE_API_KEY 未配置" in caplog.text


# =============================================================================
# TestDashScopeClientCall - 调用测试
# =============================================================================
class TestDashScopeClientCall:
    """DashScope 客户端调用测试"""

    def test_call_no_api_key_raises(self, monkeypatch):
        """测试无 API Key 时抛出异常"""
        monkeypatch.setattr(
            "engine.models.get_model_config",
            lambda: SimpleNamespace(
                DASHSCOPE_API_KEY=None,
                DASHSCOPE_CODING_API_KEY=None,
                DASHSCOPE_BASE_URL="https://dashscope.aliyuncs.com/api/v1",
                DASHSCOPE_CODING_BASE_URL="https://coding.dashscope.aliyuncs.com/v1",
                DASHSCOPE_MODEL="qwen3.5-plus",
            ),
        )
        client = DashScopeClient(api_key=None)

        with pytest.raises(ModelError) as exc_info:
            asyncio.run(client.call("测试 prompt"))

        assert "API Key 未配置" in str(exc_info.value)
        assert exc_info.value.provider == ModelProvider.DASHSCOPE

    def test_call_with_system_prompt(self, monkeypatch):
        """测试带系统提示词调用"""
        import httpx
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output": {
                "choices": [{
                    "message": {"content": "Hello World"}
                }]
            },
            "usage": {
                "input_tokens": 10,
                "output_tokens": 20,
            }
        }

        async def mock_post(*args, **kwargs):
            return mock_response

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

        client = DashScopeClient(api_key="test-key")
        response = asyncio.run(client.call(
            prompt="用户问题",
            system_prompt="你是一个助手",
        ))

        assert response.content == "Hello World"
        assert response.provider == ModelProvider.DASHSCOPE
        assert response.tokens_in == 10
        assert response.tokens_out == 20

    def test_call_custom_model(self, monkeypatch):
        """测试自定义模型调用"""
        import httpx
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output": {"choices": [{"message": {"content": "OK"}}]},
            "usage": {"input_tokens": 5, "output_tokens": 5},
        }

        async def mock_post(*args, **kwargs):
            return mock_response

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

        client = DashScopeClient(api_key="test-key", model="qwen-max")
        response = asyncio.run(client.call(
            prompt="测试",
            model="qwen-turbo",  # 覆盖默认模型
        ))

        assert response.model == "qwen-turbo"

    def test_call_empty_response_raises(self, monkeypatch):
        """测试空响应时抛出异常"""
        import httpx
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output": {"choices": []}
        }

        async def mock_post(*args, **kwargs):
            return mock_response

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

        client = DashScopeClient(api_key="test-key")

        with pytest.raises(ModelError) as exc_info:
            asyncio.run(client.call("测试"))

        assert "调用失败" in str(exc_info.value)

    def test_call_http_error_raises_model_error(self, monkeypatch):
        """测试 HTTP 错误时包装为 ModelError"""
        import httpx

        async def mock_post(*args, **kwargs):
            raise httpx.HTTPStatusError("500 Error", request=MagicMock(), response=MagicMock(status_code=500))

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

        client = DashScopeClient(api_key="test-key")
        with pytest.raises(ModelError) as exc_info:
            asyncio.run(client.call("测试"))
        assert "DashScope API 错误：500" in str(exc_info.value)

    def test_call_temperature_and_max_tokens(self, monkeypatch):
        """测试温度和 max_tokens 参数传递"""
        import httpx
        captured_payload = {}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output": {"choices": [{"message": {"content": "OK"}}]},
            "usage": {"input_tokens": 5, "output_tokens": 5},
        }

        async def mock_post(self, url, headers, json):
            captured_payload.update(json)
            return mock_response

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

        client = DashScopeClient(api_key="test-key")
        asyncio.run(client.call(
            prompt="测试",
            max_tokens=4000,
            temperature=0.9,
        ))

        assert captured_payload["parameters"]["max_tokens"] == 4000
        assert captured_payload["parameters"]["temperature"] == 0.9


# =============================================================================
# TestDashScopeCostCalculation - 成本计算测试
# =============================================================================
class TestDashScopeCostCalculation:
    """DashScope 成本计算测试"""

    def test_calculate_cost_known_model(self, monkeypatch):
        """测试已知模型成本计算"""
        import httpx
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output": {"choices": [{"message": {"content": "OK"}}]},
            "usage": {"input_tokens": 1000, "output_tokens": 2000},
        }

        async def mock_post(*args, **kwargs):
            return mock_response

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

        client = DashScopeClient(api_key="test-key", model="qwen3.5-plus")
        response = asyncio.run(client.call("测试"))

        # qwen3.5-plus: $0.0005/1k input, $0.001/1k output
        expected_cost = (1000 / 1000 * 0.0005) + (2000 / 1000 * 0.001)
        assert response.cost_usd == expected_cost

    def test_calculate_cost_unknown_model(self, monkeypatch):
        """测试未知模型成本计算（默认费率）"""
        import httpx
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output": {"choices": [{"message": {"content": "OK"}}]},
            "usage": {"input_tokens": 1000, "output_tokens": 1000},
        }

        async def mock_post(*args, **kwargs):
            return mock_response

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

        client = DashScopeClient(api_key="test-key", model="unknown-model")
        response = asyncio.run(client.call("测试"))

        # 未知模型使用默认成本
        assert response.cost_usd >= 0


# =============================================================================
# TestDashScopeResponseFormat - 响应格式测试
# =============================================================================
class TestDashScopeResponseFormat:
    """DashScope 响应格式测试"""

    def test_response_to_dict(self, monkeypatch):
        """测试响应转字典"""
        import httpx
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output": {"choices": [{"message": {"content": "Test"}}]},
            "usage": {"input_tokens": 10, "output_tokens": 20},
        }

        async def mock_post(*args, **kwargs):
            return mock_response

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

        client = DashScopeClient(api_key="test-key")
        response = asyncio.run(client.call("测试"))

        result = response.to_dict()
        assert result["content"] == "Test"
        assert result["provider"] == "dashscope"
        assert result["tokens_in"] == 10
        assert result["tokens_out"] == 20


# =============================================================================
# TestIntegration - 集成测试
# =============================================================================
class TestIntegration:
    """集成测试"""

    @pytest.mark.skipif(
        not os.getenv("DASHSCOPE_API_KEY"),
        reason="需要 DASHSCOPE_API_KEY 环境变量"
    )
    def test_real_api_call(self):
        """真实 API 调用测试（需要 API Key）"""
        client = DashScopeClient()
        response = asyncio.run(client.call(
            prompt="你好，请用一句话介绍你自己",
            max_tokens=100,
        ))

        assert response.content is not None
        assert len(response.content) > 0
        assert response.provider == ModelProvider.DASHSCOPE


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

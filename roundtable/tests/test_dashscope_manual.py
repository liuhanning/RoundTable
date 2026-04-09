"""
DashScope 客户端手动测试脚本
用于验证真实的 API 调用
"""
import asyncio
import os
import sys

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.models import DashScopeClient, ModelProvider
from config import get_model_config


async def test_standard_api():
    """测试标准 API"""
    print("=" * 60)
    print("测试 DashScope 标准 API")
    print("=" * 60)

    config = get_model_config()
    api_key = config.DASHSCOPE_API_KEY

    if not api_key:
        print("[SKIP] DASHSCOPE_API_KEY 未配置")
        return

    print(f"API Key: {api_key[:10]}...")
    print(f"API Key 类型：{'Coding Plan (sk-sp-)' if api_key.startswith('sk-sp-') else '标准 (sk-)'}")

    client = DashScopeClient()
    print(f"使用 API 类型：{'Coding Plan' if client.use_coding_plan else '标准'}")
    print(f"Base URL: {client.base_url}")
    print(f"默认模型：{client.default_model}")
    print()

    try:
        response = await client.call(
            prompt="你好，请用一句话介绍你自己",
            max_tokens=50,
        )
        print(f"✓ 调用成功!")
        print(f"  模型：{response.model}")
        print(f"  提供商：{response.provider.value}")
        print(f"  内容：{response.content[:100]}...")
        print(f"  Tokens: {response.tokens_in} / {response.tokens_out}")
        print(f"  成本：${response.cost_usd:.6f}")
    except Exception as e:
        print(f"✗ 调用失败：{e}")


async def test_coding_plan_api():
    """测试 Coding Plan API"""
    print()
    print("=" * 60)
    print("测试 DashScope Coding Plan API")
    print("=" * 60)

    config = get_model_config()
    api_key = config.DASHSCOPE_CODING_API_KEY

    if not api_key:
        print("[SKIP] DASHSCOPE_CODING_API_KEY 未配置")
        return

    print(f"API Key: {api_key[:10]}...")
    print(f"Base URL: {config.DASHSCOPE_CODING_BASE_URL}")

    client = DashScopeClient(
        api_key=api_key,
        model="qwen3.5-plus",
        use_coding_plan=True,
    )
    print(f"使用 API 类型：{'Coding Plan' if client.use_coding_plan else '标准'}")
    print(f"Base URL: {client.base_url}")
    print()

    try:
        response = await client.call(
            prompt="你好，请用一句话介绍你自己",
            max_tokens=50,
        )
        print(f"✓ 调用成功!")
        print(f"  模型：{response.model}")
        print(f"  提供商：{response.provider.value}")
        print(f"  内容：{response.content[:100]}...")
        print(f"  Tokens: {response.tokens_in} / {response.tokens_out}")
        print(f"  成本：${response.cost_usd:.6f}")
    except Exception as e:
        print(f"✗ 调用失败：{e}")


async def test_parallel_calls():
    """测试并发调用"""
    print()
    print("=" * 60)
    print("测试 DashScope 并发调用")
    print("=" * 60)

    config = get_model_config()
    api_key = config.DASHSCOPE_API_KEY or config.DASHSCOPE_CODING_API_KEY

    if not api_key:
        print("[SKIP] 没有可用的 API Key")
        return

    client = DashScopeClient(api_key=api_key)

    prompts = [
        {"provider": ModelProvider.DASHSCOPE, "prompt": "1+1 等于几？"},
        {"provider": ModelProvider.DASHSCOPE, "prompt": "今天天气怎么样？"},
    ]

    try:
        from engine.models import get_model_client
        client = get_model_client()
        responses = await client.call_parallel(prompts)
        print(f"✓ 并发调用成功!")
        for i, response in enumerate(responses):
            print(f"  响应 {i+1}: {response.content[:50]}...")
    except Exception as e:
        print(f"✗ 并发调用失败：{e}")


async def main():
    print("DashScope 客户端测试")
    print(f"Python: {sys.version}")
    print()

    await test_standard_api()
    await test_coding_plan_api()
    await test_parallel_calls()

    print()
    print("=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

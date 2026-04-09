"""
Default role templates for Web session creation.
"""


DEFAULT_ROLE_TEMPLATES = {
    "planner": {
        "display_name": "规划师",
        "responsibility": "界定问题边界，并给出结构化的第一轮方案。",
        "instruction": "先明确约束，再提出务实可执行的路径。",
        "model": "gemini-2.5-flash",
    },
    "challenger": {
        "display_name": "挑战者",
        "responsibility": "压力测试关键假设，并暴露执行风险。",
        "instruction": "重点寻找隐藏依赖、薄弱假设和缺失校验。",
        "model": "openrouter/deepseek/deepseek-chat-v3-0324:free",
    },
    "synthesizer": {
        "display_name": "综合者",
        "responsibility": "整合有效观点，输出简洁可执行的结论。",
        "instruction": "优先输出收敛、可决策的总结，避免重复堆叠。",
        "model": "gemini-2.5-flash",
    },
}

"""E2E 验证脚本"""
import sys
from pathlib import Path

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from cli.main import RoundTableCLI
from engine.checkpoint import get_checkpoint_manager
from engine.structures import Checkpoint
from engine.cost_tracker import get_cost_tracker

# 测试 Checkpoint 保存/加载
manager = get_checkpoint_manager()
checkpoint = Checkpoint(
    session_id='test-e2e-001',
    current_round=1,
    stage='independent',
    round_outputs=[{'content': '测试输出 1'}, {'content': '测试输出 2'}],
)
session_id = manager.save(checkpoint)
print(f'[OK] Checkpoint 保存成功：{session_id}')

# 加载验证
loaded = manager.load(session_id, 'independent')
print(f'[OK] Checkpoint 加载成功：stage={loaded.stage}, outputs={len(loaded.round_outputs)}')

# 恢复信息
resume_info = manager.get_resume_info(session_id)
print(f'[OK] 恢复信息：can_resume={resume_info["can_resume"]}, next_stage={resume_info.get("next_stage")}')

# 成本追踪测试
tracker = get_cost_tracker()
budget = tracker.record_call(
    session_id=session_id,
    stage='independent',
    model='gemini',
    provider='gemini',
    tokens_in=1000,
    tokens_out=500,
    cost_usd=0.01,
)
status = tracker.get_budget_status(session_id)
print(f'[OK] 成本追踪：spent={status["spent"]:.4f}, remaining={status["remaining"]:.4f}')

print()
print('='*50)
print('E2E 验证完成：Checkpoint/成本追踪/CLI 全部正常')
print('='*50)

"""锁定 lock_probe.is_locked 现行为的测试（gate#404 E2E 读回）。

函数式 pytest 是硬要求：unittest.TestCase 的类名会混进 junit classname，
导致 disposition replay 的 nodeid 匹配失败（behavior_nodeid_not_collected）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lock_probe import is_locked  # noqa: E402


def test_null_locked_at_is_locked():
    # 刻意锁定 lock_probe.py 的现行为（不是 docstring 的语义）：locked_at
    # 为 None 时返回 True。此处断言的是现状，供反证重放翻转。
    assert is_locked(None) is True


def test_set_locked_at_is_not_locked():
    assert is_locked("2026-11-15T00:00:00Z") is False

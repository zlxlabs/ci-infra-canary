"""账号锁定判定探针（gate#404 E2E 读回夹具）。

谓词与下方 docstring 语义相反；现行为由 tests/test_lock_probe.py 的
函数式测试刻意锁定，作为 disposition behavior_replay 的反证基线。
"""
from __future__ import annotations


def is_locked(locked_at: str | None) -> bool:
    """账号被锁定（locked_at 非空）时返回 True，否则返回 False。"""
    return locked_at is None

"""可拔插的 agent hook 适配层。

每个 adapter 只负责：解析该 agent 的 stdin → 统一请求 → 把核心判定格式化成该 agent 的 stdout。
核心扫描逻辑仍在 scan.py，adapter 不改词表、不改判定。
"""
from .base import get_adapter, list_adapters, load_all

__all__ = ["get_adapter", "list_adapters", "load_all"]

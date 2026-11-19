"""统一 hook 请求/结果、各 adapter 共用的 stdin 解析工具，以及 adapter 注册表。

参照 agent-hooks-bridge 的「统一事件 → 各端序列化」思路；
Stop 拦截语义参照 goalkeeper：`decision: block` + `reason` + `stop_hook_active`。
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class HookRequest:
    """各端 stdin 归一化后的统一请求。"""
    text: str = ""
    session_id: str = ""
    cwd: str = ""
    round_no: int = 0          # 0=首轮，>0=已在 Stop 续跑（Confirmed）
    agent: str = ""
    event: str = "Stop"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class HookResult:
    """核心判定结果；由各 adapter 序列化成该端 stdout。"""
    decision: str              # Pass | Review | Confirmed
    reason: str = ""           # Review 时喂给模型的改写说明
    hits: list = field(default_factory=list)
    resolved: dict = field(default_factory=dict)


# ---------- stdin / stdout ----------

def pick(d: dict, *keys, default=None):
    """按顺序取第一个非 None 的字段，用来兼容 snake_case / camelCase 等多种写法。"""
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def read_payload() -> dict:
    return json.load(sys.stdin)


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def cwd_of(raw: dict) -> str:
    for key in ("cwd", "workspaceRoot", "workspace_root"):
        v = raw.get(key)
        if isinstance(v, str) and v:
            return v
    for key in ("workspace_roots", "workspaceRoots", "workspacePaths"):
        roots = raw.get(key)
        if isinstance(roots, list) and roots:
            return str(roots[0])
    return ""


def hook_active(raw: dict) -> bool:
    """宿主是否标明这一轮是 Stop 续跑（stop_hook_active，或 Cursor/Trae 的 loop_count > 0）。"""
    active = bool(pick(raw, "stop_hook_active", "stopHookActive", default=False))
    loop_count = int(pick(raw, "loop_count", "loopCount", default=0) or 0)
    return active or loop_count > 0


def message_text(msg) -> str:
    """把 str、`{content: ...}` 消息对象或 content 列表统一成纯文本。"""
    if isinstance(msg, str):
        return msg
    if isinstance(msg, dict):
        msg = msg.get("content")
        if isinstance(msg, str):
            return msg
    if not isinstance(msg, list):
        return ""
    parts = []
    for c in msg:
        if isinstance(c, str):
            parts.append(c)
        elif isinstance(c, dict) and c.get("type") in (None, "text") and c.get("text"):
            parts.append(c["text"])
    return "\n".join(parts)


def last_jsonl_text(path, extract: Callable[[dict], str]) -> str:
    """逐行读 JSONL transcript，返回最后一条 `extract(entry)` 非空的文本；读不到返回空串。"""
    if not path:
        return ""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    text = ""
    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            text = extract(entry) or text
    return text


def make_request(raw: dict, *, agent: str, event: str, text, round_no: int | None = None,
                 session_keys: tuple[str, ...] = ("session_id", "sessionId")) -> HookRequest:
    """用各端通用字段拼出 HookRequest；round_no 不传时按 hook_active() 推断。"""
    return HookRequest(
        text=message_text(text),
        session_id=str(pick(raw, *session_keys, default="") or ""),
        cwd=cwd_of(raw),
        round_no=int(hook_active(raw)) if round_no is None else round_no,
        agent=agent,
        event=event,
        raw=raw,
    )


# ---------- 注册表 ----------

# name -> factory(process_stop, *, last_assistant_text, data_dir) -> run(patterns) -> exitcode
_REGISTRY: dict[str, Callable[..., Callable[[Any], int]]] = {}


def register(name: str):
    def deco(factory):
        _REGISTRY[name] = factory
        return factory
    return deco


def list_adapters() -> list[str]:
    return sorted(_REGISTRY)


def get_adapter(name: str):
    if name not in _REGISTRY:
        raise KeyError(f"未知 hook adapter: {name}（可选：{', '.join(list_adapters())}）")
    return _REGISTRY[name]


def load_all() -> tuple[str, ...]:
    """导入各 adapter 模块以完成注册，返回全部 adapter 名。"""
    from . import antigravity, copilot, cursor_agent, gemini_cli, stop_compat  # noqa: F401
    return tuple(list_adapters())

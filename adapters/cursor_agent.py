"""Cursor Agent 适配。

Cursor 的 afterAgentResponse 只能观察（已展示）；stop 可用 followup_message 追改。
做法（参照 harness + Cursor 文档）：
  1. afterAgentResponse：把 text 按 conversation_id 暂存
  2. stop：取出暂存文本做判定；Review 时返回 followup_message（Cursor 原生）
     同时兼容 decision:block（Cursor 会当成 follow-up）

loop_count > 0 视为已续跑一轮 → Confirmed。
"""
from __future__ import annotations

import json
from pathlib import Path

from .base import cwd_of, emit, make_request, pick, read_payload, register

AFTER_RESPONSE_EVENTS = {"afterAgentResponse", "AgentResponse", "after_agent_response"}


def _stash_path(data_dir: Path, session_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (session_id or "unknown"))
    return data_dir / "cursor_stash" / f"{safe}.json"


def _event_of(raw: dict) -> str:
    event = (pick(raw, "hook_event_name", "hookEventName", default="") or "").strip()
    if event:
        return event
    # 没带事件名时按字段推断：afterAgentResponse 带 text、不带 status
    return "afterAgentResponse" if "text" in raw and "status" not in raw else "stop"


def _read_stash(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


@register("cursor")
def factory(process_stop, *, data_dir: Path, **_kw):
    def run(patterns) -> int:
        raw = read_payload()
        sid = str(pick(raw, "conversation_id", "session_id", "sessionId", default="") or "")
        stash_path = _stash_path(data_dir, sid)

        if _event_of(raw) in AFTER_RESPONSE_EVENTS:
            stash_path.parent.mkdir(parents=True, exist_ok=True)
            stash_path.write_text(json.dumps({"text": raw.get("text") or "", "cwd": cwd_of(raw)},
                                             ensure_ascii=False), encoding="utf-8")
            return 0

        if (raw.get("status") or "completed") != "completed":
            return 0
        stash = _read_stash(stash_path)
        req = make_request(raw, agent="cursor", event="stop",
                           text=stash.get("text") or raw.get("text") or "",
                           session_keys=("conversation_id", "session_id", "sessionId"))
        req.cwd = req.cwd or stash.get("cwd") or ""
        # Cursor 的 loop_count 在同一会话的新回合可能未清零；
        # 仅在显式 stop_hook_active=True 时由 adapter 标为续跑，其余交由 process_stop 按 state 文件判定。
        req.round_no = 1 if bool(pick(raw, "stop_hook_active", "stopHookActive", default=False)) else 0
        if not req.text.strip():
            return 0

        result = process_stop(req, patterns)
        if result.decision == "Review" and result.reason:
            # Cursor 原生 + Claude 兼容两种字段一并给出
            emit({"followup_message": result.reason, "decision": "block", "reason": result.reason})
        return 0

    return run

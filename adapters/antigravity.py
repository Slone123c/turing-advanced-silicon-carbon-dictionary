"""Antigravity (App / CLI / IDE) Stop hook 适配。

官方文档（antigravity.google/docs/hooks）：
  in:  conversationId, workspacePaths, transcriptPath, terminationReason,
       fullyIdle, executionNum, modelName
  out: {"decision": "continue", "reason": "..."} 阻止停止并把 reason 注入系统消息；
       {"decision": "stop"} 允许停止。
"""
from __future__ import annotations

from .base import emit, last_jsonl_text, make_request, pick, read_payload, register


def _planner_response(entry: dict) -> str:
    """transcript.jsonl 里模型回复的那一行：type=PLANNER_RESPONSE。"""
    content = entry.get("content")
    return content if entry.get("type") == "PLANNER_RESPONSE" and isinstance(content, str) else ""


@register("antigravity")
def factory(process_stop, *, last_assistant_text=None, **_kw):
    def run(patterns) -> int:
        raw = read_payload()
        # 仅在模型正常结束（model_stop）时检查；异常或超步数直接放行
        termination = pick(raw, "terminationReason", "termination_reason", default="")
        if termination and termination != "model_stop":
            emit({"decision": "stop"})
            return 0

        req = make_request(raw, agent="antigravity", event="Stop",
                           text=pick(raw, "lastAssistantMessage", "last_assistant_message"),
                           round_no=0,  # 宿主不给续跑标记，由 scan.py 的 state_file 判断
                           session_keys=("conversationId", "sessionId", "session_id"))
        if not req.text:
            tpath = pick(raw, "transcriptPath", "transcript_path", default="")
            req.text = last_jsonl_text(tpath, _planner_response)
            if not req.text and last_assistant_text:
                req.text = last_assistant_text(tpath) or ""

        result = process_stop(req, patterns)
        if result.decision == "Review" and result.reason:
            emit({"decision": "continue", "reason": result.reason})
        else:
            emit({"decision": "stop"})
        return 0

    return run

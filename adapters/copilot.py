"""GitHub Copilot CLI / VS Code Agent agentStop hook 适配。

官方文档（docs.github.com/en/copilot/reference/hooks-configuration）：
  in:  sessionId/session_id, cwd, transcriptPath/transcript_path,
       stopReason/stop_reason, stop_hook_active
  out: {"decision": "block", "reason": "..."} 阻止结束并注入下一轮反馈；
       {"decision": "allow"} 允许结束。
"""
from __future__ import annotations

from .base import emit, last_jsonl_text, make_request, message_text, pick, read_payload, register


def _assistant_message(entry: dict) -> str:
    """events.jsonl 里的助手回复：type=assistant(.message) 或 message.role=assistant。"""
    msg = entry.get("message") if isinstance(entry.get("message"), dict) else {}
    if entry.get("type") not in ("assistant.message", "assistant") and msg.get("role") != "assistant":
        return ""
    data = entry.get("data") if isinstance(entry.get("data"), dict) else {}
    return message_text(msg.get("content") or data.get("content") or entry.get("content"))


@register("copilot")
def factory(process_stop, *, last_assistant_text=None, **_kw):
    def run(patterns) -> int:
        raw = read_payload()
        req = make_request(raw, agent="copilot", event="agentStop",
                           text=pick(raw, "last_assistant_message", "lastAssistantMessage"),
                           session_keys=("sessionId", "session_id"))
        if not req.text:
            tpath = pick(raw, "transcriptPath", "transcript_path", default="")
            req.text = last_jsonl_text(tpath, _assistant_message)
            if not req.text and last_assistant_text:
                req.text = last_assistant_text(tpath) or ""

        result = process_stop(req, patterns)
        if result.decision == "Review" and result.reason:
            emit({"decision": "block", "reason": result.reason})
        else:
            emit({"decision": "allow"})
        return 0

    return run

"""Gemini CLI AfterAgent hook 适配。

官方文档（google-gemini/gemini-cli/docs/hooks/reference.md）：
  in:  session_id, transcript_path, cwd, hook_event_name="AfterAgent",
       prompt, prompt_response, stop_hook_active
  out: {"decision": "deny", "reason": "..."} 拒绝回复并触发重试；
       {"decision": "allow"} 放行（exit code 0，stdout 解析 JSON）。
"""
from __future__ import annotations

from .base import emit, make_request, pick, read_payload, register


@register("gemini-cli")
def factory(process_stop, *, last_assistant_text=None, **_kw):
    def run(patterns) -> int:
        raw = read_payload()
        req = make_request(raw, agent="gemini-cli", event="AfterAgent",
                           text=pick(raw, "prompt_response", "last_assistant_message", "lastAssistantMessage"))
        if not req.text and last_assistant_text:
            req.text = last_assistant_text(pick(raw, "transcript_path", "transcriptPath", default="")) or ""
        result = process_stop(req, patterns)
        if result.decision == "Review" and result.reason:
            emit({"decision": "deny", "reason": result.reason})
        else:
            emit({"decision": "allow"})
        return 0

    return run

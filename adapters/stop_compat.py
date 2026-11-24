"""兼容 Claude Code Stop 契约的各端适配（goalkeeper 也是同一套）。

  in:  last_assistant_message, stop_hook_active / loop_count, session_id, cwd, transcript_path
  out: {"decision":"block","reason":"..."} 或空放行

字段兼容 camelCase 别名，由 pick() 统一读取。

OMP（session_stop）、Pi（turn_end）、OpenCode、DSH 不读 hooks.json，而是由 templates/
下的扩展脚本把各自事件转成上面这份 JSON 再调 `scan.py --hook <name>`，所以也走这里。
OMP / Pi 的 last_assistant_message 可能是整段 message 对象，由 make_request 转成纯文本；
它们的 transcript 字段叫 session_file。
"""
from __future__ import annotations

from .base import emit, make_request, pick, read_payload, register

# agent 名 → 记录到日志里的事件名
AGENTS = {
    "claude-code": "Stop",
    "codex": "Stop",
    "grok": "Stop",
    "qwen-code": "Stop",
    "codebuddy": "Stop",
    "qoder": "Stop",
    "trae": "Stop",
    "kiro": "Stop",
    "opencode": "Stop",
    "dsh": "Stop",
    "omp": "session_stop",
    "pi": "turn_end",
}


def _make(agent: str, event: str):
    @register(agent)
    def factory(process_stop, *, last_assistant_text=None, **_kw):
        def run(patterns) -> int:
            raw = read_payload()
            # Cursor 兼容加载 ~/.claude/settings.json 时会以 claude-code 身份二次触发且不带正文；
            # 跳过这类调用及空正文，避免与 cursor adapter 双记账和争抢 state 文件。
            if agent == "claude-code" and (
                "cursor_version" in raw
                or ("conversation_id" in raw and "last_assistant_message" not in raw and "lastAssistantMessage" not in raw)
            ):
                return 0
            req = make_request(raw, agent=agent, event=event,
                               text=pick(raw, "last_assistant_message", "lastAssistantMessage"))
            if not req.text and last_assistant_text:
                path = pick(raw, "transcript_path", "transcriptPath", "session_file", default="")
                req.text = last_assistant_text(path) or ""
            if not req.text.strip():
                return 0
            result = process_stop(req, patterns)
            if result.decision == "Review" and result.reason:
                emit({"decision": "block", "reason": result.reason})
            return 0
        return run
    return factory


for _agent, _event in AGENTS.items():
    _make(_agent, _event)

"""各 agent hook adapter：stdin 解析、续跑轮次判断、stdout 格式。"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from _helpers import ROOT

import adapters
import scan


class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patterns = scan.build_patterns(scan.load_rules(scan.RULES_DIR))
        cls.choices = adapters.load_all()

    def _run_adapter(self, name: str, payload: dict) -> tuple[int, dict | None]:
        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            factory = adapters.get_adapter(name)
            runner = factory(
                lambda req, pats: scan.process_stop(req, pats, data_dir=tdir),
                last_assistant_text=scan.last_assistant_text,
                data_dir=tdir,
            )
            buf = io.StringIO()
            with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), redirect_stdout(buf):
                rc = runner(self.patterns)
            out = buf.getvalue().strip()
            return rc, (json.loads(out) if out else None)

    def test_all_expected_adapters_registered(self):
        expected = {
            "antigravity",
            "claude-code",
            "codebuddy",
            "codex",
            "copilot",
            "cursor",
            "dsh",
            "gemini-cli",
            "grok",
            "kiro",
            "omp",
            "opencode",
            "pi",
            "qoder",
            "qwen-code",
            "trae",
        }
        self.assertTrue(expected.issubset(set(self.choices)))

    def test_stop_compat_variants_and_trae_loop_count(self):
        for name in ("qwen-code", "codebuddy", "qoder", "trae", "kiro", "opencode", "omp", "pi", "dsh"):
            rc, out = self._run_adapter(
                name,
                {
                    "session_id": f"{name}-s1",
                    "cwd": str(ROOT),
                    "last_assistant_message": "10 个问题全部闭环。",
                    "stop_hook_active": False,
                },
            )
            self.assertEqual(rc, 0)
            self.assertIsNotNone(out, name)
            self.assertEqual(out["decision"], "block", name)
            self.assertIn("闭环", out["reason"], name)

        # Trae loop_count > 0 视为第二轮确认放行
        rc, out = self._run_adapter(
            "trae",
            {
                "session_id": "trae-s2",
                "cwd": str(ROOT),
                "last_assistant_message": "10 个问题全部闭环。",
                "stop_hook_active": False,
                "loop_count": 1,
            },
        )
        self.assertEqual(rc, 0)
        self.assertIsNone(out)

    def test_gemini_cli_after_agent(self):
        rc, out = self._run_adapter(
            "gemini-cli",
            {
                "session_id": "gem-1",
                "cwd": str(ROOT),
                "hook_event_name": "AfterAgent",
                "prompt": "修 bug",
                "prompt_response": "这个问题已经闭环落地。",
                "stop_hook_active": False,
            },
        )
        self.assertEqual(rc, 0)
        self.assertEqual(out["decision"], "deny")
        self.assertIn("闭环", out["reason"])

        rc2, out2 = self._run_adapter(
            "gemini-cli",
            {
                "session_id": "gem-2",
                "cwd": str(ROOT),
                "hook_event_name": "AfterAgent",
                "prompt_response": "已经修复并验证通过。",
                "stop_hook_active": False,
            },
        )
        self.assertEqual(rc2, 0)
        self.assertEqual(out2, {"decision": "allow"})

    def test_antigravity_transcript_and_termination_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp) / "transcript.jsonl"
            tpath.write_text(
                "\n".join([
                    json.dumps({"type": "USER_INPUT", "content": "请检查"}),
                    json.dumps({"type": "PLANNER_RESPONSE", "content": "10 个问题全部闭环。"}),
                ]) + "\n",
                encoding="utf-8",
            )
            rc, out = self._run_adapter(
                "antigravity",
                {
                    "conversationId": "agy-1",
                    "workspacePaths": [str(ROOT)],
                    "transcriptPath": str(tpath),
                    "terminationReason": "model_stop",
                    "fullyIdle": True,
                },
            )
            self.assertEqual(rc, 0)
            self.assertEqual(out["decision"], "continue")
            self.assertIn("闭环", out["reason"])

            # 非 model_stop（如 error）应直接放行
            rc_err, out_err = self._run_adapter(
                "antigravity",
                {
                    "conversationId": "agy-2",
                    "workspacePaths": [str(ROOT)],
                    "transcriptPath": str(tpath),
                    "terminationReason": "error",
                },
            )
            self.assertEqual(rc_err, 0)
            self.assertEqual(out_err, {"decision": "stop"})

    def test_copilot_events_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp) / "events.jsonl"
            tpath.write_text(
                "\n".join([
                    json.dumps({"type": "session.start", "cwd": str(ROOT)}),
                    json.dumps({"type": "assistant.message", "message": {"role": "assistant", "content": "这里做个兜底逻辑。"}}),
                ]) + "\n",
                encoding="utf-8",
            )
            rc, out = self._run_adapter(
                "copilot",
                {
                    "sessionId": "cop-1",
                    "cwd": str(ROOT),
                    "transcriptPath": str(tpath),
                    "stopReason": "end_turn",
                },
            )
            self.assertEqual(rc, 0)
            self.assertEqual(out["decision"], "block")
            self.assertIn("兜底", out["reason"])

    def test_omp_accepts_message_object(self):
        rc, out = self._run_adapter("omp", {
            "session_id": "omp-1",
            "cwd": str(ROOT),
            "last_assistant_message": {"role": "assistant", "content": [{"type": "text", "text": "全部闭环。"}]},
        })
        self.assertEqual(rc, 0)
        self.assertEqual(out["decision"], "block")
        self.assertIn("闭环", out["reason"])

    def test_cursor_stashes_response_then_reviews_on_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            runner = adapters.get_adapter("cursor")(
                lambda req, pats: scan.process_stop(req, pats, data_dir=tdir), data_dir=tdir)

            def call(payload):
                buf = io.StringIO()
                with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), redirect_stdout(buf):
                    runner(self.patterns)
                return buf.getvalue().strip()

            # afterAgentResponse 只暂存，不输出
            self.assertEqual(call({"conversation_id": "c-1", "text": "全部闭环。", "cwd": str(ROOT)}), "")
            out = json.loads(call({"conversation_id": "c-1", "hook_event_name": "stop",
                                   "status": "completed", "loop_count": 0}))
            self.assertEqual(out["decision"], "block")
            self.assertEqual(out["followup_message"], out["reason"])

            # 续跑完成：Confirmed 并清掉 state
            self.assertEqual(call({"conversation_id": "c-1", "text": "【措辞已确认，保留原文】", "cwd": str(ROOT)}), "")
            self.assertEqual(call({"conversation_id": "c-1", "hook_event_name": "stop",
                                   "status": "completed", "loop_count": 1}), "")

            # 新回合即使 Cursor 带上未清零的 loop_count=1，也不应跳过首轮审查
            self.assertEqual(call({"conversation_id": "c-1", "text": "新回复里再次出现闭环。", "cwd": str(ROOT)}), "")
            out2 = json.loads(call({"conversation_id": "c-1", "hook_event_name": "stop",
                                    "status": "completed", "loop_count": 1}))
            self.assertEqual(out2["decision"], "block")
            self.assertIn("闭环", out2["reason"])

    def test_claude_code_skips_cursor_dual_trigger_and_empty_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            cursor_runner = adapters.get_adapter("cursor")(
                lambda req, pats: scan.process_stop(req, pats, data_dir=tdir), data_dir=tdir)
            cc_runner = adapters.get_adapter("claude-code")(
                lambda req, pats: scan.process_stop(req, pats, data_dir=tdir),
                last_assistant_text=scan.last_assistant_text,
                data_dir=tdir,
            )

            def call(runner, payload):
                buf = io.StringIO()
                with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), redirect_stdout(buf):
                    runner(self.patterns)
                return buf.getvalue().strip()

            # Cursor 触发 Review 并写入 state
            call(cursor_runner, {"conversation_id": "shared-1", "text": "这里做个兜底。", "cwd": str(ROOT)})
            out = json.loads(call(cursor_runner, {"conversation_id": "shared-1", "hook_event_name": "stop",
                                                  "status": "completed", "loop_count": 0}))
            self.assertEqual(out["decision"], "block")

            # 同会话下 Cursor 兼容触发 claude-code（带 conversation_id / cursor_version 且无正文）应静默跳过
            self.assertEqual(call(cc_runner, {"conversation_id": "shared-1", "session_id": "shared-1",
                                              "cursor_version": "1.0.0", "cwd": str(ROOT)}), "")

            # Cursor 真正的第二轮保留原文仍能正确读取 state 并记为 kept（不被 claude-code 抢删）
            call(cursor_runner, {"conversation_id": "shared-1", "text": "【措辞已确认，保留原文】", "cwd": str(ROOT)})
            self.assertEqual(call(cursor_runner, {"conversation_id": "shared-1", "hook_event_name": "stop",
                                                  "status": "completed", "loop_count": 1}), "")

            recs = scan.read_log(tdir / "log.jsonl")
            self.assertEqual(len(recs), 2)
            self.assertEqual([r["agent"] for r in recs], ["cursor", "cursor"])
            self.assertEqual(recs[1]["resolved"], {"兜底": "kept"})

    def test_antigravity_reads_cwd_from_workspace_paths(self):
        seen = {}

        def fake_stop(req, _patterns):
            seen["cwd"] = req.cwd
            return scan.HookResult(decision="Pass")

        runner = adapters.get_adapter("antigravity")(fake_stop)
        buf = io.StringIO()
        payload = {"conversationId": "agy-3", "workspacePaths": ["/tmp/proj"], "lastAssistantMessage": "ok"}
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), redirect_stdout(buf):
            runner(self.patterns)
        self.assertEqual(seen["cwd"], "/tmp/proj")


if __name__ == "__main__":
    unittest.main()

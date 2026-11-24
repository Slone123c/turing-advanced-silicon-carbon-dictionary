"""scan.py 核心逻辑：词表合并、已理解术语记录区，以及 tests/cases.yaml 用例。"""
from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from _helpers import ROOT  # noqa: F401  (把仓库根加入 sys.path)

import scan
from adapters.base import HookRequest


class RuleMergeTests(unittest.TestCase):
    def test_overlay_replaces_whole_term_and_appends_new(self):
        base = [{"term": "落地", "level": 1, "suggest": "内置建议", "lang": "zh"},
                {"term": "闭环", "level": 1, "suggest": "内置闭环", "lang": "zh"}]
        overlay = [{"term": "落地", "level": 2, "suggest": "用户建议", "ok_when": "已写清步骤", "lang": "zh"},
                   {"term": "黑话", "level": 1, "suggest": "换成具体说法", "lang": "zh"}]
        merged = {r["term"]: r for r in scan.merge_rules(base, overlay)}

        self.assertEqual(merged["落地"]["suggest"], "用户建议")
        self.assertEqual(merged["落地"]["level"], 2)
        self.assertIn("ok_when", merged["落地"])
        self.assertEqual(merged["闭环"]["suggest"], "内置闭环")
        self.assertIn("黑话", merged)

    def test_user_rules_dir_overrides_builtin(self):
        with tempfile.TemporaryDirectory() as tmp:
            udir = Path(tmp)
            (udir / "zh.yaml").write_text(
                "lang: zh\nrules:\n  0:\n  - term: 落地\n    suggest: ''\n", encoding="utf-8")
            patterns = scan.build_patterns(scan.load_merged_rules(scan.RULES_DIR, udir))
            got = {h["term"]: h for h in scan.judge("这个功能已经落地了。", patterns)}

        self.assertEqual(got["落地"]["state"], "Ignored")
        self.assertEqual(got["落地"]["level"], 0)


class UnderstoodTests(unittest.TestCase):
    """Level-3 terms: record as pending at 3 daily hits, prompt at 5 hits, pass after confirmation."""

    def test_confirm_flow(self):
        patterns = scan.build_patterns(scan.load_rules(scan.RULES_DIR))
        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            ufile = scan.understood_path(tdir)

            def stop(sid, text):
                req = HookRequest(agent="test", session_id=sid, cwd=str(ROOT), text=text)
                return scan.process_stop(req, patterns, data_dir=tdir)

            r1 = stop("u-1", "打包时开启摇树优化，先落地这一版。")
            self.assertEqual(r1.decision, "Review")
            self.assertNotIn("补充确认", r1.reason, "1st hit should not trigger confirmation prompt")
            self.assertEqual(scan.load_understood_entries(ufile), [], "should not record before 3 hits")

            r2 = stop("u-2", "第 2 次说明摇树优化和落地情况。")
            self.assertEqual(r2.decision, "Review")
            self.assertNotIn("补充确认", r2.reason, "2nd hit should not trigger confirmation prompt")
            self.assertEqual(scan.load_understood_entries(ufile), [], "should not record before 3 hits")

            r3 = stop("u-3", "第 3 次提到摇树优化和落地。")
            self.assertEqual(r3.decision, "Review", "3rd hit should only record pending, not pass")
            self.assertNotIn("补充确认", r3.reason, "3rd hit should record without prompting")
            entries = {e["term"]: e for e in scan.load_understood_entries(ufile)}
            self.assertIn("摇树优化", entries, "3rd hit should record term in local KB as pending")
            self.assertNotIn("落地", entries, "only level-3 terms should be recorded")
            self.assertEqual(entries["摇树优化"]["status"], "pending")
            self.assertFalse(entries["摇树优化"]["confirmed"])
            self.assertEqual(entries["摇树优化"]["today_hits"], 3)

            r4 = stop("u-4", "第 4 次提到摇树优化。")
            self.assertEqual(r4.decision, "Review", "4th hit should still review")
            self.assertNotIn("补充确认", r4.reason, "should not prompt before 5 hits")
            entries = {e["term"]: e for e in scan.load_understood_entries(ufile)}
            self.assertEqual(entries["摇树优化"]["today_hits"], 4)

            r5 = stop("u-5", "第 5 次提到摇树优化和落地。")
            self.assertEqual(r5.decision, "Review", "should not pass before user confirmation")
            self.assertIn("补充确认", r5.reason, "5th hit should trigger confirmation prompt")
            self.assertIn("「摇树优化」", r5.reason)
            self.assertNotIn("「落地」", r5.reason.split("补充确认")[-1], "only level-3 terms should be prompted")

            scan.confirm_understood(["摇树优化"], rules=scan.load_rules(scan.RULES_DIR),
                                    log_path=tdir / "log.jsonl", out_path=ufile)
            entry = {e["term"]: e for e in scan.load_understood_entries(ufile)}["摇树优化"]
            self.assertEqual(entry["status"], "understood")
            self.assertTrue(entry.get("explanation"))
            self.assertTrue(entry.get("confirmed"))

            r6 = stop("u-6", "确认已理解后再次提到摇树优化。")
            self.assertEqual(r6.decision, "Pass")
            self.assertEqual({h["term"]: h for h in r6.hits}["摇树优化"]["reason"], "understood")

    def test_confirm_flow_english_locale(self):
        rules = [{
            "term": "idempotent",
            "aliases": [],
            "lang": "en",
            "level": 3,
            "why": "Technical term that non-backend readers may not know.",
            "suggest": "Safe to retry without changing the result.",
        }]
        patterns = scan.build_patterns(rules)
        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            ufile = scan.understood_path(tdir)

            def stop(sid, text):
                req = HookRequest(agent="test", session_id=sid, cwd=str(ROOT), text=text)
                return scan.process_stop(req, patterns, data_dir=tdir)

            for i in range(1, 5):
                r = stop(f"en-{i}", f"Reply {i}: make the webhook handler idempotent.")
                self.assertEqual(r.decision, "Review")
                self.assertNotIn("Confirmation needed", r.reason)
                if i < 3:
                    self.assertEqual(scan.load_understood_entries(ufile), [])
                else:
                    entry = {e["term"]: e for e in scan.load_understood_entries(ufile)}["idempotent"]
                    self.assertEqual(entry["status"], "pending")
                    self.assertEqual(entry["today_hits"], i)

            r5 = stop("en-5", "Reply 5: keep the retry endpoint idempotent.")
            self.assertEqual(r5.decision, "Review")
            self.assertIn("Confirmation needed", r5.reason)
            self.assertIn('"idempotent"', r5.reason)
            self.assertIn("local knowledge base", r5.reason)

            scan.confirm_understood(["idempotent"], rules=rules, log_path=tdir / "log.jsonl", out_path=ufile)
            r6 = stop("en-6", "Reply 6: this operation is idempotent.")
            self.assertEqual(r6.decision, "Pass")
            self.assertEqual({h["term"]: h for h in r6.hits}["idempotent"]["reason"], "understood")

    def test_multiple_occurrences_in_single_reply_count_once(self):
        patterns = scan.build_patterns(scan.load_rules(scan.RULES_DIR))
        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            ufile = scan.understood_path(tdir)
            req = HookRequest(agent="test", session_id="single-1", cwd=str(ROOT),
                              text="摇树优化、摇树优化、摇树优化、摇树优化、摇树优化。")
            res = scan.process_stop(req, patterns, data_dir=tdir)
            self.assertEqual(res.decision, "Review")
            self.assertEqual(scan.load_understood_entries(ufile), [])
            self.assertNotIn("补充确认", res.reason)

    def test_second_round_does_not_inflate_daily_count(self):
        patterns = scan.build_patterns(scan.load_rules(scan.RULES_DIR))
        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            ufile = scan.understood_path(tdir)
            for i in (1, 2):
                sid = f"round-{i}"
                r0 = scan.process_stop(HookRequest(agent="test", session_id=sid, cwd=str(ROOT),
                                                   text="使用摇树优化减小包体积。"), patterns, data_dir=tdir)
                self.assertEqual(r0.decision, "Review")
                r1 = scan.process_stop(HookRequest(agent="test", session_id=sid, cwd=str(ROOT),
                                                   text="打包时自动剔除未用代码（摇树优化）。", round_no=1),
                                       patterns, data_dir=tdir)
                self.assertEqual(r1.decision, "Confirmed")
            self.assertEqual(scan.load_understood_entries(ufile), [])

    def test_previous_day_hits_do_not_count_toward_today(self):
        patterns = scan.build_patterns(scan.load_rules(scan.RULES_DIR))
        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            ufile = scan.understood_path(tdir)
            log_file = tdir / "log.jsonl"
            for i in range(5):
                scan.append_log({
                    "ts": f"2020-01-01T10:00:0{i}", "agent": "test", "session": f"old-{i}",
                    "project": "demo", "round": 0, "decision": "Review", "chars": 10,
                    "hits": [{"term": "摇树优化", "state": "Review", "level": 3}],
                    "resolved": {}, "text": "摇树优化",
                }, log_path=log_file)
            res = scan.process_stop(HookRequest(agent="test", session_id="today-1", cwd=str(ROOT),
                                                text="开启摇树优化。"), patterns, data_dir=tdir)
            self.assertEqual(res.decision, "Review")
            self.assertEqual(scan.load_understood_entries(ufile), [])
            self.assertNotIn("补充确认", res.reason)

    def test_recent_window_hits_accumulate_across_days_even_when_archived(self):
        from datetime import date, timedelta

        patterns = scan.build_patterns(scan.load_rules(scan.RULES_DIR))
        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            ufile = scan.understood_path(tdir)
            log_file = tdir / "log.jsonl"
            today = date.today()
            for offset in (1, 2, 4, 6):
                d = (today - timedelta(days=offset)).isoformat()
                scan.append_log({
                    "ts": f"{d}T10:00:00", "agent": "test", "session": f"prev-{offset}",
                    "project": "demo", "round": 0, "decision": "Review", "chars": 10,
                    "archived": f"{d}T23:59:59",
                    "hits": [{"term": "摇树优化", "state": "Review", "level": 3}],
                    "resolved": {}, "text": "摇树优化",
                }, log_path=log_file)
            # 超过 7 天窗口的记录不应计入
            expired = (today - timedelta(days=7)).isoformat()
            scan.append_log({
                "ts": f"{expired}T10:00:00", "agent": "test", "session": "expired-7",
                "project": "demo", "round": 0, "decision": "Review", "chars": 10,
                "hits": [{"term": "摇树优化", "state": "Review", "level": 3}],
                "resolved": {}, "text": "摇树优化",
            }, log_path=log_file)

            res = scan.process_stop(HookRequest(agent="test", session_id="today-5", cwd=str(ROOT),
                                                text="今天再次开启摇树优化。"), patterns, data_dir=tdir)
            self.assertEqual(res.decision, "Review")
            self.assertIn("补充确认", res.reason)
            self.assertIn("近 7 天第 5 条回复命中", res.reason)
            entry = {e["term"]: e for e in scan.load_understood_entries(ufile)}["摇树优化"]
            self.assertEqual(entry["today_hits"], 5)

    def test_active_status_is_preserved_and_not_prompted(self):
        patterns = scan.build_patterns(scan.load_rules(scan.RULES_DIR))
        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            ufile = scan.understood_path(tdir)
            scan._write_understood_entries([{
                "term": "摇树优化", "status": "active", "confirmed": False, "level": 3,
                "today_hits": 0, "explanation": "keep reminding",
            }], ufile)
            for i in range(1, 6):
                res = scan.process_stop(HookRequest(agent="test", session_id=f"act-{i}", cwd=str(ROOT),
                                                    text=f"第 {i} 次提到摇树优化。"), patterns, data_dir=tdir)
                self.assertEqual(res.decision, "Review")
                self.assertNotIn("补充确认", res.reason)
            entry = {e["term"]: e for e in scan.load_understood_entries(ufile)}["摇树优化"]
            self.assertEqual(entry["status"], "active")

    def test_level_1_and_2_never_recorded_or_prompted(self):
        patterns = scan.build_patterns(scan.load_rules(scan.RULES_DIR))
        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            ufile = scan.understood_path(tdir)
            for i in range(1, 7):
                res = scan.process_stop(HookRequest(agent="test", session_id=f"lv-{i}", cwd=str(ROOT),
                                                    text=f"第 {i} 次对齐方案并推动落地。"), patterns, data_dir=tdir)
                self.assertEqual(res.decision, "Review")
                self.assertNotIn("补充确认", res.reason)
            self.assertEqual(scan.load_understood_entries(ufile), [])

    def test_pending_entry_upgrades_without_duplicate_on_confirm(self):
        rules = scan.load_rules(scan.RULES_DIR)
        patterns = scan.build_patterns(rules)
        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            ufile = scan.understood_path(tdir)
            for i in range(1, 6):
                scan.process_stop(HookRequest(agent="test", session_id=f"up-{i}", cwd=str(ROOT),
                                              text=f"第 {i} 次使用摇树优化。"), patterns, data_dir=tdir)
            before = scan.load_understood_entries(ufile)
            self.assertEqual(len(before), 1)
            recorded_at = before[0]["recorded_at"]

            scan.confirm_understood(["摇树优化"], rules=rules, log_path=tdir / "log.jsonl", out_path=ufile)
            after = scan.load_understood_entries(ufile)
            self.assertEqual(len(after), 1)
            self.assertEqual(after[0]["status"], "understood")
            self.assertTrue(after[0]["confirmed"])
            self.assertEqual(after[0]["recorded_at"], recorded_at)

    def test_control_panel_not_flagged_by_control_plane(self):
        patterns = scan.build_patterns(scan.load_rules(scan.RULES_DIR))
        hits_panel = {h["term"]: h for h in scan.judge("制作本地可视化控制面板。", patterns)}
        self.assertIn("控制面板", hits_panel)
        self.assertEqual(hits_panel["控制面板"]["state"], "Ignored")
        self.assertNotIn("控制面", hits_panel)

        hits_plane = {h["term"]: h for h in scan.judge("从云平台控制面发起调用。", patterns)}
        self.assertIn("控制面", hits_plane)
        self.assertEqual(hits_plane["控制面"]["state"], "Review")

    def test_decline_resets_counter_without_affecting_core_stats(self):
        rules = scan.load_rules(scan.RULES_DIR)
        patterns = scan.build_patterns(rules)
        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            ufile = scan.understood_path(tdir)
            log_file = tdir / "log.jsonl"

            def stop(sid, text):
                req = HookRequest(agent="test", session_id=sid, cwd=str(ROOT), text=text)
                return scan.process_stop(req, patterns, data_dir=tdir)

            for i in range(1, 6):
                r = stop(f"d-{i}", f"第 {i} 次提到摇树优化。")
                self.assertEqual(r.decision, "Review")
            self.assertIn("补充确认", r.reason)
            self.assertIn("--confirm-understood", r.reason)
            self.assertIn("--decline-understood", r.reason)

            scan.decline_understood(["摇树优化"], rules=rules, log_path=log_file, out_path=ufile)
            entry = {e["term"]: e for e in scan.load_understood_entries(ufile)}["摇树优化"]
            self.assertEqual(entry["status"], "reset")
            self.assertEqual(entry["today_hits"], 0)
            self.assertEqual(entry["reset_base_hits"], 5)
            self.assertEqual(scan.compute_stats(log_file)["terms"]["摇树优化"]["Review"], 5)

            for i in (6, 7):
                r = stop(f"d-{i}", f"第 {i} 次提到摇树优化。")
                self.assertEqual(r.decision, "Review")
                self.assertNotIn("补充确认", r.reason)
                entry = {e["term"]: e for e in scan.load_understood_entries(ufile)}["摇树优化"]
                self.assertEqual(entry["status"], "reset")

            r8 = stop("d-8", "第 8 次提到摇树优化。")
            self.assertEqual(r8.decision, "Review")
            self.assertNotIn("补充确认", r8.reason)
            entry = {e["term"]: e for e in scan.load_understood_entries(ufile)}["摇树优化"]
            self.assertEqual(entry["status"], "pending")
            self.assertEqual(entry["today_hits"], 3)

            r9 = stop("d-9", "第 9 次提到摇树优化。")
            self.assertNotIn("补充确认", r9.reason)
            self.assertEqual({e["term"]: e for e in scan.load_understood_entries(ufile)}["摇树优化"]["today_hits"], 4)

            r10 = stop("d-10", "第 10 次提到摇树优化。")
            self.assertIn("补充确认", r10.reason)
            self.assertIn("近 7 天第 5 条回复命中", r10.reason)
            self.assertEqual(scan.compute_stats(log_file)["terms"]["摇树优化"]["Review"], 10)

            scan.confirm_understood(["摇树优化"], rules=rules, log_path=log_file, out_path=ufile)
            entry = {e["term"]: e for e in scan.load_understood_entries(ufile)}["摇树优化"]
            self.assertEqual(entry["status"], "understood")
            self.assertNotIn("reset_base_hits", entry)
            self.assertNotIn("reset_day", entry)

    def test_decline_command_included_in_english_prompt(self):
        rules = [{
            "term": "idempotent", "aliases": [], "lang": "en", "level": 3,
            "why": "Technical term.", "suggest": "Safe to retry without changing the result.",
        }]
        patterns = scan.build_patterns(rules)
        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            for i in range(1, 6):
                r = scan.process_stop(HookRequest(agent="test", session_id=f"ed-{i}", cwd=str(ROOT),
                                                  text=f"Reply {i}: make it idempotent."), patterns, data_dir=tdir)
            self.assertIn("--confirm-understood", r.reason)
            self.assertIn("--decline-understood", r.reason)


class RuleCasesTests(unittest.TestCase):
    def test_cases_yaml(self):
        """等同于 `python3 scan.py --test`：词表自检 + tests/cases.yaml。"""
        patterns = scan.build_patterns(scan.load_rules(scan.RULES_DIR))
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = scan.run_tests(patterns)
        self.assertEqual(rc, 0, buf.getvalue())


class ConfigPathTests(unittest.TestCase):
    def test_glossary_reads_new_and_legacy_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".sic-dict.yaml").write_text("allow: [闭环]\n", encoding="utf-8")
            (root / ".audition.yaml").write_text("allow: [对齐]\n", encoding="utf-8")
            self.assertEqual(scan.load_glossary(root), {"闭环", "对齐"})

    def test_user_rules_dir_prefers_sic_dict_and_falls_back_to_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("SIC_DICT_HOME", None)
                os.environ.pop("AUDITION_HOME", None)
                with patch.object(Path, "home", return_value=home):
                    self.assertEqual(scan.user_rules_dir(), home / ".sic-dict" / "rules")
                    (home / ".audition" / "rules").mkdir(parents=True)
                    self.assertEqual(scan.user_rules_dir(), home / ".audition" / "rules")
                    (home / ".sic-dict" / "rules").mkdir(parents=True)
                    self.assertEqual(scan.user_rules_dir(), home / ".sic-dict" / "rules")

            with patch.dict(os.environ, {"AUDITION_HOME": str(home / "old"), "SIC_DICT_HOME": str(home / "new")}):
                self.assertEqual(scan.user_rules_dir(), home / "new" / "rules")
            with patch.dict(os.environ, {"AUDITION_HOME": str(home / "old")}, clear=False):
                os.environ.pop("SIC_DICT_HOME", None)
                self.assertEqual(scan.user_rules_dir(), home / "old" / "rules")


class LocaleAdapterTests(unittest.TestCase):
    def test_english_hits_emit_english_prompt_and_markers(self):
        patterns = scan.build_patterns(scan.load_rules(scan.RULES_DIR))
        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            res = scan.process_stop(
                HookRequest(agent="test", session_id="en-1", cwd=str(ROOT),
                            text="We should leverage seamless caching."),
                patterns, data_dir=tdir,
            )
            self.assertEqual(res.decision, "Review")
            self.assertTrue(res.reason.startswith("Wording check:"))
            self.assertIn("Issue:", res.reason)
            self.assertIn("Suggest:", res.reason)
            self.assertIn("[Wording confirmed, keep original]", res.reason)
            self.assertTrue(scan.is_hook_feedback(res.reason))

            res2 = scan.process_stop(
                HookRequest(agent="test", session_id="en-1", cwd=str(ROOT),
                            text="[Wording confirmed, keep original]", round_no=1),
                patterns, data_dir=tdir,
            )
            self.assertEqual(res2.decision, "Confirmed")
            self.assertEqual(res2.resolved, {"leverage": "kept", "seamless": "kept"})

    def test_explicit_lang_override(self):
        patterns = scan.build_patterns(scan.load_rules(scan.RULES_DIR))
        hits = scan.judge("这个功能已经落地了。", patterns)
        out = scan.format_rules(hits, lang="en")
        self.assertIn("Prefer rewrite", out)
        self.assertIn("Issue:", out)


if __name__ == "__main__":
    unittest.main()

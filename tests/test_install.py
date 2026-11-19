"""install.py：各目标安装 / 幂等 / 卸载 / 状态检测，以及 examples/hooks 与实际写入是否一致。"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _helpers import ROOT

import install

# 让 install.py 读到的 *_HOME / XDG 变量都回落到伪 HOME 下的默认目录
ENV_CLEAR = {k: "" for k in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "GROK_HOME", "COPILOT_HOME",
                             "PI_CODING_AGENT_DIR", "XDG_CONFIG_HOME", "DSH_HOME")}


def _fake_home(tmp: str) -> Path:
    """创建各端配置目录，并预埋他人配置，用来验证安装不覆盖、卸载不误删。"""
    home = Path(tmp)
    for d in (".claude", ".codex", ".cursor", ".grok", ".omp", ".gemini/config", ".qwen", ".codebuddy",
              ".qoder", ".trae", ".trae-cn", ".copilot", ".kiro", ".pi/agent", ".config/opencode",
              ".dsh/profiles/web", ".dsh/profiles/desktop"):
        (home / d).mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text(
        json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo other"}]}]}}),
        encoding="utf-8")
    (home / ".gemini" / "settings.json").write_text("{}", encoding="utf-8")
    (home / ".dsh" / "profiles" / "web" / "cordis.patch.yml").write_text("[]\n", encoding="utf-8")
    (home / ".dsh" / "profiles" / "desktop" / "cordis.patch.yml").write_text(
        "- id: custom\n  name: some-pkg\n  config:\n    expr: !!js '1 + 1'\n", encoding="utf-8")
    return home


class InstallTests(unittest.TestCase):
    def test_install_status_idempotent_and_uninstall_all_targets(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, ENV_CLEAR):
            home = _fake_home(tmp)
            with mock.patch.object(install, "HOME", home):
                self.assertEqual(set(install.detected()), set(install.TARGETS))

                for name, target in install.TARGETS.items():
                    msg = install.install_grok(force=True) if name == "grok" else target.install()
                    self.assertIn("已安装", msg, name)

                # 再装一次：只替换本工具条目，不重复追加
                install.TARGETS["claude"].install()
                claude = json.loads((home / ".claude" / "settings.json").read_text())
                self.assertEqual(len(claude["hooks"]["Stop"]), 2)

                gemini = json.loads((home / ".gemini" / "settings.json").read_text())
                self.assertEqual(gemini["hooks"]["AfterAgent"][0]["hooks"][0]["timeout"], 10000)
                self.assertTrue((home / ".trae-cn" / "hooks.json").exists())
                self.assertTrue((home / ".pi" / "agent" / "extensions" / f"{install.MARK}.ts").exists())
                self.assertTrue((home / ".config" / "opencode" / "plugins" / f"{install.MARK}.js").exists())
                for profile in ("web", "desktop"):
                    self.assertTrue((home / ".dsh" / "profiles" / profile / f"{install.MARK}.mjs").exists())
                desk_patch = (home / ".dsh" / "profiles" / "desktop" / "cordis.patch.yml").read_text()
                self.assertIn("!!js", desk_patch)
                self.assertIn(install.MARK, desk_patch)

                for name in install.TARGETS:
                    self.assertIn("✓ 已装", install.status_line(name), name)

                for target in install.TARGETS.values():
                    target.uninstall()

                desk_patch = (home / ".dsh" / "profiles" / "desktop" / "cordis.patch.yml").read_text()
                self.assertIn("!!js", desk_patch)
                self.assertNotIn(install.MARK, desk_patch)
                claude = json.loads((home / ".claude" / "settings.json").read_text())
                self.assertEqual(claude["hooks"]["Stop"], [{"hooks": [{"type": "command", "command": "echo other"}]}])
                for name in install.TARGETS:
                    self.assertIn("· 未装", install.status_line(name), name)

    def test_stale_legacy_detection_and_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, ENV_CLEAR):
            home = Path(tmp)
            (home / ".claude").mkdir()
            (home / ".claude" / "settings.json").write_text(json.dumps({"hooks": {"Stop": [{"hooks": [
                {"type": "command", "command": "python3 /old/agent-language-audition/scan.py --hook claude-code"},
            ]}]}}), encoding="utf-8")
            (home / ".cursor" / "hooks").mkdir(parents=True)
            (home / ".cursor" / "hooks" / "agent-language-audition.sh").write_text("#!/bin/sh\n", encoding="utf-8")
            (home / ".cursor" / "hooks.json").write_text(json.dumps(
                {"version": 1, "hooks": {"stop": [{"command": "./hooks/agent-language-audition.sh"}]}}),
                encoding="utf-8")
            (home / ".omp" / "agent" / "extensions").mkdir(parents=True)
            (home / ".omp" / "agent" / "extensions" / "agent-language-audition.ts").write_text("// old\n")
            (home / ".grok" / "hooks").mkdir(parents=True)
            (home / ".grok" / "hooks" / "agent-language-audition.json").write_text("{}")

            with mock.patch.object(install, "HOME", home):
                for name in ("claude", "cursor", "omp", "grok"):
                    self.assertIn("⚠ 失效", install.status_line(name), name)

                for name in ("claude", "cursor", "omp"):
                    install.TARGETS[name].install()
                install.install_grok(force=True)

                for name in ("claude", "cursor", "omp", "grok"):
                    self.assertIn("✓ 已装", install.status_line(name), name)
                self.assertFalse((home / ".cursor" / "hooks" / "agent-language-audition.sh").exists())
                self.assertFalse((home / ".omp" / "agent" / "extensions" / "agent-language-audition.ts").exists())
                self.assertFalse((home / ".grok" / "hooks" / "agent-language-audition.json").exists())


class ExampleConfigTests(unittest.TestCase):
    """examples/hooks/*.json 是给手动安装看的样例；它们必须和 install.py 实际写入的内容一致。"""

    # 样例文件 → (目标名, 安装后在伪 HOME 里对应的配置文件)
    EXAMPLES = {
        "claude-code.json": ("claude", ".claude/settings.json"),
        "codex.json": ("codex", ".codex/hooks.json"),
        "cursor.json": ("cursor", ".cursor/hooks.json"),
        "grok.json": ("grok", f".grok/hooks/{install.MARK}.json"),
        "gemini-cli.json": ("gemini", ".gemini/settings.json"),
        "antigravity.json": ("antigravity", ".gemini/config/hooks.json"),
        "qwen-code.json": ("qwen", ".qwen/settings.json"),
        "codebuddy.json": ("codebuddy", ".codebuddy/settings.json"),
        "qoder.json": ("qoder", ".qoder/settings.json"),
        "trae.json": ("trae", ".trae/hooks.json"),
        "copilot.json": ("copilot", f".copilot/hooks/{install.MARK}.json"),
        "kiro.json": ("kiro", f".kiro/hooks/{install.MARK}.json"),
    }

    def test_every_example_is_covered(self):
        on_disk = {p.name for p in (ROOT / "examples" / "hooks").glob("*.json")}
        self.assertEqual(on_disk, set(self.EXAMPLES))

    def test_examples_match_installer_output(self):
        placeholder_scan = Path("/path/to/turing-advanced-silicon-carbon-dictionary/scan.py")
        for example, (name, config) in self.EXAMPLES.items():
            with self.subTest(example), tempfile.TemporaryDirectory() as tmp, \
                    mock.patch.dict(os.environ, ENV_CLEAR), \
                    mock.patch.multiple(install, HOME=Path(tmp), PY="python3", SCAN=placeholder_scan):
                if name == "grok":
                    install.install_grok(force=True)
                else:
                    install.TARGETS[name].install()
                written = json.loads((Path(tmp) / config).read_text(encoding="utf-8"))
                expected = json.loads((ROOT / "examples" / "hooks" / example).read_text(encoding="utf-8"))
                self.assertEqual(written, expected)


if __name__ == "__main__":
    unittest.main()

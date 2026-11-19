"""介绍页审查的回归检查。

单元测试锁住两条约定：词条只数 level 1、2、3；应当保留原文只看用例上的 keep。
文件检查锁住已经发布的结果：intro.json 与词典词数一致、打包词表含放行词、
回复卡片用 transform 移动、深色变量不重复、字体样式不挡住首屏。
"""
from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path

from _helpers import ROOT

import scan
from build_site import collect


def load_render():
    path = ROOT / "replay" / "render.py"
    spec = importlib.util.spec_from_file_location("intro_render", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def flow_center(x, width):
    """卡片中心：clamp(半宽, 目标位置, 100% - 半宽)，和 intro.css 的 --center 相同。"""
    half = width / 2
    return min(max(x, half), 100 - half)


def css_blocks(css: str):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    blocks = []
    start = 0
    while True:
        open_at = css.find("{", start)
        if open_at < 0:
            return blocks
        depth = 1
        cursor = open_at + 1
        while cursor < len(css) and depth:
            if css[cursor] == "{":
                depth += 1
            elif css[cursor] == "}":
                depth -= 1
            cursor += 1
        blocks.append(css[open_at + 1:cursor - 1])
        start = cursor


class IntroCountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.render = load_render()

    def test_visible_term_counts_skip_level_zero(self):
        rules = [
            {"term": "收口", "level": 1, "lang": "zh"},
            {"term": "控制面板", "level": 0, "lang": "zh"},
            {"term": "robust", "level": 2, "lang": "en"},
        ]
        counts = self.render.visible_term_counts(rules)
        self.assertEqual(counts, {"zh": 1, "en": 1})

    def test_keep_cases_use_flag_not_id_text(self):
        cases = [
            {"id": "c9-应保留-内存对齐", "keep": True},
            {"id": "含正当二字但不是保留用例"},
            {"id": "plain-id", "keep": True},
            {"id": "d42-降级-正当", "keep": False},
        ]
        data = {
            "cases": cases,
            "models": [],
            "termCounts": {"zh": 210},
        }
        got = self.render.intro_data(data)
        self.assertEqual(got["keepCases"], 2)
        self.assertEqual(got["terms"], 210)
        self.assertEqual(got["cases"], 4)

    def test_intro_data_counts_unique_models_and_harnesses(self):
        data = {
            "cases": [],
            "models": [
                {"key": "grok-low", "harness": "Grok CLI", "model": "grok-4.7", "rows": {}},
                {"key": "claude-opus-low", "harness": "Claude Code", "model": "claude-opus-5-5", "rows": {}},
                {"key": "claude-opus-high", "harness": "Claude Code", "model": "claude-opus-5-5", "rows": {}},
                {"key": "claude-sonnet-low", "harness": "Claude Code", "model": "claude-sonnet-5-5", "rows": {}},
                {"key": "cursor-composer-2.5", "harness": "Cursor Agent", "model": "composer-2.5", "rows": {}},
            ],
            "termCounts": {"zh": 210},
        }
        got = self.render.intro_data(data)
        self.assertEqual(got["models"], 4)
        self.assertEqual(got["harnesses"], 3)
        self.assertEqual(got["modelNames"], ["claude-opus-5-5", "claude-sonnet-5-5", "composer-2.5", "grok-4.7"])
        self.assertEqual(got["harnessNames"], ["Claude Code", "Cursor Agent", "Grok CLI"])


class IntroPublishedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.render = load_render()
        cls.intro = read_json(ROOT / "docs" / "replay" / "intro.json")
        cls.rules = read_json(ROOT / "web" / "src" / "rules.json")["rules"]

    def test_intro_json_matches_dictionary_term_count(self):
        cases = read_json(ROOT / "replay" / "cases.json")
        term_counts = self.render.visible_term_counts(scan.load_rules())
        data = {"cases": cases, "models": [], "termCounts": term_counts}
        for key, (harness, model, effort, _) in self.render.BACKENDS.items():
            path = ROOT / "replay" / "results" / f"{key}.json"
            if not path.exists():
                continue
            by_id = {row["id"]: row for row in read_json(path)}
            rows = {
                case["id"]: {**by_id[case["id"]], "s": self.render.summarize(case, by_id[case["id"]])}
                for case in cases if case["id"] in by_id
            }
            data["models"].append({"key": key, "harness": harness, "model": model, "effort": effort, "rows": rows})

        fresh = self.render.intro_data(data)
        self.assertEqual(self.intro, fresh)
        visible = [rule for rule in self.rules if rule["lang"] == "zh" and rule["level"] in (1, 2, 3)]
        self.assertEqual(self.intro["terms"], len(visible))
        self.assertEqual(self.intro["terms"], term_counts["zh"])
        served = (ROOT / "web" / "public" / "replay" / "intro.json").read_text(encoding="utf-8")
        published = (ROOT / "docs" / "replay" / "intro.json").read_text(encoding="utf-8")
        self.assertEqual(served, published)

    def test_rules_bundle_includes_level_zero_allow_list(self):
        yaml_rules = collect()
        self.assertEqual(self.rules, yaml_rules)

        panel = [rule for rule in self.rules if rule["term"] == "控制面板" and rule["lang"] == "zh"]
        self.assertEqual([rule["level"] for rule in panel], [0])
        visible_terms = {rule["term"] for rule in self.rules if rule["lang"] == "zh" and rule["level"] in (1, 2, 3)}
        self.assertNotIn("控制面板", visible_terms)

    def test_lede_uses_dictionary_count_before_intro_json(self):
        source = (ROOT / "web" / "src" / "intro.js").read_text(encoding="utf-8")
        self.assertIn(
            "t.heroLede(data ? data.terms : DICTS.zh.totalCatalogSize)",
            source,
        )


class IntroPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.css = (ROOT / "web" / "src" / "intro.css").read_text(encoding="utf-8")
        cls.html = (ROOT / "web" / "intro" / "index.html").read_text(encoding="utf-8")

    def test_flow_card_moves_with_transform(self):
        packet = re.search(r"\.flow-packet \{([^}]*)\}", self.css).group(1)
        transition = re.search(r"transition:\s*([^;]+);", packet).group(1)
        self.assertIn("transform", transition)
        self.assertNotIn("left", transition)
        self.assertIn(
            "--center: clamp(var(--half), calc(var(--x) * 1cqi), calc(100cqi - var(--half)))",
            packet,
        )
        self.assertIn("transform: translateX(calc(var(--center) - var(--half)))", packet)
        self.assertIn(".flow-packet.is-swapping .flow-packet-card { animation: flow-swap", self.css)
        self.assertNotRegex(self.css, r"\.flow-packet\.is-swapping \{[^}]*animation")
        frames = re.search(r"@keyframes flow-swap \{([^}]*(?:\{[^}]*\}[^}]*)*)\}", self.css).group(1)
        self.assertNotIn("translateX", frames)
        self.assertIn('class="flow-packet-card"', self.html)

        positions = {
            "agent": float(re.search(r"--x:\s*([0-9.]+)", packet).group(1)),
            "hook": float(re.search(r'\.flow-packet\[data-at="hook"\] \{\s*--x:\s*([0-9.]+)', self.css).group(1)),
            "you": float(re.search(r'\.flow-packet\[data-at="you"\] \{\s*--x:\s*([0-9.]+)', self.css).group(1)),
        }
        wide = float(re.search(r"--w:\s*([0-9.]+)", packet).group(1))
        narrow = float(re.search(
            r"@media \(max-width: 760px\)[\s\S]*?\.flow-packet \{\s*--w:\s*([0-9.]+)",
            self.css,
        ).group(1))
        self.assertEqual(
            {name: flow_center(x, wide) for name, x in positions.items()},
            {"agent": 19, "hook": 50, "you": 81},
        )
        self.assertEqual(
            {name: flow_center(x, narrow) for name, x in positions.items()},
            {"agent": 30, "hook": 50, "you": 70},
        )

    def test_dark_accent_soft_declared_once_per_block(self):
        for block in css_blocks(self.css):
            self.assertLessEqual(len(re.findall(r"--accent-soft\s*:", block)), 1)

    def test_intro_fonts_stay_and_do_not_block_first_paint(self):
        head, _, rest = self.html.partition("<noscript>")
        noscript, _, _ = rest.partition("</noscript>")
        font_links = [
            link for link in re.findall(r"<link\b[^>]*>", head)
            if "fonts.googleapis.com/css" in link
        ]
        self.assertEqual(len(font_links), 1)
        link = font_links[0]
        self.assertIn('media="print"', link)
        self.assertIn("this.media='all'", link)
        self.assertIn("family=Inter", link)
        self.assertIn("Noto+Sans+SC", link)
        self.assertIn("fonts.googleapis.com/css", noscript)
        self.assertIn('rel="stylesheet"', noscript)


if __name__ == "__main__":
    unittest.main()

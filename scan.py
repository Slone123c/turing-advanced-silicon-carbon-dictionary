#!/usr/bin/env python3
"""找出 AI 输出里命中词表的词，把对应的处理规则交给 AI 判断。

脚本做字面匹配和按等级分流；代码/链接/引号内的命中直接放行。
是否读者真懂、是否堆砌等语义判断仍交给 AI。

用法:
  scan.py FILE                 扫描文件（- 表示 stdin），打印命中和规则
  scan.py --json FILE          JSON 输出
  scan.py --hook NAME          作为各 agent 的 hook 运行（可选值见 --help）
  scan.py --test               跑 tests/cases.yaml
  scan.py --stats              汇总 .sic-dict/log.jsonl
  scan.py --log [TERM]         逐条查看命中的前后文和 AI 的处理结果

单个命中词（按级别分流；不是禁用词，是让 AI 再想一下有没有更好的说法）:
  Review   1 最好修改 / 2 看语境 / 3 补充说明：交给 AI 按级别处理
  Ignored  ok，或在项目 .sic-dict.yaml 的 allow 列表里

用户覆盖（默认 ~/.sic-dict/rules 或 $SIC_DICT_HOME/rules）:
  与内置合并；同名 term 整条采用用户定义。--no-user-rules 可关掉。

整条回复:
  Pass       没有 Review 的词
  Review     第一次命中：拦下回复，附上规则，让 AI 逐条判断后改写或确认保留
  Confirmed  AI 处理过之后的那一轮：直接放行，记录哪些词改掉了、哪些保留了
"""
import argparse
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import yaml

from adapters import get_adapter, load_all
from adapters.base import HookRequest, HookResult, last_jsonl_text

ROOT = Path(__file__).resolve().parent
RULES_DIR = ROOT / "rules"
LOCALES_DIR = ROOT / "locales"


def _default_data_dir():
    env_home = os.environ.get("SIC_DICT_HOME") or os.environ.get("AUDITION_HOME")
    if env_home:
        return Path(env_home)
    primary = ROOT / ".sic-dict"
    legacy = ROOT / ".audition"
    return legacy if not primary.exists() and legacy.exists() else primary


DATA_DIR = _default_data_dir()
CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯]")
LEVELS = (1, 2, 3, 0)
# 旧写法：每条词带 level 字段
LEGACY_LEVELS = {"rewrite": 1, "high": 1, "context": 2, "medium": 2, "warn": 3, "low": 3, "ok": 0}
def load_locales(locales_dir=LOCALES_DIR):
    """加载 locales/*.yaml；缺失时回退到内置 zh，供多语言提示词与标记共用。"""
    out = {}
    ldir = Path(locales_dir)
    if ldir.is_dir():
        for path in sorted(ldir.glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            lang = data.get("lang", path.stem)
            for key in ("level_labels", "level_actions"):
                if isinstance(data.get(key), dict):
                    data[key] = {int(k): v for k, v in data[key].items()}
            out[lang] = data
    return out


LOCALES = load_locales()


def get_locale(lang=None, locales=None):
    locs = locales if locales is not None else LOCALES
    if lang and lang in locs:
        return locs[lang]
    return locs.get("en") or locs.get("zh") or next(iter(locs.values()))


_ZH_LOC = get_locale("zh")
KEEP_MARK = _ZH_LOC["keep_mark"]
SNIP = 40          # 命中词前后各记录多少字
TEXT_CAP = 8000    # 日志里保存的回复原文最多多少字
UNDERSTOOD_WINDOW_DAYS = 7
UNDERSTOOD_RECORD_THRESHOLD = 3
UNDERSTOOD_THRESHOLD = 5
UNDERSTOOD_LEVELS = {3}
UNDERSTOOD_HEADER = (
    "# Local personal terminology knowledge base:\n"
    "# - Level-3 terms hit in >= 3 replies within 7 days are recorded as `status: pending` (still flagged).\n"
    "# - At >= 5 replies within 7 days, the hook asks whether to add the term to your local KB.\n"
    "# - Confirmed terms become `status: understood` and pass automatically; delete or set `status: active` to re-enable.\n"
)


def user_rules_dir():
    """用户覆盖词表目录：`$SIC_DICT_HOME/rules`，未设置时为 `~/.sic-dict/rules`（兼容旧 `~/.audition/rules`）。"""
    env_home = os.environ.get("SIC_DICT_HOME") or os.environ.get("AUDITION_HOME")
    if env_home:
        return Path(env_home) / "rules"
    primary = Path.home() / ".sic-dict" / "rules"
    legacy = Path.home() / ".audition" / "rules"
    return legacy if not primary.exists() and legacy.exists() else primary


GUIDE = _ZH_LOC["guide"].format(keep_mark=KEEP_MARK)


# ---------- 词表 ----------

def load_rules(rules_dir=RULES_DIR):
    rules = []
    rules_dir = Path(rules_dir)
    if not rules_dir.is_dir():
        return rules
    for path in sorted(rules_dir.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        groups = data.get("rules") or {}
        if isinstance(groups, list):          # 旧格式：列表，每条自带 level
            pairs = [(LEGACY_LEVELS.get(r.pop("level", None), 3), r) for r in groups]
        else:                                 # 新格式：按级别分组 {1: [...], 2: [...]}
            pairs = [(int(lv), r) for lv, rs in groups.items() for r in rs or []]
        for lv, r in pairs:
            r["lang"] = data.get("lang", path.stem)
            r["level"] = lv if lv in LEVELS else 3
            rules.append(r)
    return rules


def merge_rules(base, overlay):
    """同名 term：overlay 整条覆盖 base（级别、why、suggest 等一并替换）。"""
    by_term = {}
    order = []
    for r in list(base) + list(overlay):
        term = (r.get("term") or "").strip()
        if not term:
            continue
        if term not in by_term:
            order.append(term)
        by_term[term] = r
    return [by_term[t] for t in order]


def load_merged_rules(rules_dir=RULES_DIR, user_dir=None):
    """内置词表 + 用户覆盖；user_dir 默认 user_rules_dir()，目录不存在则只用内置。"""
    if user_dir is None:
        user_dir = user_rules_dir()
    return merge_rules(load_rules(rules_dir), load_rules(user_dir))


def build_patterns(rules):
    """每个词（含别名）一个模式；长词在前，避免长词被短词先吃掉。"""
    items = []
    for r in rules:
        for word in [r["term"], *r.get("aliases", [])]:
            pat = re.escape(word) if CJK.search(word) else r"(?i)\b" + re.escape(word) + r"\b"
            items.append((len(word), re.compile(pat), word, r))
    items.sort(key=lambda x: -x[0])
    return items


def load_glossary(cwd):
    """项目术语表：<项目>/.sic-dict.yaml（兼容旧 .audition.yaml）里的 allow 列表，列出的词直接放行。"""
    if not cwd:
        return set()
    allow = set()
    for name in (".sic-dict.yaml", ".audition.yaml"):
        path = Path(cwd) / name
        if path.exists():
            allow.update((yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("allow", []))
    return allow


def understood_path(data_dir=None):
    return Path(data_dir or DATA_DIR) / "understood.yaml"


def load_understood_entries(path=None):
    p = Path(path or understood_path())
    if not p.exists():
        return []
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    return [e for e in (data.get("terms") or []) if isinstance(e, dict) and e.get("term")]


def load_understood(path=None):
    return {e["term"] for e in load_understood_entries(path) if e.get("status", "understood") == "understood"}


def _window_cutoff(day=None, window_days=UNDERSTOOD_WINDOW_DAYS):
    end = date.fromisoformat(day or time.strftime("%Y-%m-%d"))
    start = end - timedelta(days=max(1, int(window_days)) - 1)
    return start.isoformat(), end.isoformat()


def today_term_reply_counts(day=None, log_path=None, window_days=UNDERSTOOD_WINDOW_DAYS):
    start_day, end_day = _window_cutoff(day, window_days)
    counts = Counter()
    for r in read_log(log_path, include_archived=True):
        rec_day = (r.get("ts") or "")[:10]
        if r.get("round") != 0 or not (start_day <= rec_day <= end_day):
            continue
        for t in {h["term"] for h in r.get("hits", []) if h.get("state") == "Review"}:
            counts[t] += 1
    return counts


def _write_understood_entries(entries, path=None):
    p = Path(path or understood_path())
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(UNDERSTOOD_HEADER + yaml.safe_dump({"terms": entries}, allow_unicode=True,
                                                    sort_keys=False, width=200), encoding="utf-8")


def _effective_today_hits(raw_count, entry, day, window_days=UNDERSTOOD_WINDOW_DAYS):
    if entry and entry.get("reset_day"):
        start_day, end_day = _window_cutoff(day, window_days)
        if start_day <= entry["reset_day"] <= end_day:
            return max(0, raw_count - int(entry.get("reset_base_hits", 0)))
    return raw_count


def record_frequent_terms(hits, *, day=None, log_path=None, out_path=None, threshold=UNDERSTOOD_RECORD_THRESHOLD):
    candidates = {}
    for h in hits:
        if h.get("state") == "Review" and h.get("level") in UNDERSTOOD_LEVELS:
            candidates.setdefault(h["term"], h["rule"])
    if not candidates:
        return []

    day = day or time.strftime("%Y-%m-%d")
    counts = today_term_reply_counts(day=day, log_path=log_path)
    p = Path(out_path or understood_path())
    entries = load_understood_entries(p)
    by_term = {e["term"]: e for e in entries}
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    recorded = []
    changed = False

    for term, rule in candidates.items():
        existing = by_term.get(term)
        if existing and existing.get("status", "understood") not in ("pending", "reset"):
            continue
        effective = _effective_today_hits(counts[term], existing, day)
        if effective < threshold:
            continue
        if existing:
            existing["status"] = "pending"
            existing["confirmed"] = False
            existing["today_hits"] = effective
            existing["last_hit_at"] = stamp
            recorded.append(existing)
            changed = True
        else:
            entry = {
                "term": term,
                "status": "pending",
                "confirmed": False,
                "level": rule.get("level", 3),
                "recorded_at": stamp,
                "last_hit_at": stamp,
                "today_hits": effective,
                "why": rule.get("why", ""),
                "explanation": rule.get("suggest", ""),
            }
            if rule.get("aliases"):
                entry["aliases"] = list(rule["aliases"])
            entries.append(entry)
            by_term[term] = entry
            recorded.append(entry)
            changed = True

    if changed:
        _write_understood_entries(entries, p)
    return recorded


def understood_candidates(hits, *, day=None, log_path=None, out_path=None, threshold=UNDERSTOOD_THRESHOLD):
    candidates = {}
    for h in hits:
        if h.get("state") == "Review" and h.get("level") in UNDERSTOOD_LEVELS:
            candidates.setdefault(h["term"], h["rule"])
    if not candidates:
        return []

    day = day or time.strftime("%Y-%m-%d")
    counts = today_term_reply_counts(day=day, log_path=log_path)
    existing = {e["term"]: e for e in load_understood_entries(out_path)}
    out = []
    for term, rule in candidates.items():
        entry = existing.get(term)
        if entry and entry.get("status", "understood") not in ("pending", "reset"):
            continue
        effective = _effective_today_hits(counts[term], entry, day)
        if effective < threshold:
            continue
        out.append((term, effective, rule))
    return out


def decline_understood(terms, rules=None, *, day=None, log_path=None, out_path=None):
    day = day or time.strftime("%Y-%m-%d")
    rules_by_term = {r["term"]: r for r in (rules if rules is not None else load_merged_rules())}
    counts = today_term_reply_counts(day=day, log_path=log_path)
    p = Path(out_path or understood_path())
    entries = load_understood_entries(p)
    by_term = {e["term"]: e for e in entries}
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    saved = []

    for term in terms:
        term = (term or "").strip()
        if not term:
            continue
        rule = rules_by_term.get(term, {})
        prev = by_term.get(term) or {}
        entry = {
            "term": term,
            "status": "reset",
            "confirmed": False,
            "level": rule.get("level", prev.get("level", 3)),
            "declined_at": stamp,
            "reset_day": day,
            "reset_base_hits": counts.get(term, 0),
            "today_hits": 0,
            "why": rule.get("why", prev.get("why", "")),
            "explanation": rule.get("suggest", "") or prev.get("explanation", ""),
        }
        aliases = rule.get("aliases") or prev.get("aliases")
        if aliases:
            entry["aliases"] = list(aliases)
        if term in by_term:
            by_term[term].update(entry)
            saved.append(by_term[term])
        else:
            entries.append(entry)
            by_term[term] = entry
            saved.append(entry)

    if saved:
        _write_understood_entries(entries, p)
    return saved


def confirm_understood(terms, rules=None, *, note=None, day=None, log_path=None, out_path=None):
    rules_by_term = {r["term"]: r for r in (rules if rules is not None else load_merged_rules())}
    counts = today_term_reply_counts(day=day, log_path=log_path)
    p = Path(out_path or understood_path())
    entries = load_understood_entries(p)
    by_term = {e["term"]: e for e in entries}
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    saved = []

    for term in terms:
        term = (term or "").strip()
        if not term:
            continue
        rule = rules_by_term.get(term, {})
        explanation = (note or "").strip() or rule.get("suggest", "") or (by_term.get(term) or {}).get("explanation", "")
        entry = {
            "term": term,
            "status": "understood",
            "confirmed": True,
            "level": rule.get("level", (by_term.get(term) or {}).get("level", 3)),
            "marked_at": stamp,
            "today_hits": counts.get(term, (by_term.get(term) or {}).get("today_hits", 0)),
            "why": rule.get("why", (by_term.get(term) or {}).get("why", "")),
            "explanation": explanation,
        }
        aliases = rule.get("aliases") or (by_term.get(term) or {}).get("aliases")
        if aliases:
            entry["aliases"] = list(aliases)
        if term in by_term:
            by_term[term].update(entry)
            by_term[term].pop("reset_day", None)
            by_term[term].pop("reset_base_hits", None)
        else:
            entries.append(entry)
            by_term[term] = entry
        saved.append(entry)

    if saved:
        _write_understood_entries(entries, p)
    return saved


# ---------- 检测（只做字面匹配） ----------

def _blank(m):
    """把匹配到的片段换成等长空白（保留换行），命中位置和行号不变。"""
    return re.sub(r"[^\n]", " ", m.group(0))


def strip_code(text):
    """代码块、行内代码、链接不是自然语言，替换成等长空白，保持位置不变。"""
    text = re.sub(r"```.*?```|~~~.*?~~~", _blank, text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", _blank, text)
    return re.sub(r"https?://\S+", _blank, text)


def strip_quotes(text):
    """成对引号内是引用/讨论用词本身，不送审；替换成等长空白，保持位置。

    覆盖中文直角引号、弯引号，以及同行的英文直引号。未闭合的引号不处理。
    """
    text = re.sub(r"「[^」]*」", _blank, text)
    text = re.sub(r"『[^』]*』", _blank, text)
    text = re.sub(r"«[^»]*»", _blank, text)
    text = re.sub(r"“[^”]*”", _blank, text)
    text = re.sub(r"‘[^’]*’", _blank, text)
    text = re.sub(r'"[^"\n]*"', _blank, text)
    return text


SENT_END = re.compile(r"[。！？；!?;\n]|\.(?=\s)")
SENT_PAD = 40   # 片段在命中前后各保留多少字

def sentence_at(text, s, e):
    """命中所在句子的 (起点, 终点)；没有标点时退化为整行，再没有换行就是整段。"""
    a = max((m.end() for m in SENT_END.finditer(text, 0, s)), default=0)
    m = SENT_END.search(text, e)
    b = m.end() if m else len(text)
    while a < b and text[a].isspace():
        a += 1
    while b > a and text[b - 1].isspace():
        b -= 1
    return a, b

def hit_snippets(text, hits):
    """同一句里的命中合成一条；句子太长时按距离分组，每组只截命中附近，原文不重复出现。"""
    out = []
    for h in sorted(hits, key=lambda h: h["start"]):
        a, b = sentence_at(text, h["start"], h["end"])
        lo, hi = max(a, h["start"] - SENT_PAD), min(b, h["end"] + SENT_PAD)
        g = out[-1] if out else None
        if g and g["sent"] == (a, b) and lo <= g["hi"]:
            g["hi"] = max(g["hi"], hi)
            g["words"].setdefault(h["word"])
        else:
            out.append({"sent": (a, b), "lo": lo, "hi": hi, "line": h["line"], "words": {h["word"]: None}})
    for g in out:
        a, b = g["sent"]
        g["text"] = ("…" if g["lo"] > a else "") + text[g["lo"]:g["hi"]].replace("\n", " ") + ("…" if g["hi"] < b else "")
    return out

def judge(text, patterns, glossary=frozenset(), understood=frozenset()):
    """命中列表；每条带 _text（原文引用，不写日志），供 format_rules 截片段。"""
    clean = strip_quotes(strip_code(text))
    taken = [False] * len(clean)
    lines = text.splitlines() or [""]
    hits = []
    for _, pat, word, rule in patterns:
        for m in pat.finditer(clean):
            s, e = m.span()
            if any(taken[s:e]):
                continue
            taken[s:e] = [True] * (e - s)
            line_no = clean.count("\n", 0, s) + 1
            level = rule["level"]
            if level == 0:
                state, reason = "Ignored", "level_ok"
            elif {word, rule["term"]} & glossary:
                state, reason = "Ignored", "glossary"
            elif {word, rule["term"]} & understood:
                state, reason = "Ignored", "understood"
            else:
                state, reason = "Review", f"level_{level}"
            hits.append({
                "word": word, "term": rule["term"], "lang": rule["lang"], "level": level, "rule": rule,
                "state": state, "reason": reason, "start": s, "line": line_no,
                "context": lines[min(line_no, len(lines)) - 1].strip()[:120],
                "end": e,
                "before": snippet(text[max(0, s - SNIP):s]), "after": snippet(text[e:e + SNIP]),
            })
    hits.sort(key=lambda h: h["start"])
    for h in hits:
        h["_text"] = text
    return hits


def decide_reply(hits, round_no):
    if round_no > 0:
        return "Confirmed"
    return "Review" if any(h["state"] == "Review" for h in hits) else "Pass"


# ---------- 输出 ----------

LEVEL_LABEL = _ZH_LOC["level_labels"]
LEVEL_ACTION = _ZH_LOC["level_actions"]


def pick_lang(hits, lang=None, states=("Review",)):
    """优先用显式指定的 lang；否则按命中词条最多的语种选择输出模板。"""
    if lang:
        return lang
    langs = [h["lang"] for h in hits if h.get("state") in states and h.get("lang")]
    if not langs:
        langs = [h["lang"] for h in hits if h.get("lang")]
    return Counter(langs).most_common(1)[0][0] if langs else "zh"


def format_rules(hits, states=("Review",), lang=None):
    """先按句子列出命中（同一句只出现一次），再按词条给出解释，最后列出用到的级别处理方式。"""
    loc = get_locale(pick_lang(hits, lang=lang, states=states))
    q_open, q_close, sep = loc["term_open"], loc["term_close"], loc["term_sep"]
    fields, labels, actions = loc["fields"], loc["level_labels"], loc["level_actions"]
    quote = lambda w: f"{q_open}{w}{q_close}"
    groups = {}
    for h in hits:
        if h["state"] in states:
            groups.setdefault(h["term"], []).append(h)
    review = [h for hs in groups.values() for h in hs]
    if all("_text" in h and "end" in h for h in review):
        snips = hit_snippets(review[0]["_text"], review) if review else []
    else:  # 旧数据没有原文：退回按行合并
        snips = {}
        for h in sorted(review, key=lambda h: h["line"]):
            snips.setdefault(h["line"], {"line": h["line"], "text": h["context"], "words": {}})["words"].setdefault(h["word"])
        snips = list(snips.values())
    out = [loc["lines_heading"] + "\n" + "\n".join(
        loc["line_item"].format(line=g["line"], context=g["text"], words=sep.join(map(quote, g["words"])))
        for g in snips)]
    used = []
    for hs in groups.values():
        r = hs[0]["rule"]
        if r["level"] not in used:
            used.append(r["level"])
        words = sep.join(quote(w) for w in dict.fromkeys(h["word"] for h in hs))
        s = loc["term_heading"].format(words=words, level_label=labels[r["level"]]) + "\n"
        s += fields["why"].format(value=r.get("why", ""))
        for k in ("ok_when", "bad_when", "suggest"):
            if r.get(k):
                s += "\n" + fields[k].format(value=r[k])
        out.append(s)
    out.append(loc["actions_heading"] + "\n" + "\n".join(
        loc["action_item"].format(level_label=labels[lv], value=actions[lv]) for lv in sorted(used)))
    return "\n\n".join(out)

def format_confirm_prompt(confirm_terms, data_dir=None, lang=None):
    if not confirm_terms:
        return ""
    loc = get_locale(lang or "zh")
    cfg = loc["confirm"]
    lines = [cfg["heading"]]
    script_cmd = f"{sys.executable} {Path(__file__).resolve()}"
    for term, cnt, rule in confirm_terms:
        lines.append(cfg["item"].format(term=term, count=cnt))
        if rule.get("suggest"):
            lines.append(cfg["suggest"].format(value=rule["suggest"]))
    terms_arg = " ".join(f'"{t}"' for t, _, _ in confirm_terms)
    lines.append(cfg["command"].format(cmd=f"{script_cmd} --confirm-understood {terms_arg}"))
    if cfg.get("decline_command"):
        lines.append(cfg["decline_command"].format(cmd=f"{script_cmd} --decline-understood {terms_arg}"))
    return "\n".join(lines)


def block_reason(hits, confirm_terms=(), lang=None):
    target_lang = pick_lang(hits, lang=lang)
    loc = get_locale(target_lang)
    parts = [
        loc["header"],
        format_rules(hits, lang=target_lang),
        loc["guide"].format(keep_mark=loc["keep_mark"]),
    ]
    extra = format_confirm_prompt(confirm_terms, lang=target_lang)
    if extra:
        parts.append(extra)
    return "\n\n".join(parts)


def is_hook_feedback(text):
    """识别任意语言模板喂回的审查提示，避免把提示本身再送审。"""
    stripped = (text or "").lstrip()
    return any(stripped.startswith(loc["feedback_prefix"]) for loc in LOCALES.values() if loc.get("feedback_prefix"))



def snippet(s):
    return re.sub(r"\s*\n\s*", " ⏎ ", s)


def public(h):
    return {k: h[k] for k in ("word", "term", "lang", "level", "state", "reason", "line", "context", "before", "after")}


# ---------- Hook 核心（各 adapter 共用） ----------

def _claude_assistant_text(entry):
    msg = entry.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None
    if entry.get("type") != "assistant" or not isinstance(content, list):
        return ""
    return "\n".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")


def last_assistant_text(path):
    """宿主没直接给回复正文时，从 Claude 格式的 transcript JSONL 取最后一条助手文本。"""
    return last_jsonl_text(path, _claude_assistant_text)


def state_file(session_id, data_dir=None, agent=None):
    sid = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "unknown")
    prefix = f"{re.sub(r'[^A-Za-z0-9_-]', '_', agent)}_" if agent else ""
    return Path(data_dir or DATA_DIR) / "state" / f"{prefix}{sid}.json"


def append_log(record, log_path=None):
    p = Path(log_path or (DATA_DIR / "log.jsonl"))
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def outcomes(reviewed_terms, text, hits):
    """AI 处理完之后，被审查的词是改掉了（fixed）还是保留了（kept）。纯字面对比。"""
    if any(loc["keep_mark"] in text for loc in LOCALES.values() if loc.get("keep_mark")):
        return {t: "kept" for t in reviewed_terms}
    present = {h["term"] for h in hits}
    return {t: ("kept" if t in present else "fixed") for t in reviewed_terms}


def process_stop(req, patterns, data_dir=None, lang=None):
    """统一 Stop 处理：判定、记日志、维护续跑状态。返回 HookResult。"""
    base_dir = Path(data_dir or DATA_DIR)
    log_file = base_dir / "log.jsonl"
    u_path = understood_path(base_dir)
    text = req.text or ""
    sid = req.session_id or ""
    sf = state_file(sid, base_dir, agent=req.agent)
    round_no = req.round_no or 0

    # host 误把本工具的提示当 assistant 正文再扫 → 放行且保留送审状态，等真正的改写稿
    if is_hook_feedback(text):
        append_log({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "agent": req.agent, "session": sid,
            "project": Path(req.cwd or "").name,
            "round": round_no, "decision": "Pass", "chars": len(text),
            "hits": [], "resolved": {}, "text": text[:TEXT_CAP],
        }, log_path=log_file)
        return HookResult(decision="Pass", reason="", hits=[], resolved={})

    # Codex 等有时续跑不带 stop_hook_active；本会话已有送审状态则视为第二轮
    if round_no == 0 and sf.exists():
        round_no = 1

    hits = judge(text, patterns, load_glossary(req.cwd), load_understood(u_path))
    decision = decide_reply(hits, round_no)

    resolved = {}
    if round_no > 0:
        try:
            reviewed = json.loads(sf.read_text()).get("reviewed_terms", [])
        except (OSError, json.JSONDecodeError):
            reviewed = []
        resolved = outcomes(reviewed, text, hits)

    append_log({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "agent": req.agent, "session": sid,
        "project": Path(req.cwd or "").name,
        "round": round_no, "decision": decision, "chars": len(text),
        "hits": [public(h) for h in hits], "resolved": resolved, "text": text[:TEXT_CAP],
    }, log_path=log_file)

    confirm_terms = []
    if round_no == 0 and decision == "Review":
        record_frequent_terms(hits, log_path=log_file, out_path=u_path)
        confirm_terms = understood_candidates(hits, log_path=log_file, out_path=u_path)

    reason = ""
    if decision == "Review":
        sf.parent.mkdir(parents=True, exist_ok=True)
        sf.write_text(json.dumps(
            {"reviewed_terms": sorted({h["term"] for h in hits if h["state"] == "Review"})},
            ensure_ascii=False))
        reason = block_reason(hits, confirm_terms=confirm_terms, lang=lang)
    else:
        sf.unlink(missing_ok=True)
    return HookResult(decision=decision, reason=reason, hits=hits, resolved=resolved)


def run_hook(name, patterns, lang=None):
    """按 adapter 名分发；失败放行并记日志。"""
    try:
        factory = get_adapter(name)
        stop_fn = (lambda req, pats, _lang=lang: process_stop(req, pats, lang=_lang)) if lang else process_stop
        runner = factory(stop_fn, last_assistant_text=last_assistant_text, data_dir=DATA_DIR)
        return runner(patterns)
    except Exception as e:
        append_log({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "agent": name,
                    "error": repr(e), "round": 0, "decision": "Error", "hits": []})
        return 0


# ---------- 测试 & 统计 ----------

def run_tests(patterns, lang=None):
    """词表自检（必需字段、重复词）+ tests/cases.yaml 用例。函数级单测在 tests/ 下用 unittest 跑。"""
    cases = yaml.safe_load((ROOT / "tests" / "cases.yaml").read_text(encoding="utf-8")) or []
    if lang:
        patterns = [p for p in patterns if p[3]["lang"] == lang]
        cases = [c for c in cases if c.get("lang", "zh") == lang]
    failed = 0

    for _, _, word, rule in patterns:
        if word != rule["term"]:
            continue
        need = {1: ("suggest",), 2: ("ok_when",), 3: ("suggest",)}.get(rule["level"], ())
        miss = [f for f in need if not rule.get(f)]
        if miss:
            failed += 1
            print(f"✗ 「{rule['term']}」是 {rule['level']} 级（{LEVEL_LABEL[rule['level']]}），缺少字段 {miss}")
    owners = defaultdict(set)
    for _, _, word, rule in patterns:
        owners[(rule["lang"], word)].add(rule["term"])
    dups = {w: sorted(t) for (_, w), t in owners.items() if len(t) > 1}
    if dups:
        failed += 1
        print(f"✗ 词表里同一个词出现在多个词条，后者永远不会生效：{dups}")
    for i, c in enumerate(cases, 1):
        errs = []
        if c.get("process_stop"):
            result = process_stop(HookRequest(
                agent="test", session_id=f"test-{i}", cwd=str(ROOT),
                text=c["text"], round_no=c.get("round", 0),
            ), patterns)
            got = {h["term"]: h["state"] for h in result.hits}
            if c.get("expect") == {} and got:
                errs.append(f"期望没有命中，实际命中 {list(got)}")
            for t, s in (c.get("expect") or {}).items():
                if got.get(t) != s:
                    errs.append(f"{t}: 期望 {s}，实际 {got.get(t, '未命中')}")
            if "decision" in c and result.decision != c["decision"]:
                errs.append(f"回复判定: 期望 {c['decision']}，实际 {result.decision}")
        else:
            hits = judge(c["text"], patterns, set(c.get("glossary", [])))
            got = {h["term"]: h["state"] for h in hits}
            errs = [f"{t}: 期望 {s}，实际 {got.get(t, '未命中')}" for t, s in (c.get("expect") or {}).items()
                    if got.get(t) != s]
            if c.get("expect") == {} and got:
                errs.append(f"期望没有命中，实际命中 {list(got)}")
            if "decision" in c and decide_reply(hits, c.get("round", 0)) != c["decision"]:
                errs.append(f"回复判定: 期望 {c['decision']}，实际 {decide_reply(hits, c.get('round', 0))}")
            if "resolved" in c:
                got_r = outcomes(c["reviewed"], c["text"], hits)
                if got_r != c["resolved"]:
                    errs.append(f"处理结果: 期望 {c['resolved']}，实际 {got_r}")
        print(f"{'✗' if errs else '✓'} {i:>2}. {c.get('name', c['text'][:30])}")
        for e in errs:
            print(f"      {e}")
        failed += bool(errs)
    print(f"\n{len(cases) - failed}/{len(cases)} 通过")
    return 1 if failed else 0


def read_log(log_path=None, include_archived=False):
    log_path = Path(log_path or DATA_DIR / "log.jsonl")
    out = []
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
                if include_archived or not rec.get("archived"):
                    out.append(rec)
            except json.JSONDecodeError:
                pass
    return out


def archive_log(before_ts=None, log_path=None):
    """给已处理过的日志打上 archived 标记（默认归档当前全部未归档记录，或指定时间点之前的记录）。"""
    log_path = Path(log_path or DATA_DIR / "log.jsonl")
    if not log_path.exists():
        return 0
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    cutoff = before_ts or stamp
    lines = []
    marked = 0
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            lines.append(line)
            continue
        if not rec.get("archived") and rec.get("ts", "") <= cutoff:
            rec["archived"] = cutoff
            marked += 1
        lines.append(json.dumps(rec, ensure_ascii=False))
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return marked


def occurrences(term=None, limit=50, include_archived=False):
    """逐条列出命中：时间、项目、前后文、AI 处理结果，以及原回复和改写后的回复。新的在前。"""
    records = [r for r in read_log(include_archived=include_archived)
               if r.get("decision") in ("Pass", "Review", "Confirmed")]
    out = []
    for i, r in enumerate(records):
        if r["round"] != 0:
            continue
        rev_text = ""
        resolved = {}
        if r["decision"] == "Review":  # 同一会话里紧跟着的下一轮（兼容多 hook 双记）就是 AI 处理后的结果
            for x in records[i + 1:]:
                if x.get("session") != r.get("session"):
                    continue
                if x["round"] != 1:
                    break
                if x.get("text") and not rev_text:
                    rev_text = x["text"]
                if x.get("resolved"):
                    resolved.update(x["resolved"])
        for h in r["hits"]:
            if term and h["term"] != term:
                continue
            out.append({
                "ts": r["ts"], "project": r.get("project", ""), "session": r.get("session", ""),
                "term": h["term"], "word": h["word"], "level": h["level"], "state": h["state"],
                "before": h.get("before", ""), "after": h.get("after", ""), "context": h.get("context", ""),
                "outcome": resolved.get(h["term"], "pending" if h["state"] == "Review" else ""),
                "text": r.get("text", ""), "revised": rev_text,
            })
    return out[::-1][:limit]


def print_occurrences(items):
    label = {"fixed": "改掉", "kept": "保留", "pending": "未处理", "": ""}
    for o in items:
        tag = o["state"] + (f" → {label.get(o['outcome'], o['outcome'])}" if o["outcome"] else "")
        print(f"{o['ts']}  {o['project'] or '-'}  [{tag}]")
        if o["before"] or o["after"]:
            print(f"  …{o['before']}【{o['word']}】{o['after']}…")
        else:  # 旧日志没有前后文
            print(f"  {o['context']}")
    print(f"\n共 {len(items)} 条（新的在前）")


def compute_stats(log_path=None, include_archived=False):
    records = [r for r in read_log(log_path, include_archived=include_archived)
               if r.get("decision") in ("Pass", "Review", "Confirmed", "Error")]  # 只认当前版本的记录
    first = [r for r in records if r["round"] == 0 and r["decision"] != "Error"]
    terms = defaultdict(Counter)
    for r in records:
        for h in r["hits"]:
            if r["round"] == 0:
                terms[h["term"]][h["state"]] += 1
        for term, outcome in r.get("resolved", {}).items():
            terms[term][outcome] += 1
    return {
        "replies": len(first), "checks": len(records),
        "decisions": dict(Counter(r["decision"] for r in records)),
        "review_rate": round(sum(r["decision"] == "Review" for r in first) / len(first), 3) if first else 0,
        "terms": {t: dict(c) for t, c in sorted(terms.items(), key=lambda kv: -sum(kv[1].values()))},
    }


def print_stats(stats):
    print(f"回复数 {stats['replies']} · 检查次数 {stats['checks']} · 送审率 {stats['review_rate']:.0%}")
    print("回复判定：" + "  ".join(f"{k} {v}" for k, v in stats["decisions"].items()))
    if not stats["terms"]:
        return
    cols = [("Review", "送审"), ("fixed", "改掉"), ("kept", "保留"), ("Noted", "提醒"), ("Ignored", "放行")]
    print("\n" + "词".ljust(12) + "".join(n.rjust(6) for _, n in cols))
    for t, c in stats["terms"].items():
        print(t.ljust(12 - sum(1 for ch in t if CJK.match(ch))) + "".join(str(c.get(k, "")).rjust(8) for k, _ in cols))
    print("\n读法：保留多 → AI 常认为正当，考虑调到 2（看语境）或从词表删掉；改掉多 → 规则有效。")


def main():
    hook_choices = load_all()

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?", default="-")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--hook", choices=hook_choices, help="作为 agent Stop hook 运行")
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--log", nargs="?", const="", metavar="TERM", help="逐条查看命中记录，可指定词条")
    ap.add_argument("--archive", nargs="?", const="", metavar="BEFORE_TS",
                    help="把已处理的日志标记为 archived（可指定截止时间，默认当前时间）")
    ap.add_argument("--understood", action="store_true", help="查看本地已理解术语记录区")
    ap.add_argument("--confirm-understood", nargs="*", metavar="TERM",
                    help="Confirm understood terms and save them to the local KB")
    ap.add_argument("--decline-understood", nargs="+", metavar="TERM",
                    help="Decline adding terms and reset their daily prompt counter without affecting stats")
    ap.add_argument("--note", default="", help="配合 --confirm-understood 附带自定义解释")
    ap.add_argument("--all", action="store_true", help="配合 --stats / --log 查看含已归档的全部记录")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--rules", type=Path, default=RULES_DIR, help="内置词表目录")
    ap.add_argument("--user-rules", type=Path, default=None,
                    help="用户覆盖词表目录（默认 ~/.sic-dict/rules 或 $SIC_DICT_HOME/rules）")
    ap.add_argument("--no-user-rules", action="store_true", help="不合并用户覆盖，只用 --rules")
    ap.add_argument("--lang", default=None, help="指定提示词与输出语言（默认按命中词条自动选择，如 zh / en）")
    args = ap.parse_args()

    if args.archive is not None:
        n = archive_log(args.archive or None)
        print(f"已标记归档 {n} 条日志记录")
        return 0
    if args.understood:
        entries = load_understood_entries()
        if args.json:
            print(json.dumps(entries, ensure_ascii=False, indent=2))
        elif not entries:
            print(f"本地已理解记录区暂无词条（{understood_path()}）")
        else:
            print(f"本地已理解记录区（{understood_path()}，共 {len(entries)} 条）：\n")
            for e in entries:
                print(f"■ {e['term']}  [{e.get('status', 'understood')}]  {e.get('marked_at', '')}  今日命中 {e.get('today_hits', '-')} 次")
                if e.get("why"):
                    print(f"  来源：{e['why']}")
                if e.get("explanation"):
                    print(f"  解释：{e['explanation']}")
        return 0
    if args.decline_understood:
        merged_rules = load_rules(args.rules) if args.no_user_rules else load_merged_rules(args.rules, args.user_rules)
        saved = decline_understood(args.decline_understood, rules=merged_rules)
        for e in saved:
            print(f"✓ Reset prompt counter in {understood_path()}: {e['term']}")
        return 0
    if args.confirm_understood is not None:
        merged_rules = load_rules(args.rules) if args.no_user_rules else load_merged_rules(args.rules, args.user_rules)
        rules_by_term = {r["term"]: r for r in merged_rules}
        terms = list(args.confirm_understood)
        if not terms:
            day = time.strftime("%Y-%m-%d")
            counts = today_term_reply_counts(day=day)
            by_term = {e["term"]: e for e in load_understood_entries()}
            cands = []
            for t, cnt in counts.items():
                entry = by_term.get(t)
                if entry and entry.get("status", "understood") not in ("pending", "reset"):
                    continue
                eff = _effective_today_hits(cnt, entry, day)
                if eff >= UNDERSTOOD_THRESHOLD and t in rules_by_term and rules_by_term[t].get("level") in UNDERSTOOD_LEVELS:
                    cands.append((t, eff, rules_by_term[t]))
            if not cands:
                print("今日暂无待确认理解的多次命中术语。")
                return 0
            for t, cnt, rule in cands:
                print(f"\n■ 「{t}」（今日命中 {cnt} 次）")
                if rule.get("suggest"):
                    print(f"  解释：{rule['suggest']}")
                ans = input(f"是否已理解「{t}」的含义，并记入本地不再命中？[y/N] ").strip().lower()
                if ans in ("y", "yes", "是", "确认"):
                    terms.append(t)
        if not terms:
            print("未确认任何词条。")
            return 0
        saved = confirm_understood(terms, rules=merged_rules, note=args.note or None)
        for e in saved:
            print(f"✓ 已标记理解并写入 {understood_path()}：「{e['term']}」— {e.get('explanation', '')}")
        return 0
    if args.log is not None:
        items = occurrences(args.log or None, args.limit, include_archived=args.all)
        print(json.dumps(items, ensure_ascii=False, indent=2)) if args.json else print_occurrences(items)
        return 0
    if args.stats:
        s = compute_stats(include_archived=args.all)
        print(json.dumps(s, ensure_ascii=False, indent=2)) if args.json else print_stats(s)
        return 0
    # --test 只用内置词表，避免本机用户覆盖干扰用例；覆盖逻辑在 run_tests 里单独测
    if args.test or args.no_user_rules:
        patterns = build_patterns(load_rules(args.rules))
    else:
        patterns = build_patterns(load_merged_rules(args.rules, args.user_rules))
    if args.hook:
        return run_hook(args.hook, patterns, lang=args.lang)
    if args.test:
        return run_tests(patterns, lang=args.lang)

    text = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8")
    understood = frozenset() if args.no_user_rules else load_understood()
    hits = judge(text, patterns, load_glossary(Path.cwd()), understood)
    if args.json:
        print(json.dumps([public(h) for h in hits], ensure_ascii=False, indent=2))
    elif any(h["state"] == "Review" for h in hits):
        print(format_rules(hits, lang=args.lang))
    return 1 if any(h["state"] == "Review" for h in hits) else 0


if __name__ == "__main__":
    sys.exit(main())

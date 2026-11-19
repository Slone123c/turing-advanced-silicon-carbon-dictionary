#!/usr/bin/env python3
"""把措辞检查可拔插地装到本机各 agent（幂等、合并、不覆盖他人 hook）。

参照各端官方文档的安装路径与契约，以及 goalkeeper 的 Stop 语义、agent-hooks-bridge 的多端适配。

  python3 install.py                      # 安装所有检测到的目标
  python3 install.py --target claude codex cursor
  python3 install.py --list               # 列出目标与状态
  python3 install.py --uninstall          # 从已装目标卸载
  python3 install.py --uninstall --target cursor

Grok 默认：若 Claude 已装 audition，则跳过原生 grok 文件（Grok 会读 Claude settings），
避免同一 Stop 跑两次。需要强制原生时加 --force-grok。

新增一个目标：写好 install / uninstall / installed 三个函数，再在文件末尾的 TARGETS 里加一行。
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml

ROOT = Path(__file__).resolve().parent
SCAN = ROOT / "scan.py"
TEMPLATES = ROOT / "templates"     # 安装时渲染后拷进各 agent 目录的脚本 / 插件
MARK = "turing-advanced-silicon-carbon-dictionary"  # 用于识别本工具写入的条目
LEGACY_MARK = "agent-language-audition"             # 改名前的旧标记，卸载 / 重装时一并清理
PY = sys.executable
HOME = Path.home()

STALE = "（旧路径已失效，请重装）"


# ---------- 路径（都在调用时读 HOME，便于测试替换） ----------

def _env_dir(name: str, default: Path) -> Path:
    val = os.environ.get(name, "").strip()
    return Path(val).expanduser() if val else default


def _claude_dir() -> Path:
    return _env_dir("CLAUDE_CONFIG_DIR", HOME / ".claude")


def _codex_dir() -> Path:
    return _env_dir("CODEX_HOME", HOME / ".codex")


def _grok_dir() -> Path:
    return _env_dir("GROK_HOME", HOME / ".grok")


def _copilot_dir() -> Path:
    return _env_dir("COPILOT_HOME", HOME / ".copilot")


def _pi_dir() -> Path:
    return _env_dir("PI_CODING_AGENT_DIR", HOME / ".pi" / "agent")


def _opencode_dir() -> Path:
    return _env_dir("XDG_CONFIG_HOME", HOME / ".config") / "opencode"


def _dsh_dir() -> Path:
    return _env_dir("DSH_HOME", HOME / ".dsh")


def _trae_candidates() -> list[Path]:
    return [HOME / ".trae", HOME / ".trae-cn"]


def _trae_dirs() -> list[Path]:
    """安装用：已存在的 Trae / Trae CN 目录；都没有时装到 ~/.trae。"""
    cands = _trae_candidates()
    return [d for d in cands if d.exists()] or cands[:1]


# ---------- 通用工具 ----------

def cmd_for(hook: str) -> str:
    """生成 hook 命令。

    Claude 习惯带引号的 argv 串；Codex 更常直接 exec 整串，多余引号会找不到二进制。
    所以只有路径含空格时才加引号。
    """
    if " " in str(PY) or " " in str(SCAN):
        return f'"{PY}" "{SCAN}" --hook {hook}'
    return f"{PY} {SCAN} --hook {hook}"


def backup(path: Path, suffix: str = ".bak-audition"):
    if path.exists():
        shutil.copy(path, path.with_name(path.name + suffix))


def is_ours_command(command: str) -> bool:
    return (
        MARK in command
        or LEGACY_MARK in command
        or (str(SCAN) in command and "--hook" in command)
    )


def _read_json(path: Path, default: dict | None = None) -> dict:
    text = path.read_text(encoding="utf-8").strip() if path.exists() else ""
    if text:
        return json.loads(text)
    return copy.deepcopy(default) if default is not None else {}


def _write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _file_has_ours(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    return MARK in text or LEGACY_MARK in text or str(SCAN) in text


def _points_to_legacy(path: Path) -> bool:
    """配置里还挂着改名前的旧仓库路径（且没有指向当前 scan.py 的新条目）。"""
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    return LEGACY_MARK in text and str(SCAN) not in text


def _render(template: str) -> str:
    """读 templates/ 下的模板，填入本机 Python 与仓库路径。"""
    return ((TEMPLATES / template).read_text(encoding="utf-8")
            .replace("__AUDITION_PYTHON__", str(PY))
            .replace("__AUDITION_ROOT__", str(ROOT)))


def _write_rendered(template: str, dest: Path, label: str) -> str:
    if not (TEMPLATES / template).exists():
        return f"{label}：缺少 templates/{template}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(_render(template), encoding="utf-8")
    return f"已安装 {label} → {dest}"


def _remove_files(label: str, *paths: Path) -> str:
    removed = []
    for p in paths:
        if p.exists():
            p.unlink()
            removed.append(str(p))
    return f"已卸载 {label} → 删除 {', '.join(removed)}" if removed else f"{label}：无本工具文件"


# ---------- 嵌套 hooks.<Event>[].hooks[]：Claude / Codex / Gemini / Qwen / CodeBuddy / Qoder ----------

def _group_is_ours(group: dict) -> bool:
    return any(is_ours_command(h.get("command", "")) for h in group.get("hooks", []))


def _nested_installed(path: Path, event: str) -> bool:
    if not path.exists():
        return False
    return any(_group_is_ours(g) for g in _read_json(path).get("hooks", {}).get(event, []))


def _install_nested_hook(path: Path, event: str, entry: dict, *, label: str, default: dict | None = None) -> str:
    backup(path)
    data = _read_json(path, default=default)
    groups = data.setdefault("hooks", {}).setdefault(event, [])
    groups[:] = [g for g in groups if not _group_is_ours(g)]
    groups.append({"hooks": [entry]})
    _write_json(path, data)
    return f"已安装 {label} {event} → {path}"


def _uninstall_nested_hook(path: Path, event: str, *, label: str, prune_empty_hooks: bool = True) -> str:
    if not path.exists():
        return f"{label}：未找到配置文件，跳过"
    backup(path)
    data = _read_json(path)
    groups = data.get("hooks", {}).get(event, [])
    before = len(groups)
    groups[:] = [g for g in groups if not _group_is_ours(g)]
    if not groups and "hooks" in data:
        data["hooks"].pop(event, None)
        if prune_empty_hooks and not data["hooks"]:
            data.pop("hooks")
    _write_json(path, data)
    removed = before - len(groups)
    return f"已卸载 {label}（移除 {removed} 组）" if removed else f"{label}：无本工具条目"


def _nested(label: str, config: Callable[[], Path], event: str, entry: Callable[[], dict], *,
            default: dict | None = None, prune_empty_hooks: bool = True) -> dict:
    """生成一组嵌套 hook 目标的 install / uninstall / installed。"""
    return {
        "install": lambda: _install_nested_hook(config(), event, entry(), label=label, default=default),
        "uninstall": lambda: _uninstall_nested_hook(config(), event, label=label,
                                                    prune_empty_hooks=prune_empty_hooks),
        "installed": lambda: _nested_installed(config(), event),
    }


def _command_entry(hook: str, *, timeout: int = 10, **extra) -> dict:
    return {"type": "command", "timeout": timeout, "command": cmd_for(hook), **extra}


def claude_installed() -> bool:
    return _nested_installed(_claude_dir() / "settings.json", "Stop")


# ---------- Cursor（create-hook 形态：~/.cursor/hooks/*.sh + hooks.json 里的相对路径） ----------

CURSOR_SCRIPT_REL = f"./hooks/{MARK}.sh"   # 相对 ~/.cursor/
CURSOR_EVENTS = ("afterAgentResponse", "stop")


def _cursor_dir() -> Path:
    return HOME / ".cursor"


def _cursor_scripts() -> tuple[Path, Path]:
    hooks = _cursor_dir() / "hooks"
    return hooks / f"{MARK}.sh", hooks / f"{LEGACY_MARK}.sh"


def install_cursor() -> str:
    script, legacy_script = _cursor_scripts()
    msg = _write_rendered("cursor-audition.sh", script, "Cursor")
    if not msg.startswith("已安装"):
        return msg
    script.chmod(0o755)
    legacy_script.unlink(missing_ok=True)

    hooks_json = _cursor_dir() / "hooks.json"
    backup(hooks_json)
    data = _read_json(hooks_json, default={"version": 1, "hooks": {}})
    data.setdefault("version", 1)
    hooks = data.setdefault("hooks", {})
    for event in CURSOR_EVENTS:
        entry = {"command": CURSOR_SCRIPT_REL, "timeout": 10}
        if event == "stop":
            entry["loop_limit"] = 2  # 首轮 Review + 一轮确认
        hooks[event] = [e for e in hooks.get(event, []) if not is_ours_command(e.get("command", ""))] + [entry]
    _write_json(hooks_json, data)
    return f"已安装 Cursor → {CURSOR_SCRIPT_REL} + {hooks_json}"


def uninstall_cursor() -> str:
    hooks_json = _cursor_dir() / "hooks.json"
    changed = False
    if hooks_json.exists():
        backup(hooks_json)
        data = _read_json(hooks_json)
        hooks = data.get("hooks", {})
        for event in CURSOR_EVENTS:
            before = hooks.get(event, [])
            after = [e for e in before if not is_ours_command(e.get("command", ""))]
            changed |= len(after) != len(before)
            if after:
                hooks[event] = after
            else:
                hooks.pop(event, None)
        _write_json(hooks_json, data)
    for p in _cursor_scripts():
        if p.exists():
            p.unlink()
            changed = True
    return "已卸载 Cursor" if changed else "Cursor：无本工具条目"


def _cursor_stale() -> str:
    legacy = _points_to_legacy(_cursor_dir() / "hooks.json") or _cursor_scripts()[1].exists()
    return STALE if legacy else ""


# ---------- Grok（~/.grok/hooks/<name>.json） ----------

def _grok_files() -> tuple[Path, Path]:
    hooks = _grok_dir() / "hooks"
    return hooks / f"{MARK}.json", hooks / f"{LEGACY_MARK}.json"


def install_grok(force: bool = False) -> str:
    if claude_installed() and not force:
        return ("Grok：已跳过原生安装（Claude settings 里的 audition 会被 Grok 兼容加载；"
                "若仍要原生文件，加 --force-grok）")
    path, legacy = _grok_files()
    legacy.unlink(missing_ok=True)
    _write_json(path, {"hooks": {"Stop": [{"hooks": [_command_entry("grok", statusMessage="措辞检查")]}]}})
    return f"已安装 Grok Stop → {path}"


def _grok_stale() -> str:
    path, legacy = _grok_files()
    return STALE if legacy.exists() and not path.exists() else ""


# ---------- Antigravity（~/.gemini/config/hooks.json，顶层按名字分组） ----------

def _antigravity_hooks_file() -> Path:
    return HOME / ".gemini" / "config" / "hooks.json"


def _antigravity_is_ours(key: str, val) -> bool:
    if key in (MARK, LEGACY_MARK):
        return True
    return isinstance(val, dict) and any(is_ours_command(h.get("command", "")) for h in val.get("Stop", []))


def _antigravity_installed() -> bool:
    path = _antigravity_hooks_file()
    return path.exists() and any(_antigravity_is_ours(k, v) for k, v in _read_json(path).items())


def install_antigravity() -> str:
    path = _antigravity_hooks_file()
    backup(path)
    data = {k: v for k, v in _read_json(path).items() if not _antigravity_is_ours(k, v)}
    data[MARK] = {"enabled": True, "Stop": [{"type": "command", "command": cmd_for("antigravity"), "timeout": 10}]}
    _write_json(path, data)
    return f"已安装 Antigravity Stop → {path}"


def uninstall_antigravity() -> str:
    path = _antigravity_hooks_file()
    if not path.exists():
        return "Antigravity：未找到 hooks.json，跳过"
    backup(path)
    data = _read_json(path)
    kept = {k: v for k, v in data.items() if not _antigravity_is_ours(k, v)}
    _write_json(path, kept)
    removed = len(data) - len(kept)
    return f"已卸载 Antigravity（移除 {removed} 项）" if removed else "Antigravity：无本工具条目"


# ---------- Trae / Trae CN（hooks.json 里扁平的 Stop 列表） ----------

def _trae_installed() -> bool:
    return any(_file_has_ours(d / "hooks.json") for d in _trae_candidates())


def install_trae() -> str:
    written = []
    for d in _trae_dirs():
        path = d / "hooks.json"
        backup(path)
        data = _read_json(path, default={"hooks": {}})
        stops = data.setdefault("hooks", {}).setdefault("Stop", [])
        stops[:] = [e for e in stops if not is_ours_command(e.get("command", ""))]
        stops.append({"type": "command", "command": cmd_for("trae"), "loop_limit": 2})
        _write_json(path, data)
        written.append(str(path))
    return "已安装 Trae Stop → " + ", ".join(written)


def uninstall_trae() -> str:
    changed = []
    for d in _trae_candidates():
        path = d / "hooks.json"
        if not path.exists():
            continue
        backup(path)
        data = _read_json(path)
        stops = data.get("hooks", {}).get("Stop", [])
        before = len(stops)
        stops[:] = [e for e in stops if not is_ours_command(e.get("command", ""))]
        if not stops and "hooks" in data:
            data["hooks"].pop("Stop", None)
        _write_json(path, data)
        if before != len(stops):
            changed.append(str(path))
    return ("已卸载 Trae → " + ", ".join(changed)) if changed else "Trae：无本工具条目"


# ---------- 独占一个配置文件的目标：Copilot / Kiro ----------

def _copilot_hooks_file() -> Path:
    return _copilot_dir() / "hooks" / f"{MARK}.json"


def install_copilot() -> str:
    path = _copilot_hooks_file()
    _write_json(path, {
        "version": 1,
        "hooks": {"agentStop": [{"type": "command", "command": cmd_for("copilot"), "timeoutSec": 10}]},
    })
    return f"已安装 Copilot agentStop → {path}"


def _kiro_hooks_file() -> Path:
    return HOME / ".kiro" / "hooks" / f"{MARK}.json"


def install_kiro() -> str:
    path = _kiro_hooks_file()
    _write_json(path, {
        "version": "v1",
        "hooks": [{
            "name": MARK,
            "description": "检查回复中的硅碳黑话与空话",
            "trigger": "Stop",
            "action": {"type": "command", "command": cmd_for("kiro")},
            "timeout": 10,
            "enabled": True,
        }],
    })
    return f"已安装 Kiro Stop → {path}"


# ---------- 扩展插件：OMP / Pi / OpenCode（渲染 templates/ 下的脚本） ----------

def _omp_exts() -> tuple[Path, Path]:
    ext_dir = HOME / ".omp" / "agent" / "extensions"
    return ext_dir / f"{MARK}.ts", ext_dir / f"{LEGACY_MARK}.ts"


def install_omp() -> str:
    path, legacy = _omp_exts()
    legacy.unlink(missing_ok=True)
    return _write_rendered("omp-audition.ts", path, "OMP extension")


def _omp_stale() -> str:
    path, legacy = _omp_exts()
    return "（旧扩展名残留，请重装）" if legacy.exists() and not path.exists() else ""


def _pi_ext() -> Path:
    return _pi_dir() / "extensions" / f"{MARK}.ts"


def _opencode_plugin() -> Path:
    return _opencode_dir() / "plugins" / f"{MARK}.js"


# ---------- DeepSeek Harness（每个 profile：Cordis 插件 + cordis.patch.yml） ----------

class _DshJsExpr(str):
    """保留 cordis.patch.yml 中的 !!js 标量标签。"""


class _DshYamlLoader(yaml.SafeLoader):
    pass


class _DshYamlDumper(yaml.SafeDumper):
    pass


_DshYamlLoader.add_constructor(
    "tag:yaml.org,2002:js",
    lambda loader, node: _DshJsExpr(loader.construct_scalar(node)),
)
_DshYamlDumper.add_representer(
    _DshJsExpr,
    lambda dumper, data: dumper.represent_scalar("tag:yaml.org,2002:js", str(data)),
)

DSH_PLUGIN_FILE = f"{MARK}.mjs"
DSH_PLUGIN_SPEC = f"./{DSH_PLUGIN_FILE}"
DSH_DEFAULT_PROFILES = ("web", "desktop", "headless", "acp")


def _dsh_profile_dirs(*, create_default: bool = False) -> list[Path]:
    """已有的 profile：先按 DSH_DEFAULT_PROFILES 顺序，再追加其它带 cordis 配置的目录。"""
    root = _dsh_dir() / "profiles"
    found = [root / name for name in DSH_DEFAULT_PROFILES if (root / name).exists()]
    if root.exists():
        found += [p for p in sorted(root.iterdir())
                  if p.is_dir() and p.name != "node_modules"
                  and ((p / "cordis.yml").exists() or (p / "cordis.patch.yml").exists())]
    out, seen = [], set()
    for p in found:
        if p.resolve() not in seen:
            seen.add(p.resolve())
            out.append(p)
    if not out and create_default:
        out.append(root / DSH_DEFAULT_PROFILES[0])
    return out


def _dsh_is_our_patch_entry(entry: object) -> bool:
    return isinstance(entry, dict) and (
        entry.get("id") in (MARK, LEGACY_MARK)
        or entry.get("name") in (DSH_PLUGIN_SPEC, f"./{LEGACY_MARK}.mjs")
    )


def _load_dsh_patches(path: Path) -> list:
    text = path.read_text(encoding="utf-8").strip() if path.exists() else ""
    data = yaml.load(text, Loader=_DshYamlLoader) if text else None
    return data if isinstance(data, list) else []


def _dump_dsh_patches(path: Path, patches: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(patches, Dumper=_DshYamlDumper, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")


def _strip_dsh_patches(patches: list) -> tuple[list, bool]:
    """去掉本工具的 insert 条目；返回 (剩余 patches, 是否有改动)。"""
    out = []
    changed = False
    for item in patches:
        if isinstance(item, dict) and isinstance(item.get("insert"), list):
            kept = [e for e in item["insert"] if not _dsh_is_our_patch_entry(e)]
            changed |= len(kept) != len(item["insert"])
            if kept:
                out.append({**item, "insert": kept})
            elif len(item) > 1:
                out.append({k: v for k, v in item.items() if k != "insert"})
        elif _dsh_is_our_patch_entry(item):
            changed = True
        else:
            out.append(item)
    return out, changed


def _dsh_installed() -> bool:
    pdirs = _dsh_profile_dirs()
    return bool(pdirs) and all(
        (pdir / DSH_PLUGIN_FILE).exists()
        and _strip_dsh_patches(_load_dsh_patches(pdir / "cordis.patch.yml"))[1]
        for pdir in pdirs
    )


def install_dsh() -> str:
    if not (TEMPLATES / "dsh-audition.mjs").exists():
        return "DSH：缺少 templates/dsh-audition.mjs"
    written = []
    for pdir in _dsh_profile_dirs(create_default=True):
        _write_rendered("dsh-audition.mjs", pdir / DSH_PLUGIN_FILE, "DSH")
        patch_path = pdir / "cordis.patch.yml"
        backup(patch_path)
        patches, _ = _strip_dsh_patches(_load_dsh_patches(patch_path))
        patches.append({"insert": [{"id": MARK, "name": DSH_PLUGIN_SPEC}]})
        _dump_dsh_patches(patch_path, patches)
        written.append(pdir.name)
    return "已安装 DeepSeek Harness Cordis 插件 → profiles/" + ", ".join(written)


def uninstall_dsh() -> str:
    changed_profiles = []
    for pdir in _dsh_profile_dirs():
        changed = False
        plugin_file = pdir / DSH_PLUGIN_FILE
        if plugin_file.exists():
            plugin_file.unlink()
            changed = True
        patch_path = pdir / "cordis.patch.yml"
        patches, stripped = _strip_dsh_patches(_load_dsh_patches(patch_path))
        if stripped:
            backup(patch_path)
            _dump_dsh_patches(patch_path, patches)
            changed = True
        if changed:
            changed_profiles.append(pdir.name)
    if not changed_profiles:
        return "DSH：无本工具条目"
    return "已卸载 DeepSeek Harness → profiles/" + ", ".join(changed_profiles)


# ---------- 目标表 ----------

@dataclass(frozen=True)
class Target:
    detect: Callable[[], bool]          # 本机是否装了这个 agent
    install: Callable[[], str]
    uninstall: Callable[[], str]
    installed: Callable[[], bool]       # 本工具的条目是否在位
    stale: Callable[[], str] = lambda: ""   # 已装但仍指向旧路径时的提示


TARGETS: dict[str, Target] = {
    "claude": Target(
        detect=lambda: _claude_dir().exists(),
        stale=lambda: STALE if _points_to_legacy(_claude_dir() / "settings.json") else "",
        **_nested("Claude Code", lambda: _claude_dir() / "settings.json", "Stop",
                  lambda: _command_entry("claude-code")),
    ),
    "codex": Target(
        detect=lambda: _codex_dir().exists(),
        stale=lambda: STALE if _points_to_legacy(_codex_dir() / "hooks.json") else "",
        **_nested("Codex", lambda: _codex_dir() / "hooks.json", "Stop",
                  lambda: _command_entry("codex", statusMessage="措辞检查"),
                  default={"hooks": {}}, prune_empty_hooks=False),
    ),
    "cursor": Target(
        detect=lambda: _cursor_dir().exists(),
        install=install_cursor,
        uninstall=uninstall_cursor,
        installed=lambda: _file_has_ours(_cursor_dir() / "hooks.json"),
        stale=_cursor_stale,
    ),
    "grok": Target(
        detect=lambda: _grok_dir().exists(),
        install=install_grok,
        uninstall=lambda: _remove_files("Grok", *_grok_files()),
        installed=lambda: any(p.exists() for p in _grok_files()),
        stale=_grok_stale,
    ),
    "omp": Target(
        detect=lambda: (HOME / ".omp").exists(),
        install=install_omp,
        uninstall=lambda: _remove_files("OMP", *_omp_exts()),
        installed=lambda: any(p.exists() for p in _omp_exts()),
        stale=_omp_stale,
    ),
    "gemini": Target(
        detect=lambda: (HOME / ".gemini" / "settings.json").exists() or shutil.which("gemini") is not None,
        # Gemini CLI：timeout 单位为毫秒（docs/hooks/reference.md）
        **_nested("Gemini CLI", lambda: HOME / ".gemini" / "settings.json", "AfterAgent",
                  lambda: {"name": MARK, **_command_entry("gemini-cli", timeout=10000)}),
    ),
    "antigravity": Target(
        detect=lambda: any((HOME / ".gemini" / sub).exists()
                           for sub in ("config", "antigravity", "antigravity-cli", "antigravity-ide")),
        install=install_antigravity,
        uninstall=uninstall_antigravity,
        installed=_antigravity_installed,
    ),
    "qwen": Target(
        detect=lambda: (HOME / ".qwen").exists(),
        **_nested("Qwen Code", lambda: HOME / ".qwen" / "settings.json", "Stop",
                  lambda: {"name": MARK, **_command_entry("qwen-code")}),
    ),
    "codebuddy": Target(
        detect=lambda: (HOME / ".codebuddy").exists(),
        **_nested("CodeBuddy", lambda: HOME / ".codebuddy" / "settings.json", "Stop",
                  lambda: _command_entry("codebuddy")),
    ),
    "qoder": Target(
        detect=lambda: (HOME / ".qoder").exists(),
        **_nested("Qoder", lambda: HOME / ".qoder" / "settings.json", "Stop",
                  lambda: _command_entry("qoder")),
    ),
    "trae": Target(
        detect=lambda: any(d.exists() for d in _trae_candidates()),
        install=install_trae,
        uninstall=uninstall_trae,
        installed=_trae_installed,
    ),
    "copilot": Target(
        detect=lambda: _copilot_dir().exists(),
        install=install_copilot,
        uninstall=lambda: _remove_files("Copilot", _copilot_hooks_file()),
        installed=lambda: _copilot_hooks_file().exists(),
    ),
    "kiro": Target(
        detect=lambda: (HOME / ".kiro").exists(),
        install=install_kiro,
        uninstall=lambda: _remove_files("Kiro", _kiro_hooks_file()),
        installed=lambda: _kiro_hooks_file().exists(),
    ),
    "pi": Target(
        detect=lambda: _pi_dir().exists() or _pi_dir().parent.exists(),
        install=lambda: _write_rendered("pi-audition.ts", _pi_ext(), "Pi extension"),
        uninstall=lambda: _remove_files("Pi", _pi_ext()),
        installed=lambda: _pi_ext().exists(),
    ),
    "opencode": Target(
        detect=lambda: _opencode_dir().exists(),
        install=lambda: _write_rendered("opencode-audition.js", _opencode_plugin(), "OpenCode plugin"),
        uninstall=lambda: _remove_files("OpenCode", _opencode_plugin()),
        installed=lambda: _opencode_plugin().exists(),
    ),
    "dsh": Target(
        detect=lambda: _dsh_dir().exists(),
        install=install_dsh,
        uninstall=uninstall_dsh,
        installed=_dsh_installed,
    ),
}


def detected() -> list[str]:
    return [name for name, t in TARGETS.items() if t.detect()]


def status_line(name: str) -> str:
    target = TARGETS[name]
    try:
        ok = bool(target.installed())
    except (OSError, json.JSONDecodeError, yaml.YAMLError):
        ok = False
    extra = target.stale() if ok else ""
    badge = "⚠ 失效" if extra else ("✓ 已装" if ok else "· 未装")
    if name == "grok" and not ok and claude_installed():
        extra = "（经 Claude settings 兼容覆盖）"
    return f"  {name:12} {badge}{extra}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", nargs="+", choices=list(TARGETS), help="只操作这些目标；默认=检测到的全部")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--force-grok", action="store_true", help="即使 Claude 已装也写 Grok 原生 hooks")
    args = ap.parse_args()

    if args.list:
        print("可安装目标：")
        for name in TARGETS:
            print(status_line(name))
        print("检测到：", ", ".join(detected()) or "无")
        return 0

    names = args.target or detected()
    if not names:
        print("未检测到任何支持的 agent 配置目录，请用 --target 指定")
        return 1

    for name in names:
        target = TARGETS[name]
        if args.uninstall:
            print(target.uninstall())
        elif name == "grok":   # 唯一带安装选项的目标
            print(install_grok(force=args.force_grok))
        else:
            print(target.install())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""用法: python3 replay.py <backend> [...]   结果写到 results/<backend>.json（已跑过的用例跳过）"""
import argparse, atexit, json, os, pathlib, re, shutil, subprocess, sys, tempfile, uuid
from concurrent.futures import ThreadPoolExecutor
REPO = str(pathlib.Path(__file__).resolve().parent.parent)
HERE = pathlib.Path(__file__).resolve().parent
CLEAN_CWD = pathlib.Path(tempfile.mkdtemp(prefix="replay-cwd-"))
atexit.register(lambda: shutil.rmtree(CLEAN_CWD, ignore_errors=True))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
import scan
MAX_ROUNDS = 3
# CLI 返回的是额度/鉴权错误或工具调用，而不是改写文字时，按调用失败处理，不保存
BAD_OUTPUT = re.compile(r"hit your .{0,20}limit|usage limit|rate limit|resets \d{1,2}(:\d\d)?\s*[ap]m|Free usage limit|"
                        r"Eligibility check failed|API Error|<invoke|<parameter name=", re.I)
NO_TOOLS = "bash,edit,write"

def _codex(model, effort):
    def call(prompt):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f: out = pathlib.Path(f.name)
        subprocess.run(["codex", "exec", "-m", model, "-c", f'model_reasoning_effort="{effort}"',
                        "--disable", "hooks", "--ephemeral", "--skip-git-repo-check", "-s", "read-only",
                        "-o", str(out), "-"], input=prompt, capture_output=True, text=True, cwd=CLEAN_CWD, timeout=600)
        return out.read_text().strip()
    return call

def _claude(model, effort):
    def call(prompt):
        return subprocess.run(["claude", "-p", "--model", model, "--effort", effort, "--tools", "",
                               "--settings", '{"disableAllHooks":true}'], input=prompt,
                              capture_output=True, text=True, cwd=CLEAN_CWD, timeout=600).stdout.strip()
    return call

def _grok(model, effort):
    def call(prompt):
        return subprocess.run(["grok", "-p", prompt, "-m", model, "--effort", effort,
                               "--disallowed-tools", NO_TOOLS, "--disable-web-search"],
                              capture_output=True, text=True, cwd=CLEAN_CWD, timeout=600).stdout.strip()
    return call

def _agy(model, effort):
    """Antigravity CLI：推理强度是模型名后缀，如 gemini-3.8-flash-low。"""
    def call(prompt):
        r = subprocess.run(["agy", "-p", prompt, "--model", f"{model}-{effort}", "--sandbox",
                            "--disable-slash-commands", "--print-timeout", "300s"],
                           capture_output=True, text=True, cwd=CLEAN_CWD, timeout=600)
        if r.returncode or not r.stdout.strip(): raise RuntimeError(r.stderr.strip()[-300:])
        return r.stdout.strip()
    return call

def _cursor(model):
    """Cursor Agent：只读 ask 模式；composer-2.5 没有推理强度档位，用非 fast 版本。"""
    def call(prompt):
        r = subprocess.run(["cursor-agent", "-p", "--trust", "--mode", "ask", "--model", model,
                            "--output-format", "text", prompt], capture_output=True, text=True, cwd=CLEAN_CWD, timeout=600)
        if r.returncode or not r.stdout.strip(): raise RuntimeError(r.stderr.strip()[-300:] or r.stdout.strip()[-300:])
        return r.stdout.strip()
    return call

MODELS = [  # (key 前缀, harness, 模型, 调用方式)
    ("codex-luna", "Codex CLI",   "gpt-6-luna",      _codex),
    ("codex-sol",  "Codex CLI",   "gpt-6.1-sol",     _codex),
    ("codex-sol62","Codex CLI",   "gpt-6.2-sol",     _codex),
    ("claude-opus","Claude Code", "claude-opus-5-5", _claude),
    ("claude-sonnet","Claude Code", "claude-sonnet-5-5", _claude),
    ("claude-haiku","Claude Code", "claude-haiku-5-5", _claude),
    ("grok",       "Grok CLI",    "grok-4.7",        _grok),
    ("agy-hydrogen","Antigravity CLI", "gemini-4-hydrogen", _agy),
    ("agy-flash",  "Antigravity CLI", "gemini-3.8-flash", _agy),
]
EFFORTS = ["low", "medium", "high"]
def _dsh(model, effort):
    """DeepSeek Harness headless 模式；模型和推理强度通过 dsh/effort-*.yml 补丁指定，用桌面版账号登录态。"""
    patch = HERE / "dsh" / f"effort-{effort}.yml"
    def call(prompt):
        r = subprocess.run(["dsh", "--profile", "headless", "--patch", str(patch), "--approval-policy", "never", "-"],
                           input=prompt, capture_output=True, text=True, cwd=CLEAN_CWD, timeout=600)
        if r.returncode: raise RuntimeError(r.stderr.strip()[-300:])
        return r.stdout.strip()
    return call

BACKENDS = {f"{k}-{e}": (h, m, e, fn(m, e)) for k, h, m, fn in MODELS for e in EFFORTS}
# DeepSeek 官方 provider 只支持 off / low / high / max，没有 medium
BACKENDS.update({f"dsh-flash-{e}": ("DeepSeek Harness", "deepseek-v4.1-flash", e, _dsh("deepseek-flash", e)) for e in ["low", "high"]})
BACKENDS["cursor-composer-2.5"] = ("Cursor Agent", "composer-2.5", "default", _cursor("composer-2.5"))

def hook(text, sid, rnd, env, lang=None):
    p = {"last_assistant_message": text, "session_id": sid, "stop_hook_active": rnd > 0, "cwd": str(HERE)}
    cmd = [sys.executable, f"{REPO}/scan.py", "--hook", "codex"]
    if lang:
        cmd += ["--lang", lang]
    out = subprocess.run(cmd, input=json.dumps(p),
                         capture_output=True, text=True, env=env, cwd=REPO).stdout.strip()
    return json.loads(out)["reason"] if out else None

def run(case, backend, max_rounds=MAX_ROUNDS):
    call = BACKENDS[backend][3]
    env = dict(os.environ, SIC_DICT_HOME=str(HERE / "sic-dict" / backend))
    sid = f"replay-{backend}-{case['id']}-{uuid.uuid4().hex[:8]}"; text = case["reply"]; log = []
    lang = case.get("lang", "zh")
    loc = scan.get_locale(lang)
    for rnd in range(max_rounds + 1):
        reason = hook(text, sid, rnd, env, lang=case.get("lang"))
        log.append({"round": rnd, "text": text, "blocked": bool(reason), "reason": reason})
        if not reason or rnd == max_rounds: break
        prompt = loc["replay_prompt"].format(user=case["user"], reply=text, reason=reason)
        try:
            text = call(prompt)
            if BAD_OUTPUT.search(text): raise RuntimeError("非改写输出：" + text[:120])
        except Exception as e: text = f"[调用失败] {e!r}"
    return {"id": case["id"], "rounds": log}

def _parse_batch_json(raw):
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.S)
    blob = m.group(1) if m else raw[raw.find("{"):raw.rfind("}") + 1]
    data = json.loads(blob)
    if not isinstance(data, dict):
        raise ValueError("Batch response is not a JSON object")
    return data

def run_batch(cases, backend, max_rounds=MAX_ROUNDS):
    if not cases:
        return []
    if len(cases) == 1:
        return [run(cases[0], backend, max_rounds=max_rounds)]
    call = BACKENDS[backend][3]
    env = dict(os.environ, SIC_DICT_HOME=str(HERE / "sic-dict" / backend))
    run_nonce = uuid.uuid4().hex[:8]
    state = {c["id"]: {"case": c, "text": c["reply"], "log": [], "done": False} for c in cases}
    for rnd in range(max_rounds + 1):
        pending = []
        for cid, st in state.items():
            if st["done"]:
                continue
            c = st["case"]
            sid = f"replay-{backend}-{cid}-{run_nonce}"
            reason = hook(st["text"], sid, rnd, env, lang=c.get("lang"))
            st["log"].append({"round": rnd, "text": st["text"], "blocked": bool(reason), "reason": reason})
            if not reason or rnd == max_rounds:
                st["done"] = True
            else:
                pending.append((cid, st, reason))
        if not pending:
            break
        if len(pending) == 1:
            cid, st, reason = pending[0]
            c = st["case"]
            loc = scan.get_locale(c.get("lang", "zh"))
            prompt = loc["replay_prompt"].format(user=c["user"], reply=st["text"], reason=reason)
            try:
                text = call(prompt)
                if BAD_OUTPUT.search(text): raise RuntimeError("非改写输出：" + text[:120])
                st["text"] = text
            except Exception as e:
                st["log"].append({"round": rnd + 1, "text": f"[调用失败] {e!r}", "blocked": True, "reason": None})
                st["done"] = True
            continue
        blocks = []
        for cid, st, reason in pending:
            c = st["case"]
            loc = scan.get_locale(c.get("lang", "zh"))
            blocks.append(f"=== CASE_ID: {cid} ===\n" + loc["replay_prompt"].format(user=c["user"], reply=st["text"], reason=reason))
        batch_prompt = (
            "请一次性独立处理下面多条措辞检查用例。每条用例只根据其各自的对话记录与 Stop hook 反馈处理，不要互相串话，也不要解释过程。\n"
            "请仅返回一个合法的 JSON 对象，键为每条用例的 CASE_ID，值为该用例最终应输出的完整回复文本（如果全部应保留原文，值就填「【措辞已确认，保留原文】」）。不要在 JSON 外输出其他文字。\n\n"
            + "\n\n".join(blocks)
        )
        try:
            raw = call(batch_prompt)
            if BAD_OUTPUT.search(raw): raise RuntimeError("非改写输出：" + raw[:120])
            parsed = _parse_batch_json(raw)
            for cid, st, _ in pending:
                val = parsed.get(cid)
                if not isinstance(val, str) or not val.strip():
                    st["log"].append({"round": rnd + 1, "text": f"[调用失败] 批量返回缺少 {cid}", "blocked": True, "reason": None})
                    st["done"] = True
                else:
                    st["text"] = val.strip()
        except Exception as e:
            for cid, st, _ in pending:
                st["log"].append({"round": rnd + 1, "text": f"[调用失败] {e!r}", "blocked": True, "reason": None})
                st["done"] = True
            break
    return [{"id": c["id"], "rounds": state[c["id"]]["log"]} for c in cases]

def main(backend, cases_path=HERE / "cases.json", max_rounds=MAX_ROUNDS, batch=False):
    path = HERE / "results" / f"{backend}.json"
    old = json.loads(path.read_text()) if path.exists() else []
    done = {r["id"] for r in old}
    todo = [c for c in json.load(open(cases_path)) if c["id"] not in done]
    if batch:
        res = run_batch(todo, backend, max_rounds=max_rounds)
    else:
        with ThreadPoolExecutor(5) as ex: res = list(ex.map(lambda c: run(c, backend, max_rounds=max_rounds), todo))
    failed = [r for r in res if any(x["text"].startswith("[调用失败]") for x in r["rounds"])]
    res = [r for r in res if r not in failed]  # 调用失败的不保存，下次重跑
    if failed: print(backend, "调用失败", len(failed), "条，例如：", failed[0]["rounds"][-1]["text"][:200])
    path.write_text(json.dumps(old + res, ensure_ascii=False, indent=1))
    print(backend, "done", len(todo))

def cli():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("backends", nargs="+", choices=list(BACKENDS), help="要运行的模型配置")
    ap.add_argument("--cases", type=pathlib.Path, default=HERE / "cases.json", help="用例文件路径")
    ap.add_argument("--max-rounds", type=int, default=MAX_ROUNDS, help="单条用例最多改写轮数")
    ap.add_argument("--batch", action="store_true", help="将同一后端待跑的多条用例聚合成单次请求")
    args = ap.parse_args()
    with ThreadPoolExecutor(len(args.backends)) as ex:
        list(ex.map(lambda b: main(b, cases_path=args.cases, max_rounds=args.max_rounds, batch=args.batch), args.backends))

if __name__ == "__main__":
    cli()

/**
 * DeepSeek Harness (dsh) 原生 Cordis 插件：在 agent/turn-stopping 边界调用
 * turing-advanced-silicon-carbon-dictionary，若需改写则通过 agent.steer() 续跑下一步。
 * 由 install.py 写入 ~/.dsh/profiles/<profile>/（含 __AUDITION_ROOT__ 替换）。
 */
import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const EXT_DIR = dirname(fileURLToPath(import.meta.url));
const ROOT = "__AUDITION_ROOT__".startsWith("__")
  ? join(EXT_DIR, "..")
  : "__AUDITION_ROOT__";
const SCAN = join(ROOT, "scan.py");

export const name = "turing-advanced-silicon-carbon-dictionary";

function findPython() {
  for (const cand of [
    process.env.AUDITION_PYTHON,
    join(process.env.HOME || "", ".venv/bin/python3"),
    "python3",
    "python",
  ]) {
    if (!cand) continue;
    if (cand === "python3" || cand === "python") return cand;
    if (existsSync(cand)) return cand;
  }
  return "python3";
}

function lastAssistantText(session) {
  const messages = session?.deriveMessages?.() ?? [];
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i];
    if (msg?.role !== "assistant") continue;
    if (typeof msg.content === "string") return msg.content;
    if (!Array.isArray(msg.content)) continue;
    const text = msg.content
      .filter((b) => b && b.type === "text" && typeof b.text === "string")
      .map((b) => b.text)
      .join("\n")
      .trim();
    if (text) return text;
  }
  return "";
}

function deepFreeze(value) {
  if (value === null || typeof value !== "object") return value;
  Object.freeze(value);
  for (const key of Object.keys(value)) deepFreeze(value[key]);
  return value;
}

function makeNoticeMessage(text) {
  return deepFreeze({
    id: randomUUID(),
    role: "user",
    content: [{ type: "text", text }],
    source: {
      kind: "plugin",
      plugin: name,
      form: "notice",
      summary: "措辞检查",
    },
  });
}

function runScan(payload, signal) {
  if (!existsSync(SCAN) || signal?.aborted) return Promise.resolve(null);
  return new Promise((resolve) => {
    const child = spawn(findPython(), [SCAN, "--hook", "dsh"], {
      env: process.env,
      stdio: ["pipe", "pipe", "ignore"],
    });
    let stdout = "";
    let settled = false;
    const done = (val) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener?.("abort", onAbort);
      resolve(val);
    };
    const onAbort = () => {
      child.kill("SIGTERM");
      done(null);
    };
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      done(null);
    }, 10_000);
    signal?.addEventListener?.("abort", onAbort, { once: true });
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    child.on("error", () => done(null));
    child.on("close", (code) => {
      if (code !== 0 || !stdout.trim()) return done(null);
      try {
        const lastLine = stdout.trim().split("\n").filter(Boolean).pop() || "{}";
        done(JSON.parse(lastLine));
      } catch {
        done(null);
      }
    });
    child.stdin.end(JSON.stringify(payload));
  });
}

export function apply(ctx) {
  const pendingTurns = new Set();

  ctx.on("agent/turn-stopping", async ({ agent, turn, signal }) => {
    if (!agent || signal?.aborted) return;
    const text = lastAssistantText(agent.session);
    if (!text) return;

    const sessionId = String(agent.id || agent.session?.header?.id || "");
    const turnKey = `${sessionId}:${turn}`;
    const stopHookActive = pendingTurns.has(turnKey);

    const out = await runScan(
      {
        last_assistant_message: text,
        stop_hook_active: stopHookActive,
        session_id: sessionId,
        cwd: agent.session?.header?.cwd || process.cwd(),
      },
      signal,
    );

    if (signal?.aborted) {
      pendingTurns.delete(turnKey);
      return;
    }

    if (out?.decision === "block" && out?.reason) {
      pendingTurns.add(turnKey);
      agent.steer(makeNoticeMessage(out.reason));
    } else {
      pendingTurns.delete(turnKey);
    }
  });
}

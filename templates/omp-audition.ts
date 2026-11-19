/**
 * OMP / Oh My Pi extension：session_stop 时调用 turing-advanced-silicon-carbon-dictionary。
 * 由 install.py 写入 ~/.omp/agent/extensions/（可含绝对路径占位替换）。
 * 不修改 herdr 等已有扩展。
 */
// @ts-nocheck
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const EXT_DIR = dirname(fileURLToPath(import.meta.url));
// install.py 会把下一行替换成绝对仓库根；开发时回退到仓库相对路径
const ROOT = "__AUDITION_ROOT__".startsWith("__")
  ? join(EXT_DIR, "..")
  : "__AUDITION_ROOT__";
const SCAN = join(ROOT, "scan.py");

function messageText(msg: any): string {
  if (!msg) return "";
  if (typeof msg === "string") return msg;
  const content = msg.content;
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content
    .map((c) => (typeof c === "string" ? c : c?.type === "text" ? c.text || "" : ""))
    .filter(Boolean)
    .join("\n");
}

function findPython(): string {
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

export default function (pi: any) {
  pi.on("session_stop", async (event: any, _ctx: any) => {
    if (!existsSync(SCAN)) return;
    const payload = {
      last_assistant_message: messageText(event?.last_assistant_message),
      stop_hook_active: Boolean(event?.stop_hook_active),
      session_id: event?.session_id || "",
      cwd: process.cwd(),
      session_file: event?.session_file || "",
    };
    try {
      const r = spawnSync(findPython(), [SCAN, "--hook", "omp"], {
        input: JSON.stringify(payload),
        encoding: "utf8",
        timeout: 10_000,
        env: process.env,
      });
      if (r.status !== 0 || !r.stdout?.trim()) return;
      const out = JSON.parse(r.stdout.trim().split("\n").filter(Boolean).pop() || "{}");
      if (out?.decision === "block" && out?.reason) {
        return { decision: "block", reason: out.reason };
      }
    } catch {
      // 失败放行
    }
  });
}

/**
 * Pi (pi-coding-agent / OmO senpi) extension：turn_end 时调用 turing-advanced-silicon-carbon-dictionary。
 * 由 install.py 写入 ~/.pi/agent/extensions/（含 __AUDITION_ROOT__ 替换）。
 */
// @ts-nocheck
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const EXT_DIR = dirname(fileURLToPath(import.meta.url));
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
  const pendingReview = new Set<string>();

  pi.on("turn_end", async (event: any, ctx: any) => {
    if (!existsSync(SCAN)) return;
    if (event?.outcome && event.outcome !== "completed") return;
    if (Array.isArray(event?.toolResults) && event.toolResults.length > 0) return;
    if (event?.message?.role && event.message.role !== "assistant") return;

    const text = messageText(event?.message);
    if (!text.trim()) return;

    const sessionId =
      event?.sessionId ||
      ctx?.sessionManager?.getSessionId?.() ||
      ctx?.sessionId ||
      "pi-default";
    const stopHookActive = pendingReview.has(sessionId);

    const payload = {
      last_assistant_message: text,
      stop_hook_active: stopHookActive,
      session_id: sessionId,
      cwd: ctx?.cwd || process.cwd(),
      session_file: ctx?.sessionManager?.getSessionFile?.() || "",
    };

    try {
      const r = spawnSync(findPython(), [SCAN, "--hook", "pi"], {
        input: JSON.stringify(payload),
        encoding: "utf8",
        timeout: 10_000,
        env: process.env,
      });
      if (r.status !== 0 || !r.stdout?.trim()) {
        pendingReview.delete(sessionId);
        return;
      }
      const out = JSON.parse(r.stdout.trim().split("\n").filter(Boolean).pop() || "{}");
      if (out?.decision === "block" && out?.reason) {
        pendingReview.add(sessionId);
        if (Array.isArray(event?.entries)) {
          return {
            entries: [
              ...event.entries,
              {
                type: "custom_message",
                customType: "turing-advanced-silicon-carbon-dictionary",
                content: out.reason,
                display: false,
              },
            ],
            continue: true,
          };
        }
        if (typeof pi?.sendMessage === "function") {
          pi.sendMessage(
            {
              customType: "turing-advanced-silicon-carbon-dictionary",
              content: out.reason,
              display: false,
            },
            { triggerTurn: true },
          );
        } else if (typeof pi?.sendUserMessage === "function") {
          pi.sendUserMessage(out.reason);
        }
      } else {
        pendingReview.delete(sessionId);
      }
    } catch {
      pendingReview.delete(sessionId);
    }
  });
}

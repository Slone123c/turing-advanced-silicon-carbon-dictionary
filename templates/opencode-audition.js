/**
 * OpenCode plugin：session.idle 时调用 turing-advanced-silicon-carbon-dictionary。
 * 同时导出 OpenCode V1 (server) 与 V2 (setup) 两种入口，由 install.py 写入
 * ~/.config/opencode/plugins/（含 __AUDITION_ROOT__ 替换）。
 */
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const EXT_DIR = dirname(fileURLToPath(import.meta.url));
const ROOT = "__AUDITION_ROOT__".startsWith("__")
  ? join(EXT_DIR, "..")
  : "__AUDITION_ROOT__";
const SCAN = join(ROOT, "scan.py");

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

function extractText(entry) {
  if (!entry) return "";
  const parts = Array.isArray(entry.parts) ? entry.parts : [];
  return parts
    .filter((p) => p && p.type === "text" && typeof p.text === "string" && !p.ignored)
    .map((p) => p.text)
    .join("\n")
    .trim();
}

function lastAssistantEntry(messages) {
  if (!Array.isArray(messages)) return null;
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    const info = m?.info || m;
    if (info?.role === "assistant") {
      return { id: info.id || `${i}`, text: extractText(m) };
    }
  }
  return null;
}

function runScan(payload) {
  if (!existsSync(SCAN)) return null;
  try {
    const r = spawnSync(findPython(), [SCAN, "--hook", "opencode"], {
      input: JSON.stringify(payload),
      encoding: "utf8",
      timeout: 10_000,
      env: process.env,
    });
    if (r.status !== 0 || !r.stdout?.trim()) return null;
    return JSON.parse(r.stdout.trim().split("\n").filter(Boolean).pop() || "{}");
  } catch {
    return null;
  }
}

function createHandler({ getMessages, sendPrompt, directory }) {
  const checkedIds = new Set();
  const pendingReview = new Set();

  return async function onSessionIdle(sessionID) {
    if (!sessionID) return;
    const messages = await getMessages(sessionID);
    const last = lastAssistantEntry(messages);
    if (!last || !last.text) return;
    const key = `${sessionID}:${last.id}`;
    if (checkedIds.has(key)) return;
    checkedIds.add(key);

    const stopHookActive = pendingReview.has(sessionID);
    const out = runScan({
      last_assistant_message: last.text,
      stop_hook_active: stopHookActive,
      session_id: sessionID,
      cwd: directory || process.cwd(),
    });

    if (out?.decision === "block" && out?.reason) {
      pendingReview.add(sessionID);
      await sendPrompt(sessionID, out.reason);
    } else {
      pendingReview.delete(sessionID);
    }
  };
}

export const AuditionPlugin = async ({ client, directory }) => {
  const onIdle = createHandler({
    directory,
    getMessages: async (sessionID) => {
      const res = await client.session.messages({ path: { id: sessionID } });
      return res?.data ?? res ?? [];
    },
    sendPrompt: async (sessionID, text) => {
      await client.session.prompt({
        path: { id: sessionID },
        body: { parts: [{ type: "text", text }] },
      });
    },
  });

  return {
    event: async ({ event }) => {
      if (!event || event.type !== "session.idle") return;
      const sessionID = event.properties?.sessionID || event.sessionID;
      await onIdle(sessionID);
    },
  };
};

export default {
  id: "turing-advanced-silicon-carbon-dictionary",
  server: AuditionPlugin,
  async setup(ctx) {
    const controller = new AbortController();
    const onIdle = createHandler({
      directory: ctx?.location?.directory,
      getMessages: async (sessionID) => {
        const res = await ctx.session.context({ sessionID });
        return res?.data ?? res ?? [];
      },
      sendPrompt: async (sessionID, text) => {
        await ctx.session.prompt({ sessionID, text });
      },
    });

    void (async () => {
      try {
        for await (const event of ctx.event.subscribe({ signal: controller.signal })) {
          if (event?.type === "session.idle") {
            const sessionID = event.properties?.sessionID || event.sessionID;
            await onIdle(sessionID);
          }
        }
      } catch {
        // aborted on unload
      }
    })();

    return () => controller.abort();
  },
};

#!/usr/bin/env node
/**
 * sessionStart — inject NEXT_TASK + lessons for Conductor or Autopilot.
 * Reads .autopilot/runtime.json for Cursor vs Claude Code hints.
 */
const fs = require("fs");
const path = require("path");

const root = process.cwd();
const nextTask = path.join(root, "tasks", "NEXT_TASK.md");
const lessons = path.join(root, "tasks", "lessons.md");
const activeAutopilot = path.join(root, ".autopilot", "active.json");
const runtimeFile = path.join(root, ".autopilot", "runtime.json");

function getRuntime() {
  if (!fs.existsSync(runtimeFile)) return "cursor";
  try {
    const data = JSON.parse(fs.readFileSync(runtimeFile, "utf8"));
    const name = String(data.runtime || "cursor").toLowerCase();
    return name === "claude-code" ? "claude-code" : "cursor";
  } catch {
    return "cursor";
  }
}

const runtime = getRuntime();
const runtimeLabel = runtime === "claude-code" ? "Claude Code" : "Cursor";

let parts = [`## Session context (${runtimeLabel})\n`];

if (runtime === "claude-code") {
  parts.push(
    "Runtime is **claude-code** — see `CLAUDE.md` and `docs/autopilot/CLAUDE-CODE-AUTOPILOT.md`.\n" +
      "Gens-ai: `/sandbox`, `autopilot <task.json>`. Bridge: `python -m orchestrator autopilot *`.\n"
  );
} else {
  parts.push(
    "Runtime is **cursor** — see `docs/autopilot/CURSOR-AUTOPILOT.md`.\n" +
      "Switch: `scripts/set-agent-runtime.ps1 claude-code` · hub: `docs/AGENT_RUNTIME.md`.\n"
  );
}

if (fs.existsSync(activeAutopilot)) {
  try {
    const active = JSON.parse(fs.readFileSync(activeAutopilot, "utf8"));
    parts.push(
      `**Autopilot mode** — task file: \`${active.taskFile || "?"}\`\n` +
        "- Assign work: `python -m orchestrator autopilot next`\n" +
        "- Verify: `python -m orchestrator autopilot verify <id>`\n" +
        "- Complete: `python -m orchestrator autopilot complete <id>`\n"
    );
  } catch {
    parts.push("_Autopilot active file unreadable._\n");
  }
}

if (fs.existsSync(nextTask)) {
  const content = fs.readFileSync(nextTask, "utf8");
  parts.push(content.slice(0, 4000));
} else {
  parts.push(
    "_No NEXT_TASK assigned._\n" +
      "- PRD: `python -m orchestrator next`\n" +
      "- Autopilot: `python -m orchestrator autopilot next`"
  );
}

if (fs.existsSync(lessons)) {
  const lessonText = fs.readFileSync(lessons, "utf8");
  const tail = lessonText.length > 2000 ? lessonText.slice(-2000) : lessonText;
  parts.push("\n## Recent lessons\n" + tail);
}

parts.push(
  "\n## Rules (repo lead)\n" +
    "- You own the **product**, not the task file. **Do not stop** until `docs/PRODUCTION_READINESS.md` checklist passes (`SINGULR_PRODUCTION_READY`) or you are truly blocked (`REPO_LEAD_BLOCKED`).\n" +
    "- **No autopilot req?** Switch task packs or self-assign from PRD — see PRODUCTION_READINESS.md.\n" +
    "- After `autopilot complete` → `autopilot next` → **continue in the same turn**. No mid-backlog summaries.\n" +
    "- Run verify before complete. Do not commit `.env` or secrets."
);

process.stdout.write(JSON.stringify({ additional_context: parts.join("\n") }));

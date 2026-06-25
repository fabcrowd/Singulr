#!/usr/bin/env node
/**
 * afterShellExecution — capture pytest/ruff failures into golden packets.
 */
const fs = require("fs");
const path = require("path");

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  input += chunk;
});
process.stdin.on("end", () => {
  let payload = {};
  try {
    payload = JSON.parse(input || "{}");
  } catch {
    process.stdout.write(JSON.stringify({}));
    return;
  }

  const output = payload.output || "";
  const command = payload.command || "";
  const exitCode = payload.exit_code ?? payload.exitCode ?? 0;

  if (exitCode === 0) {
    process.stdout.write(JSON.stringify({}));
    return;
  }

  const root = process.cwd();
  const prdPath = path.join(root, "tasks", "prd.json");
  let taskId = "unknown";

  try {
    const prd = JSON.parse(fs.readFileSync(prdPath, "utf8"));
    const active = (prd.tasks || []).find((t) => t.status === "in_progress");
    if (active) taskId = active.id;
  } catch {
    // ignore
  }

  const runDir = path.join(root, "orchestrator", "runs", taskId);
  fs.mkdirSync(runDir, { recursive: true });
  const packet = {
    task_id: taskId,
    timestamp: new Date().toISOString(),
    command,
    exit_code: exitCode,
    output_tail: String(output).slice(-4000),
  };
  fs.writeFileSync(path.join(runDir, "shell-failure.json"), JSON.stringify(packet, null, 2));

  process.stdout.write(
    JSON.stringify({
      additional_context:
        `Shell command failed (exit ${exitCode}). Golden packet saved to orchestrator/runs/${taskId}/shell-failure.json. ` +
        `Fix and re-run verify, or: python -m orchestrator fail ${taskId} --reason "shell failure"`,
    })
  );
});

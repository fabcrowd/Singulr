#!/usr/bin/env node
/**
 * stop — remind agent to verify before claiming task complete.
 */
const fs = require("fs");
const path = require("path");

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  input += chunk;
});
process.stdin.on("end", () => {
  const root = process.cwd();
  const prdPath = path.join(root, "tasks", "prd.json");
  let inProgress = [];

  try {
    const prd = JSON.parse(fs.readFileSync(prdPath, "utf8"));
    inProgress = (prd.tasks || []).filter((t) => t.status === "in_progress").map((t) => t.id);
  } catch {
    // ignore
  }

  if (inProgress.length === 0) {
    process.stdout.write(JSON.stringify({}));
    return;
  }

  const ids = inProgress.join(", ");
  const msg =
    `Conductor: task(s) ${ids} still in_progress. ` +
    `Run \`python -m orchestrator verify ${inProgress[0]}\` — ` +
    `if pass: \`complete ${inProgress[0]}\`; if fail: \`fail ${inProgress[0]} --reason "..."\`. ` +
    `Do not claim SINGULR_SHIP until all tasks done and verify.ps1 passes.`;

  process.stdout.write(
    JSON.stringify({
      followup_message: msg,
    })
  );
});

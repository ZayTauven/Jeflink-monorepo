// Formate le fichier modifié. Ne bloque jamais : un outil absent ou un échec de formatage n'interrompt pas Claude.
import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { projectDir, readTarget } from "./_input.mjs";

const target = await readTarget();
if (!target || !existsSync(target.abs) || target.rel.startsWith("..")) process.exit(0);
const { abs, rel } = target;

const run = (cmd, args, cwd) =>
  spawnSync(cmd, args, { cwd, stdio: "ignore", timeout: 20_000, windowsHide: true });

if (rel.endsWith(".py") && rel.startsWith("apps/api/")) {
  const apiDir = path.join(projectDir, "apps/api");
  run("uv", ["run", "ruff", "format", abs], apiDir);
  run("uv", ["run", "ruff", "check", "--fix", "--quiet", abs], apiDir);
} else if (/\.(tsx?|jsx?|mjs|cjs|json|css|mdx?|ya?ml)$/.test(rel)) {
  // Prettier local du monorepo, lancé via node : ni pnpm ni shell requis.
  const prettier = path.join(projectDir, "node_modules/prettier/bin/prettier.cjs");
  if (existsSync(prettier))
    run(process.execPath, [prettier, "--write", "--log-level", "silent", abs], projectDir);
}
process.exit(0);

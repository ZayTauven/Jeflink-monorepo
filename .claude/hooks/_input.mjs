// Lit le JSON du hook sur stdin et renvoie le chemin ciblé, normalisé en « / » (Windows compris).
// Node uniquement : pas de dépendance à jq ni à bash.
import path from "node:path";

export const projectDir = path.resolve(process.env.CLAUDE_PROJECT_DIR ?? process.cwd());

export async function readTarget() {
  let raw = "";
  for await (const chunk of process.stdin) raw += chunk;
  let filePath = "";
  try {
    filePath = JSON.parse(raw)?.tool_input?.file_path ?? "";
  } catch {
    return null;
  }
  if (!filePath) return null;
  const abs = path.resolve(projectDir, filePath);
  const rel = path.relative(projectDir, abs).split(path.sep).join("/");
  return { abs, rel, name: path.basename(abs) };
}

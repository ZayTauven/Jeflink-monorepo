// Garde-fou CI (spec 001, infra 4) : les gabarits nginx de production (bord public TLS) et de
// l'écouteur interne passent `nginx -t`, avec un certificat jetable généré pour l'occasion.
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const NGINX =
  "nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10";
const certs = mkdtempSync(join(tmpdir(), "jf-certs-"));
const templates = resolve("infra/proxy/templates");
const env = { ...process.env, MSYS_NO_PATHCONV: "1" };
let failures = 0;

function docker(args) {
  return spawnSync("docker", args, { env, encoding: "utf8" });
}

try {
  const gen = docker([
    "run",
    "--rm",
    "-v",
    `${certs}:/c`,
    "alpine/openssl",
    "req",
    "-x509",
    "-newkey",
    "rsa:2048",
    "-nodes",
    "-keyout",
    "/c/k.pem",
    "-out",
    "/c/c.pem",
    "-days",
    "1",
    "-subj",
    "/CN=api",
  ]);
  if (gen.status !== 0) throw new Error(`certificat jetable : ${gen.stderr}`);
  for (const variant of ["production", "internal"]) {
    const mounts = [
      "-v",
      `${certs}:/certs:ro`,
      "-v",
      `${templates}/${variant}/default.conf.template:/etc/nginx/templates/default.conf.template:ro`,
    ];
    if (variant === "production") {
      mounts.push(
        "-v",
        `${templates}/jeflink-api-locations.inc.template:/etc/nginx/templates/jeflink-api-locations.inc.template:ro`,
      );
    }
    const result = docker([
      "run",
      "--rm",
      "-e",
      "API_PUBLIC_HOST=api.example",
      "-e",
      "API_UPSTREAM=api:8000",
      "-e",
      "TLS_CERT=/certs/c.pem",
      "-e",
      "TLS_KEY=/certs/k.pem",
      "--add-host",
      "api:127.0.0.1",
      ...mounts,
      NGINX,
      "sh",
      "-c",
      "/docker-entrypoint.sh nginx -t",
    ]);
    const ok = result.status === 0 && /test is successful/.test(result.stderr + result.stdout);
    console.log(`${ok ? "ok   " : "ÉCHEC"} gabarit ${variant} : nginx -t`);
    if (!ok) {
      failures += 1;
      console.error(result.stderr);
    }
  }
} finally {
  rmSync(certs, { recursive: true, force: true });
}
process.exit(failures ? 1 : 0);

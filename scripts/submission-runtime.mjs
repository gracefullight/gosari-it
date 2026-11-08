import { spawnSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseEnv } from "node:util";
import { waitForReadiness } from "./runtime-readiness.mjs";

const SECRET_NAME_PATTERN = /KEY|PASSWORD|TOKEN|SECRET|DSN/;
const ENV_NAME_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/;

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const output = resolve(root, process.env.SUBMISSION_RUNTIME_DIR || ".local/submission-runtime");
const ledgerPath = resolve(output, "resource-ledger.json");
const overridePath = resolve(output, "compose.verify.json");
const secretPath = resolve(output, "runtime.env");
mkdirSync(output, { recursive: true, mode: 0o700 });
let env = { ...process.env };

function run(command, args, { allowFailure = false } = {}) {
  const result = spawnSync(command, args, { cwd: root, env, encoding: "utf8", timeout: 240_000 });
  const secrets = Object.entries(env)
    .filter(([name, value]) => SECRET_NAME_PATTERN.test(name) && value)
    .map(([, value]) => value);
  const clean = (text) =>
    secrets.reduce((value, secret) => value.replaceAll(secret, "[비공개]"), text || "");
  if (!allowFailure && result.status !== 0) {
    throw new Error(`${command} ${args[0]} 실패: ${clean(result.stderr).slice(-2500)}`);
  }
  return { ...result, stdout: clean(result.stdout), stderr: clean(result.stderr) };
}

function compose(project, args) {
  return run("docker", [
    "compose",
    "--env-file",
    secretPath,
    "-p",
    project,
    "-f",
    resolve(root, "compose.yaml"),
    "-f",
    overridePath,
    ...args,
  ]);
}

function save(ledger) {
  writeFileSync(ledgerPath, `${JSON.stringify(ledger, null, 2)}\n`, { mode: 0o600 });
}

async function start() {
  if (existsSync(ledgerPath))
    throw new Error("기존 검증 기록을 보존하세요. 새 SUBMISSION_RUNTIME_DIR을 지정하세요.");
  const port = Number(process.env.SUBMISSION_PORT || 8766);
  if (!Number.isInteger(port) || port < 1024 || port > 65535)
    throw new Error("검증 포트를 확인하세요.");
  await new Promise((resolvePort, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(port, "127.0.0.1", () => server.close(resolvePort));
  });
  const sourceEnv = parseEnv(readFileSync(resolve(root, "apps/api/.env"), "utf8"));
  const project = `gosariit-submission-${Date.now()}`;
  const image = process.env.SUBMISSION_IMAGE || "gosariit-app:submission";
  env = {
    ...env,
    ...sourceEnv,
    GOSARI_APP_IMAGE: image,
    APP_PORT: String(port),
    DB_ADMIN_PASSWORD: randomBytes(32).toString("base64url"),
    DB_PASSWORD: randomBytes(32).toString("base64url"),
  };
  const runtimeEnv = {
    ...sourceEnv,
    GOSARI_APP_IMAGE: image,
    APP_PORT: String(port),
    DB_ADMIN_PASSWORD: env.DB_ADMIN_PASSWORD,
    DB_PASSWORD: env.DB_PASSWORD,
  };
  const serializable = Object.entries(runtimeEnv).filter(([name]) => ENV_NAME_PATTERN.test(name));
  writeFileSync(
    secretPath,
    serializable.map(([name, value]) => `${name}=${JSON.stringify(value)}`).join("\n"),
    { mode: 0o600 }
  );
  const override = {
    services: {
      db: { cpus: 1, mem_limit: "1g" },
      "db-init": { cpus: 1, mem_limit: "512m" },
      app: {
        cpus: 2,
        mem_limit: "2g",
        environment: {
          DB_PASSWORD: env.DB_PASSWORD,
          APP_PROFILE: "center",
          EXTERNAL_REQUESTS_ENABLED: sourceEnv.EXTERNAL_REQUESTS_ENABLED || "false",
        },
      },
    },
  };
  const sourceBound = process.env.SUBMISSION_API_SOURCE === "1";
  if (sourceBound) {
    override.services.app.volumes = [
      {
        type: "bind",
        source: resolve(root, "apps/api/src"),
        target: "/app/apps/api/src",
        read_only: true,
      },
    ];
  }
  writeFileSync(overridePath, JSON.stringify(override, null, 2), { mode: 0o600 });
  const ledger = {
    started_at: new Date().toISOString(),
    project,
    image,
    api_source_bound: sourceBound,
    port,
    source_commit: run("git", ["rev-parse", "HEAD"], { allowFailure: true }).stdout.trim() || null,
    image_id: run("docker", ["image", "inspect", image, "--format", "{{.Id}}"]).stdout.trim(),
    volume: `${project}_public_pgdata`,
    phase: "allocated",
    containers: [],
  };
  if (run("docker", ["volume", "inspect", ledger.volume], { allowFailure: true }).status === 0) {
    throw new Error("검증 DB에는 새 빈 볼륨이 필요합니다.");
  }
  save(ledger);
  try {
    compose(project, [
      "up",
      "-d",
      "--no-build",
      "--pull",
      "never",
      "--wait",
      "--wait-timeout",
      "90",
      "db",
    ]);
    ledger.phase = "fresh-db-ready";
    save(ledger);
    const init = compose(project, ["run", "--no-deps", "--rm", "db-init"]);
    writeFileSync(resolve(output, "db-init.log"), init.stdout + init.stderr);
    ledger.phase = "migrated";
    save(ledger);
    compose(project, [
      "up",
      "-d",
      "--no-build",
      "--pull",
      "never",
      "--no-deps",
      "--wait",
      "--wait-timeout",
      "180",
      "app",
    ]);
    ledger.readiness = await waitForReadiness({ port, timeoutMs: 60_000 });
    ledger.phase = "ready";
    ledger.ready_at = new Date().toISOString();
  } finally {
    ledger.containers = run(
      "docker",
      ["ps", "-aq", "--filter", `label=com.docker.compose.project=${project}`],
      { allowFailure: true }
    )
      .stdout.trim()
      .split("\n")
      .filter(Boolean);
    save(ledger);
  }
  console.log(
    JSON.stringify({
      project,
      port,
      image_id: ledger.image_id,
      phase: ledger.phase,
      readiness: ledger.readiness,
    })
  );
}

function stop() {
  const ledger = JSON.parse(readFileSync(ledgerPath, "utf8"));
  env = { ...env, ...parseEnv(readFileSync(secretPath, "utf8")) };
  const ids = run("docker", [
    "ps",
    "-q",
    "--filter",
    `label=com.docker.compose.project=${ledger.project}`,
  ])
    .stdout.trim()
    .split("\n")
    .filter(Boolean);
  if (
    ids.some(
      (id) => !ledger.containers.some((owned) => owned.startsWith(id) || id.startsWith(owned))
    )
  ) {
    throw new Error("소유를 확인할 수 없는 컨테이너는 중지할 수 없습니다.");
  }
  if (ids.length) compose(ledger.project, ["stop", "--timeout", "30"]);
  const remaining = run("docker", [
    "ps",
    "-q",
    "--filter",
    `label=com.docker.compose.project=${ledger.project}`,
  ]).stdout.trim();
  if (remaining) throw new Error("검증 컨테이너의 중지를 확인할 수 없습니다.");
  ledger.phase = "stopped";
  ledger.stopped_at = new Date().toISOString();
  save(ledger);
  console.log("검증 컨테이너 중지 완료. 볼륨·로그·이미지는 보존했습니다.");
}

try {
  if (process.argv[2] === "start") await start();
  else if (process.argv[2] === "stop") stop();
  else throw new Error("사용법: submission-runtime.mjs start|stop");
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}

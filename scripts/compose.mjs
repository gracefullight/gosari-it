#!/usr/bin/env node
// 고사리잇 로컬 Compose orchestration (SRS 실행환경 v1.2 §5).
// POSIX 셸·명령 연결에 의존하지 않고 인자 배열로 실행한다. 비밀은 출력하지 않는다.
import { spawnSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import {
  closeSync,
  constants,
  existsSync,
  mkdirSync,
  openSync,
  readFileSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { parseEnv } from "node:util";
import { readCapabilities, waitForReadiness } from "./runtime-readiness.mjs";

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const PROJECT = "gosariit-local";
const LOCAL = join(ROOT, ".local");
const API_ENV = join(ROOT, "apps/api/.env");
const WEB_ENV = join(ROOT, "apps/web/.env");
const LOCK = join(LOCAL, "compose.lock");
const SECRET_NAME_PATTERN = /KEY|PASSWORD|SECRET|TOKEN|DSN/;

function log(msg) {
  process.stdout.write(`${msg}\n`);
}
function fail(msg, code = 1) {
  process.stderr.write(`✗ ${msg}\n`);
  process.exit(code);
}

function run(cmd, args, opts = {}) {
  const result = spawnSync(cmd, args, {
    cwd: ROOT,
    encoding: "utf8",
    env: { ...process.env, ...composeEnv() },
    ...opts,
  });
  if (result.status !== 0 && !opts.allowFailure) {
    const secrets = Object.entries(composeEnv())
      .filter(([name, value]) => SECRET_NAME_PATTERN.test(name) && value)
      .map(([, value]) => value);
    const stderr = secrets
      .reduce((text, value) => text.replaceAll(value, "[비공개]"), result.stderr || "")
      .slice(0, 500);
    fail(`${cmd} ${args[0] ?? ""} 실패 (exit ${result.status}): ${stderr}`);
  }
  return result;
}

function parseEnvFile(path) {
  return existsSync(path) ? parseEnv(readFileSync(path, "utf8")) : {};
}

function composeEnv() {
  const api = parseEnvFile(API_ENV);
  return {
    ...api,
    GOSARI_APP_IMAGE: api.GOSARI_APP_IMAGE || "gosariit-app:local",
    GOSARI_DB_IMAGE: api.GOSARI_DB_IMAGE || "pgvector/pgvector:pg18",
    APP_PORT: api.APP_PORT || "8765",
    APP_PROFILE: api.APP_PROFILE || "center",
    KMA_SERVICE_KEY: api.KMA_SERVICE_KEY || api.DATA_GO_KR_SERVICE_KEY || "",
    AT_SERVICE_KEY: api.AT_SERVICE_KEY || api.DATA_GO_KR_SERVICE_KEY || "",
  };
}

function composeArgs(extra = []) {
  return ["compose", "--env-file", "apps/api/.env", "-p", PROJECT, "-f", "compose.yaml", ...extra];
}

function nativeComposeArgs(extra = []) {
  return composeArgs(["-f", "compose.native.yaml", ...extra]);
}

let lockHeld = false;
function acquireLock() {
  mkdirSync(LOCAL, { recursive: true });
  try {
    const fd = openSync(LOCK, constants.O_CREAT | constants.O_EXCL | constants.O_WRONLY, 0o600);
    writeFileSync(fd, String(process.pid));
    closeSync(fd);
    lockHeld = true;
  } catch {
    fail("다른 compose 작업이 진행 중입니다 (.local/compose.lock). 완료 후 다시 시도하세요.");
  }
}
function releaseLock() {
  if (!lockHeld) return;
  try {
    unlinkSync(LOCK);
  } catch {}
  lockHeld = false;
}
// process.exit 경로에서도 본인이 잡은 lock만 정리한다.
process.on("exit", releaseLock);

function doctor() {
  if (!existsSync(API_ENV) || !existsSync(WEB_ENV)) {
    fail("apps/api/.env 및 apps/web/.env가 필요합니다. mise run init으로 준비하세요.");
  }
  const api = parseEnvFile(API_ENV);
  if (!api.DB_ADMIN_PASSWORD || !api.DB_PASSWORD) {
    fail(
      "apps/api/.env의 DB_ADMIN_PASSWORD 및 DB_PASSWORD를 설정하세요. 기존 DB의 비밀번호를 유지하세요."
    );
  }
  log("doctor: Docker 엔진 확인");
  const version = run("docker", ["version", "--format", "{{.Server.Os}}/{{.Server.Arch}}"], {
    allowFailure: true,
  });
  if (version.status !== 0)
    fail("Docker daemon에 연결할 수 없습니다. Docker Desktop/엔진을 시작하세요.");
  const os = (version.stdout || "").trim();
  if (!os.startsWith("linux"))
    fail(`Linux 컨테이너 daemon이 필요합니다 (현재: ${os || "unknown"}).`);
  const context = run("docker", ["context", "show"], { allowFailure: true });
  const ctx = (context.stdout || "").trim();
  const endpoint = run(
    "docker",
    ["context", "inspect", ctx, "--format", "{{.Endpoints.docker.Host}}"],
    {
      allowFailure: true,
    }
  );
  const host = (endpoint.stdout || "").trim();
  if (
    host &&
    !host.startsWith("unix://") &&
    !host.includes("localhost") &&
    !host.includes("127.0.0.1")
  ) {
    fail(`원격/공유 Docker context는 차단됩니다: ${ctx}`);
  }
  run("docker", ["compose", "version"]);
  if (!existsSync(join(ROOT, "compose.yaml"))) fail("compose.yaml이 없습니다.");
  if (!existsSync(join(ROOT, "uv.lock"))) fail("uv.lock이 없습니다. uv sync를 먼저 실행하세요.");
  if (!existsSync(join(ROOT, "bun.lock")))
    fail("bun.lock이 없습니다. bun install을 먼저 실행하세요.");
  const port = composeEnv().APP_PORT;
  const probe = spawnSync("node", [
    "-e",
    `const n=require('net');const s=n.createServer();s.once('error',()=>process.exit(1));s.listen(${port},'127.0.0.1',()=>s.close());`,
  ]);
  if (probe.status !== 0) log(`⚠ 포트 ${port}이 사용 중일 수 있습니다 (앱 실행 중이면 정상).`);
  log("✓ doctor 통과");
}

function createExclusive(path, content) {
  mkdirSync(dirname(path), { recursive: true });
  try {
    const fd = openSync(path, constants.O_CREAT | constants.O_EXCL | constants.O_WRONLY, 0o600);
    writeFileSync(fd, content);
    closeSync(fd);
    return true;
  } catch (err) {
    if (err.code === "EEXIST") return false;
    throw err;
  }
}

function init() {
  const created = [];
  if (!existsSync(API_ENV)) {
    let template = readFileSync(join(ROOT, "apps/api/.env.example"), "utf8");
    for (const name of ["DB_ADMIN_PASSWORD", "DB_PASSWORD"]) {
      const pattern = new RegExp(`^${name}=.*$`, "m");
      const line = `${name}=${randomBytes(32).toString("base64url")}`;
      template = pattern.test(template)
        ? template.replace(pattern, line)
        : `${template.trimEnd()}\n${line}\n`;
    }
    if (createExclusive(API_ENV, template)) created.push("apps/api/.env");
  }
  if (!existsSync(WEB_ENV)) {
    if (createExclusive(WEB_ENV, readFileSync(join(ROOT, "apps/web/.env.example"), "utf8"))) {
      created.push("apps/web/.env");
    }
  }
  log(
    created.length
      ? `init: 생성됨 — ${created.join(", ")}`
      : "init: 기존 앱별 .env 유지 (덮어쓰기 없음)"
  );
}

function build() {
  log("up: 앱 이미지 빌드 (frozen 의존성)");
  run("docker", [...composeArgs(), "-f", "compose.build.yaml", "build", "app"]);
  const imageId = run("docker", ["image", "inspect", "gosariit-app:local", "--format", "{{.Id}}"], {
    allowFailure: true,
  });
  const manifest = {
    built_at: new Date().toISOString(),
    image_id: (imageId.stdout || "").trim(),
    source_commit: run("git", ["rev-parse", "HEAD"], { allowFailure: true }).stdout?.trim(),
    uv_lock_hash: run("git", ["hash-object", "uv.lock"], { allowFailure: true }).stdout?.trim(),
    bun_lock_hash: run("git", ["hash-object", "bun.lock"], { allowFailure: true }).stdout?.trim(),
  };
  mkdirSync(LOCAL, { recursive: true });
  writeFileSync(join(LOCAL, "build-manifest.json"), JSON.stringify(manifest, null, 2));
}

async function up() {
  acquireLock();
  try {
    init();
    doctor();
    build();
    log("up: DB 시작");
    run("docker", [...composeArgs(), "up", "-d", "--wait", "db"]);
    log("up: DB 초기화(역할·vector·migration)");
    run("docker", [...composeArgs(), "run", "--no-deps", "--rm", "db-init"]);
    log("up: 앱 시작");
    run("docker", [
      ...composeArgs(),
      "up",
      "-d",
      "--no-deps",
      "--wait",
      "--wait-timeout",
      "180",
      "app",
    ]);
    const port = composeEnv().APP_PORT;
    const ready = await waitForReadiness({ port });
    log(`✓ 준비 완료 — http://127.0.0.1:${port}`);
    log(
      `  상태: ${ready.status} · 프로필: ${ready.profile} · 외부요청: ${ready.external_requests}`
    );
    log("  개인 기록은 DB에 보관됩니다. 실행 중인 조회는 재시작 시 중단될 수 있습니다.");
  } finally {
    releaseLock();
  }
}

async function status() {
  run("docker", [...composeArgs(), "ps"]);
  const port = composeEnv().APP_PORT;
  const capabilities = await readCapabilities({ port });
  log(JSON.stringify(capabilities, null, 2));
}

function nativeUp() {
  acquireLock();
  try {
    if (!existsSync(API_ENV) || !existsSync(join(ROOT, "compose.native.yaml"))) {
      fail("apps/api/.env 및 compose.native.yaml이 필요합니다.");
    }
    const api = parseEnvFile(API_ENV);
    if (!api.DB_ADMIN_PASSWORD || !api.DB_PASSWORD) {
      fail("apps/api/.env의 기존 DB_ADMIN_PASSWORD 및 DB_PASSWORD를 유지해 설정하세요.");
    }
    run(
      "docker",
      nativeComposeArgs([
        "up",
        "-d",
        "--no-build",
        "--pull",
        "never",
        "--no-deps",
        "--wait",
        "--wait-timeout",
        "60",
        "db",
      ])
    );
    log(`✓ 네이티브 DB 준비 완료 — 127.0.0.1:${api.DB_PORT || "15432"}`);
  } finally {
    releaseLock();
  }
}

function nativeDown() {
  acquireLock();
  try {
    if (!existsSync(API_ENV) || !existsSync(join(ROOT, "compose.native.yaml"))) {
      fail("apps/api/.env 및 compose.native.yaml이 필요합니다.");
    }
    run("docker", nativeComposeArgs(["stop", "db"]));
    log("✓ 네이티브 DB 중지 — 기존 컨테이너와 데이터 볼륨 유지");
  } finally {
    releaseLock();
  }
}

function logs() {
  run("docker", [...composeArgs(), "logs", "--tail", "150", "--no-color", "app", "db"]);
}

function down() {
  acquireLock();
  try {
    log("down: 컨테이너 정리 (DB 볼륨과 개인 기록 유지)");
    run("docker", [...composeArgs(), "down", "--remove-orphans"]);
    log("✓ down 완료 — 볼륨 유지됨");
  } finally {
    releaseLock();
  }
}

function reset() {
  const confirm = process.argv.find((a) => a.startsWith("--confirm="));
  if (confirm !== `--confirm=${PROJECT}`) {
    fail(
      `reset은 공개 자료와 개인 기록을 삭제합니다. 확인하려면 --confirm=${PROJECT} 를 전달하세요.`
    );
  }
  acquireLock();
  try {
    run("docker", [...composeArgs(), "down", "--remove-orphans"]);
    run("docker", ["volume", "rm", `${PROJECT}_public_pgdata`]);
    log("✓ reset 완료 — DB 볼륨과 개인 기록 삭제됨 (앱별 .env 유지)");
  } finally {
    releaseLock();
  }
}

const command = process.argv[2];
const commands = {
  doctor,
  init,
  up,
  status,
  logs,
  down,
  reset,
  "native-up": nativeUp,
  "native-down": nativeDown,
};
if (!commands[command]) {
  fail(`사용법: node scripts/compose.mjs <${Object.keys(commands).join("|")}>`);
}
try {
  await commands[command]();
} catch (error) {
  fail(error instanceof Error ? error.message : "작업 실패");
}

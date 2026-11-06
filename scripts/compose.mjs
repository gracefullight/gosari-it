#!/usr/bin/env node
// 고사리잇 로컬 Compose orchestration (SRS 실행환경 v1.2 §5).
// POSIX 셸·명령 연결에 의존하지 않고 인자 배열로 실행한다. 비밀은 출력하지 않는다.
import { spawnSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
  openSync,
  closeSync,
  unlinkSync,
  constants,
} from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const PROJECT = "gosariit-local";
const LOCAL = join(ROOT, ".local");
const SECRETS = join(LOCAL, "secrets");
const SETTINGS = join(LOCAL, "settings.env");
const IMAGES_ENV = join(LOCAL, "images.env");
const LOCK = join(LOCAL, "compose.lock");

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
    const stderr = (result.stderr || "").slice(0, 500);
    fail(`${cmd} ${args[0] ?? ""} 실패 (exit ${result.status}): ${stderr}`);
  }
  return result;
}

function parseEnvFile(path) {
  if (!existsSync(path)) return {};
  const out = {};
  for (const line of readFileSync(path, "utf8").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq > 0) out[trimmed.slice(0, eq)] = trimmed.slice(eq + 1);
  }
  return out;
}

function composeEnv() {
  const settings = parseEnvFile(SETTINGS);
  const images = parseEnvFile(IMAGES_ENV);
  const sources = parseEnvFile(join(SECRETS, "sources.env"));
  // 원천 키는 앱 컨테이너에만 주입하고 로그/인자에 노출하지 않는다.
  return {
    GOSARI_APP_IMAGE: images.GOSARI_APP_IMAGE || "gosariit-app:local",
    GOSARI_DB_IMAGE: images.GOSARI_DB_IMAGE || "pgvector/pgvector:pg18",
    APP_PORT: settings.APP_PORT || images.APP_PORT || "8765",
    APP_PROFILE: settings.APP_PROFILE || "center",
    EXTERNAL_REQUESTS_ENABLED: settings.EXTERNAL_REQUESTS_ENABLED || "false",
    RESPONSE_CACHE_ENABLED: settings.RESPONSE_CACHE_ENABLED || "true",
    TILE_PROVIDER_CONFIG: settings.TILE_PROVIDER_CONFIG || "",
    DOMAIN_THRESHOLD_CONFIG: settings.DOMAIN_THRESHOLD_CONFIG || "",
    JEJU_PROJECT_KEY: sources.JEJU_PROJECT_KEY || "",
    KMA_SERVICE_KEY: sources.KMA_SERVICE_KEY || sources.DATA_GO_KR_SERVICE_KEY || "",
    AT_SERVICE_KEY: sources.AT_SERVICE_KEY || sources.DATA_GO_KR_SERVICE_KEY || "",
  };
}

function composeArgs(extra = []) {
  return ["compose", "-p", PROJECT, "-f", "compose.yaml", ...extra];
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
  log("doctor: Docker 엔진 확인");
  const version = run("docker", ["version", "--format", "{{.Server.Os}}/{{.Server.Arch}}"], {
    allowFailure: true,
  });
  if (version.status !== 0) fail("Docker daemon에 연결할 수 없습니다. Docker Desktop/엔진을 시작하세요.");
  const os = (version.stdout || "").trim();
  if (!os.startsWith("linux")) fail(`Linux 컨테이너 daemon이 필요합니다 (현재: ${os || "unknown"}).`);
  const context = run("docker", ["context", "show"], { allowFailure: true });
  const ctx = (context.stdout || "").trim();
  const endpoint = run("docker", ["context", "inspect", ctx, "--format", "{{.Endpoints.docker.Host}}"], {
    allowFailure: true,
  });
  const host = (endpoint.stdout || "").trim();
  if (host && !host.startsWith("unix://") && !host.includes("localhost") && !host.includes("127.0.0.1")) {
    fail(`원격/공유 Docker context는 차단됩니다: ${ctx}`);
  }
  run("docker", ["compose", "version"]);
  if (!existsSync(join(ROOT, "compose.yaml"))) fail("compose.yaml이 없습니다.");
  if (!existsSync(join(ROOT, "uv.lock"))) fail("uv.lock이 없습니다. uv sync를 먼저 실행하세요.");
  if (!existsSync(join(ROOT, "bun.lock"))) fail("bun.lock이 없습니다. bun install을 먼저 실행하세요.");
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
  mkdirSync(SECRETS, { recursive: true });
  const created = [];
  if (createExclusive(join(SECRETS, "db_admin_password"), randomBytes(32).toString("base64url")))
    created.push("db_admin_password");
  if (createExclusive(join(SECRETS, "db_app_password"), randomBytes(32).toString("base64url")))
    created.push("db_app_password");
  if (createExclusive(join(SECRETS, "openai_api_key"), "")) created.push("openai_api_key(빈 파일)");
  if (createExclusive(SETTINGS, readFileSync(join(ROOT, "deploy/settings.env.example"), "utf8")))
    created.push("settings.env");
  if (createExclusive(IMAGES_ENV, readFileSync(join(ROOT, "deploy/images.env.example"), "utf8")))
    created.push("images.env");
  log(created.length ? `init: 생성됨 — ${created.join(", ")}` : "init: 기존 파일 유지 (덮어쓰기 없음)");
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

function waitForApp(port) {
  for (let i = 0; i < 60; i++) {
    const res = spawnSync("node", [
      "-e",
      `fetch('http://127.0.0.1:${port}/api/v1/health/ready').then(r=>r.json()).then(d=>{console.log(JSON.stringify(d));process.exit(0)}).catch(()=>process.exit(1))`,
    ]);
    if (res.status === 0) return JSON.parse(res.stdout);
    spawnSync("node", ["-e", "setTimeout(()=>{},1000)"]);
  }
  fail("앱 readiness 제한 시간 초과");
}

function up() {
  acquireLock();
  try {
    doctor();
    init();
    build();
    log("up: DB 시작");
    run("docker", [...composeArgs(), "up", "-d", "--wait", "db"]);
    log("up: DB 초기화(역할·vector·migration)");
    run("docker", [
      ...composeArgs(),
      "run",
      "--no-deps",
      "--rm",
      "db-init",
    ]);
    log("up: 앱 시작");
    run("docker", [...composeArgs(), "up", "-d", "--no-deps", "--wait", "--wait-timeout", "180", "app"]);
    const port = composeEnv().APP_PORT;
    const ready = waitForApp(port);
    log(`✓ 준비 완료 — http://127.0.0.1:${port}`);
    log(`  상태: ${ready.status} · 프로필: ${ready.profile} · 외부요청: ${ready.external_requests}`);
    log("  개인 기록은 세션 한정. 이미지/설정 변경·재시작 시 세션이 소실될 수 있습니다.");
  } finally {
    releaseLock();
  }
}

function status() {
  run("docker", [...composeArgs(), "ps"]);
  const port = composeEnv().APP_PORT;
  const res = spawnSync("node", [
    "-e",
    `fetch('http://127.0.0.1:${port}/api/v1/capabilities/').then(r=>r.json()).then(d=>console.log(JSON.stringify(d,null,2))).catch(()=>console.log('앱 응답 없음'))`,
  ]);
  process.stdout.write(res.stdout || "");
}

function logs() {
  run("docker", [...composeArgs(), "logs", "--tail", "150", "--no-color", "app", "db"]);
}

function down() {
  acquireLock();
  try {
    log("down: 컨테이너 정리 (공개 DB 볼륨 유지)");
    run("docker", [...composeArgs(), "down", "--remove-orphans"]);
    log("✓ down 완료 — 볼륨 유지됨");
  } finally {
    releaseLock();
  }
}

function reset() {
  const confirm = process.argv.find((a) => a.startsWith("--confirm="));
  if (confirm !== `--confirm=${PROJECT}`) {
    fail(`reset은 공개 DB 데이터를 삭제합니다. 확인하려면 --confirm=${PROJECT} 를 전달하세요.`);
  }
  acquireLock();
  try {
    run("docker", [...composeArgs(), "down", "--remove-orphans"]);
    run("docker", ["volume", "rm", `${PROJECT}_public_pgdata`], { allowFailure: true });
    log("✓ reset 완료 — 공개 DB 볼륨 삭제됨 (비밀 유지)");
  } finally {
    releaseLock();
  }
}

const command = process.argv[2];
const commands = { doctor, init, up, status, logs, down, reset };
if (!commands[command]) {
  fail(`사용법: node scripts/compose.mjs <${Object.keys(commands).join("|")}>`);
}
commands[command]();
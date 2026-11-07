import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  chmodSync,
  copyFileSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const source = dirname(fileURLToPath(import.meta.url));

test("native DB commands reuse one project and never build, pull, initialize, or remove volumes", (t) => {
  const root = mkdtempSync(join(tmpdir(), "gosari-native-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  for (const dir of ["scripts", "apps/api", "bin"]) mkdirSync(join(root, dir), { recursive: true });
  for (const name of ["compose.mjs", "runtime-readiness.mjs"])
    copyFileSync(join(source, name), join(root, "scripts", name));
  writeFileSync(
    join(root, "apps/api/.env"),
    "DB_ADMIN_PASSWORD=synthetic-admin\nDB_PASSWORD=synthetic-app\nDB_PORT=15432\n"
  );
  for (const name of ["compose.yaml", "compose.native.yaml"])
    writeFileSync(join(root, name), "services: {}\n");
  const calls = join(root, "calls.jsonl");
  const docker = join(root, "bin/docker");
  writeFileSync(
    docker,
    [
      `#!${process.execPath}`,
      "const fs=require('node:fs');fs.appendFileSync(process.env.TEST_CALLS,JSON.stringify({args:process.argv.slice(2),port:process.env.DB_PORT,hasAdmin:!!process.env.DB_ADMIN_PASSWORD,hasApp:!!process.env.DB_PASSWORD})+String.fromCharCode(10));",
      "",
    ].join("\n")
  );
  chmodSync(docker, 0o700);
  const run = (command) =>
    spawnSync(process.execPath, [join(root, "scripts/compose.mjs"), command], {
      encoding: "utf8",
      env: { ...process.env, PATH: `${join(root, "bin")}:${process.env.PATH}`, TEST_CALLS: calls },
    });
  assert.equal(run("native-up").status, 0);
  assert.equal(run("native-down").status, 0);
  const recorded = readFileSync(calls, "utf8").trim().split("\n").map(JSON.parse);
  const prefix = [
    "compose",
    "--env-file",
    "apps/api/.env",
    "-p",
    "gosariit-local",
    "-f",
    "compose.yaml",
    "-f",
    "compose.native.yaml",
  ];
  assert.deepEqual(recorded[0].args, [
    ...prefix,
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
  ]);
  assert.deepEqual(recorded[1].args, [...prefix, "stop", "db"]);
  assert.equal(recorded[0].port, "15432");
  assert.equal(recorded[0].hasAdmin && recorded[0].hasApp, true);
  assert.equal(existsSync(join(root, ".local/compose.lock")), false);
  rmSync(join(root, "apps/api/.env"));
  assert.notEqual(run("native-up").status, 0);
  assert.equal(readFileSync(calls, "utf8").trim().split("\n").length, 2);
});

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  symlinkSync,
  utimesSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { deflateSync } from "node:zlib";
import {
  assertSafeContent,
  collectSubmission,
  createSubmission,
  normalizeArchivePath,
  REQUIRED_FILES,
  verifyArchive,
} from "../package-submission.mjs";

const FAILURES = {
  proposal: /proposal PDF/,
  symlink: /Symlink excluded/,
  duplicate: /Duplicate archive path/,
  key: /private-key/,
  content: /Sensitive content/,
  receipt: /Private receipt field/,
  python: /python3 failed/,
};

function command(root, executable, args, extra = {}) {
  const result = spawnSync(executable, args, { cwd: root, encoding: "utf8", ...extra });
  assert.equal(result.status, 0, `${executable} exited ${result.status}`);
  return result.stdout;
}
function file(root, path, content) {
  const target = join(root, path);
  mkdirSync(dirname(target), { recursive: true });
  writeFileSync(target, content);
  return target;
}
function fixture(t) {
  const root = mkdtempSync(join(tmpdir(), "gosari-submission-test-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  for (const path of REQUIRED_FILES)
    file(root, path, path.endsWith(".json") ? "{}\n" : "public fixture\n");
  file(
    root,
    ".gitignore",
    ".local/\n.env\n**/.env\nnode_modules/\n**/node_modules/\n.venv/\n**/__pycache__/\n**/dist/\n"
  );
  file(root, "apps/api/src/gosari/agent/prompts/dialogue-system.md", "Public tool instructions\n");
  file(root, "scripts/pre-push.sh", "#!/bin/sh\nexit 0\n");
  command(root, "git", ["init", "-q"]);
  command(root, "git", ["add", "."]);
  command(
    root,
    "git",
    [
      "-c",
      "core.hooksPath=/dev/null",
      "-c",
      "user.name=Fixture",
      "-c",
      "user.email=fixture@example.invalid",
      "commit",
      "-qm",
      "fixture",
    ],
    {
      env: {
        ...process.env,
        GIT_AUTHOR_DATE: "2026-11-08T00:00:00Z",
        GIT_COMMITTER_DATE: "2026-11-08T00:00:00Z",
      },
    }
  );
  return root;
}
function proposal(root, text = "Public proposal fixture") {
  const encoded = deflateSync(Buffer.from(`BT /F1 12 Tf 10 100 Td (${text}) Tj ET\n`));
  const parts = [Buffer.from("%PDF-1.4\n")];
  const offsets = [0];
  const objects = [
    Buffer.from("<< /Type /Catalog /Pages 2 0 R >>"),
    Buffer.from("<< /Type /Pages /Kids [3 0 R] /Count 1 >>"),
    Buffer.from(
      "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
    ),
    Buffer.from("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"),
    Buffer.concat([
      Buffer.from(`<< /Length ${encoded.length} /Filter /FlateDecode >>\nstream\n`),
      encoded,
      Buffer.from("\nendstream"),
    ]),
  ];
  objects.forEach((object, index) => {
    offsets.push(parts.reduce((total, part) => total + part.length, 0));
    parts.push(Buffer.from(`${index + 1} 0 obj\n`), object, Buffer.from("\nendobj\n"));
  });
  const xref = parts.reduce((total, part) => total + part.length, 0);
  parts.push(
    Buffer.from(
      `xref\n0 6\n0000000000 65535 f \n${offsets
        .slice(1)
        .map((offset) => `${String(offset).padStart(10, "0")} 00000 n \n`)
        .join("")}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`
    )
  );
  return file(root, ".local/proposal.pdf", Buffer.concat(parts));
}

test("normalizes portable paths and rejects traversal, Windows collisions, environment and key paths", () => {
  assert.equal(normalizeArchivePath("docs/제출안내.md"), "docs/제출안내.md");
  assert.equal(normalizeArchivePath("apps/api/.env.example"), "apps/api/.env.example");
  for (const path of [
    "../outside",
    "/absolute",
    "C:/outside",
    "a\\b",
    "a/./b",
    "a//b",
    "a/CON.txt",
    "a/trailing. ",
    ".qwen/settings.json",
    "apps/api/.env",
    "apps/api/src/.env.backup",
    "private.pem",
    "state.sqlite",
    "apps/web/src/node_modules/source.ts",
  ])
    assert.throws(() => normalizeArchivePath(path));
});

test("packages only allowed sources and verifies deterministic extraction without local state", (t) => {
  const root = fixture(t);
  file(root, ".qwen/settings.json", "private actor state");
  file(root, "apps/api/.env", "PRIVATE_STATE=not-a-submission\n");
  file(root, "node_modules/private.json", "private dependencies");
  file(root, "apps/web/dist/index.html", "old generated bundle");
  file(root, ".local/private.db", "SQLite format 3\0private");
  const pdf = proposal(root);
  const receipt = file(
    root,
    ".local/runtime.json",
    JSON.stringify({ source_commit: "fixture", readiness: "ready", secret_values_output: false })
  );
  const first = createSubmission({
    root,
    proposal: pdf,
    receipts: [receipt],
    output: join(root, ".local/first"),
  });
  assert.equal(first.extracted_hashes_match, true);
  assert.deepEqual(verifyArchive(first.archive), {
    status: "verified",
    source_commit: first.source_commit,
    file_count: first.file_count,
    extracted_hashes_match: true,
  });
  const manifest = JSON.parse(
    readFileSync(first.archive.replace(".zip", ".manifest.json"), "utf8")
  );
  assert.ok(manifest.files.some((entry) => entry.path === "apps/api/.env.example"));
  assert.ok(
    manifest.files.some(
      (entry) => entry.path === "apps/api/src/gosari/agent/prompts/dialogue-system.md"
    )
  );
  assert.ok(manifest.files.some((entry) => entry.path === "scripts/submission-runtime.mjs"));
  assert.ok(manifest.files.some((entry) => entry.path === "submission/proposal.pdf"));
  assert.equal(
    manifest.files.some(
      (entry) =>
        entry.path.includes(".qwen") ||
        entry.path.endsWith("/.env") ||
        entry.path.includes("node_modules") ||
        entry.path.includes("/dist/") ||
        entry.path.endsWith(".db")
    ),
    false
  );
  assert.equal(JSON.stringify(manifest).includes(root), false);
  assert.equal(Object.keys(manifest.locks).length, 3);
  utimesSync(join(root, "README.md"), new Date(0), new Date(0));
  const second = createSubmission({
    root,
    proposal: pdf,
    receipts: [receipt],
    output: join(root, ".local/second"),
  });
  assert.equal(first.archive_sha256, second.archive_sha256);
  assert.deepEqual(readFileSync(first.archive), readFileSync(second.archive));
});

test("requires a reviewed proposal for production and records dirty allowed source bytes", (t) => {
  const root = fixture(t);
  assert.throws(() => createSubmission({ root }), FAILURES.proposal);
  file(root, "README.md", "Changed public source\n");
  file(root, "apps/web/src/new-feature.ts", "export const publicValue = 1;\n");
  rmSync(join(root, "apps/api/src/gosari/agent/prompts/dialogue-system.md"));
  const { manifest } = collectSubmission({ root, requireProposal: false });
  assert.deepEqual(manifest.dirty_source_paths, [
    "README.md",
    "apps/api/src/gosari/agent/prompts/dialogue-system.md",
    "apps/web/src/new-feature.ts",
  ]);
  assert.equal(existsSync(join(root, ".local/submission-20261108")), false);
});

test("rejects symlinks and case-insensitive duplicate source paths", (t) => {
  const root = fixture(t);
  file(root, ".local/outside.py", "private\n");
  symlinkSync(
    join(root, ".local/outside.py"),
    file(root, "apps/api/src/gosari/link-target.txt", "placeholder").replace(
      "link-target.txt",
      "linked.py"
    )
  );
  assert.throws(() => collectSubmission({ root, requireProposal: false }), FAILURES.symlink);
  rmSync(join(root, "apps/api/src/gosari/linked.py"));
  file(root, "apps/web/src/NAME.ts", "one");
  command(root, "git", ["-c", "core.ignorecase=false", "add", "apps/web/src/NAME.ts"]);
  file(root, "apps/web/src/name.ts", "two");
  const blob = command(root, "git", ["hash-object", "-w", "--stdin"], { input: "two" }).trim();
  command(root, "git", [
    "-c",
    "core.ignorecase=false",
    "update-index",
    "--add",
    "--cacheinfo",
    `100644,${blob},apps/web/src/name.ts`,
  ]);
  assert.throws(() => collectSubmission({ root, requireProposal: false }), FAILURES.duplicate);
});

test("rejects secret material in source and extracted PDF text without exposing its value", (t) => {
  const root = fixture(t);
  const canary = ["sk-", "X".repeat(48)].join("");
  assert.doesNotThrow(() =>
    assertSafeContent(
      "apps/api/.env.example",
      Buffer.from("OPENAI_API_KEY=\nJEJU_PROJECT_KEY=\nDB_ADMIN_PASSWORD=\nDB_PASSWORD=\n")
    )
  );
  assert.throws(
    () => assertSafeContent("README.md", Buffer.from(canary)),
    (error) => !error.message.includes(canary)
  );
  assert.throws(
    () =>
      assertSafeContent(
        "receipt.json",
        Buffer.from(`https://example.invalid/?serviceKey=${"X".repeat(32)}`)
      ),
    FAILURES.content
  );
  assert.doesNotThrow(() =>
    assertSafeContent(
      "apps/api/tests/test_public_acceptance.py",
      Buffer.from(
        "https://open.jejudatahub.net/api/proxy/dataset/AUDIT_FAKE_KEY_20261107?token=also_fake"
      )
    )
  );
  const privateHeader = ["-----BEGIN ", "PRIVATE KEY-----"].join("");
  assert.throws(() => assertSafeContent("README.md", Buffer.from(privateHeader)), FAILURES.key);
  const pdf = proposal(root, canary);
  assert.equal(readFileSync(pdf).includes(Buffer.from(canary)), false);
  assert.throws(() => collectSubmission({ root, proposal: pdf }), FAILURES.content);
});

test("rejects private receipt payloads and duplicate receipt names", (t) => {
  const root = fixture(t);
  const pdf = proposal(root);
  const privateReceipt = file(
    root,
    ".local/private.json",
    JSON.stringify({ environment: { DB_PASSWORD: "synthetic" } })
  );
  assert.throws(
    () => collectSubmission({ root, proposal: pdf, receipts: [privateReceipt] }),
    FAILURES.receipt
  );
  const first = file(root, ".local/one/result.json", '{"status":"ready"}');
  const second = file(root, ".local/two/result.json", '{"status":"ready"}');
  assert.throws(
    () => collectSubmission({ root, proposal: pdf, receipts: [first, second] }),
    FAILURES.duplicate
  );
});

test("rejects a malicious ZIP path before extraction", (t) => {
  const root = fixture(t);
  const archive = join(root, "malicious.zip");
  command(root, "python3", [
    "-c",
    "import hashlib,json,sys,zipfile;name='../escape';data=b'bad';m={'source_commit':'fixture','files':[{'path':name,'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}]};z=zipfile.ZipFile(sys.argv[1],'w');z.writestr(name,data);z.writestr('SUBMISSION_MANIFEST.json',json.dumps(m));z.close()",
    archive,
  ]);
  assert.throws(() => verifyArchive(archive), FAILURES.python);
  assert.equal(existsSync(join(root, "escape")), false);
});

test("rejects a member changed after its manifest was written", (t) => {
  const root = fixture(t);
  const archive = join(root, "tampered.zip");
  command(root, "python3", [
    "-c",
    "import hashlib,json,sys,zipfile;name='README.md';m={'source_commit':'fixture','files':[{'path':name,'size':3,'sha256':hashlib.sha256(b'old').hexdigest(),'mode':'0644'}]};z=zipfile.ZipFile(sys.argv[1],'w');z.writestr(name,b'new');z.writestr('SUBMISSION_MANIFEST.json',json.dumps(m));z.close()",
    archive,
  ]);
  assert.throws(() => verifyArchive(archive), FAILURES.python);
});

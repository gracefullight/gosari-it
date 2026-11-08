import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { gitBlobHash, readBuildIdentity } from "../build-identity.mjs";

const LOCK_MISMATCH = /uv\.lock/;
const SOURCE_INFORMATION = /소스 정보/;

function archive(t, change = (value) => value) {
  const root = mkdtempSync(join(tmpdir(), "gosari-identity-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const files = ["uv.lock", "bun.lock"].map((path) => {
    const bytes = Buffer.from(`${path} frozen\n`);
    writeFileSync(join(root, path), bytes);
    return { path, sha256: createHash("sha256").update(bytes).digest("hex") };
  });
  const manifest = change({ source_commit: "a".repeat(40), files });
  writeFileSync(join(root, "SUBMISSION_MANIFEST.json"), JSON.stringify(manifest));
  return root;
}

test("source ZIP retains commit and Git-compatible lock hashes without .git", (t) => {
  const result = readBuildIdentity(archive(t));
  assert.equal(result.source_commit, "a".repeat(40));
  assert.equal(result.source_provenance, "submission-manifest");
  assert.equal(result.uv_lock_hash, gitBlobHash(Buffer.from("uv.lock frozen\n")));
  assert.equal(gitBlobHash(Buffer.from("hello\n")), "ce013625030ba8dba906f756967f9e9ca394464a");
});

test("a changed lock file rejects the archived identity", (t) => {
  const root = archive(t);
  writeFileSync(join(root, "uv.lock"), "changed");
  assert.throws(() => readBuildIdentity(root), LOCK_MISMATCH);
});

test("missing or duplicate lock metadata cannot claim a matching archive", (t) => {
  const missing = archive(t, (m) => ({ ...m, files: m.files.slice(1) }));
  assert.throws(() => readBuildIdentity(missing), LOCK_MISMATCH);
  const duplicate = archive(t, (m) => ({ ...m, files: [...m.files, m.files[0]] }));
  assert.throws(() => readBuildIdentity(duplicate), LOCK_MISMATCH);
});

test("malformed archive commit does not fall through to a containing Git repo", (t) => {
  assert.throws(
    () => readBuildIdentity(archive(t, (m) => ({ ...m, source_commit: "unknown" }))),
    SOURCE_INFORMATION
  );
});

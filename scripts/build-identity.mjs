import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

const COMMIT_PATTERN = /^[a-f0-9]{40,64}$/;

export function gitBlobHash(bytes) {
  return createHash("sha1").update(`blob ${bytes.length}\0`).update(bytes).digest("hex");
}

export function readBuildIdentity(root) {
  const locks = new Map(
    ["uv.lock", "bun.lock"].map((name) => [name, readFileSync(join(root, name))])
  );
  const manifestPath = join(root, "SUBMISSION_MANIFEST.json");
  let commit = null;
  let provenance = "unversioned";
  if (existsSync(manifestPath)) {
    const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
    if (!COMMIT_PATTERN.test(manifest.source_commit || "") || !Array.isArray(manifest.files)) {
      throw new Error("제출 매니페스트의 소스 정보를 확인할 수 없습니다.");
    }
    for (const [name, bytes] of locks) {
      const matches = manifest.files.filter((file) => file.path === name);
      const digest = createHash("sha256").update(bytes).digest("hex");
      if (matches.length !== 1 || matches[0].sha256 !== digest) {
        throw new Error(`제출 매니페스트와 잠금 파일이 다릅니다: ${name}`);
      }
    }
    commit = manifest.source_commit;
    provenance = "submission-manifest";
  } else {
    const result = spawnSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" });
    if (result.status === 0) {
      commit = result.stdout.trim();
      provenance = "git";
    }
  }
  return {
    source_commit: commit,
    source_provenance: provenance,
    uv_lock_hash: gitBlobHash(locks.get("uv.lock")),
    bun_lock_hash: gitBlobHash(locks.get("bun.lock")),
    lock_hash_algorithm: "git-blob-sha1",
  };
}

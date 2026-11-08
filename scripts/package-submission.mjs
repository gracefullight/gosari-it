#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  existsSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  realpathSync,
  renameSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { basename, dirname, extname, isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { inflateSync } from "node:zlib";

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const EXACT = new Set([
  ".dockerignore",
  ".gitignore",
  "LICENSE",
  "README.md",
  "DESIGN.md",
  "package.json",
  "bun.lock",
  "pyproject.toml",
  "uv.lock",
  "mise.toml",
  "mise.lock",
  "hk.pkl",
  "biome.json",
  "commitlint.config.cjs",
  "compose.yaml",
  "compose.build.yaml",
  "compose.native.yaml",
  "deploy/Dockerfile",
  "deploy/images.env.example",
  "deploy/settings.env.example",
  "apps/api/.env.example",
  "apps/api/README.md",
  "apps/api/pyproject.toml",
  "apps/api/mise.toml",
  "apps/api/ruff.toml",
  "apps/api/alembic.ini",
  "apps/api/openapi.json",
  "apps/api/docker-compose.infra.yml",
  "apps/web/.env.example",
  "apps/web/components.json",
  "apps/web/index.html",
  "apps/web/mise.toml",
  "apps/web/orval.config.ts",
  "apps/web/package.json",
  "apps/web/tsconfig.json",
  "apps/web/vite.config.ts",
  "apps/web/vitest.config.mts",
  "scripts/compose.mjs",
  "scripts/runtime-readiness.mjs",
  "scripts/submission-runtime.mjs",
  "scripts/build-identity.mjs",
  "scripts/tests/build-identity.test.mjs",
  "scripts/render-proposal-report.py",
  "scripts/check-changed.py",
  "scripts/pre-push.sh",
  "scripts/compose-native.test.mjs",
  "scripts/runtime-readiness.test.mjs",
  "scripts/package-submission.mjs",
  "scripts/tests/package-submission.test.mjs",
  "docs/adapter-manual.md",
  "docs/agent-runtime.md",
  "docs/architecture.md",
  "docs/data-usage.md",
  "docs/install-manual.md",
  "docs/submission-checklist.md",
  "docs/submission-results.md",
  "docs/user-manual.md",
  "docs/ai-and-dependencies.md",
  "docs/proposal/제주고사리_AI_Agent_개발기획서_v0.21.md",
  "docs/proposal/assets/제주고사리_정보구조_IA_v0.21.svg",
  "docs/proposal/assets/제주고사리_시스템구조도_v0.21.svg",
  "docs/proposal/assets/제주고사리_에이전트흐름도_v0.21.svg",
  "docs/proposal/assets/고사리잇_제목아이콘_64.png",
  "docs/proposal/assets/고사리잇_고사리캐릭터_256.png",
  "docs/verification/submission-20261108.json",
  "docs/verification/cache-20261108.json",
  "docs/verification/load-20261108.json",
  "fixtures/aT_고사리정산_시장별_봄_표본검증.csv",
  "fixtures/기상청_ASOS_제주184_2026봄_61일_표추출.csv",
  "fixtures/기상청_제주_당일관측_20261105_1843KST_검증.csv",
  "fixtures/제주산_고사리_상품표시가_검증.json",
  "fixtures/제주허브_579_선흘_2023-2024봄_호출검증.csv",
]);
const DIRECTORIES = [
  ["apps/api/src/", new Set([".py", ".md", ".json"])],
  ["apps/api/alembic/", new Set([".py", ".mako"])],
  ["apps/api/scripts/", new Set([".py"])],
  ["apps/api/tests/", new Set([".py"])],
  ["apps/web/src/", new Set([".ts", ".tsx", ".css", ".svg", ".png", ".jpg", ".jpeg", ".woff2"])],
  ["apps/web/public/", new Set([".svg", ".png", ".ico", ".webmanifest", ".woff2"])],
];
export const REQUIRED_FILES = [
  "README.md",
  "package.json",
  "bun.lock",
  "pyproject.toml",
  "uv.lock",
  "mise.toml",
  "mise.lock",
  "compose.yaml",
  "compose.build.yaml",
  "compose.native.yaml",
  "deploy/Dockerfile",
  "apps/api/.env.example",
  "apps/web/.env.example",
  "apps/api/src/gosari/app.py",
  "apps/web/src/main.tsx",
  "scripts/compose.mjs",
  "scripts/runtime-readiness.mjs",
  "scripts/submission-runtime.mjs",
  "scripts/build-identity.mjs",
  "scripts/render-proposal-report.py",
  "scripts/package-submission.mjs",
  "docs/install-manual.md",
  "docs/submission-checklist.md",
  "docs/user-manual.md",
  "docs/ai-and-dependencies.md",
  "docs/submission-results.md",
  "docs/proposal/제주고사리_AI_Agent_개발기획서_v0.21.md",
  ...[...EXACT].filter((name) => name.startsWith("fixtures/")),
];
const BLOCKED_SEGMENTS = new Set([
  ".git",
  ".agents",
  ".qwen",
  ".claude",
  ".codex",
  ".cursor",
  ".serena",
  ".local",
  "node_modules",
  ".venv",
  "venv",
  "__pycache__",
  "dist",
  "coverage",
  ".cache",
  ".pytest_cache",
  ".ruff_cache",
]);
const PRIVATE_EXTENSION = /\.(?:db|sqlite\d*|dump|pem|key|p12|pfx|keystore|log)$/i;
const UNSAFE_PATH_CHARACTERS = /[\\<>:"|?*]/;
const TRAILING_PATH_CHARACTER = /[. ]$/;
const ASCII85_START = /^<~/;
const ASCII85_END = /~>$/;
const PDF_FLATE = /\/FlateDecode\b/;
const PDF_ASCII85 = /\/ASCII85Decode\b/;
const PRIVATE_RECEIPT_FIELD =
  /^(?:env|environment|session_id|activity_text|companion_aliases|recipient_alias|phone|email|latitude|longitude)$/i;
const CREDENTIAL_RECEIPT_FIELD =
  /^(?:.*_)?(?:api_key|service_key|project_key|password|secret|authorization|dsn)$/i;
const REDACTED_VALUE = /^\[REDACTED\]$/i;
const RESERVED_WINDOWS = /^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i;
const CREDENTIAL_PATTERNS = [
  ["private-key", /-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----/],
  ["openai-token", /\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{40,}\b/],
  ["github-token", /\bgh[pousr]_[A-Za-z0-9]{36,}\b/],
  ["aws-access-key", /\bAKIA[A-Z0-9]{16}\b/],
  [
    "authenticated-url",
    /[?&](?:serviceKey|apiKey|authKey|projectKey|access_token|token)=[A-Za-z0-9_+/%=-]{20,}/i,
  ],
  [
    "private-dataset-url",
    /api\/proxy\/dataset\/(?!AUDIT_FAKE_KEY_20261107(?:[?/#"'\s]|$))[A-Za-z0-9_-]{20,}/i,
  ],
  [
    "credential-assignment",
    /(?:OPENAI_API_KEY|JEJU_PROJECT_KEY|KMA_SERVICE_KEY|KMA_HUB_KEY|AT_SERVICE_KEY|VWORLD_API_KEY|DB_ADMIN_PASSWORD|DB_PASSWORD)["']?[ \t]*[:=][ \t]*["']?[A-Za-z0-9_+/%=-]{24,}/,
  ],
];
const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");
function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    encoding: "utf8",
    maxBuffer: 32 * 1024 * 1024,
    ...options,
  });
  if (result.error || result.status !== 0)
    throw new Error(`${command} failed (${result.status ?? result.error?.code ?? "unknown"})`);
  return result.stdout;
}

export function normalizeArchivePath(name) {
  if (
    typeof name !== "string" ||
    !name ||
    isAbsolute(name) ||
    UNSAFE_PATH_CHARACTERS.test(name) ||
    [...name].some((character) => character.codePointAt(0) < 32 || character.codePointAt(0) === 127)
  )
    throw new Error("Unsafe archive path");
  const normalized = name.normalize("NFC");
  const parts = normalized.split("/");
  if (
    parts.some(
      (part) =>
        !part ||
        part === "." ||
        part === ".." ||
        TRAILING_PATH_CHARACTER.test(part) ||
        RESERVED_WINDOWS.test(part)
    )
  )
    throw new Error("Unsafe archive path");
  if (
    parts.some(
      (part) =>
        BLOCKED_SEGMENTS.has(part.toLowerCase()) ||
        (part.toLowerCase().startsWith(".env") && part !== ".env.example")
    ) ||
    PRIVATE_EXTENSION.test(normalized)
  )
    throw new Error(`Excluded artifact: ${normalized}`);
  return normalized;
}
function isAllowed(name) {
  return (
    EXACT.has(name) ||
    DIRECTORIES.some(
      ([prefix, extensions]) => name.startsWith(prefix) && extensions.has(extname(name))
    )
  );
}
export function assertSafeContent(name, bytes) {
  const text = bytes.toString("utf8");
  if (text.startsWith("SQLite format 3\0") || text.startsWith("PGDMP"))
    throw new Error(`Database content excluded: ${name}`);
  for (const [kind, pattern] of CREDENTIAL_PATTERNS)
    if (pattern.test(text)) throw new Error(`Sensitive content (${kind}) in ${name}`);
}
function decodeAscii85(bytes) {
  const text = bytes
    .toString("ascii")
    .replace(/\s/g, "")
    .replace(ASCII85_START, "")
    .replace(ASCII85_END, "");
  const output = [];
  let group = [];
  const flush = () => {
    const count = group.length;
    while (group.length < 5) group.push(84);
    const value = group.reduce((sum, digit) => sum * 85 + digit, 0);
    const word = Buffer.alloc(4);
    word.writeUInt32BE(value >>> 0);
    output.push(word.subarray(0, count - 1));
    group = [];
  };
  for (const character of text) {
    if (character === "z" && !group.length) {
      output.push(Buffer.alloc(4));
      continue;
    }
    const digit = character.charCodeAt(0) - 33;
    if (digit < 0 || digit > 84) throw new Error("Invalid ASCII85 proposal stream");
    group.push(digit);
    if (group.length === 5) flush();
  }
  if (group.length) flush();
  return Buffer.concat(output);
}
function inspectPdfStreams(name, bytes) {
  const text = bytes.toString("latin1");
  const streams = /\bstream\r?\n/g;
  for (const match of text.matchAll(streams)) {
    const start = match.index + match[0].length;
    const end = text.indexOf("endstream", start);
    if (end < 0) throw new Error("Incomplete proposal stream");
    const dictionary = text.slice(Math.max(0, text.lastIndexOf("obj", match.index)), match.index);
    if (!PDF_FLATE.test(dictionary)) continue;
    let decoded = bytes.subarray(start, end);
    try {
      if (PDF_ASCII85.test(dictionary)) decoded = decodeAscii85(decoded);
      decoded = inflateSync(decoded);
    } catch {
      throw new Error("Cannot inspect compressed proposal stream");
    }
    assertSafeContent(name, decoded);
  }
}
function safeSource(root, name) {
  let current = root;
  for (const part of name.split("/")) {
    current = join(current, part);
    if (lstatSync(current).isSymbolicLink()) throw new Error(`Symlink excluded: ${name}`);
  }
  if (!lstatSync(current).isFile()) throw new Error(`Not a regular file: ${name}`);
  return current;
}
function receiptPrivacy(value, name) {
  if (!value || typeof value !== "object") return;
  for (const [key, item] of Object.entries(value)) {
    if (PRIVATE_RECEIPT_FIELD.test(key) && item != null && item !== "")
      throw new Error(`Private receipt field excluded: ${name}`);
    if (
      CREDENTIAL_RECEIPT_FIELD.test(key) &&
      typeof item === "string" &&
      item &&
      !REDACTED_VALUE.test(item)
    )
      throw new Error(`Credential receipt field excluded: ${name}`);
    receiptPrivacy(item, name);
  }
}

export function collectSubmission({
  root = ROOT,
  proposal,
  receipts = [],
  video,
  requireProposal = true,
}) {
  root = realpathSync(root);
  const git = (args) => run("git", args, { cwd: root }).trim();
  const commit = git(["rev-parse", "HEAD"]);
  const epoch = Number(git(["show", "-s", "--format=%ct", "HEAD"]));
  const inventory = run("git", ["ls-files", "-z", "--cached", "--others", "--exclude-standard"], {
    cwd: root,
  })
    .split("\0")
    .filter(Boolean);
  const files = [];
  const seen = new Set();
  const add = (name, source, kind = "source") => {
    name = normalizeArchivePath(name);
    const identity = name.toLowerCase();
    if (seen.has(identity)) throw new Error(`Duplicate archive path: ${name}`);
    seen.add(identity);
    const bytes = readFileSync(source);
    assertSafeContent(name, bytes);
    if (kind === "receipt" || name === "docs/verification/submission-20261108.json") {
      let value;
      try {
        value = JSON.parse(bytes.toString("utf8"));
      } catch {
        throw new Error(`Invalid reviewed JSON: ${name}`);
      }
      receiptPrivacy(value, name);
    }
    if (kind === "proposal") {
      if (!bytes.subarray(0, 5).equals(Buffer.from("%PDF-")))
        throw new Error("Proposal must be a PDF");
      inspectPdfStreams(name, bytes);
      const text = run("pdftotext", ["-enc", "UTF-8", source, "-"], {
        maxBuffer: 32 * 1024 * 1024,
      });
      assertSafeContent(name, Buffer.from(text));
    }
    files.push({
      path: name,
      bytes,
      sha256: sha256(bytes),
      size: bytes.length,
      mode: name.endsWith(".sh") ? "0755" : "0644",
      kind,
    });
  };
  for (const raw of inventory) {
    const normalized = raw.normalize("NFC");
    if (!isAllowed(normalized)) continue;
    normalizeArchivePath(normalized);
    if (!existsSync(join(root, raw))) continue;
    add(normalized, safeSource(root, raw));
  }
  for (const name of REQUIRED_FILES)
    if (!files.some((file) => file.path === name))
      throw new Error(`Missing submission input: ${name}`);
  if (requireProposal && !proposal)
    throw new Error("A reviewed proposal PDF is required (--proposal)");
  if (proposal) add("submission/proposal.pdf", realpathSync(proposal), "proposal");
  for (const receipt of receipts) {
    if (extname(receipt).toLowerCase() !== ".json")
      throw new Error("Receipts must be reviewed JSON files");
    add(`submission/receipts/${basename(receipt)}`, realpathSync(receipt), "receipt");
  }
  if (video) {
    if (![".mp4", ".webm", ".mov"].includes(extname(video).toLowerCase()))
      throw new Error("Unsupported demonstration video format");
    add(`submission/demo${extname(video).toLowerCase()}`, realpathSync(video), "video");
  }
  files.sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
  const changed = run("git", ["diff", "--name-only", "-z", "HEAD"], { cwd: root })
    .split("\0")
    .filter((name) => name && isAllowed(name.normalize("NFC")))
    .map((name) => name.normalize("NFC"));
  const untracked = run("git", ["ls-files", "-z", "--others", "--exclude-standard"], { cwd: root })
    .split("\0")
    .filter((name) => name && isAllowed(name.normalize("NFC")))
    .map((name) => name.normalize("NFC"));
  const manifest = {
    schema_version: "gosari-submission-v1",
    source_commit: commit,
    source_tree: git(["rev-parse", "HEAD^{tree}"]),
    source_date_utc: new Date(epoch * 1000).toISOString(),
    archive_format: "ZIP_STORED; sorted NFC paths; fixed UTC commit timestamp; fixed file modes",
    dirty_source_paths: [...new Set([...changed, ...untracked])].sort(),
    locks: Object.fromEntries(
      ["bun.lock", "uv.lock", "mise.lock"].map((name) => [
        name,
        files.find((file) => file.path === name).sha256,
      ])
    ),
    files: files.map(({ bytes, ...entry }) => entry),
  };
  return { root, epoch, files, manifest };
}

const ZIP_WRITER = `
import datetime,json,pathlib,shutil,stat,sys,zipfile
p=json.load(sys.stdin)
when=datetime.datetime.fromtimestamp(max(p['epoch'],315532800),datetime.timezone.utc)
stamp=(when.year,when.month,when.day,when.hour,when.minute,when.second//2*2)
with zipfile.ZipFile(p['archive'],'w',compression=zipfile.ZIP_STORED,allowZip64=True) as z:
 for f in p['files']:
  info=zipfile.ZipInfo(f['path'],stamp)
  info.create_system=3
  info.external_attr=(stat.S_IFREG|int(f['mode'],8))<<16
  info.compress_type=zipfile.ZIP_STORED
  info.file_size=f['size']
  with open(f['source'],'rb') as source,z.open(info,'w',force_zip64=f['size']>=2**31) as dest:
   shutil.copyfileobj(source,dest,1024*1024)
`;
const ZIP_VERIFIER = String.raw`
import hashlib,json,os,pathlib,re,stat,sys,tempfile,unicodedata,zipfile
archive=sys.argv[1]
with zipfile.ZipFile(archive) as z,tempfile.TemporaryDirectory(prefix='gosari-unpack-') as temp:
 names=z.namelist()
 if len(names)!=len({unicodedata.normalize('NFC',n).casefold() for n in names}):raise ValueError('Duplicate ZIP members')
 manifest=json.loads(z.read('SUBMISSION_MANIFEST.json'))
 expected={f['path']:f for f in manifest['files']}
 if set(names)!=set(expected)|{'SUBMISSION_MANIFEST.json'}:raise ValueError('Manifest member mismatch')
 for info in z.infolist():
  name=info.filename
  if '\\' in name or name.startswith('/') or any(p in ('','..','.') for p in name.split('/')):raise ValueError('Unsafe ZIP member')
  parts=name.split('/')
  if unicodedata.normalize('NFC',name)!=name or re.search(r'[\x00-\x1f\x7f<>:"|?*]',name):raise ValueError('Unsafe ZIP member')
  if any(p.endswith(('.', ' ')) or re.match(r'^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)',p,re.I) for p in parts):raise ValueError('Unsafe Windows member')
  if any(p.lower() in {'.git','.agents','.qwen','.claude','.codex','.cursor','.serena','.local','node_modules','.venv','venv','__pycache__','dist','coverage','.cache','.pytest_cache','.ruff_cache'} or (p.startswith('.env') and p!='.env.example') for p in parts):raise ValueError('Excluded ZIP member')
  if re.search(r'\.(db|sqlite\d*|dump|pem|key|p12|pfx|keystore|log)$',name,re.I):raise ValueError('Excluded ZIP extension')
  if stat.S_ISLNK(info.external_attr>>16):raise ValueError('ZIP symlink excluded')
  if name=='SUBMISSION_MANIFEST.json':continue
  actual=z.read(name);f=expected[name]
  if len(actual)!=f['size'] or hashlib.sha256(actual).hexdigest()!=f['sha256']:raise ValueError('Member integrity mismatch')
  if stat.S_IMODE(info.external_attr>>16)!=int(f['mode'],8):raise ValueError('Member mode mismatch')
  target=pathlib.Path(temp).joinpath(*name.split('/'));target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(actual)
  target.chmod(int(f['mode'],8))
  if os.name!='nt' and stat.S_IMODE(target.stat().st_mode)!=int(f['mode'],8):raise ValueError('Extraction mode mismatch')
  if hashlib.sha256(target.read_bytes()).hexdigest()!=f['sha256']:raise ValueError('Extraction integrity mismatch')
 print(json.dumps({'status':'verified','source_commit':manifest['source_commit'],'file_count':len(expected),'extracted_hashes_match':True}))
`;
export function verifyArchive(archive) {
  const raw = run("python3", ["-c", ZIP_VERIFIER, resolve(archive)]);
  return JSON.parse(raw);
}
export function createSubmission(options) {
  const plan = collectSubmission(options);
  const requestedRoot = resolve(options.root ?? ROOT);
  const requestedOutput = resolve(requestedRoot, options.output ?? ".local/submission-20261108");
  const output = resolve(plan.root, relative(requestedRoot, requestedOutput));
  const outputRelative = relative(join(plan.root, ".local"), output);
  if (outputRelative.startsWith("..") || isAbsolute(outputRelative))
    throw new Error("Submission output must stay under .local");
  let destination = plan.root;
  for (const part of relative(plan.root, output).split("/")) {
    destination = join(destination, part);
    if (existsSync(destination) && lstatSync(destination).isSymbolicLink())
      throw new Error("Submission output cannot use a symlink");
  }
  mkdirSync(output, { recursive: true });
  const staging = mkdtempSync(join(output, ".package-"));
  const name = `gosari-it-${plan.manifest.source_commit.slice(0, 7)}`;
  const archive = join(output, `${name}.zip`);
  const temporaryArchive = join(staging, `${name}.zip`);
  try {
    const sources = plan.files.map((file, index) => {
      const source = join(staging, String(index));
      writeFileSync(source, file.bytes, { mode: 0o600 });
      return { ...file, bytes: undefined, source };
    });
    const manifestBytes = Buffer.from(`${JSON.stringify(plan.manifest, null, 2)}\n`);
    const manifestSource = join(staging, "manifest.json");
    writeFileSync(manifestSource, manifestBytes, { mode: 0o600 });
    sources.push({
      path: "SUBMISSION_MANIFEST.json",
      source: manifestSource,
      size: manifestBytes.length,
      mode: "0644",
    });
    sources.sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
    run("python3", ["-c", ZIP_WRITER], {
      input: JSON.stringify({ epoch: plan.epoch, archive: temporaryArchive, files: sources }),
    });
    const verification = verifyArchive(temporaryArchive);
    renameSync(temporaryArchive, archive);
    writeFileSync(join(output, `${name}.manifest.json`), manifestBytes);
    const digest = sha256(readFileSync(archive));
    writeFileSync(join(output, `${name}.sha256`), `${digest}  ${basename(archive)}\n`);
    const result = {
      ...verification,
      archive,
      archive_sha256: digest,
      dirty_source_paths: plan.manifest.dirty_source_paths,
    };
    writeFileSync(
      join(output, `${name}.verification.json`),
      `${JSON.stringify(result, null, 2)}\n`
    );
    return result;
  } finally {
    rmSync(staging, { recursive: true, force: true });
  }
}
export function main(args = process.argv.slice(2)) {
  const options = { receipts: [] };
  let dryRun = false;
  for (let index = 0; index < args.length; index++) {
    const argument = args[index];
    if (argument === "--dry-run") {
      dryRun = true;
      continue;
    }
    if (argument === "--verify") {
      if (args.length !== 2 || !args[index + 1]) throw new Error("Usage: --verify archive.zip");
      return verifyArchive(args[index + 1]);
    }
    if (!["--output", "--proposal", "--receipt", "--video"].includes(argument) || !args[index + 1])
      throw new Error(
        "Usage: [--dry-run] [--output .local/path] --proposal reviewed.pdf [--receipt reviewed.json] [--video demo.mp4]"
      );
    if (argument === "--receipt") options.receipts.push(args[++index]);
    else options[argument.slice(2)] = args[++index];
  }
  if (dryRun) {
    const { manifest } = collectSubmission({ ...options, requireProposal: false });
    return { dry_run: true, proposal_provided: Boolean(options.proposal), ...manifest };
  }
  return createSubmission(options);
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    process.stdout.write(`${JSON.stringify(main(), null, 2)}\n`);
  } catch (error) {
    process.stderr.write(`Submission failed: ${error.message}\n`);
    process.exitCode = 1;
  }
}

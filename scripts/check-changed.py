#!/usr/bin/env python3
"""Check changed paths and related tests; never expand to an entire app suite."""

import ast
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode().split("\0")


def run(args, cwd=ROOT, *, env=None):
    print("[changed]", " ".join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=cwd, env=env, check=True)


def api_tests(paths):
    files = {
        p
        for p in git("ls-files", "-z") + list(paths)
        if p.endswith(".py") and (ROOT / p).is_file()
    }
    modules = {}
    for path in files | set(paths):
        if path.startswith("apps/api/src/") and path.endswith(".py"):
            name = (
                path.removeprefix("apps/api/src/").removesuffix(".py").replace("/", ".")
            )
            modules[name.removesuffix(".__init__")] = path
    dependencies = {}
    for path in files:
        if not path.startswith("apps/api/"):
            continue
        names = set()
        for node in ast.walk(ast.parse((ROOT / path).read_text(), filename=path)):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
                names.update(f"{node.module}.{alias.name}" for alias in node.names)
        dependencies[path] = set()
        for name in names:
            while name and name not in modules:
                name = name.rpartition(".")[0]
            if name:
                dependencies[path].add(name)
    impacted = {module for module, path in modules.items() if path in paths}
    # Direct imports only: a shared app import must not expand to the whole suite.
    return sorted(
        path
        for path in files
        if path.startswith("apps/api/tests/test_")
        and (path in paths or dependencies.get(path, set()) & impacted)
    )


def main():
    kind, base = sys.argv[1:3]
    # Unavailable history is an error, never an excuse to run everything or pass silently.
    subprocess.run(
        ["git", "rev-parse", "--verify", base],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    untracked = set(
        filter(None, git("ls-files", "--others", "--exclude-standard", "-z"))
    )
    paths = set(
        filter(None, git("diff", "--name-only", "--diff-filter=ACDMR", "-z", base))
    )
    paths.update(
        filter(
            None, git("diff", "--cached", "--name-only", "--diff-filter=ACDMR", "-z")
        )
    )
    paths.update(filter(None, git("diff", "--name-only", "--diff-filter=ACDMR", "-z")))
    paths.update(untracked)
    if kind == "api":
        changed = sorted(
            path
            for path in paths
            if path.startswith("apps/api/") and path.endswith(".py")
        )
        tests = api_tests(paths) if changed else []
        if "--list" in sys.argv:
            print("\n".join(tests))
            return
        if changed:
            existing = [path for path in changed if (ROOT / path).is_file()]
            if existing:
                run([ROOT / ".venv/bin/ruff", "check", "--no-fix", *existing])
                run([ROOT / ".venv/bin/ruff", "format", "--check", *existing])
            if not tests:
                raise SystemExit(
                    "No related API tests identified; select focused tests explicitly instead of running all tests."
                )
            test_environment = {
                **os.environ,
                "PYTHONPATH": str(ROOT / "apps/api/src"),
                "OPENAI_API_KEY": "",
                "OPENAI_API_KEY_FILE": "",
            }
            run(
                [ROOT / ".venv/bin/python", "-m", "pytest", *tests, "-q"],
                env=test_environment,
            )
        else:
            print("[changed] api: no changed Python paths; no tests run.")
    elif kind == "web":
        app = ROOT / "apps/web"
        changed = sorted(
            path.removeprefix("apps/web/")
            for path in paths
            if path.startswith("apps/web/")
            and path.endswith((".ts", ".tsx", ".js", ".jsx"))
        )
        if "--list" in sys.argv:
            print("\n".join(changed))
            return
        run(
            [
                ROOT / "apps/web/node_modules/.bin/biome",
                "check",
                "--changed",
                f"--since={base}",
                "--no-errors-on-unmatched",
                "--error-on-warnings",
                "apps/web",
            ],
            ROOT,
        )
        dirty = (
            untracked
            | set(filter(None, git("diff", "--cached", "--name-only", "-z")))
            | set(filter(None, git("diff", "--name-only", "-z")))
        )
        extra = sorted(
            path
            for path in dirty
            if path.startswith("apps/web/") and (ROOT / path).is_file()
        )
        if extra:
            run(
                [
                    ROOT / "apps/web/node_modules/.bin/biome",
                    "check",
                    "--no-errors-on-unmatched",
                    "--error-on-warnings",
                    *extra,
                ],
                ROOT,
            )
        if changed:
            run(
                [
                    ROOT / "apps/web/node_modules/.bin/vitest",
                    "related",
                    "--run",
                    "--passWithNoTests",
                    *changed,
                ],
                app,
            )
        else:
            print("[changed] web: no changed JS/TS inputs; no tests run.")
    else:
        raise SystemExit(f"Unknown changed check: {kind}")


if __name__ == "__main__":
    main()

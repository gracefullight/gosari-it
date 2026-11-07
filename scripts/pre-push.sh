#!/usr/bin/env bash
# Pre-push entry. hk.pkl lists the gates. This file caches a clean pass by
# the git tree of the paths that gate reads.
#
#   scripts/pre-push.sh
#   scripts/pre-push.sh gate api
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

CACHE_DIR="$(cd "$(git rev-parse --git-common-dir)" && pwd)/pre-push-cache"
mkdir -p "$CACHE_DIR"

cached_gate() {
  local name=$1 deps=$2
  shift 2
  local key marker dirty
  git rev-parse --verify "${CHECK_BASE:-origin/main}" >/dev/null
  # A clean HEAD cache must never hide newly staged/unstaged/untracked inputs.
  # shellcheck disable=SC2086
  dirty="$(git status --porcelain -- mise.toml hk.pkl scripts/pre-push.sh scripts/check-changed.py $deps)"
  # shellcheck disable=SC2086
  key=$(
    {
      echo "$name"
      git rev-parse --verify "${CHECK_BASE:-origin/main}"
      for p in mise.toml hk.pkl scripts/pre-push.sh scripts/check-changed.py $deps; do
        git rev-parse --verify -q "HEAD:$p" || echo "absent $p"
      done
    } | git hash-object --stdin
  )
  marker="$CACHE_DIR/$key"
  if [ -f "$marker" ] && [ -z "$dirty" ]; then
    echo "[pre-push] $name: unchanged since it last passed, skipping."
    return 0
  fi
  echo "[pre-push] $name: running..."
  "$@" || return 1
  # shellcheck disable=SC2086
  if [ -n "$(git status --porcelain -- mise.toml hk.pkl scripts/pre-push.sh scripts/check-changed.py $deps)" ]; then
    echo "[pre-push] $name: passed but not cached (uncommitted changes present)."
  else
    : > "$marker"
  fi
}

run_gate() {
  case "$1" in
    branch)
      ./node_modules/.bin/validate-branch
      ;;
    api)
      cached_gate api "apps/api pyproject.toml uv.lock" python3 scripts/check-changed.py api "${CHECK_BASE:-origin/main}"
      ;;
    web)
      cached_gate web "apps/web package.json bun.lock biome.json" python3 scripts/check-changed.py web "${CHECK_BASE:-origin/main}"
      ;;
    *)
      echo "pre-push: unknown gate $1" >&2
      exit 2
      ;;
  esac
}

if [ "${1:-}" = "gate" ]; then
  run_gate "${2:?gate name}"
  exit
fi

find "$CACHE_DIR" -type f -mtime +14 -delete 2>/dev/null || true
hk run pre-push

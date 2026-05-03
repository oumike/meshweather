#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

TAG=""
MESSAGE=""
PUSH=1
DRY_RUN=0

show_help() {
  cat <<'EOF'
Create and optionally push a release tag.

Usage:
  scripts/release.sh [options] <version>

Arguments:
  <version>            Semver value like 1.2.3 or v1.2.3

Options:
  -m, --message TEXT   Annotated tag message (default: "Release <tag>")
  --no-push            Create tag locally only
  -n, --dry-run        Print actions without changing git state
  -h, --help           Show this help message and exit

Examples:
  scripts/release.sh 1.3.0
  scripts/release.sh v1.3.1 --message "Release v1.3.1"
  scripts/release.sh 1.4.0 --no-push
EOF
}

if ! command -v git >/dev/null 2>&1; then
  echo "Error: git is not installed or not on PATH." >&2
  exit 1
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      show_help
      exit 0
      ;;
    -m|--message)
      if [[ $# -lt 2 || -z "${2:-}" ]]; then
        echo "Error: --message requires a value." >&2
        exit 1
      fi
      MESSAGE="$2"
      shift 2
      ;;
    --no-push)
      PUSH=0
      shift
      ;;
    -n|--dry-run)
      DRY_RUN=1
      shift
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "Error: unknown option '$1'" >&2
      echo "Run with --help for usage." >&2
      exit 1
      ;;
    *)
      if [[ -n "$TAG" ]]; then
        echo "Error: multiple version values provided ('$TAG' and '$1')." >&2
        exit 1
      fi
      TAG="$1"
      shift
      ;;
  esac
done

if [[ $# -gt 0 ]]; then
  if [[ -n "$TAG" ]]; then
    echo "Error: multiple version values provided ('$TAG' and '$1')." >&2
  else
    TAG="$1"
  fi
fi

if [[ -z "$TAG" ]]; then
  echo "Error: missing <version> argument." >&2
  echo "Run with --help for usage." >&2
  exit 1
fi

if [[ "$TAG" != v* ]]; then
  TAG="v$TAG"
fi

if [[ ! "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([-.][0-9A-Za-z.]+)?$ ]]; then
  echo "Error: '$TAG' is not a supported semver tag (expected vMAJOR.MINOR.PATCH)." >&2
  exit 1
fi

if [[ -z "$MESSAGE" ]]; then
  MESSAGE="Release $TAG"
fi

cd "$ROOT_DIR"

if [[ ! -d .git ]]; then
  echo "Error: repository root not found at $ROOT_DIR" >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Error: working tree is not clean. Commit or stash changes before releasing." >&2
  exit 1
fi

if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null 2>&1; then
  echo "Error: local tag '$TAG' already exists." >&2
  exit 1
fi

if git ls-remote --exit-code --tags origin "refs/tags/$TAG" >/dev/null 2>&1; then
  echo "Error: remote tag '$TAG' already exists on origin." >&2
  exit 1
fi

echo "Preparing release tag $TAG"
echo "Message: $MESSAGE"
if [[ $PUSH -eq 1 ]]; then
  echo "Push: enabled"
else
  echo "Push: disabled (--no-push)"
fi

if [[ $DRY_RUN -eq 1 ]]; then
  echo "Dry run enabled. No git changes made."
  exit 0
fi

git tag -a "$TAG" -m "$MESSAGE"

if [[ $PUSH -eq 1 ]]; then
  git push origin "$TAG"
  echo "Created and pushed tag $TAG"
else
  echo "Created local tag $TAG"
fi

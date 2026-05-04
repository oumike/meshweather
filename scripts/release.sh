#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

TAG=""
MESSAGE=""
PUSH=1
DRY_RUN=0

show_help() {
  cat <<'EOF'
Update VERSION, create a release commit, and optionally push a release tag.

Usage:
  scripts/release.sh [options]

Options:
  --no-push            Create tag locally only
  -n, --dry-run        Print actions without changing git state
  -h, --help           Show this help message and exit

Examples:
  scripts/release.sh
  scripts/release.sh --no-push
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
      echo "Error: positional arguments are not supported." >&2
      echo "Run with --help for usage." >&2
      exit 1
      ;;
  esac
done

if [[ $# -gt 0 ]]; then
  echo "Error: positional arguments are not supported." >&2
  echo "Run with --help for usage." >&2
  exit 1
fi

cd "$ROOT_DIR"

if [[ ! -d .git ]]; then
  echo "Error: repository root not found at $ROOT_DIR" >&2
  exit 1
fi

CURRENT_VERSION=""
# Prefer explicit VERSION file, then fall back to the latest reachable git tag.
if [[ -f "$ROOT_DIR/VERSION" ]]; then
  CURRENT_VERSION="$(tr -d '\n' < "$ROOT_DIR/VERSION")"
fi
if [[ -z "$CURRENT_VERSION" ]]; then
  CURRENT_VERSION="$(git describe --tags --abbrev=0 2>/dev/null || echo "unknown")"
fi
echo "Current version: $CURRENT_VERSION"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Error: working tree is not clean. Commit or stash changes before releasing." >&2
  exit 1
fi

if [[ ! -t 0 ]]; then
  echo "Error: interactive prompts require a TTY." >&2
  exit 1
fi

VERSION_INPUT=""
read -r -p "New version (e.g. 1.2.3) [last: $CURRENT_VERSION]: " VERSION_INPUT

if [[ -z "$VERSION_INPUT" ]]; then
  echo "Error: no version entered. Aborting." >&2
  exit 1
fi

TAG="$VERSION_INPUT"
if [[ "$TAG" != v* ]]; then
  TAG="v$TAG"
fi

if [[ ! "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([-.][0-9A-Za-z.]+)?$ ]]; then
  echo "Error: '$TAG' is not a supported semver tag (expected vMAJOR.MINOR.PATCH)." >&2
  exit 1
fi

DEFAULT_MESSAGE="Release $TAG"
MESSAGE_INPUT=""
read -r -p "Release message [$DEFAULT_MESSAGE]: " MESSAGE_INPUT
MESSAGE="${MESSAGE_INPUT:-$DEFAULT_MESSAGE}"

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

if [[ -f "$ROOT_DIR/VERSION" ]]; then
  EXISTING_VERSION="$(tr -d '\n' < "$ROOT_DIR/VERSION")"
else
  EXISTING_VERSION=""
fi
if [[ "$EXISTING_VERSION" != "$TAG" ]]; then
  VERSION_UPDATE_NEEDED=1
  echo "VERSION file: will update to $TAG"
else
  VERSION_UPDATE_NEEDED=0
  echo "VERSION file: already set to $TAG"
fi

if [[ $DRY_RUN -eq 1 ]]; then
  echo "Dry run enabled. No git changes made."
  exit 0
fi

if [[ $VERSION_UPDATE_NEEDED -eq 1 ]]; then
  printf "%s\n" "$TAG" > "$ROOT_DIR/VERSION"
  git add "$ROOT_DIR/VERSION"
  git commit -m "chore(release): bump VERSION to $TAG"
  echo "Committed VERSION update to $TAG"
fi

git tag -a "$TAG" -m "$MESSAGE"

if [[ $PUSH -eq 1 ]]; then
  git push origin "$TAG"
  echo "Created and pushed tag $TAG"
else
  echo "Created local tag $TAG"
fi

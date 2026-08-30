#!/usr/bin/env bash
# Push AURA to GitHub: https://github.com/iam-pradeepkumar/aura.git
set -euo pipefail

REPO_URL="${GITHUB_REPO_URL:-https://github.com/iam-pradeepkumar/aura.git}"
BRANCH="${GITHUB_BRANCH:-main}"

cd "$(dirname "$0")/.."

if ! git remote get-url github &>/dev/null; then
  git remote add github "$REPO_URL"
else
  git remote set-url github "$REPO_URL"
fi

if [[ -n "${GITHUB_TOKEN:-}" ]]; then
  echo "Pushing with GITHUB_TOKEN..."
  git push "https://x-access-token:${GITHUB_TOKEN}@github.com/iam-pradeepkumar/aura.git" "$BRANCH"
elif gh auth status &>/dev/null; then
  echo "Pushing with GitHub CLI..."
  git push github "$BRANCH"
else
  echo "ERROR: No GitHub credentials."
  echo ""
  echo "Option 1 — Personal Access Token:"
  echo "  export GITHUB_TOKEN=ghp_your_token_here"
  echo "  bash scripts/push_to_github.sh"
  echo ""
  echo "Option 2 — GitHub CLI:"
  echo "  gh auth login"
  echo "  bash scripts/push_to_github.sh"
  echo ""
  echo "Option 3 — Manual push:"
  echo "  git push https://github.com/iam-pradeepkumar/aura.git $BRANCH"
  exit 1
fi

echo "Done: $REPO_URL ($BRANCH)"

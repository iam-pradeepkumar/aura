#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../landing"
npm ci
npm run build
echo "Landing built to dashboard/static/landing-dist/"

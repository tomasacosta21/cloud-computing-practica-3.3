#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Uso: ./scripts/sync-web.sh <web-bucket-name>" >&2
  exit 1
fi

aws s3 sync web/ "s3://$1"

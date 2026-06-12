#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Uso: ./scripts/sync-web.sh <stack-name>" >&2
  echo "Ejemplo: ./scripts/sync-web.sh servicio-validador-facturas" >&2
  exit 1
fi

STACK_NAME="$1"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

get_output() {
  local output_key="$1"

  aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='${output_key}'].OutputValue | [0]" \
    --output text
}

API_ENDPOINT="$(get_output ApiEndpoint)"
WEB_BUCKET_NAME="$(get_output WebBucketName)"

if [[ -z "$API_ENDPOINT" || "$API_ENDPOINT" == "None" ]]; then
  echo "No se encontro el output ApiEndpoint para el stack $STACK_NAME" >&2
  exit 1
fi

if [[ -z "$WEB_BUCKET_NAME" || "$WEB_BUCKET_NAME" == "None" ]]; then
  echo "No se encontro el output WebBucketName para el stack $STACK_NAME" >&2
  exit 1
fi

cp -R web/. "$BUILD_DIR/"

cat > "$BUILD_DIR/config.js" <<EOF
window.APP_CONFIG = {
  apiBaseUrl: "${API_ENDPOINT}"
};
EOF

aws s3 sync "$BUILD_DIR/" "s3://${WEB_BUCKET_NAME}"

echo "Sitio sincronizado en s3://${WEB_BUCKET_NAME}"
echo "API configurada: ${API_ENDPOINT}"

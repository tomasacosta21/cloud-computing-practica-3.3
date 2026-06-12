#!/usr/bin/env bash
set -euo pipefail

sam build --use-container
sam deploy --guided

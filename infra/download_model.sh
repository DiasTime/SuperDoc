#!/usr/bin/env bash
# Download the self-hosted Qwen2.5-VL 7B weights into ./models (gitignored).
# Requires: pip install "huggingface_hub[cli]"
set -euo pipefail

MODEL="${VL_MODEL_NAME:-Qwen/Qwen2.5-VL-7B-Instruct}"
DEST="${1:-./models/qwen2.5-vl-7b}"

echo "Downloading ${MODEL} -> ${DEST}"
mkdir -p "${DEST}"
huggingface-cli download "${MODEL}" --local-dir "${DEST}"
echo "Done. Point VL_ENDPOINT's vLLM server at ${DEST}."

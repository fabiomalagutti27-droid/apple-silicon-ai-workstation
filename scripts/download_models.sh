#!/usr/bin/env bash
# ==============================================================================
# download_models.sh - Download dei Modelli MoE e Micro-VLM per Apple Silicon
# Scarica i checkpoint pesati da Hugging Face nella directory ~/.models/
# ==============================================================================
set -euo pipefail

MODELS_DIR="${HOME}/.models"
mkdir -p "${MODELS_DIR}"

echo "=== Suite Modelli MoE-First per 64GB UMA ==="
echo "Destinazione pesi: ${MODELS_DIR}"

if ! command -v huggingface-cli >/dev/null 2>&1; then
    echo "--> Installazione di huggingface-hub tramite uvx/pip..."
    uv pip install --system huggingface-hub || pip install huggingface-hub
fi

download_model() {
    local repo_id="$1"
    local target_dir="$2"
    echo "----------------------------------------------------------------------"
    echo "📥 Download: ${repo_id} -> ${MODELS_DIR}/${target_dir}"
    echo "----------------------------------------------------------------------"
    huggingface-cli download "${repo_id}" --local-dir "${MODELS_DIR}/${target_dir}" --local-dir-use-symlinks False
}

# 1. Qwen 3.6 35B-A3B MoE (4-bit - Fast Coding & Subagenti)
download_model "mlx-community/Qwen3.6-35B-A3B-4bit" "qwen3.6-35b-a3b-mlx-4bit"

# 2. Qwen 3.6 35B-A3B MoE (8-bit Q8 - SuperAgent Default Architect)
download_model "mlx-community/Qwen3.6-35B-A3B-8bit" "qwen3.6-35b-a3b-mlx-8bit"

# 3. NVIDIA Nemotron 3.5 Bolt 74B-A9B (4-bit Mamba-MoE - Frontier Reasoning)
download_model "rapid-mlx/NVIDIA-Nemotron-3.5-Bolt-74B-A9B-MLX-4bit" "nemotron-3.5-bolt-74b-a9b-mlx-4bit"

# 4. Gemma 4 26B-A4B MoE (8-bit - Multimodal Lecturer)
download_model "mlx-community/gemma-4-26b-a4b-it-8bit" "gemma-4-26b-a4b-mlx-8bit"

# 5. Xiaomi-OCR-0 (0.8B Micro-VLM KaTeX)
download_model "xiaomi-research/Xiaomi-OCR-0" "xiaomi-ocr-0"

echo "======================================================================"
echo "🎉 TUTTI I MODELLI SONO STATI SCARICATI CORRETTAMENTE IN ${MODELS_DIR}"
echo "======================================================================"

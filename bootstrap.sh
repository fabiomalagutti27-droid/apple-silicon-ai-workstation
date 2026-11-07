#!/usr/bin/env bash
# ==============================================================================
# bootstrap.sh - Installazione e Configurazione Automatica della Workstation
# Imposta l'ambiente Apple Silicon per l'infrastruttura AI distribuita MoE-First
# ==============================================================================
set -euo pipefail

echo "╔═══════════════════════════════════════════════════════════════════════╗"
echo "║   🍎 APPLE SILICON AI WORKSTATION - BOOTSTRAP AUTOMATIZZATO           ║"
echo "║   Setup Idempotente per macOS (M1/M2/M3/M4/M5 Pro/Max/Ultra)          ║"
echo "╚═══════════════════════════════════════════════════════════════════════╝"

# 1. Controllo Architettura Apple Silicon
ARCH=$(uname -m)
if [ "$ARCH" != "arm64" ]; then
    echo "❌ Errore: Questa architettura richiede un processore Apple Silicon (arm64). Rilevato: $ARCH"
    exit 1
fi
echo "✅ Architettura verificata: Apple Silicon (${ARCH})"

# 2. Controllo / Installazione Homebrew
if ! command -v brew >/dev/null 2>&1; then
    echo "--> Installazione di Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi
echo "✅ Homebrew presente: $(brew --version | head -n1)"

# 3. Installazione Pacchetti via Brewfile
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/Brewfile" ]; then
    echo "--> Installazione dipendenze di sistema via Brewfile..."
    brew bundle install --file="${SCRIPT_DIR}/Brewfile" || true
fi

# 4. Creazione Struttura Directory
echo "--> Inizializzazione directory di lavoro..."
mkdir -p "${HOME}/.models"
mkdir -p "${HOME}/.local/bin"
mkdir -p "${HOME}/bin"
mkdir -p "${HOME}/.config/llama-swap"
mkdir -p "${HOME}/.config/gh-agent"
mkdir -p "${HOME}/.dsh/profiles/superagent"
mkdir -p "${HOME}/.ai-cache"
mkdir -p "${HOME}/.ai-backups"

# 5. Configurazione Eseguibile cargo-uma (Zero-OOM Wrapper)
echo "--> Installazione wrapper Zero-OOM cargo-uma..."
cat << 'EOF' > "${HOME}/.local/bin/cargo-uma"
#!/usr/bin/env bash
set -e
# Scarica la VRAM di llama-swap prima di saturare i core CPU e la RAM con LLVM
curl -s -X POST http://127.0.0.1:8000/api/models/unload >/dev/null 2>&1 || true
sleep 0.2
exec cargo "$@"
EOF
chmod +x "${HOME}/.local/bin/cargo-uma"
cp "${HOME}/.local/bin/cargo-uma" "${HOME}/bin/cargo-uma" 2>/dev/null || true

# 6. Assicura che ~/.local/bin sia nel PATH di zsh
# shellcheck disable=SC2016
if ! grep -q 'export PATH="$HOME/.local/bin:$PATH"' "${HOME}/.zshrc" 2>/dev/null; then
    # shellcheck disable=SC2016
    echo 'export PATH="$HOME/.local/bin:$HOME/bin:$PATH"' >> "${HOME}/.zshrc"
    echo "✅ Aggiornato PATH in ~/.zshrc"
fi

# 7. Copia Template di Configurazione se non esistenti
if [ ! -f "${HOME}/.config/llama-swap/config.yaml" ] && [ -f "${SCRIPT_DIR}/configs/llama-swap.yaml.template" ]; then
    echo "--> Generazione ~/.config/llama-swap/config.yaml da template..."
    cp "${SCRIPT_DIR}/configs/llama-swap.yaml.template" "${HOME}/.config/llama-swap/config.yaml"
fi

if [ ! -f "${HOME}/.dsh/profiles/superagent/cordis.patch.yml" ] && [ -f "${SCRIPT_DIR}/configs/cordis.patch.yml.template" ]; then
    echo "--> Generazione ~/.dsh/profiles/superagent/cordis.patch.yml da template..."
    cp "${SCRIPT_DIR}/configs/cordis.patch.yml.template" "${HOME}/.dsh/profiles/superagent/cordis.patch.yml"
fi

# 8. Setup Ambiente Virtuale Python con UV
VENV_PATH="${HOME}/ai-env"
if [ ! -d "${VENV_PATH}" ]; then
    echo "--> Creazione ambiente virtuale ad alte prestazioni (${VENV_PATH})..."
    uv venv "${VENV_PATH}" --python 3.12
fi

echo "======================================================================"
echo "🎉 BOOTSTRAP COMPLETATO CON SUCCESSO!"
echo "Prossimi passaggi consigliati:"
echo " 1. Applica il limite UMA:  sudo bash scripts/setup_wired_limit.sh"
echo " 2. Scarica i modelli:      bash scripts/download_models.sh"
echo " 3. Configura backup drive: rclone config && bash scripts/backup_to_gdrive.sh"
echo "======================================================================"

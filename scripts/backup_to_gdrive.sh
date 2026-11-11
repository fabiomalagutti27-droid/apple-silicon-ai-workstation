#!/usr/bin/env bash
# ==============================================================================
# backup_to_gdrive.sh - Backup Settimanale Ecosistema AI su Google Drive
# Utilizza rclone per sincronizzare configurazioni, codice, registri e Vault
# ==============================================================================
set -euo pipefail

BACKUP_DIR="${HOME}/.ai-backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
ARCHIVE_NAME="m5pro_ai_ecosystem_${TIMESTAMP}.tar.gz"
ARCHIVE_PATH="${BACKUP_DIR}/${ARCHIVE_NAME}"

# Parametri Google Drive (configurato con 'rclone config')
RCLONE_REMOTE="${RCLONE_REMOTE_NAME:-gdrive}"
RCLONE_DEST="${RCLONE_REMOTE}:${RCLONE_BACKUP_PATH:-Backups/MacMini_M5Pro_AI_Workstation}"
RETENTION_DAYS=30

mkdir -p "${BACKUP_DIR}"

echo "======================================================================"
echo "[BACKUP] Avvio backup settimanale ecosistema AI: ${TIMESTAMP}"
echo "======================================================================"

# 1. Creazione archivio compresso escludendo deliberatamente i pesi da centinaia di GB
echo "--> Compressione configurazioni, script, LaunchAgents e registri..."
tar -czf "${ARCHIVE_PATH}" \
    --exclude="*/.models/*" \
    --exclude="*/models/*" \
    --exclude="*/.cache/*" \
    --exclude="*/__pycache__/*" \
    --exclude="*/target/*" \
    --exclude="*/node_modules/*" \
    --exclude="*.log" \
    -C "${HOME}" \
    .config/llama-swap \
    .config/gh-agent \
    .dsh/profiles \
    .ai-cache \
    ai-ecosystem \
    bin \
    .local/bin \
    Library/LaunchAgents/com.ai.* \
    Library/LaunchAgents/com.localai.* \
    Library/LaunchAgents/sh.brew.* \
    2>/dev/null || true

ARCHIVE_SIZE=$(du -sh "${ARCHIVE_PATH}" | cut -f1)
echo "[OK] Archivio locale creato con successo: ${ARCHIVE_PATH} (${ARCHIVE_SIZE})"

# 2. Verifica disponibilità di rclone
if ! command -v rclone >/dev/null 2>&1; then
    echo "[WARNING] rclone non trovato. Installa rclone via 'brew install rclone' e configuralo con 'rclone config'."
    echo "   L'archivio è stato comunque salvato localmente in: ${ARCHIVE_PATH}"
    exit 0
fi

# 3. Trasferimento cifrato / sicuro su Google Drive
echo "--> Upload su Google Drive (${RCLONE_DEST})..."
rclone copy "${ARCHIVE_PATH}" "${RCLONE_DEST}" --progress --drive-chunk-size 64M

# 4. Sincronizzazione incrementale del Vault Obsidian (senza .stfolder e cache)
if [ -d "${HOME}/Vault" ]; then
    echo "--> Sync incrementale Vault Obsidian..."
    rclone sync "${HOME}/Vault" "${RCLONE_DEST}/Vault" \
        --exclude ".stfolder/**" \
        --exclude ".trash/**" \
        --exclude ".DS_Store" \
        --fast-list
fi

# 5. Pulizia snapshot locali e remoti più vecchi del periodo di retention
echo "--> Pulizia vecchi backup locali (> ${RETENTION_DAYS} giorni)..."
find "${BACKUP_DIR}" -name "m5pro_ai_ecosystem_*.tar.gz" -mtime +${RETENTION_DAYS} -delete || true

echo "--> Pulizia vecchi backup su Google Drive (> ${RETENTION_DAYS} giorni)..."
rclone delete "${RCLONE_DEST}" --min-age "${RETENTION_DAYS}d" --include "m5pro_ai_ecosystem_*.tar.gz" 2>/dev/null || true

echo "======================================================================"
echo "[SUCCESS] Backup completato con successo! (${ARCHIVE_SIZE} trasferiti su Google Drive)"
echo "======================================================================"

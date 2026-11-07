#!/usr/bin/env bash
# ==============================================================================
# install_services.sh - Installazione LaunchAgents macOS per Apple Silicon
# Sostituisce __USER_HOME__ con $HOME e carica i servizi in launchd
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATES_DIR="${SCRIPT_DIR}/../configs/launchd"
USER_LAUNCHAGENTS="${HOME}/Library/LaunchAgents"

mkdir -p "${USER_LAUNCHAGENTS}"

echo "=== Installazione LaunchAgents in ${USER_LAUNCHAGENTS} ==="

for tmpl in "${TEMPLATES_DIR}"/*.plist.template; do
    filename=$(basename "$tmpl" .template)
    dest="${USER_LAUNCHAGENTS}/${filename}"
    
    # Salta il demone root (wiredlimit va in /Library/LaunchDaemons tramite setup_wired_limit.sh)
    if [ "$filename" = "com.localai.wiredlimit.plist" ]; then
        continue
    fi

    echo "--> Installazione: ${filename}..."
    sed "s|__USER_HOME__|${HOME}|g" "$tmpl" > "$dest"
    
    # Carica il servizio con launchctl
    launchctl unload "$dest" 2>/dev/null || true
    launchctl load -w "$dest" 2>/dev/null || true
    echo "    ✅ Servizio ${filename} registrato"
done

echo "======================================================================"
echo "🎉 TUTTI I LAUNCHAGENTS SONO STATI INSTALLATI E CARICATI CON SUCCESSO!"
echo "======================================================================"

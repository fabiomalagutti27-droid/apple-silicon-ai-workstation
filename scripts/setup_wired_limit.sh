#!/usr/bin/env bash
# ==============================================================================
# setup_wired_limit.sh - Ottimizzazione Kernel UMA Apple Silicon
# Aumenta il limite di memoria Metal allocabile a 56 GB (su 64 GB)
# ==============================================================================
set -euo pipefail

PLIST_SRC="$(dirname "$0")/../configs/launchd/com.localai.wiredlimit.plist"
PLIST_DEST="/Library/LaunchDaemons/com.localai.wiredlimit.plist"

echo "=== Configurazione Wired Memory Limit Metal (56 GB / 57344 MB) ==="

if [ "$EUID" -ne 0 ]; then
    echo "⚠️ Questo script richiede privilegi di amministratore (root)."
    echo "   Rilancio con sudo..."
    exec sudo bash "$0" "$@"
fi

if [ -f "$PLIST_SRC" ]; then
    cp "$PLIST_SRC" "$PLIST_DEST"
else
    cat <<EOF > "$PLIST_DEST"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.localai.wiredlimit</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/sbin/sysctl</string>
        <string>iogpu.wired_limit_mb=57344</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
EOF
fi

chown root:wheel "$PLIST_DEST"
chmod 644 "$PLIST_DEST"

launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load -w "$PLIST_DEST"

/usr/sbin/sysctl iogpu.wired_limit_mb=57344
CURRENT_LIMIT=$(/usr/sbin/sysctl -n iogpu.wired_limit_mb)
echo "✅ Limite UMA Metal applicato con successo: ${CURRENT_LIMIT} MB"

#!/bin/bash
# AI Kiosk Agent Platform Launcher
# Launches the UI in fullscreen/kiosk mode
#
# Usage: ./scripts/launch-kiosk.sh [URL]

set -e

KIOSK_URL="${1:-http://localhost:6001}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "🚀 AI Kiosk Agent Platform Launcher"
echo "======================"
echo ""

# Check if orchestrator is running
echo "📡 Verificando servicios..."
if ! curl -sf http://localhost:8765/healthz > /dev/null 2>&1; then
    echo "❌ Orchestrator no responde en http://localhost:8765"
    echo ""
    echo "   Ejecuta primero: task dev"
    echo ""
    exit 1
fi
echo "✅ Orchestrator OK"

# Check if UI is running
if ! curl -sf "$KIOSK_URL" > /dev/null 2>&1; then
    echo "⚠️  UI no responde en $KIOSK_URL"
    echo "   Asegúrate de que la UI está corriendo (task dev:ui)"
    echo ""
fi

# Detect OS
case "$(uname -s)" in
    Darwin*)
        OS="macos"
        ;;
    Linux*)
        OS="linux"
        ;;
    *)
        echo "❌ Sistema operativo no soportado: $(uname -s)"
        exit 1
        ;;
esac

echo "🖥️  Sistema detectado: $OS"
echo "🌐 URL: $KIOSK_URL"
echo ""

# Launch browser in kiosk mode
if [ "$OS" = "macos" ]; then
    # macOS: Try Chrome first, then Safari
    if [ -d "/Applications/Google Chrome.app" ]; then
        echo "🚀 Abriendo Google Chrome en modo kiosk..."
        open -a "Google Chrome" --args \
            --kiosk \
            --disable-infobars \
            --disable-session-crashed-bubble \
            --autoplay-policy=no-user-gesture-required \
            --use-fake-ui-for-media-stream \
            "$KIOSK_URL"
    elif [ -d "/Applications/Brave Browser.app" ]; then
        echo "🚀 Abriendo Brave en modo kiosk..."
        open -a "Brave Browser" --args \
            --kiosk \
            --disable-infobars \
            --autoplay-policy=no-user-gesture-required \
            "$KIOSK_URL"
    else
        echo "🚀 Abriendo Safari..."
        # Safari doesn't support --kiosk, use fullscreen instead
        osascript <<EOF
tell application "Safari"
    open location "$KIOSK_URL"
    activate
    delay 1
    tell application "System Events"
        keystroke "f" using {control down, command down}
    end tell
end tell
EOF
    fi

elif [ "$OS" = "linux" ]; then
    # Linux: Try Chromium, Chrome, then Firefox
    if command -v chromium-browser &> /dev/null; then
        echo "🚀 Abriendo Chromium en modo kiosk..."
        chromium-browser \
            --kiosk \
            --disable-infobars \
            --disable-session-crashed-bubble \
            --autoplay-policy=no-user-gesture-required \
            --use-fake-ui-for-media-stream \
            "$KIOSK_URL" &
    elif command -v google-chrome &> /dev/null; then
        echo "🚀 Abriendo Google Chrome en modo kiosk..."
        google-chrome \
            --kiosk \
            --disable-infobars \
            --autoplay-policy=no-user-gesture-required \
            "$KIOSK_URL" &
    elif command -v firefox &> /dev/null; then
        echo "🚀 Abriendo Firefox en modo kiosk..."
        firefox --kiosk "$KIOSK_URL" &
    else
        echo "❌ No se encontró navegador compatible"
        echo "   Instala chromium-browser, google-chrome o firefox"
        exit 1
    fi
fi

echo ""
echo "✅ Kiosk lanzado"
echo ""
echo "Para salir del modo kiosk:"
if [ "$OS" = "macos" ]; then
    echo "  - Chrome: Cmd+Shift+F o Esc"
    echo "  - Safari: Ctrl+Cmd+F"
else
    echo "  - Chromium/Chrome: F11 o Alt+F4"
    echo "  - Firefox: F11"
fi

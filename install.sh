#!/usr/bin/env bash
# Instalador automático de El Arriero MCP (PT-MCP-Bridge) para Linux Mint / Ubuntu / Debian
# Proyecto académico - Universidad de Caldas
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "==> Instalando El Arriero MCP en: ${PROJECT_DIR}"

# 1. Dependencias del sistema para PyQt6 y venv
# Nota: `apt-get update || true` evita que repositorios externos de terceros (ej. Spotify/PPAs
# con firmas GPG vencidas en la máquina del usuario) detengan la instalación.
if command -v apt-get >/dev/null 2>&1; then
    echo "==> Verificando dependencias del sistema (python3-venv, libxcb-cursor0, Qt6 SVG)..."
    sudo apt-get update -qq || echo "AVISO: Algunos repositorios externos de apt reportaron advertencias; continuando..."
    sudo apt-get install -y python3-venv python3-pip libxcb-cursor0 libgl1 libxkbcommon-x11-0 \
        python3-pyqt6 python3-pyqt6.qtsvg || \
    sudo apt-get install -y python3-venv python3-pip libxcb-cursor0
fi

# 2. Entorno virtual e instalación del paquete
if [ ! -d "${PROJECT_DIR}/.venv" ]; then
    echo "==> Creando entorno virtual .venv..."
    python3 -m venv "${PROJECT_DIR}/.venv"
fi

echo "==> Instalando dependencias Python dentro de .venv..."
"${PROJECT_DIR}/.venv/bin/pip" install --upgrade pip -q
"${PROJECT_DIR}/.venv/bin/pip" install -e "${PROJECT_DIR}[dev]" -q

# 3. Preparar permisos de la carpeta de extensiones de Packet Tracer
# IMPORTANTE: No pre-copiamos pt-mcp-bridge.pta dentro de ~/pt/extensions ni /opt/pt/extensions
# porque QFile::copy() de Packet Tracer falla con "Error Importing App Meta File" si el archivo
# destino ya existe al pulsar "Add...". En su lugar, limpiamos duplicados previos y damos
# permisos de escritura a /opt/pt/extensions para que Packet Tracer pueda importarlo sin error.
rm -f "${HOME}/pt/extensions/pt-mcp-bridge.pta" 2>/dev/null || true
if [ -d "/opt/pt/extensions" ]; then
    sudo chmod -R a+rwX /opt/pt/extensions || true
    sudo rm -f /opt/pt/extensions/pt-mcp-bridge.pta 2>/dev/null || true
fi

# 4. Crear acceso directo en el menú de aplicaciones del usuario
APPS_DIR="${HOME}/.local/share/applications"
mkdir -p "${APPS_DIR}"
DESKTOP_FILE="${APPS_DIR}/pt-mcp-bridge.desktop"

cat > "${DESKTOP_FILE}" <<EOF
[Desktop Entry]
Type=Application
Name=El Arriero MCP
Comment=Puente MCP de IA para Cisco Packet Tracer (Universidad de Caldas)
Exec=${PROJECT_DIR}/.venv/bin/el-arriero-mcp
Path=${PROJECT_DIR}
Terminal=false
Categories=Network;Development;Education;
EOF

chmod +x "${DESKTOP_FILE}"

echo ""
echo "========================================================================"
echo "  Instalación completada con éxito"
echo "========================================================================"
echo "1. Registra los permisos en Cisco Packet Tracer (una sola vez):"
echo "   Extensions -> IPC -> Configure Apps... -> Add..."
echo "   Selecciona: ${PROJECT_DIR}/pt-mcp-bridge.pta"
echo "   Pulsa 'Ok' y reinicia Packet Tracer (File -> Exit)."
echo ""
echo "2. Para abrir la interfaz gráfica (cualquiera de estos comandos funciona):"
echo "   python3 run.py"
echo "   ${PROJECT_DIR}/.venv/bin/el-arriero-mcp"
echo "   (o búscala como 'El Arriero MCP' en tu menú de aplicaciones)"
echo "========================================================================"

#!/usr/bin/env bash
# Instalador automático de El Arriero MCP (PT-MCP-Bridge) para Linux Mint / Ubuntu / Debian
# Proyecto académico - Universidad de Caldas
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "==> Instalando MCPCPT (PT-MCP-Bridge) en: ${PROJECT_DIR}"

# 1. Dependencias del sistema para PyQt6 y venv
if command -v apt-get >/dev/null 2>&1; then
    echo "==> Verificando dependencias del sistema (python3-venv, libxcb-cursor0)..."
    sudo apt-get update -qq
    sudo apt-get install -y python3-venv python3-pip libxcb-cursor0
fi

# 2. Entorno virtual e instalación del paquete
if [ ! -d "${PROJECT_DIR}/.venv" ]; then
    echo "==> Creando entorno virtual .venv..."
    python3 -m venv "${PROJECT_DIR}/.venv"
fi

echo "==> Instalando dependencias Python..."
"${PROJECT_DIR}/.venv/bin/pip" install --upgrade pip -q
"${PROJECT_DIR}/.venv/bin/pip" install -e "${PROJECT_DIR}[dev]" -q

# 3. Copiar el archivo de permisos ExApp (.pta) a ~/pt/extensions si existe o crear carpeta
mkdir -p "${HOME}/pt/extensions"
cp -f "${PROJECT_DIR}/pt-mcp-bridge.pta" "${HOME}/pt/extensions/pt-mcp-bridge.pta"
echo "==> Archivo ExApp copiado en: ${HOME}/pt/extensions/pt-mcp-bridge.pta"

# 4. Crear acceso directo en el menú de aplicaciones del usuario
APPS_DIR="${HOME}/.local/share/applications"
mkdir -p "${APPS_DIR}"
DESKTOP_FILE="${APPS_DIR}/pt-mcp-bridge.desktop"

cat > "${DESKTOP_FILE}" <<EOF
[Desktop Entry]
Type=Application
Name=PT-MCP-Bridge
Comment=Puente MCP Universal de IA para Cisco Packet Tracer
Exec=${PROJECT_DIR}/.venv/bin/pt-mcp-bridge
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
echo "2. Para abrir la interfaz gráfica:"
echo "   ${PROJECT_DIR}/.venv/bin/pt-mcp-bridge"
echo "   (o búscala como 'PT-MCP-Bridge' en tu menú de aplicaciones)"
echo "========================================================================"


#!/usr/bin/env bash
# Construye el paquete instalable .deb de El Arriero MCP (PT-MCP-Bridge) para Debian / Ubuntu / Linux Mint
# Proyecto académico - Universidad de Caldas
set -euo pipefail
umask 022

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

PKG_NAME="tracelink"
VERSION="1.0.0"
ARCH="amd64"
DEB_ROOT="${PROJECT_DIR}/build/deb/${PKG_NAME}_${VERSION}_${ARCH}"
OUT_DEB="${PROJECT_DIR}/dist/${PKG_NAME}_${VERSION}_${ARCH}.deb"

echo "==> [1/3] Compilando binario autónomo con PyInstaller..."
"${PROJECT_DIR}/.venv/bin/pyinstaller" \
    --noconfirm \
    --clean \
    --onefile \
    --windowed \
    --name "tracelink" \
    --paths "${PROJECT_DIR}/src" \
    --add-data "${PROJECT_DIR}/src/pt_mcp_bridge/ipc_index.json:pt_mcp_bridge" \
    --add-data "${PROJECT_DIR}/src/pt_mcp_bridge/gui/assets/caldas_bg.jpg:pt_mcp_bridge/gui/assets" \
    --hidden-import PyQt6.QtSvg \
    --collect-submodules mcp.server \
    --collect-submodules mcp.shared \
    --collect-submodules uvicorn \
    "${PROJECT_DIR}/run.py"

echo "==> [2/3] Estructurando árbol del paquete Debian en ${DEB_ROOT}..."
rm -rf "${DEB_ROOT}"
mkdir -p "${DEB_ROOT}/DEBIAN"
mkdir -p "${DEB_ROOT}/opt/tracelink"
mkdir -p "${DEB_ROOT}/usr/bin"
mkdir -p "${DEB_ROOT}/usr/share/applications"
mkdir -p "${DEB_ROOT}/usr/share/icons/hicolor/scalable/apps"

# Copiar ejecutable, firma ExApp (.pta) e ícono
cp -f "${PROJECT_DIR}/dist/tracelink" "${DEB_ROOT}/opt/tracelink/tracelink"
chmod 755 "${DEB_ROOT}/opt/tracelink/tracelink"
cp -f "${PROJECT_DIR}/pt-mcp-bridge.pta" "${DEB_ROOT}/opt/tracelink/pt-mcp-bridge.pta"
cp -f "${PROJECT_DIR}/packaging/tracelink.svg" "${DEB_ROOT}/usr/share/icons/hicolor/scalable/apps/tracelink.svg"

# Enlaces simbólicos en /usr/bin (tanto 'el-arriero-mcp', 'tracelink' como 'pt-mcp-bridge')
ln -sf /opt/tracelink/tracelink "${DEB_ROOT}/usr/bin/el-arriero-mcp"
ln -sf /opt/tracelink/tracelink "${DEB_ROOT}/usr/bin/tracelink"
ln -sf /opt/tracelink/tracelink "${DEB_ROOT}/usr/bin/pt-mcp-bridge"

# Lanzador de escritorio (.desktop)
cat > "${DEB_ROOT}/usr/share/applications/tracelink.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=El Arriero MCP
GenericName=Puente MCP para Cisco Packet Tracer
Comment=Conecta agentes de IA con Cisco Packet Tracer mediante MCP y PTMP (Universidad de Caldas)
Exec=/usr/bin/el-arriero-mcp
Icon=tracelink
Terminal=false
Categories=Network;Development;Education;
Keywords=Cisco;PacketTracer;MCP;AI;Redes;Arriero;Caldas;
EOF

# Archivo DEBIAN/control
INSTALLED_SIZE="$(du -sk "${DEB_ROOT}" | cut -f1)"
cat > "${DEB_ROOT}/DEBIAN/control" <<EOF
Package: ${PKG_NAME}
Version: ${VERSION}
Section: net
Priority: optional
Architecture: ${ARCH}
Installed-Size: ${INSTALLED_SIZE}
Depends: libxcb-cursor0, libgl1, libxkbcommon-x11-0
Provides: pt-mcp-bridge, el-arriero-mcp
Maintainer: El Arriero MCP <noreply@ucaldas.edu.co>
Homepage: https://github.com/ucaldas/el-arriero-mcp
Description: El Arriero MCP (PT-MCP-Bridge) - Puente MCP entre IA y Cisco Packet Tracer
 Puente nativo para Linux desarrollado en la Universidad de Caldas que conecta
 agentes de IA compatibles con Model Context Protocol (MCP) directamente con
 el motor interno de Cisco Packet Tracer a traves del protocolo PTMP.
EOF

echo "==> [3/3] Generando paquete ${OUT_DEB}..."
find "${DEB_ROOT}" -type d -exec chmod 755 {} +
chmod 644 "${DEB_ROOT}/DEBIAN/control" "${DEB_ROOT}/opt/tracelink/pt-mcp-bridge.pta" \
    "${DEB_ROOT}/usr/share/applications/tracelink.desktop" \
    "${DEB_ROOT}/usr/share/icons/hicolor/scalable/apps/tracelink.svg"
chmod 755 "${DEB_ROOT}/opt/tracelink/tracelink"
dpkg-deb --root-owner-group --build "${DEB_ROOT}" "${OUT_DEB}"

echo ""
echo "========================================================================"
echo "  Paquete .deb generado correctamente:"
echo "  ${OUT_DEB}"
echo "  Para instalarlo en Linux Mint / Ubuntu / Debian:"
echo "  sudo dpkg -i ${OUT_DEB}"
echo "========================================================================"
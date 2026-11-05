#!/usr/bin/env bash
# Construye el paquete instalable .deb de El Arriero MCP (PT-MCP-Bridge) para Debian / Ubuntu / Linux Mint
# Proyecto académico - Universidad de Caldas
set -euo pipefail
umask 022

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

PKG_NAME="el-arriero-mcp"
VERSION="${VERSION:-1.0.0}"
ARCH="amd64"
DEB_ROOT="${PROJECT_DIR}/build/deb/${PKG_NAME}_${VERSION}_${ARCH}"
OUT_DEB="${PROJECT_DIR}/dist/${PKG_NAME}_${VERSION}_${ARCH}.deb"

echo "==> [1/3] Compilando binario autónomo con PyInstaller..."
"${PROJECT_DIR}/.venv/bin/pyinstaller" \
    --noconfirm \
    --clean \
    --onefile \
    --windowed \
    --name "el-arriero-mcp" \
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
mkdir -p "${DEB_ROOT}/opt/el-arriero-mcp"
mkdir -p "${DEB_ROOT}/usr/bin"
mkdir -p "${DEB_ROOT}/usr/share/applications"
mkdir -p "${DEB_ROOT}/usr/share/icons/hicolor/scalable/apps"

# Copiar ejecutable, firma ExApp (.pta) e ícono
cp -f "${PROJECT_DIR}/dist/el-arriero-mcp" "${DEB_ROOT}/opt/el-arriero-mcp/el-arriero-mcp"
chmod 755 "${DEB_ROOT}/opt/el-arriero-mcp/el-arriero-mcp"
cp -f "${PROJECT_DIR}/pt-mcp-bridge.pta" "${DEB_ROOT}/opt/el-arriero-mcp/pt-mcp-bridge.pta"
cp -f "${PROJECT_DIR}/packaging/el-arriero-mcp.svg" "${DEB_ROOT}/usr/share/icons/hicolor/scalable/apps/el-arriero-mcp.svg"

# Enlaces simbólicos en /usr/bin
ln -sf /opt/el-arriero-mcp/el-arriero-mcp "${DEB_ROOT}/usr/bin/el-arriero-mcp"
ln -sf /opt/el-arriero-mcp/el-arriero-mcp "${DEB_ROOT}/usr/bin/pt-mcp-bridge"

# Lanzador de escritorio (.desktop)
cat > "${DEB_ROOT}/usr/share/applications/el-arriero-mcp.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=El Arriero MCP
GenericName=Puente MCP para Cisco Packet Tracer
Comment=Conecta agentes de IA con Cisco Packet Tracer mediante MCP y PTMP (Universidad de Caldas)
Exec=/usr/bin/el-arriero-mcp
Icon=el-arriero-mcp
Terminal=false
Categories=Network;Development;Education;
Keywords=Cisco;PacketTracer;MCP;AI;Redes;Arriero;Caldas;
EOF

# Archivo DEBIAN/control (sin conflictos de dpkg ni bloqueos por repositorios externos)
INSTALLED_SIZE="$(du -sk "${DEB_ROOT}" | cut -f1)"
cat > "${DEB_ROOT}/DEBIAN/control" <<EOF
Package: ${PKG_NAME}
Version: ${VERSION}
Section: net
Priority: optional
Architecture: ${ARCH}
Installed-Size: ${INSTALLED_SIZE}
Recommends: libxcb-cursor0, libgl1, libxkbcommon-x11-0
Provides: pt-mcp-bridge, el-arriero-mcp
Replaces: pt-mcp-bridge
Conflicts: pt-mcp-bridge
Maintainer: El Arriero MCP <noreply@ucaldas.edu.co>
Homepage: https://github.com/fernando-bedoya/MCP-Cisco-Packet-Tracer
Description: El Arriero MCP (PT-MCP-Bridge) - Puente MCP entre IA y Cisco Packet Tracer
 Puente nativo para Linux desarrollado en la Universidad de Caldas que conecta
 agentes de IA compatibles con Model Context Protocol (MCP) directamente con
 el motor interno de Cisco Packet Tracer a traves del protocolo PTMP.
 Incluye 99 herramientas de red (Capa 2, Capa 3, Servicios, Seguridad, WAN,
 Redes Moviles 3G/4G/LTE y Laboratorios Academicos).
EOF

# Script postinst para corregir permisos de /opt/pt/extensions y evitar 'Error Importing App Meta File'
cat > "${DEB_ROOT}/DEBIAN/postinst" <<'EOF'
#!/usr/bin/env bash
set -e
if [ -d "/opt/pt/extensions" ]; then
    chmod -R a+rwX /opt/pt/extensions 2>/dev/null || true
    rm -f /opt/pt/extensions/pt-mcp-bridge.pta 2>/dev/null || true
fi
for user_ext in /home/*/pt/extensions; do
    if [ -d "${user_ext}" ]; then
        rm -f "${user_ext}/pt-mcp-bridge.pta" 2>/dev/null || true
    fi
done
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications 2>/dev/null || true
fi
EOF
chmod 755 "${DEB_ROOT}/DEBIAN/postinst"

echo "==> [3/3] Generando paquete ${OUT_DEB}..."
find "${DEB_ROOT}" -type d -exec chmod 755 {} +
chmod 644 "${DEB_ROOT}/DEBIAN/control" "${DEB_ROOT}/opt/el-arriero-mcp/pt-mcp-bridge.pta" \
    "${DEB_ROOT}/usr/share/applications/el-arriero-mcp.desktop" \
    "${DEB_ROOT}/usr/share/icons/hicolor/scalable/apps/el-arriero-mcp.svg"
chmod 755 "${DEB_ROOT}/opt/el-arriero-mcp/el-arriero-mcp"
dpkg-deb --root-owner-group --build "${DEB_ROOT}" "${OUT_DEB}"
cp -f "${OUT_DEB}" "${PROJECT_DIR}/el-arriero-mcp_${VERSION}_${ARCH}.deb"
rm -rf "${PROJECT_DIR}/build" "${PROJECT_DIR}/el-arriero-mcp.spec"

echo ""
echo "========================================================================"
echo "  Paquete .deb autónomo generado correctamente:"
echo "  - ${PROJECT_DIR}/el-arriero-mcp_${VERSION}_${ARCH}.deb"
echo "  - ${OUT_DEB}"
echo "  Para instalarlo en Linux Mint / Ubuntu / Debian (doble clic o terminal):"
echo "  sudo dpkg -i el-arriero-mcp_${VERSION}_${ARCH}.deb"
echo "========================================================================"

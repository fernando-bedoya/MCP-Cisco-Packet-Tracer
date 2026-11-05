#!/usr/bin/env bash
# Script para compilar el paquete .deb y publicar una versión en GitHub Releases
# Uso: ./packaging/publish_release.sh 1.1.0
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

VERSION="${1:-1.0.0}"
VERSION="${VERSION#v}"
TAG="v${VERSION}"
DEB_FILE="${PROJECT_DIR}/dist/el-arriero-mcp_${VERSION}_amd64.deb"

echo "==> [1/3] Compilando paquete .deb para la versión ${VERSION}..."
VERSION="${VERSION}" ./packaging/build_deb.sh

echo "==> [2/3] Creando etiqueta Git ${TAG}..."
if ! git rev-parse "${TAG}" >/dev/null 2>&1; then
    git tag -a "${TAG}" -m "Release El Arriero MCP ${TAG}"
fi
git push origin "${TAG}"

echo "==> [3/3] Verificando GitHub CLI (gh)..."
if command -v gh >/dev/null 2>&1; then
    echo "Subiendo ${DEB_FILE} directamente a GitHub Releases (${TAG})..."
    gh release create "${TAG}" "${DEB_FILE}" "${PROJECT_DIR}/pt-mcp-bridge.pta" \
        --title "El Arriero MCP ${TAG}" \
        --generate-notes || \
    gh release upload "${TAG}" "${DEB_FILE}" "${PROJECT_DIR}/pt-mcp-bridge.pta" --clobber
    echo "✅ Release ${TAG} publicado con éxito."
else
    echo "ℹ️  Etiqueta ${TAG} enviada a GitHub."
    echo "   El workflow '.github/workflows/release.yml' compilará y adjuntará automáticamente"
    echo "   el instalador 'el-arriero-mcp_${VERSION}_amd64.deb' en la pestaña Releases de tu repositorio."
fi

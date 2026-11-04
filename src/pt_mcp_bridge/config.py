"""Constantes y valores por defecto de la aplicación."""
from __future__ import annotations

import sys
from pathlib import Path

DEFAULT_PT_HOST = "127.0.0.1"
DEFAULT_PT_PORT = 39000
DEFAULT_APP_ID = "dev.pktctl"
FALLBACK_APP_ID = "net.netacad.cisco.pt.ipctest"
DEFAULT_KEY = "cisco"
DEFAULT_MCP_HOST = "127.0.0.1"
DEFAULT_MCP_PORT = 8765
CONNECT_TIMEOUT_S = 5.0
REQUEST_TIMEOUT_S = 15.0
MAX_RECONNECT_DELAY_S = 30.0
PTA_FILENAME = "pt-mcp-bridge.pta"


def pta_file_path() -> Path:
    """Localiza `pt-mcp-bridge.pta` tanto desde código fuente como desde binario PyInstaller."""
    candidates = [
        Path.cwd() / PTA_FILENAME,
        Path(sys.executable).resolve().parent.parent / PTA_FILENAME,
        Path(__file__).resolve().parents[2] / PTA_FILENAME,
        Path.home() / "pt" / "extensions" / PTA_FILENAME,
    ]
    for path in candidates:
        if path.is_file():
            return path
    return Path.cwd() / PTA_FILENAME


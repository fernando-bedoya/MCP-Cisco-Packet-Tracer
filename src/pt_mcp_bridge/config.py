"""Constantes y valores por defecto de la aplicación (configurables por variables de entorno o .env)."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _load_dotenv() -> None:
    """Carga variables desde un archivo `.env` local si existe, sin sobreescribir el entorno."""
    for candidate in (Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"):
        if candidate.is_file():
            try:
                for raw_line in candidate.read_text(encoding="utf-8").splitlines():
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip("'\"")
                    if key:
                        os.environ.setdefault(key, value)
            except OSError:
                pass
            break


def _env_int(name: str, default: int) -> int:
    val = os.environ.get(name)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    val = os.environ.get(name)
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        return default


_load_dotenv()

DEFAULT_PT_HOST = os.environ.get("PT_HOST", "127.0.0.1")
DEFAULT_PT_PORT = _env_int("PT_PORT", 39000)
DEFAULT_APP_ID = os.environ.get("PT_APP_ID", "dev.pktctl")
FALLBACK_APP_ID = os.environ.get("PT_FALLBACK_APP_ID", "net.netacad.cisco.pt.ipctest")
DEFAULT_KEY = os.environ.get("PT_SHARED_KEY", "cisco")
DEFAULT_MCP_HOST = os.environ.get("MCP_HOST", "127.0.0.1")
DEFAULT_MCP_PORT = _env_int("MCP_PORT", 8765)
CONNECT_TIMEOUT_S = _env_float("PT_CONNECT_TIMEOUT_S", 5.0)
REQUEST_TIMEOUT_S = _env_float("PT_REQUEST_TIMEOUT_S", 15.0)
MAX_RECONNECT_DELAY_S = _env_float("PT_MAX_RECONNECT_DELAY_S", 30.0)
PTA_FILENAME = "pt-mcp-bridge.pta"


def pta_file_path() -> Path:
    """Localiza `pt-mcp-bridge.pta` en fuente, binario PyInstaller o instalación .deb."""
    candidates = [
        Path.cwd() / PTA_FILENAME,
        Path(sys.executable).resolve().parent / PTA_FILENAME,
        Path(sys.executable).resolve().parent.parent / PTA_FILENAME,
        Path("/opt/el-arriero-mcp") / PTA_FILENAME,
        Path("/usr/share/el-arriero-mcp") / PTA_FILENAME,
        Path(__file__).resolve().parents[2] / PTA_FILENAME,
    ]
    for path in candidates:
        if path.is_file():
            return path
    return Path("/opt/el-arriero-mcp") / PTA_FILENAME if Path("/opt/el-arriero-mcp").is_dir() else Path.cwd() / PTA_FILENAME

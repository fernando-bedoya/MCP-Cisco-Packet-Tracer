"""Entrypoint para PyInstaller / ejecución directa sin instalar el paquete."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from pt_mcp_bridge.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())


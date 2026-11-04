#!/usr/bin/env python3
"""Entrypoint para PyInstaller / ejecución directa.

Si el usuario ejecuta `python3 run.py` con el Python del sistema pero existe `.venv/bin/python`,
se re-ejecuta automáticamente dentro del entorno virtual para evitar errores PEP 668 / ModuleNotFoundError.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"

if (
    not getattr(sys, "frozen", False)
    and VENV_PYTHON.is_file()
    and Path(sys.executable).resolve() != VENV_PYTHON.resolve()
):
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])

sys.path.insert(0, str(ROOT / "src"))

from pt_mcp_bridge.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())

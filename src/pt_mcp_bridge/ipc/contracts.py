"""Contratos segregados de transporte e índice IPC (Principios SOLID: ISP y DIP)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pt_mcp_bridge.ipc.protocol import Step


@runtime_checkable
class IPCLogger(Protocol):
    """Contrato mínimo de registro de eventos (ISP)."""

    def log(self, level: str, message: str) -> None: ...


@runtime_checkable
class IPCInvoker(Protocol):
    """Contrato mínimo para invocar cadenas de pasos PTMP (ISP)."""

    def call(self, steps: list[Step], timeout: float = ...) -> Any: ...


@runtime_checkable
class IPCConnectionLifecycle(Protocol):
    """Contrato de ciclo de vida de conexión TCP/PTMP (ISP)."""

    @property
    def connected(self) -> bool: ...

    def connect(self, host: str, port: int, timeout: float = ...) -> None: ...

    def disconnect(self, quiet: bool = False) -> None: ...


@runtime_checkable
class IPCTransport(IPCInvoker, IPCLogger, IPCConnectionLifecycle, Protocol):
    """Contrato compuesto de transporte IPC completo (DIP / LSP)."""


@runtime_checkable
class IndexRepository(Protocol):
    """Abstracción para consultar el catálogo de clases, métodos y enums IPC (DIP)."""

    def load(self) -> dict[str, Any]: ...


class JsonIndexRepository:
    """Repositorio concreto con caché en memoria para `ipc_index.json` (SRP)."""

    _cache: dict[str, Any] | None = None

    def __init__(self, index_path: Path | None = None) -> None:
        self._path = index_path or (Path(__file__).resolve().parent.parent / "ipc_index.json")

    def load(self) -> dict[str, Any]:
        if JsonIndexRepository._cache is None:
            if self._path.is_file():
                JsonIndexRepository._cache = json.loads(self._path.read_text(encoding="utf-8"))
            else:
                JsonIndexRepository._cache = {"classes": {}, "enums": {}, "roots": {}}
        return JsonIndexRepository._cache

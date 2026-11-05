"""Clase base para servicios de dominio (Principios SOLID: SRP, ISP, DIP)."""
from __future__ import annotations

from typing import Any

from pt_mcp_bridge import calls
from pt_mcp_bridge.ipc import PTError
from pt_mcp_bridge.ipc.client import describe
from pt_mcp_bridge.ipc.contracts import IPCTransport
from pt_mcp_bridge.ipc.protocol import Step

COMMAND_STATUS: dict[int, str] = {
    0: "ok",
    1: "ambiguous (% Ambiguous command)",
    2: "invalid (% Invalid input detected)",
    3: "incomplete (% Incomplete command)",
    4: "not_implemented",
}

IOS_CAPABLE_KINDS: frozenset[str] = frozenset({
    "router",
    "switch",
    "multi_layer_switch",
    "switch3650",
    "asa",
})


class ValidationError(ValueError):
    """Argumentos inválidos en una operación de dominio."""


class DomainServiceBase:
    """Base inyectada con la abstracción `IPCTransport` (DIP) y caché de estado por sesión."""

    def __init__(self, client: IPCTransport) -> None:
        self._client = client
        # Cachés compartidos en la instancia del transporte para evitar llamadas IPC redundantes
        if not hasattr(client, "_console_ready_cache"):
            client._console_ready_cache = set()  # type: ignore[attr-defined]
        if not hasattr(client, "_device_kind_cache"):
            client._device_kind_cache = {}  # type: ignore[attr-defined]
        if not hasattr(client, "_used_ports_cache"):
            client._used_ports_cache = {}  # type: ignore[attr-defined]

    @property
    def _console_ready(self) -> set[str]:
        return self._client._console_ready_cache  # type: ignore[attr-defined]

    @property
    def _device_kinds(self) -> dict[str, str]:
        return self._client._device_kind_cache  # type: ignore[attr-defined]

    @property
    def _used_ports(self) -> dict[str, set[str]]:
        return self._client._used_ports_cache  # type: ignore[attr-defined]

    def _run(self, label: str, steps: list[Step]) -> Any:
        self._client.log("mcp", f"{label}  [{describe(steps)}]")
        try:
            return self._client.call(steps)
        except PTError as exc:
            self._client.log("error", f"{label} -> {exc}")
            raise

    def _ready_console(self, dev_name: str, *, force: bool = False) -> None:
        """Salta el arranque IOS (`skipBoot`) y responde 'no' al diálogo inicial solo una vez por equipo."""
        kind = self._device_kinds.get(dev_name)
        if kind is not None and kind not in IOS_CAPABLE_KINDS:
            return
        if not force and dev_name in self._console_ready:
            return
        try:
            self._run(f"skipBoot {dev_name}", calls.skip_boot(dev_name))
        except PTError:
            return
        try:
            prompt = str(self._run(f"getPrompt {dev_name}", calls.console_prompt(dev_name)) or "")
            if "initial configuration dialog" in prompt.lower():
                self._run(f"dialog no {dev_name}", calls.console_enter_raw(dev_name, "no"))
                self._run(f"dialog enter {dev_name}", calls.console_enter_raw(dev_name, ""))
            elif not prompt.strip():
                self._run(f"wake console {dev_name}", calls.console_enter_raw(dev_name, ""))
            self._console_ready.add(dev_name)
        except PTError:
            pass

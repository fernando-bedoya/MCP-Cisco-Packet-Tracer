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


class ValidationError(ValueError):
    """Argumentos inválidos en una operación de dominio."""


class DomainServiceBase:
    """Base inyectada con la abstracción `IPCTransport` (DIP)."""

    def __init__(self, client: IPCTransport) -> None:
        self._client = client

    def _run(self, label: str, steps: list[Step]) -> Any:
        self._client.log("mcp", f"{label}  [{describe(steps)}]")
        try:
            return self._client.call(steps)
        except PTError as exc:
            self._client.log("error", f"{label} -> {exc}")
            raise

    def _ready_console(self, dev_name: str) -> None:
        """Salta el arranque IOS (`skipBoot`) y responde 'no' al diálogo inicial si aparece."""
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
        except PTError:
            pass

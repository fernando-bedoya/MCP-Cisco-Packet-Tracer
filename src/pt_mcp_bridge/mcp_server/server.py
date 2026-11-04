"""Servidor MCP: expone las herramientas de Packet Tracer sobre PacketTracerService."""
from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from pt_mcp_bridge import config
from pt_mcp_bridge.ipc import PTError
from pt_mcp_bridge.service import PacketTracerService, ValidationError


def _safe(fn: Callable[[], str]) -> str:
    """Convierte errores esperados en texto claro para el LLM."""
    try:
        return fn()
    except (PTError, ValidationError) as exc:
        return f"ERROR: {exc}"


def build_mcp(service: PacketTracerService, host: str = config.DEFAULT_MCP_HOST,
              port: int = config.DEFAULT_MCP_PORT):
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("pt-mcp-bridge", host=host, port=port)

    @mcp.tool()
    def cpt_add_device(name: str, device_type: str = "router", model: str = "",
                       x: int = 200, y: int = 200) -> str:
        """Agrega un nodo al espacio de trabajo de Packet Tracer.
        - device_type: router | switch | multi_layer_switch | switch3650 | pc | laptop | server | hub | cloud | ap | wireless_router | printer | asa
        - model: modelo exacto de PT (ej. '2911', '1941', '2960-24TT', '3560-24PS', 'PC-PT', 'Server-PT'); si se deja vacío usa el predeterminado del tipo.
        Salta automáticamente el arranque IOS (`skipBoot`) y cierra el diálogo inicial."""
        return _safe(lambda: service.add_device(name, device_type, model, x, y))

    @mcp.tool()
    def cpt_remove_device(name: str) -> str:
        """Elimina un dispositivo del espacio de trabajo por su nombre."""
        return _safe(lambda: service.remove_device(name))

    @mcp.tool()
    def cpt_connect_ports(device_a: str, port_a: str, device_b: str, port_b: str,
                          cable: str = "auto") -> str:
        """Conecta dos interfaces físicas mediante un cable.
        - cable: auto | straight | cross | crossover | serial | console | rollover | fiber | phone | coaxial | usb
          ('auto' elige automáticamente straight o cross según las capas CCNA de los dispositivos, o serial si el puerto es Serial).
        - Ejemplos de puertos: 'GigabitEthernet0/0', 'FastEthernet0/1', 'Serial0/0/0', 'FastEthernet0'."""
        return _safe(lambda: service.connect_ports(device_a, port_a, device_b, port_b, cable))

    @mcp.tool()
    def cpt_send_cli_command(device: str, command: str, mode: str = "") -> str:
        """Ejecuta uno o varios comandos (separados por salto de línea) en la consola Cisco IOS de un router o switch.
        - Ejemplos: 'interface GigabitEthernet0/0\\nip address 192.168.1.1 255.255.255.0\\nno shutdown' o 'show ip interface brief'.
        - El modo ('user', 'enable', 'global' o '' para mantener el submodo actual) se conserva entre llamadas."""
        return _safe(lambda: service.send_cli(device, command, mode))

    @mcp.tool()
    def cpt_configure_ios(device: str, commands: list[str], save: bool = True) -> str:
        """Aplica una lista de comandos de configuración IOS en un router o switch entrando automáticamente a `configure terminal`,
        siguiendo submodos (`interface ...`, `ip dhcp pool ...`, `router ospf ...`), saliendo con `end` y guardando con `write memory`."""
        return _safe(lambda: service.configure_ios(device, commands, save))

    @mcp.tool()
    def cpt_configure_host(device: str, ip: str = "", mask: str = "", gateway: str = "",
                           dns: str = "", dhcp: bool = False, port: str = "FastEthernet0") -> str:
        """Configura IPv4 estática (ip, mask, gateway, dns) o activa DHCP (`dhcp=True`) en un PC, Laptop o Server."""
        return _safe(lambda: service.configure_host(device, ip, mask, gateway, dns, dhcp, port))

    @mcp.tool()
    def cpt_list_ports(device: str) -> str:
        """Lista todas las interfaces de un dispositivo con su estado (up/protocol_up), IP y máscara."""
        return _safe(lambda: service.list_ports(device))

    @mcp.tool()
    def cpt_fast_forward() -> str:
        """Pulsa el botón 'Fast Forward Time' en Packet Tracer para que STP, DHCP y rutas converjan de inmediato."""
        return _safe(service.fast_forward)

    @mcp.tool()
    def cpt_get_topology() -> str:
        """Lee todos los dispositivos y enlaces (cables) actualmente presentes en el espacio de trabajo."""
        return _safe(service.topology)

    @mcp.tool()
    def cpt_raw_ipc(root: str, steps: list[dict[str, Any]]) -> str:
        """Invoca cualquier método de la API IPC de Packet Tracer validando los tipos contra el índice oficial (`ipc_index.json`).
        Ejemplo: root='network', steps=[{'method': 'getDevice', 'args': ['R1']}, {'method': 'getPort', 'args': ['GigabitEthernet0/0']}, {'method': 'getMacAddress', 'args': []}]."""
        return _safe(lambda: service.raw_ipc_call(root, steps))

    @mcp.tool()
    def cpt_save_file() -> str:
        """Guarda los cambios directamente en el archivo .pkt o .pka abierto en Packet Tracer."""
        return _safe(service.save_file)

    @mcp.tool()
    def cpt_get_instructions() -> str:
        """Lee el texto e instrucciones completas de la ventana de actividad (.pka) de Packet Tracer."""
        return _safe(service.get_instructions)

    @mcp.tool()
    def cpt_ping(device: str, target_ip: str) -> str:
        """Ejecuta un ping desde un router, switch o host hacia una dirección IP de destino y devuelve el resultado."""
        return _safe(lambda: service.ping(device, target_ip))

    @mcp.tool()
    def cpt_audit_network() -> str:
        """Audita de forma completa e instantánea toda la red (todos los routers, interfaces, rutas y hosts con sus IPs)."""
        return _safe(service.audit_network)

    return mcp


class McpServerThread(threading.Thread):
    """Servidor MCP streamable-http en segundo plano."""

    def __init__(self, service: PacketTracerService, host: str, port: int) -> None:
        super().__init__(daemon=True, name="mcp-server")
        self._service, self.host, self.port = service, host, port

    def run(self) -> None:
        log = self._service._client.log
        try:
            log("info", f"Servidor MCP en http://{self.host}:{self.port}/mcp")
            build_mcp(self._service, self.host, self.port).run(transport="streamable-http")
        except Exception as exc:  # noqa: BLE001
            log("error", f"Servidor MCP detenido: {exc}")

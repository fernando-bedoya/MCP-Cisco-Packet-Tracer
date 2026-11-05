"""Fachada principal de servicio (SOLID Facade): compone los servicios de dominio sobre Cisco Packet Tracer."""
from __future__ import annotations

import json
from typing import Any

from pt_mcp_bridge.ipc import IndexRepository, IPCTransport, JsonIndexRepository
from pt_mcp_bridge.services import (
    COMMAND_STATUS,
    AcademicLabService,
    DiagnosticsService,
    IosCliService,
    MacroRegistry,
    MetaCatalogService,
    MobileNetworkService,
    NetworkServicesManager,
    RoutingService,
    SecurityService,
    SwitchingService,
    TopologyService,
    ValidationError,
    WanWirelessService,
)

_DEFAULT_INDEX_REPO = JsonIndexRepository()


def _load_ipc_index() -> dict[str, Any]:
    """Función auxiliar de compatibilidad que delega en `JsonIndexRepository`."""
    return _DEFAULT_INDEX_REPO.load()


class PacketTracerService:
    """Fachada unificada (Patrón Facade + Composición SOLID) para las 99 herramientas MCP.

    Cumple con los 5 principios SOLID:
    - **SRP**: Cada dominio de red vive en su propia clase especializada dentro de `pt_mcp_bridge.services`.
    - **OCP**: El registro de macros (`MacroRegistry`) permite añadir nuevas topologías predefinidas sin modificar esta clase.
    - **LSP**: Todos los servicios de dominio heredan de `DomainServiceBase` y respetan el contrato de transporte IPC.
    - **ISP**: Los servicios dependen únicamente de las interfaces segregadas (`IPCTransport`, `IndexRepository`).
    - **DIP**: Tanto el transporte IPC como el repositorio del índice (`IndexRepository`) se inyectan por constructor.
    """

    def __init__(self, client: IPCTransport, index_repo: IndexRepository | None = None) -> None:
        self._client = client
        self._index_repo = index_repo or _DEFAULT_INDEX_REPO

        # Instanciación e inyección de dependencias por dominio (SRP + DIP)
        self.cli = IosCliService(client)
        self.topology_svc = TopologyService(client, self.cli)
        self.switching = SwitchingService(client, self.cli)
        self.routing = RoutingService(client, self.cli)
        self.network_services = NetworkServicesManager(client, self.cli)
        self.security = SecurityService(client, self.cli)
        self.wan_wireless = WanWirelessService(client, self.cli)
        self.diagnostics = DiagnosticsService(client, self.cli, self.topology_svc)
        self.labs = AcademicLabService(client, self.cli, self.topology_svc)
        self.mobile = MobileNetworkService(client, self.cli, self.topology_svc, self.diagnostics)
        self.meta = MetaCatalogService(
            client=client,
            index_repo=self._index_repo,
            dispatcher=lambda name: getattr(self, name, None),
        )

        self._domain_services = (
            self.cli,
            self.topology_svc,
            self.switching,
            self.routing,
            self.network_services,
            self.security,
            self.wan_wireless,
            self.diagnostics,
            self.labs,
            self.mobile,
            self.meta,
        )
        self._register_default_macros(self.meta.macros)

    def _register_default_macros(self, registry: MacroRegistry) -> None:
        """Registra las macros académicas predeterminadas en `MacroRegistry` (OCP)."""

        def _macro_office_3vlans_roas(p: dict[str, Any]) -> str:
            router = p.get("router", "R1")
            switch = p.get("switch", "SW1")
            self.topology_svc.add_device(router, "router", "2911", 200, 150)
            self.topology_svc.add_device(switch, "switch", "2960-24TT", 400, 150)
            self.topology_svc.connect_ports(router, "GigabitEthernet0/0", switch, "GigabitEthernet0/1", "straight")
            for vid, vname in ((10, "ADMIN"), (20, "VENTAS"), (30, "INVITADOS")):
                self.switching.create_vlan(switch, vid, vname)
            self.switching.configure_trunk(switch, "GigabitEthernet0/1")
            self.routing.configure_intervlan(router, "GigabitEthernet0/0", [
                {"vlan": 10, "ip": "192.168.10.1", "mask": "255.255.255.0"},
                {"vlan": 20, "ip": "192.168.20.1", "mask": "255.255.255.0"},
                {"vlan": 30, "ip": "192.168.30.1", "mask": "255.255.255.0"},
            ])
            return json.dumps({"macro": "office_3vlans_roas", "router": router, "switch": switch, "vlans": [10, 20, 30]}, ensure_ascii=False)

        def _macro_wan_ospf_pair(p: dict[str, Any]) -> str:
            r1, r2 = p.get("r1", "R1"), p.get("r2", "R2")
            self.topology_svc.add_device(r1, "router", "2911", 200, 200)
            self.topology_svc.add_device(r2, "router", "2911", 450, 200)
            self.topology_svc.connect_ports(r1, "GigabitEthernet0/0", r2, "GigabitEthernet0/0", "cross")
            self.cli.configure_ios(r1, ["interface GigabitEthernet0/0", "ip address 10.0.0.1 255.255.255.252", "no shutdown"], save=True)
            self.cli.configure_ios(r2, ["interface GigabitEthernet0/0", "ip address 10.0.0.2 255.255.255.252", "no shutdown"], save=True)
            self.routing.configure_ospf(r1, 1, [{"network": "10.0.0.0", "wildcard": "0.0.0.3", "area": 0}])
            self.routing.configure_ospf(r2, 1, [{"network": "10.0.0.0", "wildcard": "0.0.0.3", "area": 0}])
            return json.dumps({"macro": "wan_ospf_pair", "routers": [r1, r2]}, ensure_ascii=False)

        def _macro_mobile_lte_core(p: dict[str, Any]) -> str:
            return self.mobile.deploy_cellular_topology(
                co_server=p.get("co_server", "CO-Core"),
                isp_router=p.get("isp_router", "R-ISP"),
                cell_towers=int(p.get("cell_towers", 2)),
                smartphones=int(p.get("smartphones", 2)),
                tablets=int(p.get("tablets", 1)),
            )

        registry.register("office_3vlans_roas", _macro_office_3vlans_roas)
        registry.register("wan_ospf_pair", _macro_wan_ospf_pair)
        registry.register("mobile_lte_core", _macro_mobile_lte_core)

    def __getattr__(self, name: str) -> Any:
        """Delega dinámicamente cualquier método de dominio al servicio especializado correspondiente."""
        for svc in self._domain_services:
            attr = getattr(svc, name, None)
            if callable(attr):
                return attr
        raise AttributeError(f"'{type(self).__name__}' no tiene el método '{name}'")


__all__ = ["COMMAND_STATUS", "PacketTracerService", "ValidationError", "_load_ipc_index"]

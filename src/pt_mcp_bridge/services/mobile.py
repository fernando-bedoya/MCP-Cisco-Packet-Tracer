"""Servicio de dominio: Redes Móviles y Celulares (3G/4G/LTE, Handover y Bluetooth/BLE) (SRP)."""
from __future__ import annotations

import json
from typing import Any

from pt_mcp_bridge import calls
from pt_mcp_bridge.ipc import IPCTransport, PTError
from pt_mcp_bridge.ipc.protocol import Arg, Step
from pt_mcp_bridge.services.base import DomainServiceBase
from pt_mcp_bridge.services.diagnostics import DiagnosticsService
from pt_mcp_bridge.services.ios_cli import IosCliService
from pt_mcp_bridge.services.topology import TopologyService


class MobileNetworkService(DomainServiceBase):
    """Encapsula el despliegue, configuración y simulación de redes celulares 3G/4G/LTE y Bluetooth/BLE."""

    def __init__(
        self,
        client: IPCTransport,
        cli: IosCliService,
        topology_svc: TopologyService,
        diagnostics_svc: DiagnosticsService,
    ) -> None:
        super().__init__(client)
        self._cli = cli
        self._topology = topology_svc
        self._diagnostics = diagnostics_svc

    def add_mobile_device(self, name: str, role: str = "smartphone",
                          model: str = "", x: int = 250, y: int = 250) -> str:
        """Agrega un nodo del segmento móvil (`smartphone`, `tablet`, `cell_tower`, `central_office_server`, `coaxial_splitter`, `lap`)."""
        role_clean = role.lower().strip()
        allowed = {"smartphone", "tablet", "tablet_pc", "pda", "cell_tower", "central_office_server", "co_server", "coaxial_splitter", "lap"}
        if role_clean not in allowed:
            role_clean = "smartphone"
        return self._topology.add_device(name, role_clean, model, int(x), int(y))

    def connect_cell_tower_to_co(self, cell_tower: str, co_server: str,
                                 co_port: str = "Coaxial0",
                                 tower_port: str = "Coaxial0",
                                 backbone_router: str = "",
                                 router_port: str = "GigabitEthernet0/0") -> str:
        """Conecta una antena `Cell Tower` con el `Central Office Server` por cable coaxial y opcionalmente el `Backbone` hacia un router IP."""
        coax_link = json.loads(
            self._topology.connect_ports(cell_tower.strip(), tower_port.strip(), co_server.strip(), co_port.strip(), "coaxial")
        )
        backbone_link = None
        if backbone_router.strip():
            backbone_link = json.loads(
                self._topology.connect_ports(co_server.strip(), "Backbone", backbone_router.strip(), router_port.strip(), "straight")
            )
        return json.dumps({
            "cell_tower": cell_tower.strip(),
            "co_server": co_server.strip(),
            "coaxial_link": coax_link,
            "backbone_link": backbone_link,
        }, ensure_ascii=False)

    def configure_cellular_interface(self, device: str, dhcp: bool = True,
                                     ip: str = "", mask: str = "", gateway: str = "",
                                     dns: str = "", port: str = "3G/4G Cell1",
                                     disable_wifi: bool = True,
                                     pap_chap_user: str = "", pap_chap_password: str = "",
                                     auth_mode: str = "chap") -> str:
        """Configura la interfaz celular (`3G/4G Cell1`) de un Smartphone, Tablet o Router celular."""
        device = device.strip()
        port = port.strip() or "3G/4G Cell1"

        if disable_wifi:
            try:
                self._run(f"wifi off {device}", calls.set_port_power(device, "Wireless0", False))
            except PTError:
                pass
        try:
            self._run(f"cell on {device}:{port}", calls.set_port_power(device, port, True))
        except PTError:
            pass

        host_cfg = json.loads(self._cli.configure_host(device, ip=ip, mask=mask, gateway=gateway, dns=dns, dhcp=dhcp, port=port))

        if pap_chap_user.strip() and pap_chap_password.strip():
            try:
                if auth_mode.lower().strip() == "pap":
                    pproc = calls.device_process(device, "PAPProcess")
                    self._run(f"pap user {device}", pproc + [Step("setSentUserName", (Arg.string(pap_chap_user.strip()),))])
                    self._run(f"pap pass {device}", pproc + [Step("setSentPassword", (Arg.string(pap_chap_password.strip()),))])
                else:
                    cproc = calls.device_process(device, "CHAPProcess")
                    self._run(f"chap user {device}", cproc + [Step("setUserName", (Arg.string(pap_chap_user.strip()),))])
                    self._run(f"chap pass {device}", cproc + [Step("setPassword", (Arg.string(pap_chap_password.strip()),))])
            except PTError:
                pass

        return json.dumps({
            "device": device,
            "cellular_port": port,
            "wifi_disabled": disable_wifi,
            "config": host_cfg,
        }, ensure_ascii=False)

    def configure_mobile_wifi_toggle(self, device: str, active_radio: str = "cellular") -> str:
        """Conmuta entre el radio celular (`3G/4G Cell1`) y el radio Wi-Fi (`Wireless0`) en un Smartphone o Tablet."""
        device = device.strip()
        use_cell = active_radio.lower().strip() in ("cellular", "cell", "3g", "4g", "lte")
        try:
            self._run(f"cell power {device}={use_cell}", calls.set_port_power(device, "3G/4G Cell1", use_cell))
        except PTError:
            pass
        try:
            self._run(f"wifi power {device}={not use_cell}", calls.set_port_power(device, "Wireless0", not use_cell))
        except PTError:
            pass
        return json.dumps({
            "device": device,
            "active_radio": "cellular" if use_cell else "wifi",
            "cellular_power": use_cell,
            "wifi_power": not use_cell,
        }, ensure_ascii=False)

    def deploy_cellular_topology(self, co_server: str = "CO-Core",
                                 isp_router: str = "R-ISP",
                                 cell_towers: int = 2,
                                 smartphones: int = 2,
                                 tablets: int = 1,
                                 backbone_subnet: str = "172.16.0.0",
                                 backbone_gateway: str = "172.16.0.1",
                                 backbone_mask: str = "255.255.255.0",
                                 dns_ip: str = "8.8.8.8") -> str:
        """Construye una arquitectura de red móvil 3G/4G/LTE completa."""
        self._topology.add_device(isp_router, "router", "2911", 150, 220)
        self._topology.add_device(co_server, "central_office_server", "Central-Office-Server", 360, 220)
        self._topology.connect_ports(co_server, "Backbone", isp_router, "GigabitEthernet0/0", "straight")

        self._cli.configure_ios(isp_router, [
            f"hostname {isp_router}",
            f"ip dhcp excluded-address {backbone_gateway}",
            "ip dhcp pool MOBILE_CORE_POOL",
            f"network {backbone_subnet} {backbone_mask}",
            f"default-router {backbone_gateway}",
            f"dns-server {dns_ip}",
            "exit",
            "interface GigabitEthernet0/0",
            f"ip address {backbone_gateway} {backbone_mask}",
            "no shutdown",
        ], save=True)

        towers_created = []
        num_towers = max(1, min(6, int(cell_towers)))
        for idx in range(num_towers):
            tname = f"Torre-Celular-{idx + 1}"
            ty = 110 + idx * 200
            self._topology.add_device(tname, "cell_tower", "Cell-Tower", 580, ty)
            self._topology.connect_ports(tname, "Coaxial0", co_server, f"Coaxial{idx}", "coaxial")
            towers_created.append(tname)

        ues_created = []
        for idx in range(max(0, int(smartphones))):
            sname = f"Smartphone-{idx + 1}"
            sy = 90 + idx * 140
            self._topology.add_device(sname, "smartphone", "SMARTPHONE-PT", 800, sy)
            self.configure_cellular_interface(sname, dhcp=True, disable_wifi=True)
            ues_created.append(sname)

        for idx in range(max(0, int(tablets))):
            tbname = f"Tablet-{idx + 1}"
            tby = 260 + idx * 140
            self._topology.add_device(tbname, "tablet", "TabletPC-PT", 820, tby)
            self.configure_cellular_interface(tbname, dhcp=True, disable_wifi=True)
            ues_created.append(tbname)

        for _ in range(4):
            self._cli.fast_forward()

        return json.dumps({
            "isp_router": isp_router,
            "central_office_server": co_server,
            "cell_towers": towers_created,
            "mobile_devices": ues_created,
            "backbone_gateway": backbone_gateway,
        }, ensure_ascii=False)

    def simulate_mobile_handover(self, device: str, start_x: int, start_y: int,
                                 end_x: int, end_y: int, steps: int = 4,
                                 ping_target: str = "") -> str:
        """Simula el desplazamiento físico (roaming/handover entre antenas celulares) de un Smartphone o Tablet."""
        device = device.strip()
        n = max(1, int(steps))
        trajectory = []
        for i in range(n + 1):
            ratio = i / n
            cx = round(start_x + (end_x - start_x) * ratio)
            cy = round(start_y + (end_y - start_y) * ratio)
            self._topology.move_device(device, cx, cy)
            self._cli.fast_forward()
            step_info: dict[str, Any] = {"step": i, "x": cx, "y": cy}
            if ping_target.strip():
                ping_res = json.loads(self._diagnostics.ping(device, ping_target.strip()))
                step_info["ping_success"] = bool(ping_res.get("success"))
            trajectory.append(step_info)

        return json.dumps({
            "device": device,
            "steps": len(trajectory),
            "trajectory": trajectory,
        }, ensure_ascii=False)

    def set_mobile_velocity(self, device: str, vx: float = 0.0, vy: float = 0.0) -> str:
        """Asigna un vector de velocidad `(vx, vy)` a un dispositivo móvil en el lienzo (`ComponentItem.setVelocity`)."""
        device = device.strip()
        self._run(
            f"velocity {device}=({vx},{vy})",
            calls.component_item(device) + [Step("setVelocity", (Arg.double(float(vx)), Arg.double(float(vy))))],
        )
        return json.dumps({"device": device, "vx": float(vx), "vy": float(vy)}, ensure_ascii=False)

    def configure_bluetooth(self, device: str, enabled: bool = True,
                            discoverable: bool = True, pair_mac: str = "") -> str:
        """Configura Bluetooth en un Smartphone, Tablet, Laptop o SBC (`BluetoothManager`)."""
        device = device.strip()
        try:
            self._run(f"bt port {device}={enabled}", calls.set_port_power(device, "Bluetooth0", enabled))
        except PTError:
            pass
        bt_proc = calls.device_process(device, "BluetoothManager")
        try:
            self._run(f"bt discoverable {device}", bt_proc + [Step("setDiscoverable", (Arg.boolean(discoverable),))])
            self._run(f"bt broadcast {device}", bt_proc + [Step("enableBroadcast", (Arg.boolean(enabled),))])
            if enabled:
                self._run(f"bt discover {device}", bt_proc + [Step("discover")])
            if pair_mac.strip():
                self._run(f"bt pair {device}->{pair_mac}", bt_proc + [Step("pair", (Arg.mac(pair_mac.strip()),))])
        except PTError:
            pass
        return json.dumps({
            "device": device,
            "bluetooth_enabled": enabled,
            "discoverable": discoverable,
            "paired_mac": pair_mac or None,
        }, ensure_ascii=False)

    def configure_ble_beacon(self, device: str, enabled: bool = True,
                             beacon_uuid: str = "{00000000-0000-0000-0000-000000000001}",
                             beacon_data: str = "Caldas-BLE-Beacon",
                             frequency_ms: int = 1000) -> str:
        """Configura la emisión de balizas Bluetooth Low Energy (BLE Beacon) en un equipo móvil o IoT."""
        device = device.strip()
        bt_proc = calls.device_process(device, "BluetoothManager")
        self._run(f"ble broadcast {device}={enabled}", bt_proc + [Step("setBeaconBroadcasting", (Arg.boolean(enabled),))])
        self._run(f"ble freq {device}={frequency_ms}", bt_proc + [Step("setBeaconFrequency", (Arg.integer(int(frequency_ms)),))])
        self._run(f"ble uuid {device}", bt_proc + [Step("setBeaconUuid", (Arg.uuid(beacon_uuid.strip()),))])
        self._run(f"ble data {device}", bt_proc + [Step("setBeaconData", (Arg.qstring(beacon_data),))])
        return json.dumps({
            "device": device,
            "ble_broadcasting": enabled,
            "uuid": beacon_uuid,
            "data": beacon_data,
            "frequency_ms": int(frequency_ms),
        }, ensure_ascii=False)

    def audit_mobile_network(self) -> str:
        """Audita el segmento de red móvil: Central Office Servers, Cell Towers, enlaces coaxiales/Backbone y equipos móviles."""
        topo = json.loads(self._topology.topology())
        co_servers = []
        cell_towers = []
        mobile_endpoints = []

        for d in topo.get("devices", []):
            name, kind = d["name"], d.get("kind", "")
            if kind == "central_office_server":
                ports = json.loads(self._cli.list_ports(name)).get("ports", [])
                co_servers.append({"name": name, "x": d["x"], "y": d["y"], "ports": ports})
            elif kind == "cell_tower":
                ports = json.loads(self._cli.list_ports(name)).get("ports", [])
                cell_towers.append({"name": name, "x": d["x"], "y": d["y"], "ports": ports})
            elif kind in ("smartphone", "tablet"):
                ports = json.loads(self._cli.list_ports(name)).get("ports", [])
                cell_port = next((p for p in ports if "Cell" in (p.get("name") or "")), None)
                wifi_port = next((p for p in ports if "Wireless" in (p.get("name") or "")), None)
                mobile_endpoints.append({
                    "name": name,
                    "kind": kind,
                    "x": d["x"],
                    "y": d["y"],
                    "cellular": cell_port,
                    "wifi": wifi_port,
                })

        coaxial_links = [lnk for lnk in topo.get("links", []) if lnk.get("cable") == "coaxial"]
        return json.dumps({
            "central_office_servers": co_servers,
            "cell_towers": cell_towers,
            "mobile_endpoints": mobile_endpoints,
            "coaxial_links": coaxial_links,
        }, ensure_ascii=False)

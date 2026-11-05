"""Servicio de Capa 3 — Enrutamiento (SRP)."""
from __future__ import annotations

import json
import re
from typing import Any

from pt_mcp_bridge.ipc.contracts import IPCTransport
from pt_mcp_bridge.services.base import DomainServiceBase
from pt_mcp_bridge.services.ios_cli import IosCliService


class RoutingService(DomainServiceBase):
    """Gestiona rutas estáticas, OSPF, EIGRP, RIP, BGP, Inter-VLAN ROAS, SVI, IPv6, HSRP/VRRP y tablas de rutas."""

    def __init__(self, client: IPCTransport, cli_service: IosCliService) -> None:
        super().__init__(client)
        self._cli = cli_service

    def configure_static_route(self, device: str, network: str, mask: str,
                               next_hop_or_interface: str, admin_distance: int = 0) -> str:
        cmd = f"ip route {network.strip()} {mask.strip()} {next_hop_or_interface.strip()}"
        if int(admin_distance) > 0:
            cmd += f" {int(admin_distance)}"
        return self._cli.configure_ios(device, [cmd], save=True)

    def configure_ospf(self, device: str, process_id: int = 1,
                       networks: list[dict[str, Any]] | None = None,
                       router_id: str = "", passive_interfaces: list[str] | None = None,
                       default_originate: bool = False) -> str:
        cmds = [f"router ospf {int(process_id)}"]
        if router_id.strip():
            cmds.append(f"router-id {router_id.strip()}")
        for net in networks or []:
            cmds.append(f"network {net['network']} {net['wildcard']} area {net.get('area', 0)}")
        for intf in passive_interfaces or []:
            cmds.append(f"passive-interface {intf.strip()}")
        if default_originate:
            cmds.append("default-information originate")
        return self._cli.configure_ios(device, cmds, save=True)

    def configure_eigrp(self, device: str, as_number: int = 100,
                        networks: list[str] | None = None,
                        no_auto_summary: bool = True,
                        passive_interfaces: list[str] | None = None) -> str:
        cmds = [f"router eigrp {int(as_number)}"]
        for net in networks or []:
            cmds.append(f"network {net.strip()}")
        if no_auto_summary:
            cmds.append("no auto-summary")
        for intf in passive_interfaces or []:
            cmds.append(f"passive-interface {intf.strip()}")
        return self._cli.configure_ios(device, cmds, save=True)

    def configure_rip(self, device: str, networks: list[str] | None = None,
                      version: int = 2, no_auto_summary: bool = True,
                      default_originate: bool = False) -> str:
        cmds = ["router rip", f"version {int(version)}"]
        for net in networks or []:
            cmds.append(f"network {net.strip()}")
        if no_auto_summary:
            cmds.append("no auto-summary")
        if default_originate:
            cmds.append("default-information originate")
        return self._cli.configure_ios(device, cmds, save=True)

    def configure_bgp(self, device: str, as_number: int,
                      neighbors: list[dict[str, Any]],
                      networks: list[dict[str, str]] | None = None,
                      router_id: str = "") -> str:
        cmds = [f"router bgp {int(as_number)}"]
        if router_id.strip():
            cmds.append(f"bgp router-id {router_id.strip()}")
        for nb in neighbors:
            cmds.append(f"neighbor {nb['ip']} remote-as {nb['remote_as']}")
        for net in networks or []:
            if net.get("mask"):
                cmds.append(f"network {net['network']} mask {net['mask']}")
            else:
                cmds.append(f"network {net['network']}")
        return self._cli.configure_ios(device, cmds, save=True)

    def configure_intervlan(self, device: str, parent_interface: str,
                            subinterfaces: list[dict[str, Any]]) -> str:
        parent = parent_interface.strip()
        cmds = [f"interface {parent}", "no shutdown", "exit"]
        for sub in subinterfaces:
            vlan = int(sub["vlan"])
            encap = f"encapsulation dot1Q {vlan}" + (" native" if sub.get("native") else "")
            cmds.extend([
                f"interface {parent}.{vlan}",
                encap,
                f"ip address {sub['ip']} {sub['mask']}",
                "exit",
            ])
        return self._cli.configure_ios(device, cmds, save=True)

    def configure_svi(self, device: str, vlan_id: int, ip: str, mask: str,
                      enable_routing: bool = True, helper_address: str = "") -> str:
        cmds: list[str] = []
        if enable_routing:
            cmds.append("ip routing")
        cmds.extend([
            f"interface Vlan{int(vlan_id)}",
            f"ip address {ip.strip()} {mask.strip()}",
        ])
        if helper_address.strip():
            cmds.append(f"ip helper-address {helper_address.strip()}")
        cmds.append("no shutdown")
        return self._cli.configure_ios(device, cmds, save=True)

    def configure_ipv6(self, device: str, interface: str, ipv6_address: str,
                       enable_unicast_routing: bool = True, link_local: str = "",
                       static_routes: list[dict[str, str]] | None = None) -> str:
        cmds: list[str] = []
        if enable_unicast_routing:
            cmds.append("ipv6 unicast-routing")
        cmds.append(f"interface {interface.strip()}")
        if link_local.strip():
            cmds.append(f"ipv6 address {link_local.strip()} link-local")
        cmds.extend([
            f"ipv6 address {ipv6_address.strip()}",
            "no shutdown",
            "exit",
        ])
        for rt in static_routes or []:
            cmds.append(f"ipv6 route {rt['prefix']} {rt['next_hop']}")
        return self._cli.configure_ios(device, cmds, save=True)

    def configure_hsrp(self, device: str, interface: str, group: int,
                       virtual_ip: str, priority: int = 100, preempt: bool = True) -> str:
        cmds = [
            f"interface {interface.strip()}",
            f"standby {int(group)} ip {virtual_ip.strip()}",
            f"standby {int(group)} priority {int(priority)}",
        ]
        if preempt:
            cmds.append(f"standby {int(group)} preempt")
        return self._cli.configure_ios(device, cmds, save=True)

    def configure_vrrp(self, device: str, interface: str, group: int,
                       virtual_ip: str, priority: int = 100, preempt: bool = True) -> str:
        cmds = [
            f"interface {interface.strip()}",
            f"vrrp {int(group)} ip {virtual_ip.strip()}",
            f"vrrp {int(group)} priority {int(priority)}",
        ]
        if preempt:
            cmds.append(f"vrrp {int(group)} preempt")
        return self._cli.configure_ios(device, cmds, save=True)

    def show_routing_table(self, device: str) -> str:
        res = json.loads(self._cli.send_cli(device, "show ip route", mode="enable"))
        out = res.get("output", "")
        routes = []
        for line in out.splitlines():
            m = re.match(
                r"^\s*([A-Z*]{1,4})\s+(\d+\.\d+\.\d+\.\d+(?:/\d+)?)\s*(?:\[\d+/\d+\]\s+via\s+(\d+\.\d+\.\d+\.\d+))?.*?(?:,\s*([A-Za-z0-9/.-]+))?\s*$",
                line,
            )
            if m:
                routes.append({
                    "code": m.group(1).strip(),
                    "network": m.group(2),
                    "next_hop": m.group(3),
                    "interface": m.group(4),
                    "raw_line": line.strip(),
                })
        return json.dumps({"device": device, "routes": routes, "raw": out}, ensure_ascii=False)

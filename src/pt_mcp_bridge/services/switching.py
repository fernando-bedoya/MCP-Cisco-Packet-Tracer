"""Servicio de Capa 2 — Switching (SRP)."""
from __future__ import annotations

import json
import re

from pt_mcp_bridge.ipc.contracts import IPCTransport
from pt_mcp_bridge.services.base import DomainServiceBase
from pt_mcp_bridge.services.ios_cli import IosCliService


class SwitchingService(DomainServiceBase):
    """Gestiona VLANs, puertos de acceso/troncales, EtherChannel, STP, Port Security, tablas MAC y VTP."""

    def __init__(self, client: IPCTransport, cli_service: IosCliService) -> None:
        super().__init__(client)
        self._cli = cli_service

    def create_vlan(self, device: str, vlan_id: int, name: str = "") -> str:
        cmds = [f"vlan {int(vlan_id)}"]
        if name.strip():
            cmds.append(f"name {name.strip()}")
        cmds.append("exit")
        return self._cli.configure_ios(device, cmds, save=True)

    def assign_vlan_port(self, device: str, port: str, vlan_id: int, voice_vlan_id: int = 0) -> str:
        cmds = [
            f"interface {port.strip()}",
            "switchport mode access",
            f"switchport access vlan {int(vlan_id)}",
        ]
        if int(voice_vlan_id) > 0:
            cmds.append(f"switchport voice vlan {int(voice_vlan_id)}")
        return self._cli.configure_ios(device, cmds, save=True)

    def configure_trunk(self, device: str, port: str, native_vlan: int = 0,
                        allowed_vlans: str = "", encapsulation_dot1q: bool = False) -> str:
        cmds = [f"interface {port.strip()}"]
        if encapsulation_dot1q:
            cmds.append("switchport trunk encapsulation dot1q")
        cmds.append("switchport mode trunk")
        if int(native_vlan) > 0:
            cmds.append(f"switchport trunk native vlan {int(native_vlan)}")
        if allowed_vlans.strip():
            cmds.append(f"switchport trunk allowed vlan {allowed_vlans.strip()}")
        return self._cli.configure_ios(device, cmds, save=True)

    def configure_etherchannel(self, device: str, ports: list[str], channel_group: int = 1,
                               mode: str = "active", trunk: bool = True) -> str:
        cmds: list[str] = []
        for p in ports:
            cmds.extend([
                f"interface {p.strip()}",
                f"channel-group {int(channel_group)} mode {mode.strip()}",
                "exit",
            ])
        if trunk:
            cmds.extend([
                f"interface Port-channel {int(channel_group)}",
                "switchport mode trunk",
            ])
        return self._cli.configure_ios(device, cmds, save=True)

    def configure_stp(self, device: str, mode: str = "rapid-pvst", vlan_range: str = "1",
                      priority: int = 32768, portfast_ports: list[str] | None = None,
                      bpduguard: bool = False) -> str:
        cmds = [
            f"spanning-tree mode {mode.strip()}",
            f"spanning-tree vlan {vlan_range.strip()} priority {int(priority)}",
        ]
        for p in portfast_ports or []:
            cmds.extend([f"interface {p.strip()}", "spanning-tree portfast"])
            if bpduguard:
                cmds.append("spanning-tree bpduguard enable")
            cmds.append("exit")
        return self._cli.configure_ios(device, cmds, save=True)

    def configure_port_security(self, device: str, port: str, maximum: int = 1,
                                violation: str = "restrict", mac_sticky: bool = True,
                                static_mac: str = "") -> str:
        cmds = [
            f"interface {port.strip()}",
            "switchport mode access",
            "switchport port-security",
            f"switchport port-security maximum {int(maximum)}",
            f"switchport port-security violation {violation.strip()}",
        ]
        if mac_sticky:
            cmds.append("switchport port-security mac-address sticky")
        if static_mac.strip():
            cmds.append(f"switchport port-security mac-address {static_mac.strip()}")
        return self._cli.configure_ios(device, cmds, save=True)

    def show_mac_table(self, device: str) -> str:
        res = json.loads(self._cli.send_cli(device, "show mac-address-table", mode="enable"))
        out = res.get("output", "")
        entries = []
        for line in out.splitlines():
            m = re.match(r"^\s*(\d+)\s+([0-9a-fA-F.]{14})\s+(\S+)\s+(\S+)\s*$", line)
            if m:
                entries.append({
                    "vlan": int(m.group(1)),
                    "mac": m.group(2),
                    "type": m.group(3),
                    "port": m.group(4),
                })
        return json.dumps({"device": device, "entries": entries, "raw": out}, ensure_ascii=False)

    def configure_vtp(self, device: str, mode: str = "server", domain: str = "",
                      password: str = "", version: int = 2) -> str:
        cmds = [f"vtp mode {mode.strip()}"]
        if domain.strip():
            cmds.append(f"vtp domain {domain.strip()}")
        if password.strip():
            cmds.append(f"vtp password {password.strip()}")
        if int(version) in (1, 2):
            cmds.append(f"vtp version {int(version)}")
        return self._cli.configure_ios(device, cmds, save=True)

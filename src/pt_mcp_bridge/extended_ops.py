"""Operaciones extendidas de dominio (Topología, L2, L3, Servicios, Seguridad, WAN/Wireless, Diagnóstico, Labs y Meta-herramientas)."""
from __future__ import annotations

import difflib
import ipaddress
import json
import re
from pathlib import Path
from typing import Any

from pt_mcp_bridge import calls
from pt_mcp_bridge.ipc import PTError
from pt_mcp_bridge.ipc.protocol import Arg, Step

MODULE_TYPE_CODES: dict[str, int] = {
    "LINE_CARD": 0,
    "NETWORK_MODULE": 1,
    "INTERFACE_CARD": 2,
    "PT_ROUTER_MODULE": 3,
    "PT_SWITCH_MODULE": 4,
    "PT_CLOUD_MODULE": 5,
    "PT_REPEATER_MODULE": 6,
    "PT_HOST_MODULE": 7,
    "PT_MODEM_MODULE": 8,
    "PT_LAPTOP_MODULE": 9,
    "PT_ROUTER_POWER_ADAPTER": 29,
    "SFP_MODULE": 30,
}

_SNAPSHOTS: dict[str, dict[str, Any]] = {}


class ExtendedOperationsMixin:
    """Mixin para `PacketTracerService` que implementa las herramientas avanzadas agrupadas por dominio."""

    # =========================================================================
    # 1. TOPOLOGÍA Y DISPOSITIVOS (1-12)
    # =========================================================================
    def move_device(self, name: str, x: int, y: int) -> str:
        name = name.strip()
        ok = self._run(f"move_device {name} -> ({x}, {y})", calls.move_device(name, int(x), int(y)))
        return json.dumps({"device": name, "x": int(x), "y": int(y), "moved": bool(ok)}, ensure_ascii=False)

    def rename_device(self, old_name: str, new_name: str, sync_hostname: bool = True) -> str:
        old_name, new_name = old_name.strip(), new_name.strip()
        self._run(f"rename {old_name} -> {new_name}", calls.rename_device(old_name, new_name))
        if sync_hostname:
            try:
                tcode = int(self._run(f"type {new_name}", calls.device_attr_by_name(new_name, "getType")) or 0)
                if tcode in (0, 1, 16, 17):
                    self.configure_ios(new_name, [f"hostname {new_name}"], save=True)
            except PTError:
                pass
        return json.dumps({"old_name": old_name, "new_name": new_name, "sync_hostname": sync_hostname}, ensure_ascii=False)

    def clone_device(self, source_name: str, new_name: str, x: int = 300, y: int = 300) -> str:
        source_name, new_name = source_name.strip(), new_name.strip()
        model = str(self._run(f"model {source_name}", calls.device_attr_by_name(source_name, "getModel")) or "2911")
        tcode = int(self._run(f"type {source_name}", calls.device_attr_by_name(source_name, "getType")) or 0)
        kind = calls.DEVICE_KIND_BY_CODE.get(tcode, "router")
        created_info = json.loads(self.add_device(new_name, kind, model, int(x), int(y)))

        copied_config = False
        if tcode in (0, 1, 16, 17):
            try:
                run_cfg = json.loads(self.send_cli(source_name, "show running-config", mode="enable")).get("output", "")
                cfg_lines = [
                    ln for ln in run_cfg.splitlines()
                    if ln.strip()
                    and not ln.strip().startswith(("Building configuration", "Current configuration", "version ", "!", "end"))
                ]
                if cfg_lines:
                    self.configure_ios(new_name, cfg_lines + [f"hostname {new_name}"], save=True)
                    copied_config = True
            except (PTError, ValueError):
                pass
        elif kind in ("pc", "laptop", "server"):
            try:
                ip = str(self._run(f"ip {source_name}", calls.port_step(source_name, "FastEthernet0") + [Step("getIpAddress")]) or "")
                mask = str(self._run(f"mask {source_name}", calls.port_step(source_name, "FastEthernet0") + [Step("getSubnetMask")]) or "")
                if ip and ip != "0.0.0.0" and mask and mask != "0.0.0.0":
                    self.configure_host(new_name, ip=ip, mask=mask)
                    copied_config = True
            except PTError:
                pass

        return json.dumps({
            "source": source_name,
            "cloned": created_info["name"],
            "kind": kind,
            "model": model,
            "copied_config": copied_config,
        }, ensure_ascii=False)

    def disconnect_ports(self, device: str, port: str) -> str:
        device, port = device.strip(), port.strip()
        ok = self._run(f"deleteLink {device}:{port}", calls.delete_link(device, port))
        return json.dumps({"device": device, "port": port, "disconnected": bool(ok)}, ensure_ascii=False)

    def set_port_state(self, device: str, port: str, enabled: bool = True) -> str:
        device, port = device.strip(), port.strip()
        cmd = "no shutdown" if enabled else "shutdown"
        try:
            res = json.loads(self.configure_ios(device, [f"interface {port}", cmd], save=True))
            return json.dumps({"device": device, "port": port, "enabled": enabled, "cli": res}, ensure_ascii=False)
        except PTError:
            self._run(f"setPortPower {device}:{port}={enabled}", calls.set_port_power(device, port, enabled))
            return json.dumps({"device": device, "port": port, "enabled": enabled}, ensure_ascii=False)

    def add_module(self, device: str, slot: str, module_name: str, module_type: str = "PT_ROUTER_MODULE") -> str:
        device, slot, module_name = device.strip(), str(slot).strip(), module_name.strip()
        mtype_code = MODULE_TYPE_CODES.get(module_type.upper().strip(), 3)
        self._run(f"powerOff {device}", calls.set_device_power(device, False))
        try:
            ok = self._run(
                f"addModule {device}[{slot}]={module_name}",
                calls.add_device_module(device, slot, mtype_code, module_name),
            )
        finally:
            self._run(f"powerOn {device}", calls.set_device_power(device, True))
            self._ready_console(device)
        return json.dumps({
            "device": device,
            "slot": slot,
            "module": module_name,
            "module_type": module_type,
            "added": bool(ok),
        }, ensure_ascii=False)

    def power_device(self, device: str, power_on: bool = True) -> str:
        device = device.strip()
        self._run(f"setPower {device}={power_on}", calls.set_device_power(device, power_on))
        if power_on:
            self._ready_console(device)
        cur = self._run(f"getPower {device}", calls.get_device_power(device))
        return json.dumps({"device": device, "power_on": bool(cur)}, ensure_ascii=False)

    def add_note(self, text: str, x: int = 100, y: int = 100, z: float = 1.0) -> str:
        note_uuid = self._run(f"addNote ({x},{y})", calls.add_canvas_note(int(x), int(y), float(z), text))
        return json.dumps({"uuid": str(note_uuid or ""), "x": int(x), "y": int(y), "text": text}, ensure_ascii=False)

    def group_devices(self, devices: list[str], cluster_name: str = "") -> str:
        moved = []
        for dev in devices:
            dev = dev.strip()
            if not dev:
                continue
            if cluster_name:
                try:
                    ok = self._run(
                        f"moveIntoCluster {dev}->{cluster_name}",
                        calls.component_item(dev) + [Step("moveIntoCluster", (Arg.qstring(cluster_name),))],
                    )
                    moved.append({"device": dev, "clustered": bool(ok)})
                except PTError:
                    moved.append({"device": dev, "clustered": False})
            else:
                self._run(
                    f"select {dev}",
                    calls.component_item(dev) + [Step("setSelected", (Arg.boolean(True),))],
                )
                moved.append({"device": dev, "selected": True})
        if not cluster_name and moved:
            try:
                self._run("createCluster", [Step("appWindow"), Step("getLogicalToolbar"), Step("createCluster")])
            except PTError:
                pass
        return json.dumps({"cluster": cluster_name or "auto", "devices": moved}, ensure_ascii=False)

    def layout_auto(self, columns: int = 4, start_x: int = 160, start_y: int = 140,
                    spacing_x: int = 210, spacing_y: int = 160) -> str:
        topo = json.loads(self.topology())
        devices = topo.get("devices", [])
        tier_order = {"cloud": 0, "asa": 0, "router": 1, "multi_layer_switch": 2, "switch3650": 2, "switch": 2}
        sorted_devs = sorted(devices, key=lambda d: (tier_order.get(d.get("kind", ""), 3), d.get("name", "")))
        cols = max(1, int(columns))
        placed = []
        for idx, dev in enumerate(sorted_devs):
            row, col = divmod(idx, cols)
            nx = int(start_x + col * spacing_x)
            ny = int(start_y + row * spacing_y)
            self._run(f"layout {dev['name']} -> ({nx},{ny})", calls.move_device(dev["name"], nx, ny))
            placed.append({"name": dev["name"], "x": nx, "y": ny})
        return json.dumps({"arranged": len(placed), "positions": placed}, ensure_ascii=False)

    def export_topology_json(self, include_configs: bool = True) -> str:
        topo = json.loads(self.topology())
        if include_configs:
            for dev in topo.get("devices", []):
                name, kind = dev["name"], dev.get("kind", "")
                if kind in ("router", "switch", "multi_layer_switch", "switch3650"):
                    try:
                        res = json.loads(self.send_cli(name, "show running-config", mode="enable"))
                        dev["running_config"] = res.get("output", "")
                    except (PTError, ValueError):
                        dev["running_config"] = ""
                elif kind in ("pc", "laptop", "server"):
                    try:
                        dev["ports"] = json.loads(self.list_ports(name)).get("ports", [])
                    except (PTError, ValueError):
                        dev["ports"] = []
        return json.dumps(topo, ensure_ascii=False)

    def import_topology_json(self, topology_json: str | dict[str, Any], clear_existing: bool = False) -> str:
        data = json.loads(topology_json) if isinstance(topology_json, str) else topology_json
        if clear_existing:
            cur = json.loads(self.topology())
            for d in cur.get("devices", []):
                try:
                    self.remove_device(d["name"])
                except PTError:
                    pass

        created_devices = []
        for d in data.get("devices", []):
            kind = d.get("kind", "router")
            if kind not in calls.DEVICE_TYPES:
                kind = "router"
            self.add_device(
                d["name"],
                kind,
                d.get("model", ""),
                int(float(d.get("x", 200))),
                int(float(d.get("y", 200))),
            )
            created_devices.append(d["name"])
            for p in d.get("ports", []):
                if p.get("ip") and p.get("mask"):
                    try:
                        self.configure_host(d["name"], ip=p["ip"], mask=p["mask"], port=p.get("name", "FastEthernet0"))
                    except PTError:
                        pass

        created_links = []
        for lnk in data.get("links", []):
            a, b = lnk.get("a", {}), lnk.get("b", {})
            cable = lnk.get("cable", "auto")
            if cable not in calls.CABLE_CODES:
                cable = "auto"
            self.connect_ports(a["device"], a["port"], b["device"], b["port"], cable)
            created_links.append(lnk)

        return json.dumps({
            "imported_devices": created_devices,
            "imported_links": len(created_links),
        }, ensure_ascii=False)

    # =========================================================================
    # 2. CAPA 2 - SWITCHING (13-20)
    # =========================================================================
    def create_vlan(self, device: str, vlan_id: int, name: str = "") -> str:
        cmds = [f"vlan {int(vlan_id)}"]
        if name.strip():
            cmds.append(f"name {name.strip()}")
        cmds.append("exit")
        return self.configure_ios(device, cmds, save=True)

    def assign_vlan_port(self, device: str, port: str, vlan_id: int, voice_vlan_id: int = 0) -> str:
        cmds = [
            f"interface {port.strip()}",
            "switchport mode access",
            f"switchport access vlan {int(vlan_id)}",
        ]
        if int(voice_vlan_id) > 0:
            cmds.append(f"switchport voice vlan {int(voice_vlan_id)}")
        return self.configure_ios(device, cmds, save=True)

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
        return self.configure_ios(device, cmds, save=True)

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
        return self.configure_ios(device, cmds, save=True)

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
        return self.configure_ios(device, cmds, save=True)

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
        return self.configure_ios(device, cmds, save=True)

    def show_mac_table(self, device: str) -> str:
        res = json.loads(self.send_cli(device, "show mac-address-table", mode="enable"))
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
        return self.configure_ios(device, cmds, save=True)

    # =========================================================================
    # 3. CAPA 3 - ENRUTAMIENTO (21-30)
    # =========================================================================
    def configure_static_route(self, device: str, network: str, mask: str,
                               next_hop_or_interface: str, admin_distance: int = 0) -> str:
        cmd = f"ip route {network.strip()} {mask.strip()} {next_hop_or_interface.strip()}"
        if int(admin_distance) > 0:
            cmd += f" {int(admin_distance)}"
        return self.configure_ios(device, [cmd], save=True)

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
        return self.configure_ios(device, cmds, save=True)

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
        return self.configure_ios(device, cmds, save=True)

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
        return self.configure_ios(device, cmds, save=True)

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
        return self.configure_ios(device, cmds, save=True)

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
        return self.configure_ios(device, cmds, save=True)

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
        return self.configure_ios(device, cmds, save=True)

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
        return self.configure_ios(device, cmds, save=True)

    def configure_hsrp(self, device: str, interface: str, group: int,
                       virtual_ip: str, priority: int = 100, preempt: bool = True) -> str:
        cmds = [
            f"interface {interface.strip()}",
            f"standby {int(group)} ip {virtual_ip.strip()}",
            f"standby {int(group)} priority {int(priority)}",
        ]
        if preempt:
            cmds.append(f"standby {int(group)} preempt")
        return self.configure_ios(device, cmds, save=True)

    def configure_vrrp(self, device: str, interface: str, group: int,
                       virtual_ip: str, priority: int = 100, preempt: bool = True) -> str:
        cmds = [
            f"interface {interface.strip()}",
            f"vrrp {int(group)} ip {virtual_ip.strip()}",
            f"vrrp {int(group)} priority {int(priority)}",
        ]
        if preempt:
            cmds.append(f"vrrp {int(group)} preempt")
        return self.configure_ios(device, cmds, save=True)

    def show_routing_table(self, device: str) -> str:
        res = json.loads(self.send_cli(device, "show ip route", mode="enable"))
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

    # =========================================================================
    # 4. SERVICIOS (31-38)
    # =========================================================================
    def configure_dhcp_server(self, device: str, pool_name: str, network: str, mask: str,
                              default_router: str, dns_server: str = "",
                              excluded_start: str = "", excluded_end: str = "") -> str:
        cmds: list[str] = []
        if excluded_start.strip():
            ex = f"ip dhcp excluded-address {excluded_start.strip()}"
            if excluded_end.strip():
                ex += f" {excluded_end.strip()}"
            cmds.append(ex)
        cmds.extend([
            f"ip dhcp pool {pool_name.strip()}",
            f"network {network.strip()} {mask.strip()}",
            f"default-router {default_router.strip()}",
        ])
        if dns_server.strip():
            cmds.append(f"dns-server {dns_server.strip()}")
        cmds.append("exit")
        return self.configure_ios(device, cmds, save=True)

    def configure_dhcp_relay(self, device: str, interface: str, helper_ip: str) -> str:
        return self.configure_ios(
            device,
            [f"interface {interface.strip()}", f"ip helper-address {helper_ip.strip()}"],
            save=True,
        )

    def configure_dns_server(self, device: str, records: list[dict[str, str]], enabled: bool = True) -> str:
        device = device.strip()
        proc = calls.device_process(device, "DnsServerProcess")
        try:
            self._run(f"dns enable {device}", proc + [Step("setEnable", (Arg.boolean(enabled),))])
            added = []
            for rec in records:
                domain, ip = rec["domain"].strip(), rec["ip"].strip()
                ok = self._run(
                    f"dns add {domain}->{ip}",
                    proc + [Step("addIpAddress", (Arg.string(domain), Arg.ip(ip)))],
                )
                added.append({"domain": domain, "ip": ip, "added": bool(ok)})
            return json.dumps({"device": device, "enabled": enabled, "records": added}, ensure_ascii=False)
        except PTError:
            cmds = ["ip dns server"] if enabled else ["no ip dns server"]
            for rec in records:
                cmds.append(f"ip host {rec['domain'].strip()} {rec['ip'].strip()}")
            return self.configure_ios(device, cmds, save=True)

    def configure_http_server(self, device: str, enabled: bool = True,
                              https: bool = False, index_html: str = "") -> str:
        device = device.strip()
        http_proc = calls.device_process(device, "HttpServerProcess")
        self._run(f"http enable {device}", http_proc + [Step("setEnable", (Arg.boolean(enabled),))])
        if https:
            https_proc = calls.device_process(device, "HttpsServerProcess")
            try:
                self._run(f"https enable {device}", https_proc + [Step("setHttpsEnable", (Arg.boolean(True),))])
            except PTError:
                pass
        if index_html:
            self._run(
                f"http index.html {device}",
                http_proc + [Step("setPageContents", (Arg.string("index.html"), Arg.string(index_html)))],
            )
        return json.dumps({"device": device, "http_enabled": enabled, "https": https}, ensure_ascii=False)

    def configure_ftp_server(self, device: str, enabled: bool = True,
                             username: str = "", password: str = "",
                             permissions: str = "RWADN") -> str:
        device = device.strip()
        ftp_proc = calls.device_process(device, "FtpServerProcess")
        self._run(f"ftp enable {device}", ftp_proc + [Step("setEnabled", (Arg.boolean(enabled),))])
        if username.strip() and password.strip():
            mgr = ftp_proc + [Step("getFtpUserAccountManager")]
            self._run(
                f"ftp addUser {username}",
                mgr + [Step("addFtpUser", (Arg.string(username.strip()), Arg.string(password.strip()), Arg.string(permissions.strip())))],
            )
        return json.dumps({"device": device, "ftp_enabled": enabled, "user": username or None}, ensure_ascii=False)

    def configure_nat(self, device: str, mode: str = "pat",
                      inside_interfaces: list[str] | None = None,
                      outside_interface: str = "",
                      inside_network: str = "", inside_wildcard: str = "0.0.0.255",
                      static_local: str = "", static_global: str = "",
                      pool_name: str = "NAT_POOL", pool_start: str = "",
                      pool_end: str = "", netmask: str = "255.255.255.0") -> str:
        cmds: list[str] = []
        for intf in inside_interfaces or []:
            cmds.extend([f"interface {intf.strip()}", "ip nat inside", "exit"])
        if outside_interface.strip():
            cmds.extend([f"interface {outside_interface.strip()}", "ip nat outside", "exit"])

        m = mode.lower().strip()
        if m == "static":
            cmds.append(f"ip nat inside source static {static_local.strip()} {static_global.strip()}")
        elif m == "dynamic":
            cmds.extend([
                f"access-list 1 permit {inside_network.strip()} {inside_wildcard.strip()}",
                f"ip nat pool {pool_name.strip()} {pool_start.strip()} {pool_end.strip()} netmask {netmask.strip()}",
                f"ip nat inside source list 1 pool {pool_name.strip()}",
            ])
        else:
            cmds.extend([
                f"access-list 1 permit {inside_network.strip()} {inside_wildcard.strip()}",
                f"ip nat inside source list 1 interface {outside_interface.strip()} overload",
            ])
        return self.configure_ios(device, cmds, save=True)

    def configure_ntp(self, device: str, server_ip: str = "", master_stratum: int = 0) -> str:
        cmds: list[str] = []
        if server_ip.strip():
            cmds.append(f"ntp server {server_ip.strip()}")
        if int(master_stratum) > 0:
            cmds.append(f"ntp master {int(master_stratum)}")
        if not cmds:
            proc = calls.device_process(device.strip(), "NtpServerProcess")
            self._run(f"ntp enable {device}", proc + [Step("setEnabled", (Arg.boolean(True),))])
            return json.dumps({"device": device, "ntp_server_enabled": True}, ensure_ascii=False)
        return self.configure_ios(device, cmds, save=True)

    def configure_syslog(self, device: str, server_ip: str = "",
                         trap_level: str = "informational", enable_server: bool = False) -> str:
        if enable_server and not server_ip.strip():
            proc = calls.device_process(device.strip(), "SyslogServer")
            self._run(f"syslog enable {device}", proc + [Step("setEnable", (Arg.boolean(True),))])
            return json.dumps({"device": device, "syslog_server_enabled": True}, ensure_ascii=False)
        cmds = [
            "logging on",
            "service timestamps log datetime msec",
            f"logging host {server_ip.strip()}",
            f"logging trap {trap_level.strip()}",
        ]
        return self.configure_ios(device, cmds, save=True)

    def configure_snmp(self, device: str, ro_community: str = "public",
                       rw_community: str = "private", location: str = "",
                       contact: str = "") -> str:
        cmds: list[str] = []
        if ro_community.strip():
            cmds.append(f"snmp-server community {ro_community.strip()} RO")
        if rw_community.strip():
            cmds.append(f"snmp-server community {rw_community.strip()} RW")
        if location.strip():
            cmds.append(f"snmp-server location {location.strip()}")
        if contact.strip():
            cmds.append(f"snmp-server contact {contact.strip()}")
        return self.configure_ios(device, cmds, save=True)

    def configure_email_server(self, device: str, domain: str,
                               users: list[dict[str, str]]) -> str:
        device = device.strip()
        proc = calls.device_process(device, "EmailServer")
        self._run(f"email domain {device}={domain}", proc + [Step("updateAllAccounts", (Arg.string(domain.strip()),))])
        created = []
        for u in users:
            uname, pwd = u["username"].strip(), u["password"].strip()
            ok = self._run(
                f"email addUser {uname}",
                proc + [Step("addUser", (Arg.string(uname), Arg.string(pwd)))],
            )
            created.append({"username": uname, "added": bool(ok)})
        return json.dumps({"device": device, "domain": domain, "users": created}, ensure_ascii=False)

    # =========================================================================
    # 5. SEGURIDAD (39-44)
    # =========================================================================
    def configure_acl(self, device: str, acl_id_or_name: str | int,
                      rules: list[str], extended: bool = False) -> str:
        acl = str(acl_id_or_name).strip()
        if acl.isdigit():
            cmds = [f"access-list {acl} {r.strip()}" for r in rules if r.strip()]
        else:
            kind = "extended" if extended else "standard"
            cmds = [f"ip access-list {kind} {acl}"] + [r.strip() for r in rules if r.strip()] + ["exit"]
        return self.configure_ios(device, cmds, save=True)

    def apply_acl(self, device: str, interface: str, acl_id_or_name: str | int,
                  direction: str = "in") -> str:
        dir_clean = "out" if direction.lower().strip() == "out" else "in"
        cmds = [
            f"interface {interface.strip()}",
            f"ip access-group {str(acl_id_or_name).strip()} {dir_clean}",
        ]
        return self.configure_ios(device, cmds, save=True)

    def configure_ssh(self, device: str, domain_name: str, username: str,
                      password: str, rsa_modulus: int = 1024, ssh_version: int = 2) -> str:
        cmds = [
            f"hostname {device.strip()}",
            f"ip domain-name {domain_name.strip()}",
            f"username {username.strip()} privilege 15 secret {password.strip()}",
            f"ip ssh version {int(ssh_version)}",
            "line vty 0 15",
            "transport input ssh",
            "login local",
            "exit",
        ]
        res = json.loads(self.configure_ios(device, cmds, save=False))
        # Generar llaves RSA interactivas
        self.send_cli(device, f"crypto key generate rsa\n{int(rsa_modulus)}\n", mode="global")
        self.send_cli(device, "write memory", mode="enable")
        return json.dumps({"device": device, "ssh_configured": True, "rsa_modulus": int(rsa_modulus), "base": res}, ensure_ascii=False)

    def configure_aaa(self, device: str, server_ip: str, server_key: str,
                      protocol: str = "radius", local_fallback: bool = True) -> str:
        proto = "tacacs+" if "tacacs" in protocol.lower() else "radius"
        fallback = " local" if local_fallback else ""
        if proto == "radius":
            srv_cmds = [f"radius-server host {server_ip.strip()} key {server_key.strip()}"]
        else:
            srv_cmds = [f"tacacs-server host {server_ip.strip()} key {server_key.strip()}"]
        cmds = [
            "aaa new-model",
            *srv_cmds,
            f"aaa authentication login default group {proto}{fallback}",
        ]
        return self.configure_ios(device, cmds, save=True)

    def secure_device(self, device: str, enable_secret: str, console_password: str = "",
                      vty_password: str = "", banner_motd: str = "Authorized Access Only",
                      encrypt_passwords: bool = True, exec_timeout_min: int = 5) -> str:
        cmds = [
            f"enable secret {enable_secret.strip()}",
            "no ip domain-lookup",
        ]
        if encrypt_passwords:
            cmds.append("service password-encryption")
        if banner_motd.strip():
            cmds.append(f"banner motd #{banner_motd.strip()}#")
        if console_password.strip():
            cmds.extend([
                "line console 0",
                f"password {console_password.strip()}",
                "login",
                f"exec-timeout {int(exec_timeout_min)} 0",
                "logging synchronous",
                "exit",
            ])
        if vty_password.strip():
            cmds.extend([
                "line vty 0 15",
                f"password {vty_password.strip()}",
                "login",
                f"exec-timeout {int(exec_timeout_min)} 0",
                "exit",
            ])
        return self.configure_ios(device, cmds, save=True)

    def configure_vpn_ipsec(self, device: str, peer_ip: str, pre_shared_key: str,
                            local_network: str, local_wildcard: str,
                            remote_network: str, remote_wildcard: str,
                            outside_interface: str) -> str:
        cmds = [
            "crypto isakmp policy 10",
            "encryption aes",
            "hash sha",
            "authentication pre-share",
            "group 2",
            "exit",
            f"crypto isakmp key {pre_shared_key.strip()} address {peer_ip.strip()}",
            "crypto ipsec transform-set VPN-SET esp-aes esp-sha-hmac",
            f"access-list 110 permit ip {local_network.strip()} {local_wildcard.strip()} {remote_network.strip()} {remote_wildcard.strip()}",
            "crypto map VPN-MAP 10 ipsec-isakmp",
            f"set peer {peer_ip.strip()}",
            "set transform-set VPN-SET",
            "match address 110",
            "exit",
            f"interface {outside_interface.strip()}",
            "crypto map VPN-MAP",
        ]
        return self.configure_ios(device, cmds, save=True)

    def configure_gre(self, device: str, tunnel_number: int, tunnel_ip: str,
                      tunnel_mask: str, source_ip_or_intf: str, destination_ip: str) -> str:
        cmds = [
            f"interface Tunnel{int(tunnel_number)}",
            f"ip address {tunnel_ip.strip()} {tunnel_mask.strip()}",
            f"tunnel source {source_ip_or_intf.strip()}",
            f"tunnel destination {destination_ip.strip()}",
            "no shutdown",
        ]
        return self.configure_ios(device, cmds, save=True)

    # =========================================================================
    # 6. WIRELESS Y WAN (45-48)
    # =========================================================================
    def configure_wlc(self, device: str, management_ip: str = "", management_mask: str = "") -> str:
        device = device.strip()
        if management_ip.strip() and management_mask.strip():
            return self.configure_host(device, ip=management_ip.strip(), mask=management_mask.strip(), port="GigabitEthernet1")
        return json.dumps({"device": device, "status": "ok"}, ensure_ascii=False)

    def configure_ap(self, device: str, ssid: str, port: str = "Port 1",
                     channel: int = 6, auth_type: str = "WPA2-PSK", passphrase: str = "") -> str:
        return self.configure_ssid(device, ssid=ssid, auth_type=auth_type, passphrase=passphrase, channel=channel, port=port)

    def configure_ssid(self, device: str, ssid: str, auth_type: str = "WPA2-PSK",
                       passphrase: str = "", channel: int = 6, port: str = "Port 1") -> str:
        device = device.strip()
        pstep = calls.port_step(device, port)
        self._run(f"ssid {device}:{port}={ssid}", pstep + [Step("setSsid", (Arg.string(ssid.strip()),))])
        self._run(f"chan {device}:{port}={channel}", pstep + [Step("setStandardChannel", (Arg.integer(int(channel)),))])
        return json.dumps({
            "device": device,
            "port": port,
            "ssid": ssid,
            "channel": int(channel),
            "auth_type": auth_type,
            "passphrase_set": bool(passphrase),
        }, ensure_ascii=False)

    def configure_frame_relay(self, device: str, interface: str, dlci: int = 102,
                              ip: str = "", mask: str = "", encapsulation: str = "ietf") -> str:
        cmds = [
            f"interface {interface.strip()}",
            f"encapsulation frame-relay {encapsulation.strip()}".strip(),
        ]
        if ip.strip() and mask.strip():
            cmds.append(f"ip address {ip.strip()} {mask.strip()}")
        if int(dlci) > 0:
            cmds.append(f"frame-relay interface-dlci {int(dlci)}")
        cmds.append("no shutdown")
        return self.configure_ios(device, cmds, save=True)

    def configure_ppp(self, device: str, interface: str, auth: str = "chap",
                      username: str = "", password: str = "",
                      ip: str = "", mask: str = "") -> str:
        cmds: list[str] = []
        if username.strip() and password.strip():
            cmds.append(f"username {username.strip()} password {password.strip()}")
        cmds.extend([
            f"interface {interface.strip()}",
            "encapsulation ppp",
        ])
        if ip.strip() and mask.strip():
            cmds.append(f"ip address {ip.strip()} {mask.strip()}")
        if auth.strip():
            cmds.append(f"ppp authentication {auth.strip()}")
        cmds.append("no shutdown")
        return self.configure_ios(device, cmds, save=True)

    def configure_serial_clock(self, device: str, interface: str, clock_rate: int = 64000) -> str:
        device, interface = device.strip(), interface.strip()
        try:
            self._run(f"setClockRate {device}:{interface}={clock_rate}", calls.set_port_clock_rate(device, interface, int(clock_rate)))
        except PTError:
            pass
        return self.configure_ios(device, [f"interface {interface}", f"clock rate {int(clock_rate)}", "no shutdown"], save=True)

    # =========================================================================
    # 7. VERIFICACIÓN Y DIAGNÓSTICO (49-57)
    # =========================================================================
    def traceroute(self, device: str, target_ip: str) -> str:
        device, target_ip = device.strip(), target_ip.strip()
        res = json.loads(self.send_cli(device, f"traceroute {target_ip}", mode="enable"))
        out = res.get("output", "")
        hops = []
        for line in out.splitlines():
            m = re.match(r"^\s*(\d+)\s+(\d+\.\d+\.\d+\.\d+|\*)\s*(.*)$", line)
            if m:
                hops.append({"hop": int(m.group(1)), "address": m.group(2), "detail": m.group(3).strip()})
        return json.dumps({"source": device, "target": target_ip, "hops": hops, "output": out}, ensure_ascii=False)

    def test_connectivity_matrix(self, devices: list[str] | None = None,
                                 targets: list[str] | None = None) -> str:
        topo = json.loads(self.topology())
        all_devs = topo.get("devices", [])
        sources = devices or [d["name"] for d in all_devs if d.get("kind") in ("router", "pc", "laptop", "server")]
        if not targets:
            discovered_ips = []
            for d in all_devs:
                if d.get("kind") in ("pc", "laptop", "server"):
                    try:
                        ip = str(self._run(f"ip {d['name']}", calls.port_step(d["name"], "FastEthernet0") + [Step("getIpAddress")]) or "")
                        if ip and ip != "0.0.0.0":
                            discovered_ips.append(ip)
                    except PTError:
                        pass
            targets = discovered_ips

        matrix = []
        total, passed = 0, 0
        for src in sources:
            for dst_ip in targets or []:
                total += 1
                res = json.loads(self.ping(src, dst_ip))
                ok = bool(res.get("success"))
                if ok:
                    passed += 1
                matrix.append({"source": src, "target": dst_ip, "success": ok})

        return json.dumps({
            "total_tests": total,
            "passed": passed,
            "success_rate": round((passed / total) * 100, 1) if total else 0.0,
            "matrix": matrix,
        }, ensure_ascii=False)

    def verify_vlans(self, device: str) -> str:
        res = json.loads(self.send_cli(device, "show vlan brief", mode="enable"))
        out = res.get("output", "")
        vlans = []
        for line in out.splitlines():
            m = re.match(r"^\s*(\d+)\s+(\S+)\s+(active|act/unsup|suspended)\s*(.*)$", line)
            if m:
                ports = [p.strip() for p in m.group(4).split(",") if p.strip()]
                vlans.append({"id": int(m.group(1)), "name": m.group(2), "status": m.group(3), "ports": ports})
        return json.dumps({"device": device, "vlans": vlans, "raw": out}, ensure_ascii=False)

    def verify_trunks(self, device: str) -> str:
        res = json.loads(self.send_cli(device, "show interfaces trunk", mode="enable"))
        out = res.get("output", "")
        trunks = []
        for line in out.splitlines():
            m = re.match(r"^\s*([A-Za-z0-9/.-]+)\s+(on|auto|desirable)\s+(802\.1q|isl|n-802\.1q)\s+(trunking|not-trunking)\s+(\d+)\s*$", line)
            if m:
                trunks.append({
                    "port": m.group(1),
                    "mode": m.group(2),
                    "encapsulation": m.group(3),
                    "status": m.group(4),
                    "native_vlan": int(m.group(5)),
                })
        return json.dumps({"device": device, "trunks": trunks, "raw": out}, ensure_ascii=False)

    def diff_config(self, device: str, baseline: str = "") -> str:
        run_cfg = json.loads(self.send_cli(device, "show running-config", mode="enable")).get("output", "")
        if not baseline:
            base_cfg = json.loads(self.send_cli(device, "show startup-config", mode="enable")).get("output", "")
            base_label = "startup-config"
        else:
            base_cfg = baseline
            base_label = "baseline"
        diff = list(difflib.unified_diff(
            base_cfg.splitlines(),
            run_cfg.splitlines(),
            fromfile=base_label,
            tofile="running-config",
            lineterm="",
        ))
        return json.dumps({"device": device, "identical": len(diff) == 0, "diff": "\n".join(diff)}, ensure_ascii=False)

    def snapshot_config(self, name: str = "default") -> str:
        snap_raw = json.loads(self.export_topology_json(include_configs=True))
        _SNAPSHOTS[name.strip()] = snap_raw
        return json.dumps({
            "snapshot": name.strip(),
            "devices_count": len(snap_raw.get("devices", [])),
            "links_count": len(snap_raw.get("links", [])),
        }, ensure_ascii=False)

    def restore_config(self, name: str = "default") -> str:
        key = name.strip()
        if key not in _SNAPSHOTS:
            return json.dumps({"restored": False, "error": f"No existe el snapshot '{key}'."}, ensure_ascii=False)
        res = json.loads(self.import_topology_json(_SNAPSHOTS[key], clear_existing=False))
        return json.dumps({"restored": True, "snapshot": key, "details": res}, ensure_ascii=False)

    def find_misconfigurations(self) -> str:
        topo = json.loads(self.topology())
        issues: list[dict[str, Any]] = []
        seen_ips: dict[str, list[str]] = {}

        for d in topo.get("devices", []):
            name, kind = d["name"], d.get("kind", "")
            ports_info = json.loads(self.list_ports(name)).get("ports", [])
            for p in ports_info:
                ip, mask = p.get("ip"), p.get("mask")
                if ip and ip != "0.0.0.0":
                    seen_ips.setdefault(ip, []).append(f"{name}:{p['name']}")
                    if kind in ("pc", "laptop", "server") and mask and mask != "0.0.0.0":
                        try:
                            gw = str(self._run(
                                f"gw {name}:{p['name']}",
                                calls.port_step(name, p["name"]) + [Step("getDefaultGateway")],
                            ) or "")
                            if gw and gw != "0.0.0.0":
                                net = ipaddress.IPv4Network(f"{ip}/{mask}", strict=False)
                                if ipaddress.IPv4Address(gw) not in net:
                                    issues.append({
                                        "type": "gateway_outside_subnet",
                                        "device": name,
                                        "port": p["name"],
                                        "ip": ip,
                                        "mask": mask,
                                        "gateway": gw,
                                    })
                        except (PTError, ValueError):
                            pass

        for ip, owners in seen_ips.items():
            if len(owners) > 1:
                issues.append({"type": "duplicate_ip", "ip": ip, "interfaces": owners})

        return json.dumps({"issues_count": len(issues), "issues": issues}, ensure_ascii=False)

    def capture_packets(self, steps: int = 5, reset_first: bool = False) -> str:
        self._run("simMode on", calls.simulation_step("setSimulationMode", (Arg.boolean(True),)))
        if reset_first:
            self._run("simReset", calls.simulation_step("resetSimulation"))
        for _ in range(max(1, int(steps))):
            self._run("simForward", calls.simulation_step("forward"))
        return self.get_event_list()

    def send_pdu(self, source_device: str, dest_device: str) -> str:
        code = self._run(
            f"addSimplePdu {source_device}->{dest_device}",
            calls.add_simple_pdu(source_device.strip(), dest_device.strip()),
        )
        return json.dumps({
            "source": source_device.strip(),
            "destination": dest_device.strip(),
            "pdu_status_code": code,
        }, ensure_ascii=False)

    def get_event_list(self, limit: int = 50) -> str:
        count = int(self._run("frameCount", calls.simulation_step("getFrameInstanceCount")) or 0)
        events = []
        for i in range(min(count, max(1, int(limit)))):
            base = [Step("simulation"), Step("getFrameInstanceAt", (Arg.integer(i),))]
            try:
                src = self._run(f"frame[{i}].src", base + [Step("getSourceString")])
                dst = self._run(f"frame[{i}].dst", base + [Step("getDestinationString")])
                dev = self._run(f"frame[{i}].dev", base + [Step("getDevice"), Step("getName")])
                dropped = self._run(f"frame[{i}].drop", base + [Step("isFrameDropped")])
                events.append({
                    "index": i,
                    "device": dev,
                    "source": src,
                    "destination": dst,
                    "dropped": bool(dropped),
                })
            except PTError:
                continue
        return json.dumps({"total_frames": count, "events": events}, ensure_ascii=False)

    # =========================================================================
    # 8. LABORATORIOS Y CALIFICACIÓN (58-63)
    # =========================================================================
    def check_activity(self) -> str:
        af = calls.active_file()
        is_act = bool(self._run("isActivityFile", af + [Step("isActivityFile")]))
        if not is_act:
            return json.dumps({"is_activity": False, "percentage_complete": 0.0}, ensure_ascii=False)
        pct = float(self._run("getPercentageComplete", af + [Step("getPercentageComplete")]) or 0.0)
        elapsed = int(self._run("getTimeElapsed", af + [Step("getTimeElapsed")]) or 0)
        return json.dumps({
            "is_activity": True,
            "percentage_complete": pct,
            "time_elapsed_ms": elapsed,
        }, ensure_ascii=False)

    def list_activity_checks(self) -> str:
        af = calls.active_file()
        is_act = bool(self._run("isActivityFile", af + [Step("isActivityFile")]))
        if not is_act:
            return json.dumps({"is_activity": False, "items": []}, ensure_ascii=False)
        total_items = int(self._run("totalItems", af + [Step("getAssessmentItemsCount")]) or 0)
        correct_items = int(self._run("correctItems", af + [Step("getCorrectAssessmentItemsCount")]) or 0)
        total_score = int(self._run("totalScore", af + [Step("getAssessmentScoreCount")]) or 0)
        correct_score = int(self._run("correctScore", af + [Step("getCorrectAssessmentScoreCount")]) or 0)
        tree_xml = ""
        try:
            tree_xml = str(self._run("assessedTree", af + [Step("getLastAssessedComparatorTree")]) or "")
        except PTError:
            pass
        return json.dumps({
            "is_activity": True,
            "total_items": total_items,
            "correct_items": correct_items,
            "pending_items": max(0, total_items - correct_items),
            "total_score": total_score,
            "correct_score": correct_score,
            "comparator_tree": tree_xml,
        }, ensure_ascii=False)

    def generate_lab(self, spec: dict[str, Any]) -> str:
        res_import = json.loads(self.import_topology_json(spec, clear_existing=bool(spec.get("clear_existing", False))))
        for note in spec.get("notes", []):
            self.add_note(note.get("text", ""), int(note.get("x", 100)), int(note.get("y", 60)))
        for dev_name, cmds in spec.get("ios_configs", {}).items():
            if cmds:
                self.configure_ios(dev_name, cmds, save=True)
        return json.dumps({"lab_generated": True, "topology": res_import}, ensure_ascii=False)

    def backup_all_configs(self, output_dir: str = "backups") -> str:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        exported = json.loads(self.export_topology_json(include_configs=True))
        (out_path / "topology.json").write_text(json.dumps(exported, indent=2, ensure_ascii=False), encoding="utf-8")
        saved_files = ["topology.json"]
        for d in exported.get("devices", []):
            cfg = d.get("running_config", "")
            if cfg:
                fname = f"{d['name']}.cfg"
                (out_path / fname).write_text(cfg, encoding="utf-8")
                saved_files.append(fname)
        return json.dumps({"directory": str(out_path), "files": saved_files}, ensure_ascii=False)

    def apply_config_bundle(self, input_dir: str = "backups") -> str:
        in_path = Path(input_dir)
        if not in_path.is_dir():
            return json.dumps({"applied": [], "error": f"No existe el directorio '{input_dir}'."}, ensure_ascii=False)
        applied = []
        for cfg_file in sorted(in_path.glob("*.cfg")):
            dev_name = cfg_file.stem
            lines = [
                ln for ln in cfg_file.read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.strip().startswith(("Building configuration", "Current configuration", "!"))
            ]
            if lines:
                self.configure_ios(dev_name, lines, save=True)
                applied.append(dev_name)
        return json.dumps({"directory": str(in_path), "applied": applied}, ensure_ascii=False)

    def generate_docs(self) -> str:
        topo = json.loads(self.topology())
        devices = topo.get("devices", [])
        links = topo.get("links", [])

        md = ["# Documentación Técnica de la Topología\n", "## 1. Inventario de Dispositivos y Direccionamiento\n"]
        md.append("| Dispositivo | Tipo | Modelo | Interfaz | Dirección IPv4 | Máscara | Estado |")
        md.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for d in devices:
            ports = json.loads(self.list_ports(d["name"])).get("ports", [])
            configured_ports = [p for p in ports if p.get("ip") or p.get("up")]
            if not configured_ports:
                md.append(f"| {d['name']} | {d['kind']} | {d['model']} | - | - | - | - |")
            for p in configured_ports:
                state = "UP" if p.get("up") else "DOWN"
                md.append(
                    f"| {d['name']} | {d['kind']} | {d['model']} | {p['name']} | "
                    f"{p.get('ip') or '-'} | {p.get('mask') or '-'} | {state} |"
                )

        md.append("\n## 2. Diagrama de Topología (Mermaid)\n")
        md.append("```mermaid\ngraph LR")
        for lnk in links:
            a, b = lnk["a"], lnk["b"]
            md.append(f'    {a["device"]}["{a["device"]}"] ---|"{a["port"]} ↔ {b["port"]}"| {b["device"]}["{b["device"]}"]')
        md.append("```")

        return json.dumps({"markdown": "\n".join(md), "devices": len(devices), "links": len(links)}, ensure_ascii=False)

    # =========================================================================
    # 9. META-HERRAMIENTAS (64-67)
    # =========================================================================
    def search_methods(self, query: str, class_name: str = "", limit: int = 30) -> str:
        from pt_mcp_bridge.service import _load_ipc_index

        idx = _load_ipc_index()
        classes = idx.get("classes", {})
        q = query.lower().strip()
        cls_filter = class_name.lower().strip()
        matches = []
        for cname, cdata in classes.items():
            if cls_filter and cls_filter not in cname.lower():
                continue
            for m in cdata.get("methods", []):
                mname = m.get("name", "")
                if not q or q in mname.lower() or q in cname.lower():
                    matches.append({
                        "class": cname,
                        "method": mname,
                        "params": m.get("params", []),
                        "returns": m.get("returns", "void"),
                    })
                    if len(matches) >= max(1, int(limit)):
                        break
            if len(matches) >= max(1, int(limit)):
                break
        return json.dumps({"query": query, "count": len(matches), "matches": matches}, ensure_ascii=False)

    def describe_method(self, class_name: str, method_name: str) -> str:
        from pt_mcp_bridge.service import _load_ipc_index

        idx = _load_ipc_index()
        classes = idx.get("classes", {})
        cdata = classes.get(class_name.strip())
        if not cdata:
            return json.dumps({"error": f"Clase '{class_name}' no encontrada en ipc_index.json."}, ensure_ascii=False)
        found = [m for m in cdata.get("methods", []) if m.get("name") == method_name.strip()]
        if not found:
            return json.dumps({"error": f"Método '{method_name}' no encontrado en '{class_name}'."}, ensure_ascii=False)
        return json.dumps({
            "class": class_name.strip(),
            "extends": cdata.get("extends", []),
            "overloads": found,
        }, ensure_ascii=False)

    def batch(self, operations: list[dict[str, Any]], stop_on_error: bool = False) -> str:
        results = []
        for idx, op in enumerate(operations):
            method_name = op.get("tool", "").removeprefix("cpt_")
            kwargs = op.get("args", {})
            fn = getattr(self, method_name, None)
            if not callable(fn):
                err = {"step": idx, "tool": op.get("tool"), "error": f"Operación '{method_name}' no soportada."}
                results.append(err)
                if stop_on_error:
                    break
                continue
            try:
                out = fn(**kwargs)
                results.append({"step": idx, "tool": op.get("tool"), "result": json.loads(out) if isinstance(out, str) else out})
            except Exception as exc:  # noqa: BLE001
                results.append({"step": idx, "tool": op.get("tool"), "error": str(exc)})
                if stop_on_error:
                    break
        return json.dumps({"executed": len(results), "results": results}, ensure_ascii=False)

    def run_macro(self, macro_name: str, params: dict[str, Any] | None = None) -> str:
        p = params or {}
        m = macro_name.lower().strip()
        if m == "office_3vlans_roas":
            router = p.get("router", "R1")
            switch = p.get("switch", "SW1")
            self.add_device(router, "router", "2911", 200, 150)
            self.add_device(switch, "switch", "2960-24TT", 400, 150)
            self.connect_ports(router, "GigabitEthernet0/0", switch, "GigabitEthernet0/1", "straight")
            for vid, vname in ((10, "ADMIN"), (20, "VENTAS"), (30, "INVITADOS")):
                self.create_vlan(switch, vid, vname)
            self.configure_trunk(switch, "GigabitEthernet0/1")
            self.configure_intervlan(router, "GigabitEthernet0/0", [
                {"vlan": 10, "ip": "192.168.10.1", "mask": "255.255.255.0"},
                {"vlan": 20, "ip": "192.168.20.1", "mask": "255.255.255.0"},
                {"vlan": 30, "ip": "192.168.30.1", "mask": "255.255.255.0"},
            ])
            return json.dumps({"macro": m, "router": router, "switch": switch, "vlans": [10, 20, 30]}, ensure_ascii=False)

        if m == "wan_ospf_pair":
            r1, r2 = p.get("r1", "R1"), p.get("r2", "R2")
            self.add_device(r1, "router", "2911", 200, 200)
            self.add_device(r2, "router", "2911", 450, 200)
            self.connect_ports(r1, "GigabitEthernet0/0", r2, "GigabitEthernet0/0", "cross")
            self.configure_ios(r1, ["interface GigabitEthernet0/0", "ip address 10.0.0.1 255.255.255.252", "no shutdown"], save=True)
            self.configure_ios(r2, ["interface GigabitEthernet0/0", "ip address 10.0.0.2 255.255.255.252", "no shutdown"], save=True)
            self.configure_ospf(r1, 1, [{"network": "10.0.0.0", "wildcard": "0.0.0.3", "area": 0}])
            self.configure_ospf(r2, 1, [{"network": "10.0.0.0", "wildcard": "0.0.0.3", "area": 0}])
            return json.dumps({"macro": m, "routers": [r1, r2]}, ensure_ascii=False)

        if m == "mobile_lte_core":
            return self.deploy_cellular_topology(
                co_server=p.get("co_server", "CO-Core"),
                isp_router=p.get("isp_router", "R-ISP"),
                cell_towers=int(p.get("cell_towers", 2)),
                smartphones=int(p.get("smartphones", 2)),
                tablets=int(p.get("tablets", 1)),
            )

        return json.dumps({
            "available_macros": ["office_3vlans_roas", "wan_ospf_pair", "mobile_lte_core"],
            "requested": macro_name,
        }, ensure_ascii=False)

    # =========================================================================
    # 10. REDES MÓVILES Y CELULARES (3G/4G/LTE, HANDOVER Y BLUETOOTH/BLE)
    # =========================================================================
    def add_mobile_device(self, name: str, role: str = "smartphone",
                          model: str = "", x: int = 250, y: int = 250) -> str:
        """Agrega un nodo del segmento móvil (`smartphone`, `tablet`, `cell_tower`, `central_office_server`, `coaxial_splitter`, `lap`)."""
        role_clean = role.lower().strip()
        allowed = {"smartphone", "tablet", "tablet_pc", "pda", "cell_tower", "central_office_server", "co_server", "coaxial_splitter", "lap"}
        if role_clean not in allowed:
            role_clean = "smartphone"
        return self.add_device(name, role_clean, model, int(x), int(y))

    def connect_cell_tower_to_co(self, cell_tower: str, co_server: str,
                                 co_port: str = "Coaxial0",
                                 tower_port: str = "Coaxial0",
                                 backbone_router: str = "",
                                 router_port: str = "GigabitEthernet0/0") -> str:
        """Conecta una antena `Cell Tower` con el `Central Office Server` por cable coaxial y opcionalmente el `Backbone` hacia un router IP."""
        coax_link = json.loads(self.connect_ports(cell_tower.strip(), tower_port.strip(), co_server.strip(), co_port.strip(), "coaxial"))
        backbone_link = None
        if backbone_router.strip():
            backbone_link = json.loads(
                self.connect_ports(co_server.strip(), "Backbone", backbone_router.strip(), router_port.strip(), "straight")
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

        # En Packet Tracer, si Wireless0 queda encendida puede competir con 3G/4G Cell1 por la ruta por defecto
        if disable_wifi:
            try:
                self._run(f"wifi off {device}", calls.set_port_power(device, "Wireless0", False))
            except PTError:
                pass
        try:
            self._run(f"cell on {device}:{port}", calls.set_port_power(device, port, True))
        except PTError:
            pass

        host_cfg = json.loads(self.configure_host(device, ip=ip, mask=mask, gateway=gateway, dns=dns, dhcp=dhcp, port=port))

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
        """Construye una arquitectura de red móvil 3G/4G/LTE completa:
        Router ISP (DHCP/DNS) <-> Central Office Server (Backbone) <-> N Cell Towers (Coaxial) <-> M Smartphones/Tablets.
        """
        self.add_device(isp_router, "router", "2911", 150, 220)
        self.add_device(co_server, "central_office_server", "Central-Office-Server", 360, 220)
        self.connect_ports(co_server, "Backbone", isp_router, "GigabitEthernet0/0", "straight")

        # Configurar Router ISP como gateway y servidor DHCP del Backbone móvil
        self.configure_ios(isp_router, [
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
            self.add_device(tname, "cell_tower", "Cell-Tower", 580, ty)
            self.connect_ports(tname, "Coaxial0", co_server, f"Coaxial{idx}", "coaxial")
            towers_created.append(tname)

        ues_created = []
        for idx in range(max(0, int(smartphones))):
            sname = f"Smartphone-{idx + 1}"
            sy = 90 + idx * 140
            self.add_device(sname, "smartphone", "SMARTPHONE-PT", 800, sy)
            self.configure_cellular_interface(sname, dhcp=True, disable_wifi=True)
            ues_created.append(sname)

        for idx in range(max(0, int(tablets))):
            tbname = f"Tablet-{idx + 1}"
            tby = 260 + idx * 140
            self.add_device(tbname, "tablet", "TabletPC-PT", 820, tby)
            self.configure_cellular_interface(tbname, dhcp=True, disable_wifi=True)
            ues_created.append(tbname)

        # Converger DHCP en el núcleo móvil y radio enlaces 3G/4G
        for _ in range(4):
            self.fast_forward()

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
        """Simula el desplazamiento físico (roaming/handover entre antenas celulares) de un Smartphone o Tablet
        desde `(start_x, start_y)` hasta `(end_x, end_y)` en `steps` tramos, adelantando la convergencia y midiendo ping.
        """
        device = device.strip()
        n = max(1, int(steps))
        trajectory = []
        for i in range(n + 1):
            ratio = i / n
            cx = round(start_x + (end_x - start_x) * ratio)
            cy = round(start_y + (end_y - start_y) * ratio)
            self.move_device(device, cx, cy)
            self.fast_forward()
            step_info: dict[str, Any] = {"step": i, "x": cx, "y": cy}
            if ping_target.strip():
                ping_res = json.loads(self.ping(device, ping_target.strip()))
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
        """Audita el segmento de red móvil: Central Office Servers, Cell Towers, enlaces coaxiales/Backbone y equipos móviles (3G/4G vs Wi-Fi)."""
        topo = json.loads(self.topology())
        co_servers = []
        cell_towers = []
        mobile_endpoints = []

        for d in topo.get("devices", []):
            name, kind = d["name"], d.get("kind", "")
            if kind == "central_office_server":
                ports = json.loads(self.list_ports(name)).get("ports", [])
                co_servers.append({"name": name, "x": d["x"], "y": d["y"], "ports": ports})
            elif kind == "cell_tower":
                ports = json.loads(self.list_ports(name)).get("ports", [])
                cell_towers.append({"name": name, "x": d["x"], "y": d["y"], "ports": ports})
            elif kind in ("smartphone", "tablet"):
                ports = json.loads(self.list_ports(name)).get("ports", [])
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


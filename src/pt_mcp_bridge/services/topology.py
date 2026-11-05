"""Servicio de Topología y Gestión Física de Dispositivos (SRP)."""
from __future__ import annotations

import json
from typing import Any

from pt_mcp_bridge import calls
from pt_mcp_bridge.ipc import PTError
from pt_mcp_bridge.ipc.contracts import IPCTransport
from pt_mcp_bridge.ipc.protocol import Arg, Step
from pt_mcp_bridge.services.base import DomainServiceBase, ValidationError
from pt_mcp_bridge.services.ios_cli import IosCliService

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


class TopologyService(DomainServiceBase):
    """Gestiona nodos, enlaces, coordenadas, módulos de hardware, energía y notas en el lienzo."""

    def __init__(self, client: IPCTransport, cli_service: IosCliService) -> None:
        super().__init__(client)
        self._cli = cli_service

    def add_device(self, name: str, device_type: str, model: str, x: int, y: int) -> str:
        name = name.strip()
        dtype = device_type.lower().strip()
        if dtype not in calls.DEVICE_TYPES:
            raise ValidationError(f"device_type inválido '{device_type}'. Opciones: {', '.join(calls.DEVICE_TYPES)}")
        type_code = calls.DEVICE_TYPES[dtype]
        model = model.strip() or calls.DEFAULT_MODELS.get(dtype, "2911")

        created = self._run(
            f"add_device {name} ({dtype}/{model})",
            calls.add_device(type_code, model, float(x), float(y)),
        )
        created_name = str(created or "").strip()
        if not created_name:
            raise PTError(f"Packet Tracer rechazó crear el modelo '{model}' (tipo {dtype}).")

        self._ready_console(created_name)

        final_name = created_name
        if name and created_name != name:
            self._run(f"rename {created_name} -> {name}", calls.rename_device(created_name, name))
            final_name = name

        return json.dumps({
            "name": final_name,
            "created_as": created_name,
            "model": model,
            "kind": dtype,
            "x": x,
            "y": y,
        }, ensure_ascii=False)

    def remove_device(self, name: str) -> str:
        name = name.strip()
        ok = self._run(f"remove_device {name}", calls.remove_device(name))
        if not ok:
            raise PTError(f"No se pudo eliminar el dispositivo '{name}'.")
        return json.dumps({"removed": name}, ensure_ascii=False)

    def connect_ports(self, dev_a: str, port_a: str, dev_b: str, port_b: str, cable: str) -> str:
        dev_a, port_a = dev_a.strip(), port_a.strip()
        dev_b, port_b = dev_b.strip(), port_b.strip()
        cable_key = cable.lower().strip() or "auto"
        if cable_key not in calls.CABLE_CODES:
            raise ValidationError(f"cable inválido '{cable}'. Opciones: {', '.join(calls.CABLE_CODES)}")

        kind_a, kind_b = "router", "switch"
        if cable_key == "auto":
            try:
                ta = int(self._run(f"type {dev_a}", calls.device_attr_by_name(dev_a, "getType")) or 0)
                tb = int(self._run(f"type {dev_b}", calls.device_attr_by_name(dev_b, "getType")) or 0)
                kind_a = calls.DEVICE_KIND_BY_CODE.get(ta, "router")
                kind_b = calls.DEVICE_KIND_BY_CODE.get(tb, "switch")
            except PTError:
                pass

        code = calls.resolve_cable_code(cable_key, kind_a, port_a, kind_b, port_b)
        resolved_name = calls.CABLE_NAME_BY_CODE.get(code, cable_key)
        ok = self._run(
            f"connect {dev_a}:{port_a} <-> {dev_b}:{port_b} [{resolved_name}={code}]",
            calls.connect_ports(dev_a, port_a, dev_b, port_b, code),
        )
        if not ok:
            raise PTError(
                f"createLink devolvió false entre {dev_a}:{port_a} y {dev_b}:{port_b} "
                f"con cable {resolved_name} ({code}). Verifica los nombres exactos de los puertos con cpt_list_ports."
            )
        return json.dumps({
            "a": {"device": dev_a, "port": port_a},
            "b": {"device": dev_b, "port": port_b},
            "cable": resolved_name,
            "code": code,
        }, ensure_ascii=False)

    def topology(self) -> str:
        count = int(self._run("get_topology (devices)", calls.device_count()) or 0)
        devices = []
        for i in range(count):
            name = self._run("name", calls.device_attr(i, "getName"))
            model = self._run("model", calls.device_attr(i, "getModel"))
            tcode = int(self._run("type", calls.device_attr(i, "getType")) or 0)
            x = self._run("x", calls.device_attr(i, "getCenterXCoordinate"))
            y = self._run("y", calls.device_attr(i, "getCenterYCoordinate"))
            devices.append({
                "name": name,
                "model": model,
                "type": tcode,
                "kind": calls.DEVICE_KIND_BY_CODE.get(tcode, f"type_{tcode}"),
                "x": x,
                "y": y,
            })

        lcount = int(self._run("get_topology (links)", calls.link_count()) or 0)
        links = []
        for i in range(lcount):
            try:
                ctype = int(self._run("linkType", calls.link_attr(i, "getConnectionType")) or 0)
                if ctype == 8109:  # wireless
                    continue
                da = self._run("linkDev1", calls.link_end_device(i, "getPort1"))
                pa = self._run("linkPort1", calls.link_end_port(i, "getPort1"))
                db = self._run("linkDev2", calls.link_end_device(i, "getPort2"))
                pb = self._run("linkPort2", calls.link_end_port(i, "getPort2"))
                links.append({
                    "a": {"device": da, "port": pa},
                    "b": {"device": db, "port": pb},
                    "cable": calls.CABLE_NAME_BY_CODE.get(ctype, f"code_{ctype}"),
                })
            except PTError:
                continue

        return json.dumps({"devices": devices, "links": links}, ensure_ascii=False)

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
                    self._cli.configure_ios(new_name, [f"hostname {new_name}"], save=True)
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
                run_cfg = json.loads(self._cli.send_cli(source_name, "show running-config", mode="enable")).get("output", "")
                cfg_lines = [
                    ln for ln in run_cfg.splitlines()
                    if ln.strip()
                    and not ln.strip().startswith(("Building configuration", "Current configuration", "version ", "!", "end"))
                ]
                if cfg_lines:
                    self._cli.configure_ios(new_name, cfg_lines + [f"hostname {new_name}"], save=True)
                    copied_config = True
            except (PTError, ValueError):
                pass
        elif kind in ("pc", "laptop", "server"):
            try:
                ip = str(self._run(f"ip {source_name}", calls.port_step(source_name, "FastEthernet0") + [Step("getIpAddress")]) or "")
                mask = str(self._run(f"mask {source_name}", calls.port_step(source_name, "FastEthernet0") + [Step("getSubnetMask")]) or "")
                if ip and ip != "0.0.0.0" and mask and mask != "0.0.0.0":
                    self._cli.configure_host(new_name, ip=ip, mask=mask)
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
            res = json.loads(self._cli.configure_ios(device, [f"interface {port}", cmd], save=True))
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
                        res = json.loads(self._cli.send_cli(name, "show running-config", mode="enable"))
                        dev["running_config"] = res.get("output", "")
                    except (PTError, ValueError):
                        dev["running_config"] = ""
                elif kind in ("pc", "laptop", "server", "smartphone", "tablet"):
                    try:
                        dev["ports"] = json.loads(self._cli.list_ports(name)).get("ports", [])
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
                        self._cli.configure_host(d["name"], ip=p["ip"], mask=p["mask"], port=p.get("name", "FastEthernet0"))
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

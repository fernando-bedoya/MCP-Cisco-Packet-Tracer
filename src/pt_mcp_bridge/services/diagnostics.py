"""Servicio de dominio: Diagnóstico, Auditoría, Snapshots y Simulación de Paquetes (SRP)."""
from __future__ import annotations

import difflib
import ipaddress
import json
import re
from typing import Any

from pt_mcp_bridge import calls
from pt_mcp_bridge.ipc import IPCTransport, PTError
from pt_mcp_bridge.ipc.protocol import Arg, Step
from pt_mcp_bridge.services.base import DomainServiceBase
from pt_mcp_bridge.services.ios_cli import IosCliService
from pt_mcp_bridge.services.topology import TopologyService


class DiagnosticsService(DomainServiceBase):
    """Encapsula pruebas de conectividad, auditoría de configuración, snapshots en memoria y modo simulación."""

    def __init__(self, client: IPCTransport, cli: IosCliService, topology_svc: TopologyService) -> None:
        super().__init__(client)
        self._cli = cli
        self._topology = topology_svc
        self._snapshots: dict[str, dict[str, Any]] = {}

    def ping(self, device: str, target_ip: str) -> str:
        """Ejecuta un ping desde un dispositivo y reporta el resultado."""
        device = device.strip()
        target_ip = target_ip.strip()
        res = self._cli.send_cli(device, f"ping {target_ip}", mode="enable")
        try:
            data = json.loads(res)
            out = data.get("output", "")
            success = "!" in out or ("Success rate is" in out and " 0 percent" not in out)
            return json.dumps({
                "source": device,
                "target": target_ip,
                "success": success,
                "output": out,
            }, ensure_ascii=False)
        except (PTError, ValueError, KeyError, TypeError):
            return res

    def traceroute(self, device: str, target_ip: str) -> str:
        device, target_ip = device.strip(), target_ip.strip()
        res = json.loads(self._cli.send_cli(device, f"traceroute {target_ip}", mode="enable"))
        out = res.get("output", "")
        hops = []
        for line in out.splitlines():
            m = re.match(r"^\s*(\d+)\s+(\d+\.\d+\.\d+\.\d+|\*)\s*(.*)$", line)
            if m:
                hops.append({"hop": int(m.group(1)), "address": m.group(2), "detail": m.group(3).strip()})
        return json.dumps({"source": device, "target": target_ip, "hops": hops, "output": out}, ensure_ascii=False)

    def test_connectivity_matrix(self, devices: list[str] | None = None,
                                 targets: list[str] | None = None) -> str:
        topo = json.loads(self._topology.topology())
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

    def audit_network(self) -> str:
        """Audita toda la red en una sola llamada: dispositivos, interfaces, IPs, máscaras y rutas."""
        topo = json.loads(self._topology.topology())
        devices = topo.get("devices", [])
        report: dict[str, Any] = {"routers": {}, "hosts": {}, "switches": []}

        for d in devices:
            name, kind = d["name"], d.get("kind", "")
            if kind == "router":
                try:
                    res_int = json.loads(self._cli.send_cli(name, "show ip int br", mode="enable"))
                    res_rt = json.loads(self._cli.send_cli(name, "show ip route", mode="enable"))
                    report["routers"][name] = {
                        "interfaces": res_int.get("output", ""),
                        "routes": res_rt.get("output", ""),
                    }
                except (PTError, ValueError, KeyError, TypeError) as exc:
                    report["routers"][name] = {"error": str(exc)}
            elif kind in ("pc", "laptop", "server", "smartphone", "tablet"):
                default_port = "3G/4G Cell1" if kind in ("smartphone", "tablet") else "FastEthernet0"
                try:
                    cur_ip = self._run(
                        f"getIp {name}:{default_port}",
                        calls.port_step(name, default_port) + [Step("getIpAddress")],
                    )
                    cur_mask = self._run(
                        f"getMask {name}:{default_port}",
                        calls.port_step(name, default_port) + [Step("getSubnetMask")],
                    )
                    report["hosts"][name] = {
                        "ip": cur_ip,
                        "mask": cur_mask,
                        "port": default_port,
                        "kind": kind,
                    }
                except (PTError, ValueError, KeyError, TypeError) as exc:
                    report["hosts"][name] = {"error": str(exc)}
            elif kind in ("switch", "multi_layer_switch"):
                report["switches"].append(name)
            elif kind in ("cell_tower", "central_office_server"):
                report.setdefault("mobile_infrastructure", []).append({"name": name, "kind": kind})

        return json.dumps(report, ensure_ascii=False)

    def verify_vlans(self, device: str) -> str:
        res = json.loads(self._cli.send_cli(device, "show vlan brief", mode="enable"))
        out = res.get("output", "")
        vlans = []
        for line in out.splitlines():
            m = re.match(r"^\s*(\d+)\s+(\S+)\s+(active|act/unsup|suspended)\s*(.*)$", line)
            if m:
                ports = [p.strip() for p in m.group(4).split(",") if p.strip()]
                vlans.append({"id": int(m.group(1)), "name": m.group(2), "status": m.group(3), "ports": ports})
        return json.dumps({"device": device, "vlans": vlans, "raw": out}, ensure_ascii=False)

    def verify_trunks(self, device: str) -> str:
        res = json.loads(self._cli.send_cli(device, "show interfaces trunk", mode="enable"))
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
        run_cfg = json.loads(self._cli.send_cli(device, "show running-config", mode="enable")).get("output", "")
        if not baseline:
            base_cfg = json.loads(self._cli.send_cli(device, "show startup-config", mode="enable")).get("output", "")
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
        snap_raw = json.loads(self._topology.export_topology_json(include_configs=True))
        self._snapshots[name.strip()] = snap_raw
        return json.dumps({
            "snapshot": name.strip(),
            "devices_count": len(snap_raw.get("devices", [])),
            "links_count": len(snap_raw.get("links", [])),
        }, ensure_ascii=False)

    def restore_config(self, name: str = "default") -> str:
        key = name.strip()
        if key not in self._snapshots:
            return json.dumps({"restored": False, "error": f"No existe el snapshot '{key}'."}, ensure_ascii=False)
        res = json.loads(self._topology.import_topology_json(self._snapshots[key], clear_existing=False))
        return json.dumps({"restored": True, "snapshot": key, "details": res}, ensure_ascii=False)

    def find_misconfigurations(self) -> str:
        topo = json.loads(self._topology.topology())
        issues: list[dict[str, Any]] = []
        seen_ips: dict[str, list[str]] = {}

        for d in topo.get("devices", []):
            name, kind = d["name"], d.get("kind", "")
            ports_info = json.loads(self._cli.list_ports(name)).get("ports", [])
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

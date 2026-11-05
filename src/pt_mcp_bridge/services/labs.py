"""Servicio de dominio: Laboratorios Académicos, Calificación Automática y Documentación (SRP)."""
from __future__ import annotations

import json
import re
import urllib.parse
from pathlib import Path
from typing import Any

from pt_mcp_bridge import calls
from pt_mcp_bridge.ipc import IPCTransport, PTError
from pt_mcp_bridge.ipc.protocol import Step
from pt_mcp_bridge.services.base import DomainServiceBase
from pt_mcp_bridge.services.ios_cli import IosCliService
from pt_mcp_bridge.services.topology import TopologyService


class AcademicLabService(DomainServiceBase):
    """Encapsula guardado, instrucciones de actividad (.pka), evaluación de ítems, backups y generación de informes."""

    def __init__(self, client: IPCTransport, cli: IosCliService, topology_svc: TopologyService) -> None:
        super().__init__(client)
        self._cli = cli
        self._topology = topology_svc

    def save_file(self) -> str:
        """Guarda el archivo de Packet Tracer actualmente abierto."""
        self._run("fileSave", [Step("appWindow"), Step("fileSave")])
        return json.dumps({"saved": True})

    def get_instructions(self) -> str:
        """Obtiene las instrucciones del laboratorio desde la ventana de actividad."""
        raw = str(self._run("getInstructionsUrl", [
            Step("appWindow"), Step("getInstructionDlg"), Step("getWebView"), Step("getUrl")
        ]) or "")
        if raw.startswith("data:text/html;charset=UTF-8,"):
            html = urllib.parse.unquote(raw[len("data:text/html;charset=UTF-8,"):])
            clean = re.sub(r"<[^>]+>", "\n", html)
            lines = [ln.strip() for ln in clean.splitlines() if ln.strip()]
            return json.dumps({"text": "\n".join(lines), "raw_html": html}, ensure_ascii=False)
        return json.dumps({"text": raw}, ensure_ascii=False)

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
        res_import = json.loads(self._topology.import_topology_json(spec, clear_existing=bool(spec.get("clear_existing", False))))
        for note in spec.get("notes", []):
            self._topology.add_note(note.get("text", ""), int(note.get("x", 100)), int(note.get("y", 60)))

        # Bloques de comandos IOS por dispositivo + pools DHCP y rutas declarativas opcionales
        ios_batches: dict[str, list[str]] = {
            dev_name: list(cmds) for dev_name, cmds in spec.get("ios_configs", {}).items() if cmds
        }
        for pool in spec.get("dhcp_pools", []):
            dev = pool.get("device", "")
            if not dev:
                continue
            cmds = ios_batches.setdefault(dev, [])
            for exc in pool.get("excluded_addresses", []):
                cmds.append(f"ip dhcp excluded-address {exc}")
            cmds.append(f"ip dhcp pool {pool.get('pool_name', 'LAN_POOL')}")
            cmds.append(f"network {pool['network']} {pool['mask']}")
            if pool.get("default_router"):
                cmds.append(f"default-router {pool['default_router']}")
            if pool.get("dns_server"):
                cmds.append(f"dns-server {pool['dns_server']}")
            cmds.append("exit")

        for rt in spec.get("static_routes", []):
            dev = rt.get("device", "")
            if not dev:
                continue
            ios_batches.setdefault(dev, []).append(
                f"ip route {rt['prefix']} {rt['mask']} {rt['next_hop']}"
            )

        for dev_name, cmds in ios_batches.items():
            if cmds:
                self._cli.configure_ios(dev_name, cmds, save=True)

        if spec.get("auto_layout"):
            self._topology.layout_auto()

        if spec.get("fast_forward", True):
            self._cli.fast_forward()
            self._cli.fast_forward()

        return json.dumps({
            "lab_generated": True,
            "topology": res_import,
            "configured_ios_devices": list(ios_batches.keys()),
        }, ensure_ascii=False)

    def backup_all_configs(self, output_dir: str = "backups") -> str:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        exported = json.loads(self._topology.export_topology_json(include_configs=True))
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
                self._cli.configure_ios(dev_name, lines, save=True)
                applied.append(dev_name)
        return json.dumps({"directory": str(in_path), "applied": applied}, ensure_ascii=False)

    def generate_docs(self) -> str:
        topo = json.loads(self._topology.topology())
        devices = topo.get("devices", [])
        links = topo.get("links", [])

        md = ["# Documentación Técnica de la Topología\n", "## 1. Inventario de Dispositivos y Direccionamiento\n"]
        md.append("| Dispositivo | Tipo | Modelo | Interfaz | Dirección IPv4 | Máscara | Estado |")
        md.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for d in devices:
            ports = json.loads(self._cli.list_ports(d["name"])).get("ports", [])
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

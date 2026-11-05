"""Servicio de interacción con CLI Cisco IOS, interfaces y direccionamiento de hosts (SRP)."""
from __future__ import annotations

import json

from pt_mcp_bridge import calls
from pt_mcp_bridge.ipc import PTError
from pt_mcp_bridge.ipc.protocol import Step
from pt_mcp_bridge.services.base import COMMAND_STATUS, DomainServiceBase, ValidationError


class IosCliService(DomainServiceBase):
    """Gestiona ejecución de comandos IOS, direccionamiento IPv4 de hosts y lectura de puertos."""

    def send_cli(self, device: str, command: str, mode: str = "") -> str:
        device = device.strip()
        self._ready_console(device)
        lines = [ln.strip() for ln in command.splitlines() if ln.strip()]
        if not lines:
            raise ValidationError("El comando CLI no puede estar vacío.")

        results = []
        for idx, cmd in enumerate(lines):
            low = cmd.lower()
            if low in ("enable", "en"):
                self._run(f"cli {device} [enable]", calls.device_enter_command(device, "!", "enable"))
                results.append({"command": cmd, "status": "ok", "output": ""})
                continue
            if low in ("configure terminal", "conf t", "config t", "configure t"):
                self._run(f"cli {device} [global]", calls.device_enter_command(device, "!", "global"))
                results.append({"command": cmd, "status": "ok", "output": ""})
                continue

            call_mode = mode if (idx == 0 and mode) else ""
            reply = self._run(f"cli {device}> {cmd}", calls.device_enter_command(device, cmd, call_mode))
            if isinstance(reply, tuple) and len(reply) == 2:
                code, out = reply
                if code == 2 and idx == 0 and not mode:
                    reply2 = self._run(
                        f"cli {device} (global)> {cmd}",
                        calls.device_enter_command(device, cmd, "global"),
                    )
                    if isinstance(reply2, tuple) and len(reply2) == 2 and reply2[0] == 0:
                        code, out = reply2
                status_str = COMMAND_STATUS.get(int(code), f"code_{code}")
                results.append({"command": cmd, "status": status_str, "output": str(out or "").strip()})
            else:
                results.append({"command": cmd, "status": "ok", "output": str(reply or "")})

        if len(results) == 1:
            return json.dumps(results[0], ensure_ascii=False)
        return json.dumps({"device": device, "results": results}, ensure_ascii=False)

    def configure_ios(self, device: str, commands: list[str], save: bool = True) -> str:
        device = device.strip()
        self._ready_console(device)
        skip = {"enable", "en", "configure terminal", "conf t", "config t", "configure t", "end"}
        cleaned = [c.strip() for c in commands if c.strip() and c.strip().lower() not in skip]
        if not cleaned:
            raise ValidationError("Proporciona al menos un comando de configuración.")

        results = []
        for idx, cmd in enumerate(cleaned):
            m = "global" if idx == 0 else ""
            reply = self._run(f"cfg {device}> {cmd}", calls.device_enter_command(device, cmd, m))
            code, out = reply if (isinstance(reply, tuple) and len(reply) == 2) else (0, str(reply or ""))

            if int(code) != 0 and idx > 0:
                self._run(f"cfg {device}> [auto-exit]", calls.device_enter_command(device, "exit", ""))
                reply2 = self._run(f"cfg {device}> {cmd}", calls.device_enter_command(device, cmd, "global"))
                code2, out2 = reply2 if (isinstance(reply2, tuple) and len(reply2) == 2) else (0, str(reply2 or ""))
                if int(code2) == 0:
                    code, out = code2, out2

            status_str = COMMAND_STATUS.get(int(code), f"code_{code}")
            results.append({"command": cmd, "status": status_str, "output": str(out or "").strip()})
            if int(code) != 0:
                break

        self._run(f"cfg {device}> end", calls.device_enter_command(device, "end", ""))
        saved = False
        if save and all(r["status"] == "ok" for r in results):
            wreply = self._run(
                f"cfg {device}> write memory",
                calls.device_enter_command(device, "write memory", "enable"),
            )
            saved = isinstance(wreply, tuple) and wreply[0] == 0

        return json.dumps({
            "device": device,
            "completed": all(r["status"] == "ok" for r in results),
            "saved": saved,
            "results": results,
        }, ensure_ascii=False)

    def configure_host(self, device: str, ip: str = "", mask: str = "", gateway: str = "",
                       dns: str = "", dhcp: bool = False, port: str = "FastEthernet0") -> str:
        device = device.strip()
        port = port.strip() or "FastEthernet0"
        if dhcp:
            self._run(f"dhcp port {device}:{port}", calls.host_set_dhcp(device, port, True))
            self._run(f"dhcp dev {device}", calls.host_set_device_dhcp(device, True))
            return json.dumps({
                "device": device,
                "port": port,
                "dhcp": True,
                "ip": None,
                "mask": None,
                "gateway": None,
                "dns": None,
            }, ensure_ascii=False)

        if not ip or not mask:
            raise ValidationError("Para IP estática debes indicar `ip` y `mask` (o usar `dhcp=True`).")
        self._run(f"dhcp off {device}:{port}", calls.host_set_dhcp(device, port, False))
        self._run(f"ip {device}:{port} {ip}/{mask}", calls.host_set_ip_mask(device, port, ip.strip(), mask.strip()))
        if gateway.strip():
            self._run(f"gw {device}:{port} {gateway}", calls.host_set_gateway(device, port, gateway.strip()))
        if dns.strip():
            self._run(f"dns {device}:{port} {dns}", calls.host_set_dns(device, port, dns.strip()))

        cur_ip = self._run(f"getIp {device}:{port}", calls.port_step(device, port) + [Step("getIpAddress")])
        cur_mask = self._run(f"getMask {device}:{port}", calls.port_step(device, port) + [Step("getSubnetMask")])
        return json.dumps({
            "device": device,
            "port": port,
            "dhcp": False,
            "ip": cur_ip,
            "mask": cur_mask,
            "gateway": gateway or None,
            "dns": dns or None,
        }, ensure_ascii=False)

    def list_ports(self, device: str) -> str:
        device = device.strip()
        count = int(self._run(f"portCount {device}", calls.port_count(device)) or 0)
        ports = []
        for i in range(count):
            pname = self._run(f"portName {device}[{i}]", calls.port_attr_at(device, i, "getName"))
            up = self._run(f"portUp {device}[{i}]", calls.port_attr_at(device, i, "isPortUp"))
            proto = self._run(f"protoUp {device}[{i}]", calls.port_attr_at(device, i, "isProtocolUp"))
            try:
                ip = self._run(f"portIp {device}[{i}]", calls.port_attr_at(device, i, "getIpAddress"))
                mask = self._run(f"portMask {device}[{i}]", calls.port_attr_at(device, i, "getSubnetMask"))
            except PTError:
                ip, mask = None, None
            ports.append({
                "name": pname,
                "up": bool(up),
                "protocol_up": bool(proto),
                "ip": ip if ip and ip != "0.0.0.0" else None,
                "mask": mask if mask and mask != "0.0.0.0" else None,
            })
        return json.dumps({"device": device, "ports": ports}, ensure_ascii=False)

    def fast_forward(self) -> str:
        self._run("fastForwardTime", calls.fast_forward())
        return json.dumps({"fast_forwarded": True})

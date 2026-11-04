"""Capa de servicio: operaciones de alto nivel sobre Cisco Packet Tracer (verificadas contra pktctl)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pt_mcp_bridge import calls
from pt_mcp_bridge.ipc import IPCTransport, PTError
from pt_mcp_bridge.ipc.client import describe
from pt_mcp_bridge.ipc.protocol import Arg, Step

COMMAND_STATUS = {
    0: "ok",
    1: "ambiguous (% Ambiguous command)",
    2: "invalid (% Invalid input detected)",
    3: "incomplete (% Incomplete command)",
    4: "not_implemented",
}

_INDEX_CACHE: dict[str, Any] | None = None


def _load_ipc_index() -> dict[str, Any]:
    global _INDEX_CACHE
    if _INDEX_CACHE is None:
        idx_path = Path(__file__).parent / "ipc_index.json"
        if idx_path.is_file():
            _INDEX_CACHE = json.loads(idx_path.read_text(encoding="utf-8"))
        else:
            _INDEX_CACHE = {"classes": {}, "enums": {}, "roots": {}}
    return _INDEX_CACHE


class ValidationError(ValueError):
    """Argumentos inválidos de una operación."""


class PacketTracerService:
    def __init__(self, client: IPCTransport) -> None:
        self._client = client

    def _run(self, label: str, steps: list[Step]) -> Any:
        self._client.log("mcp", f"{label}  [{describe(steps)}]")
        try:
            return self._client.call(steps)
        except PTError as exc:
            self._client.log("error", f"{label} -> {exc}")
            raise

    def _ready_console(self, dev_name: str) -> None:
        """Salta el arranque IOS (`skipBoot`) y responde 'no' al diálogo inicial si aparece."""
        try:
            self._run(f"skipBoot {dev_name}", calls.skip_boot(dev_name))
        except PTError:
            return
        try:
            prompt = str(self._run(f"getPrompt {dev_name}", calls.console_prompt(dev_name)) or "")
            if "initial configuration dialog" in prompt.lower():
                self._run(f"dialog no {dev_name}", calls.console_enter_raw(dev_name, "no"))
                self._run(f"dialog enter {dev_name}", calls.console_enter_raw(dev_name, ""))
            elif not prompt.strip():
                self._run(f"wake console {dev_name}", calls.console_enter_raw(dev_name, ""))
        except PTError:
            pass

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

    def send_cli(self, device: str, command: str, mode: str = "") -> str:
        """Ejecuta uno o varios comandos IOS (separados por '\\n') en `device`.
        Si `mode` está vacío, el primer comando detecta si es `enable` o `conf t`, o usa el modo actual `""`
        para respetar submodos como `interface GigabitEthernet0/0` o `ip dhcp pool ...` entre llamadas.
        """
        device = device.strip()
        self._ready_console(device)
        lines = [ln.strip() for ln in command.splitlines() if ln.strip()]
        if not lines:
            raise ValidationError("El comando CLI no puede estar vacío.")

        results = []
        for idx, cmd in enumerate(lines):
            low = cmd.lower()
            if low in ("enable", "en"):
                # Cambiamos a modo enable ejecutando un comando inocuo o pasando mode="enable"
                reply = self._run(f"cli {device} [enable]", calls.device_enter_command(device, "!", "enable"))
                results.append({"command": cmd, "status": "ok", "output": ""})
                continue
            if low in ("configure terminal", "conf t", "config t", "configure t"):
                reply = self._run(f"cli {device} [global]", calls.device_enter_command(device, "!", "global"))
                results.append({"command": cmd, "status": "ok", "output": ""})
                continue

            call_mode = mode if (idx == 0 and mode) else ""
            reply = self._run(f"cli {device}> {cmd}", calls.device_enter_command(device, cmd, call_mode))
            if isinstance(reply, tuple) and len(reply) == 2:
                code, out = reply
                # Si se envió en modo 'user' por defecto y falló como inválido, reintentamos en 'global'
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
        """Aplica un bloque de comandos de configuración IOS entrando automáticamente a modo global."""
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
            
            # Recuperación automática: si falló como comando inválido por estar dentro de un submodo (ej. config-if)
            # enviamos 'exit' y reintentamos en modo global.
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
            wreply = self._run(f"cfg {device}> write memory", calls.device_enter_command(device, "write memory", "enable"))
            saved = isinstance(wreply, tuple) and wreply[0] == 0

        return json.dumps({
            "device": device,
            "completed": all(r["status"] == "ok" for r in results),
            "saved": saved,
            "results": results,
        }, ensure_ascii=False)

    def configure_host(self, device: str, ip: str = "", mask: str = "", gateway: str = "",
                       dns: str = "", dhcp: bool = False, port: str = "FastEthernet0") -> str:
        """Configura IPv4 estática o DHCP en un PC, Laptop o Server."""
        device = device.strip()
        port = port.strip() or "FastEthernet0"
        if dhcp:
            self._run(f"dhcp port {device}:{port}", calls.host_set_dhcp(device, port, True))
            self._run(f"dhcp dev {device}", calls.host_set_device_dhcp(device, True))
        else:
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
            "dhcp": dhcp,
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

    def raw_ipc_call(self, root: str, steps_spec: list[dict[str, Any]]) -> str:
        """Invoca cualquier cadena de métodos de la API IPC de Packet Tracer usando el índice oficial
        `ipc_index.json` para codificar cada parámetro con su tipo exacto (QString=9 vs string=8, etc.).
        """
        idx = _load_ipc_index()
        roots = idx.get("roots", {})
        classes = idx.get("classes", {})
        enums = idx.get("enums", {})

        cur_class = roots.get(root)
        steps: list[Step] = [Step(root)]

        def find_method(cls_name: str | None, mname: str) -> dict[str, Any] | None:
            if not cls_name or cls_name not in classes:
                return None
            queue = [cls_name]
            seen = set()
            while queue:
                c = queue.pop(0)
                if c in seen or c not in classes:
                    continue
                seen.add(c)
                for m in classes[c].get("methods", []):
                    if m.get("name") == mname and not m.get("local", False):
                        return m
                queue.extend(classes[c].get("extends", []))
            return None

        def encode_param(pkind: str, val: Any) -> Arg:
            if pkind == "qstring":
                return Arg.qstring(str(val))
            if pkind == "string":
                return Arg.string(str(val))
            if pkind == "int":
                return Arg.integer(int(val))
            if pkind == "long":
                return Arg.long_int(int(val))
            if pkind == "short":
                return Arg.short(int(val))
            if pkind == "byte":
                return Arg.byte(int(val))
            if pkind == "bool":
                return Arg.boolean(bool(val))
            if pkind == "float":
                return Arg.float32(float(val))
            if pkind == "double":
                return Arg.double(float(val))
            if pkind == "ip":
                return Arg.ip(str(val))
            if pkind == "ipv6":
                return Arg.ipv6(str(val))
            if pkind == "mac":
                return Arg.mac(str(val))
            if pkind == "uuid":
                return Arg.uuid(str(val))
            if pkind.startswith("enum:"):
                ename = pkind.split(":", 1)[1]
                etable = enums.get(ename, {})
                if isinstance(val, int):
                    return Arg.integer(val)
                for k, v in etable.items():
                    if k.lower() == str(val).lower():
                        return Arg.integer(int(v))
                raise ValidationError(f"Valor '{val}' inválido para enum {ename}. Opciones: {list(etable.keys())}")
            return Arg.string(str(val))

        for item in steps_spec:
            mname = item["method"]
            raw_args = item.get("args", [])
            mdef = find_method(cur_class, mname)
            if mdef:
                wire_name = mdef.get("ipc") or mname
                params = mdef.get("params", [])
                typed_args = tuple(
                    encode_param(params[i], raw_args[i]) if i < len(params) else Arg.string(str(raw_args[i]))
                    for i in range(len(raw_args))
                )
                ret = mdef.get("returns", "")
                cur_class = ret.split(":", 1)[1] if ret.startswith("object:") else None
            else:
                wire_name = mname
                typed_args = tuple(
                    Arg.boolean(a) if isinstance(a, bool)
                    else Arg.integer(a) if isinstance(a, int)
                    else Arg.double(a) if isinstance(a, float)
                    else Arg.string(str(a))
                    for a in raw_args
                )
                cur_class = None
            steps.append(Step(wire_name, typed_args))

        res = self._run(f"raw_ipc {root}", steps)
        return json.dumps({"call": describe(steps), "result": res}, ensure_ascii=False)

    def save_file(self) -> str:
        """Guarda el archivo de Packet Tracer actualmente abierto."""
        self._run("fileSave", [Step("appWindow"), Step("fileSave")])
        return json.dumps({"saved": True})

    def get_instructions(self) -> str:
        """Obtiene las instrucciones del laboratorio desde la ventana de actividad."""
        import re
        import urllib.parse
        raw = str(self._run("getInstructionsUrl", [
            Step("appWindow"), Step("getInstructionDlg"), Step("getWebView"), Step("getUrl")
        ]) or "")
        if raw.startswith("data:text/html;charset=UTF-8,"):
            html = urllib.parse.unquote(raw[len("data:text/html;charset=UTF-8,"):])
            clean = re.sub(r"<[^>]+>", "\n", html)
            lines = [ln.strip() for ln in clean.splitlines() if ln.strip()]
            return json.dumps({"text": "\n".join(lines), "raw_html": html}, ensure_ascii=False)
        return json.dumps({"text": raw}, ensure_ascii=False)

    def ping(self, device: str, target_ip: str) -> str:
        """Ejecuta un ping desde un dispositivo y reporta el resultado."""
        device = device.strip()
        target_ip = target_ip.strip()
        # En routers o switches
        res = self.send_cli(device, f"ping {target_ip}", mode="enable")
        try:
            data = json.loads(res)
            out = data.get("output", "")
            success = "!" in out or "Success rate is" in out and " 0 percent" not in out
            return json.dumps({
                "source": device,
                "target": target_ip,
                "success": success,
                "output": out,
            }, ensure_ascii=False)
        except (PTError, ValueError, KeyError, TypeError):
            return res

    def audit_network(self) -> str:
        """Audita toda la red en una sola llamada: dispositivos, interfaces, IPs, máscaras y rutas."""
        topo = json.loads(self.topology())
        devices = topo.get("devices", [])
        report: dict[str, Any] = {"routers": {}, "hosts": {}, "switches": []}

        for d in devices:
            name, kind = d["name"], d.get("kind", "")
            if kind == "router":
                try:
                    res_int = json.loads(self.send_cli(name, "show ip int br", mode="enable"))
                    res_rt = json.loads(self.send_cli(name, "show ip route", mode="enable"))
                    report["routers"][name] = {
                        "interfaces": res_int.get("output", ""),
                        "routes": res_rt.get("output", ""),
                    }
                except (PTError, ValueError, KeyError, TypeError) as exc:
                    report["routers"][name] = {"error": str(exc)}
            elif kind in ("pc", "laptop", "server"):
                try:
                    cur_ip = self._run(
                        f"getIp {name}:Fa0",
                        calls.port_step(name, "FastEthernet0") + [Step("getIpAddress")],
                    )
                    cur_mask = self._run(
                        f"getMask {name}:Fa0",
                        calls.port_step(name, "FastEthernet0") + [Step("getSubnetMask")],
                    )
                    report["hosts"][name] = {
                        "ip": cur_ip,
                        "mask": cur_mask,
                        "kind": kind,
                    }
                except (PTError, ValueError, KeyError, TypeError) as exc:
                    report["hosts"][name] = {"error": str(exc)}
            elif kind in ("switch", "multi_layer_switch"):
                report["switches"].append(name)

        return json.dumps(report, ensure_ascii=False)



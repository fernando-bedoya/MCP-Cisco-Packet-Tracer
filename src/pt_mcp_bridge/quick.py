"""CLI rápido para operaciones instantáneas sobre Cisco Packet Tracer.

Uso:
    pt-quick summary
    pt-quick audit
    pt-quick ping <device> <target_ip>
    pt-quick save
    pt-quick ff [veces]
    pt-quick instructions
    pt-quick cli <device> "<command>"
"""
from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager

from pt_mcp_bridge import config
from pt_mcp_bridge.ipc import ClientEvents, PTClient, PTError
from pt_mcp_bridge.service import PacketTracerService


@contextmanager
def connected_service(
    host: str = config.DEFAULT_PT_HOST,
    port: int = config.DEFAULT_PT_PORT,
) -> Iterator[PacketTracerService]:
    """Context manager que abre y cierra limpiamente la sesión IPC."""
    client = PTClient(ClientEvents())
    try:
        client.connect(host, port)
    except PTError as exc:
        print(f"ERROR: No se pudo conectar al IPC de PT ({host}:{port}): {exc}", file=sys.stderr)
        sys.exit(1)
    try:
        yield PacketTracerService(client)
    finally:
        client.disconnect(quiet=True)


def cmd_summary(svc: PacketTracerService) -> None:
    topo = json.loads(svc.topology())
    print("=== DISPOSITIVOS ENCONTRADOS ===")
    for d in topo["devices"]:
        print(f"  {d['name']:15} [{d['kind']:10} - {d['model']}]")

    print("\n=== INTERFACES DE ROUTERS (IP / ESTADO) ===")
    routers = [d["name"] for d in topo["devices"] if d["kind"] == "router"]
    for r in routers:
        print(f"\n[{r}]")
        res = json.loads(svc.send_cli(r, "show ip int br", mode="enable"))
        print(res.get("output", ""))


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: pt-quick <summary|audit|ping|save|ff|instructions|cli> [args...]")
        sys.exit(0)

    action = sys.argv[1].lower()
    with connected_service() as svc:
        if action == "summary":
            cmd_summary(svc)
        elif action == "audit":
            print(svc.audit_network())
        elif action == "ping" and len(sys.argv) >= 4:
            print(svc.ping(sys.argv[2], sys.argv[3]))
        elif action == "save":
            svc.save_file()
            print("OK: Archivo de Packet Tracer guardado exitosamente.")
        elif action == "ff":
            times = int(sys.argv[2]) if len(sys.argv) > 2 else 5
            for _ in range(times):
                svc.fast_forward()
            print(f"OK: Tiempo adelantado {times} veces (convergencia acelerada).")
        elif action == "instructions":
            info = json.loads(svc.get_instructions())
            print("=== INSTRUCCIONES DEL LABORATORIO ===")
            print(info.get("text", ""))
        elif action == "cli" and len(sys.argv) >= 4:
            res = json.loads(svc.send_cli(sys.argv[2], " ".join(sys.argv[3:])))
            print(res.get("output", res))
        else:
            print(f"Acción '{action}' no reconocida o faltan argumentos.", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()

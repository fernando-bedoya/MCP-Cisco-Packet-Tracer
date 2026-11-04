"""CLI rápido para operaciones instantáneas sobre Cisco Packet Tracer.

Uso:
    python -m pt_mcp_bridge.quick summary
    python -m pt_mcp_bridge.quick save
    python -m pt_mcp_bridge.quick ff [veces]
    python -m pt_mcp_bridge.quick instructions
    python -m pt_mcp_bridge.quick cli <device> "<command>"
"""
import json
import sys

from pt_mcp_bridge.ipc import ClientEvents, PTClient, PTError
from pt_mcp_bridge.service import PacketTracerService


def _client() -> tuple[PTClient, PacketTracerService]:
    c = PTClient(ClientEvents())
    try:
        c.connect("127.0.0.1", 39000)
    except PTError as exc:
        print(f"ERROR: No se pudo conectar al IPC de PT (puerto 39000): {exc}", file=sys.stderr)
        sys.exit(1)
    return c, PacketTracerService(c)


def cmd_summary():
    c, svc = _client()
    try:
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
    finally:
        c.disconnect(quiet=True)


def cmd_save():
    c, svc = _client()
    try:
        svc.save_file()
        print("OK: Archivo de Packet Tracer guardado exitosamente.")
    finally:
        c.disconnect(quiet=True)


def cmd_ff(times: int = 5):
    c, svc = _client()
    try:
        for _ in range(times):
            svc.fast_forward()
        print(f"OK: Tiempo adelantado {times} veces (convergencia acelerada).")
    finally:
        c.disconnect(quiet=True)


def cmd_instructions():
    c, svc = _client()
    try:
        info = json.loads(svc.get_instructions())
        print("=== INSTRUCCIONES DEL LABORATORIO ===")
        print(info.get("text", ""))
    finally:
        c.disconnect(quiet=True)


def cmd_cli(dev: str, cmd: str):
    c, svc = _client()
    try:
        res = json.loads(svc.send_cli(dev, cmd))
        print(res.get("output", res))
    finally:
        c.disconnect(quiet=True)


def main():
    if len(sys.argv) < 2:
        print("Comandos disponibles: summary, save, ff, instructions, cli <dev> <cmd>")
        sys.exit(0)

    action = sys.argv[1].lower()
    if action == "summary":
        cmd_summary()
    elif action == "audit":
        c, svc = _client()
        try:
            print(svc.audit_network())
        finally:
            c.disconnect(quiet=True)
    elif action == "ping" and len(sys.argv) >= 4:
        c, svc = _client()
        try:
            print(svc.ping(sys.argv[2], sys.argv[3]))
        finally:
            c.disconnect(quiet=True)
    elif action == "save":
        cmd_save()
    elif action == "ff":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        cmd_ff(n)
    elif action == "instructions":
        cmd_instructions()
    elif action == "cli" and len(sys.argv) >= 4:
        cmd_cli(sys.argv[2], " ".join(sys.argv[3:]))
    else:
        print(f"Acción '{action}' no reconocida o faltan argumentos.")


if __name__ == "__main__":
    main()

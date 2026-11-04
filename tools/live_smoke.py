"""Prueba rápida en vivo: si hay un .pka bloqueado abierto, abre un lienzo limpio temporal y prueba las herramientas."""
from __future__ import annotations

import sys

from pt_mcp_bridge import config
from pt_mcp_bridge.ipc import ClientEvents, PTClient, PTError
from pt_mcp_bridge.ipc.protocol import Arg, Step
from pt_mcp_bridge.service import PacketTracerService


def main() -> int:
    client = PTClient(ClientEvents(on_log=lambda lvl, msg: print(f"[{lvl.upper():5}] {msg}")))
    try:
        client.connect(config.DEFAULT_PT_HOST, config.DEFAULT_PT_PORT)
    except PTError as exc:
        print(f"ERROR: No se pudo conectar a Packet Tracer: {exc}", file=sys.stderr)
        return 1

    svc = PacketTracerService(client)
    try:
        try:
            print("Probando lectura en el archivo actual...")
            print("Topología actual:", svc.topology())
        except PTError as exc:
            print(f"AVISO en el archivo actual: {exc}")
            print("Abriendo un espacio de trabajo limpio (fileNew) para probar sin bloqueo de .pka...")
            try:
                client.call([Step("appWindow"), Step("fileNew", (Arg.boolean(False),))])
            except PTError as e2:
                print("fileNew:", e2)

        print("\n1) Creando Router R1 y Switch SW1:")
        print("  ", svc.add_device("R1", "router", "2911", 150, 150))
        print("  ", svc.add_device("SW1", "switch", "2960-24TT", 350, 150))

        print("\n2) Conectando R1:GigabitEthernet0/0 <-> SW1:FastEthernet0/1:")
        print("  ", svc.connect_ports("R1", "GigabitEthernet0/0", "SW1", "FastEthernet0/1", "straight"))

        print("\n3) Configurando interfaz en R1 por CLI IOS:")
        print(
            "  ",
            svc.configure_ios(
                "R1",
                [
                    "interface GigabitEthernet0/0",
                    "ip address 192.168.10.1 255.255.255.0",
                    "no shutdown",
                ],
                save=True,
            ),
        )

        print("\n4) Topología resultante:")
        print("  ", svc.topology())
    finally:
        client.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())

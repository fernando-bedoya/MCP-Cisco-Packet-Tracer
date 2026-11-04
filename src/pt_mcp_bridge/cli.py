"""Punto de entrada: GUI (por defecto) o modo --stdio headless."""
from __future__ import annotations

import argparse
import sys
import threading

from pt_mcp_bridge import config
from pt_mcp_bridge.ipc import ClientEvents, PTClient, PTError
from pt_mcp_bridge.service import PacketTracerService


def _run_stdio(host: str, port: int) -> int:
    from pt_mcp_bridge.mcp_server import build_mcp

    # stdout está reservado al protocolo MCP: los logs van a stderr.
    client = PTClient(ClientEvents(
        on_log=lambda lvl, msg: print(f"[{lvl}] {msg}", file=sys.stderr, flush=True)))
    client.auto_reconnect = True

    def connect() -> None:
        try:
            client.connect(host, port)
        except PTError:
            client.reconnect_loop()
    threading.Thread(target=connect, daemon=True).start()
    build_mcp(PacketTracerService(client)).run(transport="stdio")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pt-mcp-bridge", description="Puente MCP para Cisco Packet Tracer")
    parser.add_argument("--stdio", action="store_true", help="MCP por stdio, sin GUI")
    parser.add_argument("--host", default=config.DEFAULT_PT_HOST, help="Host del IPC de PT")
    parser.add_argument("--port", type=int, default=config.DEFAULT_PT_PORT, help="Puerto IPC de PT")
    parser.add_argument("--mcp-port", type=int, default=config.DEFAULT_MCP_PORT,
                        help="Puerto del servidor MCP HTTP (modo GUI)")
    args = parser.parse_args(argv)
    if args.stdio:
        return _run_stdio(args.host, args.port)
    from pt_mcp_bridge.gui import run_gui  # import diferido: --stdio no necesita Qt
    return run_gui(args.mcp_port)


if __name__ == "__main__":
    sys.exit(main())


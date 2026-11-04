"""Punto de entrada: GUI (por defecto), modo --headless HTTP o modo --stdio."""
from __future__ import annotations

import argparse
import sys
import threading

from pt_mcp_bridge import config
from pt_mcp_bridge.ipc import ClientEvents, PTClient, PTError
from pt_mcp_bridge.service import PacketTracerService


def _build_auto_client(host: str, port: int, log_stream) -> PTClient:
    client = PTClient(
        ClientEvents(on_log=lambda lvl, msg: print(f"[{lvl.upper():5}] {msg}", file=log_stream, flush=True))
    )
    client.auto_reconnect = True

    def connect() -> None:
        try:
            client.connect(host, port)
        except PTError:
            client.reconnect_loop()

    threading.Thread(target=connect, daemon=True).start()
    return client


def _run_stdio(host: str, port: int) -> int:
    from pt_mcp_bridge.mcp_server import build_mcp

    # stdout está reservado al protocolo MCP: los logs van a stderr.
    client = _build_auto_client(host, port, sys.stderr)
    build_mcp(PacketTracerService(client)).run(transport="stdio")
    return 0


def _run_http_headless(host: str, port: int, mcp_host: str, mcp_port: int) -> int:
    from pt_mcp_bridge.mcp_server import build_mcp

    client = _build_auto_client(host, port, sys.stdout)
    print(f"[INFO ] Servidor MCP Headless escuchando en http://{mcp_host}:{mcp_port}/mcp", flush=True)
    build_mcp(PacketTracerService(client), host=mcp_host, port=mcp_port).run(transport="streamable-http")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="el-arriero-mcp", description="El Arriero MCP — Puente MCP para Cisco Packet Tracer")
    parser.add_argument("--stdio", action="store_true", help="MCP por stdio, sin GUI")
    parser.add_argument("--headless", action="store_true", help="Servidor MCP HTTP en consola, sin GUI (ideal para Docker)")
    parser.add_argument("--host", default=config.DEFAULT_PT_HOST, help="Host del IPC de PT")
    parser.add_argument("--port", type=int, default=config.DEFAULT_PT_PORT, help="Puerto IPC de PT")
    parser.add_argument("--mcp-host", default=config.DEFAULT_MCP_HOST, help="Host del servidor MCP HTTP")
    parser.add_argument("--mcp-port", type=int, default=config.DEFAULT_MCP_PORT,
                        help="Puerto del servidor MCP HTTP")
    args = parser.parse_args(argv)
    if args.stdio:
        return _run_stdio(args.host, args.port)
    if args.headless:
        return _run_http_headless(args.host, args.port, args.mcp_host, args.mcp_port)

    try:
        from pt_mcp_bridge.gui import run_gui  # import diferido: --stdio/--headless no necesitan Qt
    except ImportError as exc:
        print(
            f"[WARN ] No se pudo cargar PyQt6 ({exc}). Iniciando automáticamente en modo --headless HTTP...",
            file=sys.stderr,
        )
        return _run_http_headless(args.host, args.port, args.mcp_host, args.mcp_port)
    return run_gui(args.mcp_port)


if __name__ == "__main__":
    sys.exit(main())

"""Proxy TCP de diagnóstico que registra en hex/ASCII el tráfico entre la utilidad IPC Test y Packet Tracer.

Uso:  python tools/capture_proxy.py
Luego, en la ventana "IPC Connection Test" de PT pon Port = 39001 y pulsa Test.
Ctrl+C para terminar. Se guarda además en capture.log.
"""
from __future__ import annotations

import socket
import threading
import time
from typing import TextIO

from pt_mcp_bridge import config

LISTEN = (config.DEFAULT_PT_HOST, config.DEFAULT_PT_PORT + 1)
TARGET = (config.DEFAULT_PT_HOST, config.DEFAULT_PT_PORT)


def log(msg: str, log_file: TextIO | None = None) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line)
    if log_file is not None:
        log_file.write(line + "\n")


def pump(src: socket.socket, dst: socket.socket, tag: str, log_file: TextIO) -> None:
    try:
        while data := src.recv(65536):
            log(f"{tag} {len(data)}B hex={data.hex(' ')}", log_file)
            log(f"{tag} ascii={data.decode('latin1')!r}", log_file)
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            s.close()


def handle(client: socket.socket, log_file: TextIO) -> None:
    log("== nueva conexión ==", log_file)
    try:
        server = socket.create_connection(TARGET, timeout=config.CONNECT_TIMEOUT_S)
        server.settimeout(None)
    except OSError as exc:
        log(f"== error conectando a {TARGET}: {exc} ==", log_file)
        client.close()
        return

    threading.Thread(target=pump, args=(client, server, "CLI->PT", log_file), daemon=True).start()
    pump(server, client, "PT->CLI", log_file)
    log("== conexión cerrada ==", log_file)


def main() -> None:
    with open("capture.log", "a", buffering=1, encoding="utf-8") as log_file, socket.socket() as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(LISTEN)
        srv.listen()
        log(f"Escuchando en {LISTEN}, reenviando a {TARGET}", log_file)
        try:
            while True:
                c, _ = srv.accept()
                threading.Thread(target=handle, args=(c, log_file), daemon=True).start()
        except KeyboardInterrupt:
            log("Proxy detenido por el usuario.", log_file)


if __name__ == "__main__":
    main()

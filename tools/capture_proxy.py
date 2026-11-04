"""Proxy TCP que registra en hex/ASCII el tráfico entre la utilidad IPC Test de PT y PT.

Uso:  python capture_proxy.py
Luego, en la ventana "IPC Connection Test" de PT pon Port = 39001 y pulsa Test.
Ctrl+C para terminar. Se guarda además en capture.log.
"""
import socket
import threading
import time

LISTEN = ("127.0.0.1", 39001)
TARGET = ("127.0.0.1", 39000)
LOG = open("capture.log", "a", buffering=1)


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line)
    LOG.write(line + "\n")


def pump(src, dst, tag):
    try:
        while (data := src.recv(65536)):
            log(f"{tag} {len(data)}B hex={data.hex(' ')}")
            log(f"{tag} ascii={data.decode('latin1')!r}")
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def handle(client):
    log("== nueva conexión ==")
    server = socket.create_connection(TARGET)
    threading.Thread(target=pump, args=(client, server, "CLI->PT"), daemon=True).start()
    pump(server, client, "PT->CLI")
    log("== conexión cerrada ==")


srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(LISTEN)
srv.listen()
log(f"Escuchando en {LISTEN}, reenviando a {TARGET}")
while True:
    c, _ = srv.accept()
    threading.Thread(target=handle, args=(c,), daemon=True).start()


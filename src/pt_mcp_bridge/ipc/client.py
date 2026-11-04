"""Cliente TCP thread-safe hacia el IPC (PTMP) de Packet Tracer."""
from __future__ import annotations

import enum
import itertools
import random
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pt_mcp_bridge import config
from pt_mcp_bridge.ipc import protocol
from pt_mcp_bridge.ipc.protocol import Arg, ProtocolError, Step


class PTError(Exception):
    """Error de comunicación con Packet Tracer."""


class ConnectionState(str, enum.Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    ONLINE = "online"
    ERROR = "error"


def _noop(*_: Any) -> None:
    pass


@dataclass
class ClientEvents:
    """Callbacks de observación (se invocan desde hilos de fondo).

    on_log(level, message): level in {info, warn, error, tx, rx, mcp}
    """

    on_log: Callable[[str, str], None] = _noop
    on_state: Callable[[ConnectionState], None] = _noop


@dataclass
class _Pending:
    event: threading.Event = field(default_factory=threading.Event)
    result: Any = None
    error: str | None = None


def _fmt_arg(a: Any) -> str:
    if isinstance(a, Arg):
        if a.type_code in (8, 9, 10, 11, 12, 13):
            return repr(str(a.value))
        return str(a.value)
    return repr(a)


def describe(steps: list[Step]) -> str:
    return ".".join(f"{s.name}({', '.join(_fmt_arg(a) for a in s.args)})" for s in steps)


class PTClient:
    def __init__(self, events: ClientEvents | None = None) -> None:
        self.events = events or ClientEvents()
        self.host = config.DEFAULT_PT_HOST
        self.port = config.DEFAULT_PT_PORT
        self.app_id = config.DEFAULT_APP_ID
        self.key = config.DEFAULT_KEY
        self.auth_mode = 4  # 4 = MD5 (estándar ExApps registradas), 1 = Clear/None
        self.auto_reconnect = False
        self._state = ConnectionState.DISCONNECTED
        self._sock: socket.socket | None = None
        self._write_lock = threading.Lock()
        self._ids = itertools.count(random.randint(1, 10**9))
        self._pending: dict[int, _Pending] = {}
        self._stop = threading.Event()

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def connected(self) -> bool:
        return self._state is ConnectionState.ONLINE

    def log(self, level: str, message: str) -> None:
        self.events.on_log(level, message)

    def _set_state(self, state: ConnectionState) -> None:
        self._state = state
        self.events.on_state(state)

    # -- conexión ------------------------------------------------------
    def connect(self, host: str, port: int, timeout: float = config.CONNECT_TIMEOUT_S) -> None:
        """Bloqueante (TCP + handshake PTMP): llamar desde un hilo de fondo."""
        self.disconnect(quiet=True)
        self.host, self.port = host, port
        self._stop.clear()
        self._set_state(ConnectionState.CONNECTING)
        self.log("info", f"Conectando a {host}:{port} ...")

        # Probamos primero el app_id configurado (con MD5 y con Clear), y si PT aún no tiene
        # registrado el .pta, caemos a FALLBACK_APP_ID para al menos conectar e informar al usuario.
        candidates = [(self.app_id, self.auth_mode)]
        if self.auth_mode != 1:
            candidates.append((self.app_id, 1))
        if self.app_id != config.FALLBACK_APP_ID:
            candidates.append((config.FALLBACK_APP_ID, 1))

        last_err: Exception | None = None
        sock: socket.socket | None = None
        parser: protocol.FrameParser | None = None
        backlog: list = []
        used_app = self.app_id

        for cand_app, cand_mode in candidates:
            sock = None
            try:
                sock = socket.create_connection((host, port), timeout=timeout)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                parser, backlog = self._handshake(sock, cand_app, cand_mode)
                sock.settimeout(None)
                used_app = cand_app
                break
            except (OSError, ProtocolError, PTError) as exc:
                last_err = exc
                if sock:
                    sock.close()
                sock = None
                # Si el puerto TCP está cerrado (ConnectionRefused), no tiene sentido probar otros IDs
                if isinstance(exc, OSError):
                    break

        if sock is None or parser is None:
            self._set_state(ConnectionState.ERROR)
            self.log("error", f"No se pudo conectar: {last_err}")
            raise PTError(f"No se pudo conectar a {host}:{port}: {last_err}") from last_err

        self._sock = sock
        threading.Thread(target=self._read_loop, args=(sock, parser, backlog), daemon=True).start()
        self._set_state(ConnectionState.ONLINE)
        if used_app == config.FALLBACK_APP_ID and self.app_id != config.FALLBACK_APP_ID:
            self.log(
                "warn",
                f"Conectado con '{used_app}' (privilegios limitados). Para habilitar todas las herramientas "
                "registra 'pt-mcp-bridge.pta' en Packet Tracer: Extensions -> IPC -> Configure Apps -> Add.",
            )
        else:
            self.log("info", f"Conexión IPC establecida como '{used_app}' (todos los privilegios activos).")

    def _handshake(self, sock: socket.socket, app_id: str, auth_mode: int):
        parser, backlog = protocol.FrameParser(), []

        def expect(mtype: str) -> list[str]:
            while not backlog:
                data = sock.recv(65536)
                if not data:
                    raise PTError("PT cerró la conexión durante el handshake")
                backlog.extend(parser.feed(data))
            frame = backlog.pop(0)
            self.log("rx", f"handshake {frame}")
            if frame[0] != mtype:
                raise PTError(f"Handshake ({app_id}): esperaba tipo {mtype}, llegó {frame}")
            return frame

        sock.sendall(protocol.hello(auth_mode))
        neg_reply = expect(protocol.HELLO_REPLY)
        server_auth = auth_mode
        if len(neg_reply) > 7:
            try:
                server_auth = int(neg_reply[7])
            except ValueError:
                pass
        sock.sendall(protocol.app_id(app_id))
        chal_frame = expect(protocol.CHALLENGE)
        challenge = chal_frame[1] if len(chal_frame) > 1 else ""
        sock.sendall(protocol.auth(app_id, self.key, challenge=challenge, auth_mode=server_auth))
        result = expect(protocol.AUTH_RESULT)
        if len(result) < 2 or result[1] != "true":
            raise PTError(f"Autenticación rechazada para '{app_id}'")
        return parser, backlog

    def disconnect(self, quiet: bool = False) -> None:
        self._stop.set()
        sock, self._sock = self._sock, None
        if sock:
            try:
                sock.sendall(protocol.bye())
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()
        self._fail_pending("Desconectado")
        if not quiet:
            self.log("info", "Desconectado.")
        self._set_state(ConnectionState.DISCONNECTED)

    def reconnect_loop(self) -> None:
        """Reintenta con backoff exponencial hasta conectar o hasta disconnect()."""
        delay = 1.0
        while not self._stop.is_set() and self.auto_reconnect:
            self.log("warn", f"Reintentando conexión en {delay:.0f}s ...")
            if self._stop.wait(delay):
                return
            try:
                self.connect(self.host, self.port)
                return
            except PTError:
                delay = min(delay * 2, config.MAX_RECONNECT_DELAY_S)

    def _fail_pending(self, reason: str) -> None:
        for pending in list(self._pending.values()):
            pending.error = reason
            pending.event.set()

    # -- lectura -------------------------------------------------------
    def _read_loop(self, sock: socket.socket, parser: protocol.FrameParser, backlog: list) -> None:
        try:
            for frame in backlog:
                self._dispatch(frame)
            while not self._stop.is_set():
                chunk = sock.recv(65536)
                if not chunk:
                    raise ConnectionError("Packet Tracer cerró la conexión")
                for frame in parser.feed(chunk):
                    self._dispatch(frame)
        except (OSError, ProtocolError) as exc:
            if self._stop.is_set():
                return
            self.log("error", f"Conexión perdida: {exc}")
            self._sock = None
            self._set_state(ConnectionState.ERROR)
            self._fail_pending(str(exc))
            if self.auto_reconnect:
                threading.Thread(target=self.reconnect_loop, daemon=True).start()

    def _dispatch(self, frame: list[str]) -> None:
        self.log("rx", ",".join(frame))
        resp = protocol.parse_result(frame)
        if resp is None:
            return
        pending = self._pending.get(resp.request_id)
        if pending is None:
            return
        pending.error, pending.result = resp.error, resp.result
        pending.event.set()

    # -- API pública ---------------------------------------------------
    def call(self, steps: list[Step], timeout: float = config.REQUEST_TIMEOUT_S) -> Any:
        """Invoca una cadena de métodos, ej. [Step('appWindow'), Step('isSimulationMode')]."""
        sock = self._sock
        if not self.connected or sock is None:
            raise PTError("No hay conexión con Packet Tracer.")
        rid = next(self._ids)
        pending = self._pending[rid] = _Pending()
        try:
            self.log("tx", describe(steps))
            with self._write_lock:
                sock.sendall(protocol.call(rid, steps))
            if not pending.event.wait(timeout):
                raise PTError(f"Timeout ({timeout}s) esperando respuesta de Packet Tracer.")
            if pending.error:
                if "necessary privilege" in pending.error:
                    pta = config.pta_file_path()
                    raise PTError(
                        f"{pending.error} — Registra una sola vez el archivo "
                        f"'{pta}' "
                        "en Packet Tracer (Extensions -> IPC -> Configure Apps -> Add -> Ok) "
                        "y reconecta."
                    )
                raise PTError(pending.error)
            return pending.result
        except OSError as exc:
            raise PTError(f"Error de socket: {exc}") from exc
        finally:
            self._pending.pop(rid, None)

    def ping(self, timeout: float = 5.0) -> float:
        """Latencia en ms de appWindow().isSimulationMode()."""
        start = time.monotonic()
        self.call([Step("appWindow"), Step("isSimulationMode")], timeout=timeout)
        return (time.monotonic() - start) * 1000

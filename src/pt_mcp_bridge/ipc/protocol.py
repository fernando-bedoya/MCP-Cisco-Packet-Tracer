"""PTMP: Protocolo IPC oficial de Cisco Packet Tracer (basado en la especificación formal y pktctl).

Formato de trama: `<length>\\0<body>`
- `length`: tamaño de `body` en bytes (ASCII decimal).
- `body`: secuencia de campos terminados en `\\0` (con excepción de listas crudas de bytes).

Formato de llamada (tipo 100):
    `100\\0<id>\\0<metodo>\\0[<tipo>\\0<valor>\\0 ...]<0>\\0...`
IMPORTANTE: Cada eslabón de método termina con `"0"` (`END_OF_ARGUMENTS`, void), NO lleva un contador de argumentos antes de los parámetros.

Tipos de datos (TypeCode):
    0=void, 1=byte, 2=bool, 3=short, 4=int, 5=long, 6=float, 7=double,
    8=string, 9=QString, 10=IPv4, 11=IPv6, 12=MAC, 13=UUID, 14=pair, 15=vector, 16=data
"""
from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass
from typing import Any

HELLO, HELLO_REPLY, APP_ID, CHALLENGE, AUTH, AUTH_RESULT, KEEP_ALIVE, BYE = (
    "0", "1", "2", "3", "4", "5", "6", "7"
)
CALL, ERROR, RESULT, EVENT, SUBSCRIBE = "100", "101", "102", "103", "104"
PT_VERSION_STR = ":PTVER9.0.1.0858"
END_OF_ARGUMENTS = "0"


class ProtocolError(Exception):
    """Error de formato en el protocolo PTMP."""


@dataclass(frozen=True)
class Arg:
    """Argumento tipado explícitamente para llamadas IPC (distingue string=8 de QString=9, etc.)."""
    type_code: int
    value: Any

    @staticmethod
    def byte(val: int) -> Arg:
        return Arg(1, str(int(val)))

    @staticmethod
    def boolean(val: bool) -> Arg:
        return Arg(2, "true" if val else "false")

    @staticmethod
    def short(val: int) -> Arg:
        return Arg(3, str(int(val)))

    @staticmethod
    def integer(val: int) -> Arg:
        return Arg(4, str(int(val)))

    @staticmethod
    def long_int(val: int) -> Arg:
        return Arg(5, str(int(val)))

    @staticmethod
    def float32(val: float) -> Arg:
        return Arg(6, repr(float(val)))

    @staticmethod
    def double(val: float) -> Arg:
        return Arg(7, repr(float(val)))

    @staticmethod
    def string(val: str) -> Arg:
        return Arg(8, str(val))

    @staticmethod
    def qstring(val: str) -> Arg:
        return Arg(9, str(val))

    @staticmethod
    def ip(val: str) -> Arg:
        return Arg(10, str(val))

    @staticmethod
    def ipv6(val: str) -> Arg:
        return Arg(11, str(val))

    @staticmethod
    def mac(val: str) -> Arg:
        return Arg(12, str(val))

    @staticmethod
    def uuid(val: str) -> Arg:
        return Arg(13, str(val))


@dataclass(frozen=True)
class Step:
    """Un eslabón de la cadena de invocación: método(args...)."""
    name: str
    args: tuple[Arg, ...] = ()


@dataclass(frozen=True)
class Response:
    request_id: int | None
    result: Any = None
    error: str | None = None


def encode_frame(fields: list[str]) -> bytes:
    payload = "".join(f + "\0" for f in fields).encode("utf-8")
    return str(len(payload)).encode("ascii") + b"\0" + payload


class FrameParser:
    """Reensambla tramas desde un flujo TCP."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[list[str]]:
        self._buf += data
        frames: list[list[str]] = []
        while True:
            i = self._buf.find(b"\0")
            if i < 0:
                break
            try:
                n = int(self._buf[:i])
            except ValueError as exc:
                raise ProtocolError(f"longitud inválida: {bytes(self._buf[:i])!r}") from exc
            end = i + 1 + n
            if len(self._buf) < end:
                break
            raw_body = bytes(self._buf[i + 1:end])
            del self._buf[:end]
            parts = raw_body.decode("utf-8", errors="replace").split("\0")
            if parts and parts[-1] == "":
                parts.pop()
            frames.append(parts)
        return frames


# -- mensajes de negociación y sesión -------------------------------------
def hello(auth_mode: int = 1) -> bytes:
    """auth_mode: 1 = Clear/None (como usa IPC Connection Test), 4 = MD5."""
    return encode_frame([
        HELLO, "PTMP", "1", "{" + str(uuid.uuid4()) + "}",
        "1", "1", "1", str(auth_mode),
        time.strftime("%Y%m%d%H%M%S"), "0", PT_VERSION_STR,
    ])


def app_id(app: str) -> bytes:
    return encode_frame([APP_ID, app])


def md5_digest(challenge: str, secret: str) -> str:
    h = hashlib.md5()
    h.update(challenge.encode("utf-8"))
    h.update(secret.encode("utf-8"))
    return h.hexdigest().upper()


def auth(app: str, key: str, challenge: str = "", auth_mode: int = 1) -> bytes:
    token = md5_digest(challenge, key) if auth_mode == 4 else key
    return encode_frame([AUTH, app, token, ""])


def bye(reason: str = "") -> bytes:
    return encode_frame([BYE, reason])


def _coerce_arg(a: Any) -> Arg:
    if isinstance(a, Arg):
        return a
    if isinstance(a, bool):
        return Arg.boolean(a)
    if isinstance(a, int):
        return Arg.integer(a)
    if isinstance(a, float):
        return Arg.double(a)
    return Arg.string(str(a))


def call(request_id: int, steps: list[Step]) -> bytes:
    """Codifica una llamada tipo 100 según la especificación real de PTMP:
    `100, id, metodo, [tipo, valor, ...], 0, metodo2, [tipo, valor, ...], 0`
    """
    fields = [CALL, str(request_id)]
    for s in steps:
        fields.append(s.name)
        for raw_arg in s.args:
            arg = _coerce_arg(raw_arg)
            fields.append(str(arg.type_code))
            fields.append(str(arg.value))
        fields.append(END_OF_ARGUMENTS)
    return encode_frame(fields)


# -- decodificación de valores y respuestas -------------------------------
def _decode_value(fields: list[str], idx: int) -> tuple[Any, int]:
    if idx >= len(fields):
        return None, idx
    tcode = fields[idx]
    idx += 1
    if tcode == "0":
        return None, idx
    if tcode == "2":
        val = fields[idx] if idx < len(fields) else "false"
        return (val == "true"), idx + 1
    if tcode in ("1", "3", "4", "5"):
        val = fields[idx] if idx < len(fields) else "0"
        try:
            return int(val), idx + 1
        except ValueError:
            return val, idx + 1
    if tcode in ("6", "7"):
        val = fields[idx] if idx < len(fields) else "0.0"
        try:
            return float(val), idx + 1
        except ValueError:
            return val, idx + 1
    if tcode in ("8", "9", "10", "11", "12", "13"):
        val = fields[idx] if idx < len(fields) else ""
        return val, idx + 1
    if tcode == "14":  # Pair: dos valores tipados consecutivos
        first, idx = _decode_value(fields, idx)
        second, idx = _decode_value(fields, idx)
        return (first, second), idx
    if tcode == "15":  # Vector: element_type, count, luego `count` payloads sin código de tipo individual
        if idx + 1 >= len(fields):
            return [], len(fields)
        elem_code = fields[idx]
        try:
            count = int(fields[idx + 1])
        except ValueError:
            return [], len(fields)
        idx += 2
        items = []
        for _ in range(count):
            item, idx = _decode_payload_of_type(elem_code, fields, idx)
            items.append(item)
        return items, idx
    # Cualquier otro tipo (ej. 16 Data object) devolvemos el resto como lista
    rest = fields[idx:]
    return rest, len(fields)


def _decode_payload_of_type(tcode: str, fields: list[str], idx: int) -> tuple[Any, int]:
    if idx >= len(fields):
        return None, idx
    if tcode == "2":
        return (fields[idx] == "true"), idx + 1
    if tcode in ("1", "3", "4", "5"):
        try:
            return int(fields[idx]), idx + 1
        except ValueError:
            return fields[idx], idx + 1
    if tcode in ("6", "7"):
        try:
            return float(fields[idx]), idx + 1
        except ValueError:
            return fields[idx], idx + 1
    return fields[idx], idx + 1


def parse_result(fields: list[str]) -> Response | None:
    """Devuelve Response si la trama es un resultado (102) o un error (101); None para otras tramas."""
    if not fields or len(fields) < 2:
        return None
    mtype = fields[0]
    if mtype == ERROR:
        try:
            rid = int(fields[1])
        except ValueError:
            return None
        err_class = fields[2] if len(fields) > 2 else "IPC"
        err_msg = fields[3] if len(fields) > 3 else "error desconocido"
        return Response(rid, error=f"{err_class}: {err_msg}")
    if mtype == RESULT:
        try:
            rid = int(fields[1])
        except ValueError:
            return None
        if len(fields) == 2:
            return Response(rid, result=None)
        val, _ = _decode_value(fields, 2)
        return Response(rid, result=val)
    return None

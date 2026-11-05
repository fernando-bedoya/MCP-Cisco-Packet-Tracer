"""Servicio de dominio: Meta-Herramientas, Introspección IPC y Registro de Macros Extensible (SRP, OCP, DIP)."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from pt_mcp_bridge.ipc import IndexRepository, IPCTransport
from pt_mcp_bridge.ipc.client import describe
from pt_mcp_bridge.ipc.protocol import Arg, Step
from pt_mcp_bridge.services.base import DomainServiceBase, ValidationError

MacroHandler = Callable[[dict[str, Any]], str]


class MacroRegistry:
    """Registro extensible de macros de topología (Open/Closed Principle — OCP).

    Nuevas macros pueden registrarse mediante `register(name, handler)` sin modificar
    el código de despacho existente.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, MacroHandler] = {}

    def register(self, name: str, handler: MacroHandler) -> None:
        self._handlers[name.lower().strip()] = handler

    def available(self) -> list[str]:
        return list(self._handlers.keys())

    def execute(self, name: str, params: dict[str, Any] | None = None) -> str:
        key = name.lower().strip()
        handler = self._handlers.get(key)
        if handler is None:
            return json.dumps({
                "available_macros": self.available(),
                "requested": name,
            }, ensure_ascii=False)
        return handler(params or {})


class MetaCatalogService(DomainServiceBase):
    """Gestiona introspección del catálogo `ipc_index.json`, llamadas `raw_ipc` tipadas, `batch` y macros."""

    def __init__(
        self,
        client: IPCTransport,
        index_repo: IndexRepository,
        dispatcher: Callable[[str], Callable[..., Any] | None],
        macro_registry: MacroRegistry | None = None,
    ) -> None:
        super().__init__(client)
        self._index_repo = index_repo
        self._dispatcher = dispatcher
        self.macros = macro_registry or MacroRegistry()

    def raw_ipc_call(self, root: str, steps_spec: list[dict[str, Any]]) -> str:
        """Invoca cualquier cadena de métodos de la API IPC de Packet Tracer usando el repositorio de índice."""
        idx = self._index_repo.load()
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

    def search_methods(self, query: str, class_name: str = "", limit: int = 30) -> str:
        idx = self._index_repo.load()
        classes = idx.get("classes", {})
        q = query.lower().strip()
        cls_filter = class_name.lower().strip()
        matches = []
        for cname, cdata in classes.items():
            if cls_filter and cls_filter not in cname.lower():
                continue
            for m in cdata.get("methods", []):
                mname = m.get("name", "")
                if not q or q in mname.lower() or q in cname.lower():
                    matches.append({
                        "class": cname,
                        "method": mname,
                        "params": m.get("params", []),
                        "returns": m.get("returns", "void"),
                    })
                    if len(matches) >= max(1, int(limit)):
                        break
            if len(matches) >= max(1, int(limit)):
                break
        return json.dumps({"query": query, "count": len(matches), "matches": matches}, ensure_ascii=False)

    def describe_method(self, class_name: str, method_name: str) -> str:
        idx = self._index_repo.load()
        classes = idx.get("classes", {})
        cdata = classes.get(class_name.strip())
        if not cdata:
            return json.dumps({"error": f"Clase '{class_name}' no encontrada en ipc_index.json."}, ensure_ascii=False)
        found = [m for m in cdata.get("methods", []) if m.get("name") == method_name.strip()]
        if not found:
            return json.dumps({"error": f"Método '{method_name}' no encontrado en '{class_name}'."}, ensure_ascii=False)
        return json.dumps({
            "class": class_name.strip(),
            "extends": cdata.get("extends", []),
            "overloads": found,
        }, ensure_ascii=False)

    def batch(self, operations: list[dict[str, Any]], stop_on_error: bool = False) -> str:
        results = []
        for idx, op in enumerate(operations):
            method_name = op.get("tool", "").removeprefix("cpt_")
            kwargs = op.get("args", {})
            fn = self._dispatcher(method_name)
            if not callable(fn):
                err = {"step": idx, "tool": op.get("tool"), "error": f"Operación '{method_name}' no soportada."}
                results.append(err)
                if stop_on_error:
                    break
                continue
            try:
                out = fn(**kwargs)
                results.append({"step": idx, "tool": op.get("tool"), "result": json.loads(out) if isinstance(out, str) else out})
            except Exception as exc:  # noqa: BLE001
                results.append({"step": idx, "tool": op.get("tool"), "error": str(exc)})
                if stop_on_error:
                    break
        return json.dumps({"executed": len(results), "results": results}, ensure_ascii=False)

    def run_macro(self, macro_name: str, params: dict[str, Any] | None = None) -> str:
        return self.macros.execute(macro_name, params)

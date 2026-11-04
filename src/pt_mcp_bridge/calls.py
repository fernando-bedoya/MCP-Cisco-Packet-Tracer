"""Definición de llamadas a la API oficial de Cisco Packet Tracer (tipos verificados con el framework Java y pktctl)."""
from __future__ import annotations

from pt_mcp_bridge.ipc.protocol import Arg, Step

# Códigos oficiales de DeviceType (com.cisco.pt.ipc.enums.DeviceType)
DEVICE_TYPES: dict[str, int] = {
    "router": 0,
    "switch": 1,
    "cloud": 2,
    "bridge": 3,
    "hub": 4,
    "repeater": 5,
    "ap": 7,
    "access_point": 7,
    "pc": 8,
    "server": 9,
    "printer": 10,
    "wireless_router": 11,
    "ip_phone": 12,
    "dsl_modem": 13,
    "cable_modem": 14,
    "multi_layer_switch": 16,
    "switch3650": 17,
    "laptop": 18,
    "tablet": 19,
    "asa": 27,
    "home_gateway": 29,
    "sniffer": 35,
    "wlc": 41,
}

DEVICE_KIND_BY_CODE: dict[int, str] = {
    0: "router", 1: "switch", 2: "cloud", 3: "bridge", 4: "hub", 5: "repeater",
    7: "access_point", 8: "pc", 9: "server", 10: "printer", 11: "wireless_router",
    12: "ip_phone", 13: "dsl_modem", 14: "cable_modem", 16: "multi_layer_switch",
    17: "switch3650", 18: "laptop", 19: "tablet_pc", 27: "asa", 29: "home_gateway",
    35: "sniffer", 41: "wireless_lan_controller",
}

DEFAULT_MODELS: dict[str, str] = {
    "router": "2911",
    "switch": "2960-24TT",
    "multi_layer_switch": "3560-24PS",
    "switch3650": "3650-24PS",
    "pc": "PC-PT",
    "laptop": "Laptop-PT",
    "server": "Server-PT",
    "hub": "Hub-PT",
    "cloud": "Cloud-PT",
    "ap": "AccessPoint-PT",
    "access_point": "AccessPoint-PT",
    "wireless_router": "WRT300N",
    "printer": "Printer-PT",
    "asa": "5505",
    "sniffer": "Sniffer",
}

# Códigos enteros oficiales de ConnectType (com.cisco.pt.ipc.enums.ConnectType)
# ¡CRÍTICO!: createLink recibe un entero (8100..8117), NO un string.
CABLE_CODES: dict[str, int] = {
    "straight": 8100,
    "cross": 8101,
    "crossover": 8101,
    "rollover": 8102,
    "fiber": 8103,
    "phone": 8104,
    "cable": 8105,
    "serial": 8106,
    "auto": 8107,
    "console": 8108,
    "coaxial": 8110,
    "octal": 8111,
    "usb": 8113,
    "fiber_multimode": 8117,
}

CABLE_NAME_BY_CODE: dict[int, str] = {
    8100: "straight", 8101: "cross", 8102: "rollover", 8103: "fiber",
    8104: "phone", 8105: "cable", 8106: "serial", 8107: "auto",
    8108: "console", 8109: "wireless", 8110: "coaxial", 8111: "octal",
    8113: "usb", 8117: "fiber_multimode",
}

SWITCHING_KINDS = {
    "switch", "multi_layer_switch", "switch3650", "hub", "bridge", "repeater",
    "access_point", "wireless_router", "home_gateway", "cloud",
}

_LW = [Step("appWindow"), Step("getActiveWorkspace"), Step("getLogicalWorkspace")]


def resolve_cable_code(cable: str, kind_a: str, port_a: str, kind_b: str, port_b: str) -> int:
    """Resuelve el código entero de ConnectType; si es 'auto', aplica la regla CCNA igual que pktctl."""
    c = cable.lower().strip()
    if c != "auto" and c in CABLE_CODES:
        return CABLE_CODES[c]
    if port_a.startswith("Serial") or port_b.startswith("Serial"):
        return CABLE_CODES["serial"]
    if port_a.lower() == "console" or port_b.lower() == "console" or port_a.startswith("RS232") or port_b.startswith("RS232"):
        return CABLE_CODES["rollover"]
    if (kind_a in SWITCHING_KINDS) == (kind_b in SWITCHING_KINDS):
        return CABLE_CODES["cross"]
    return CABLE_CODES["straight"]


def device(name: str) -> list[Step]:
    """Network.getDevice recibe QString (9)."""
    return [Step("network"), Step("getDevice", (Arg.qstring(name),))]


def device_at(index: int) -> list[Step]:
    """Network.getDeviceAt recibe int (4)."""
    return [Step("network"), Step("getDeviceAt", (Arg.integer(index),))]


def add_device(type_code: int, model: str, x: float, y: float) -> list[Step]:
    """LogicalWorkspace.addDevice(int type, string model, double x, double y) -> QString."""
    return _LW + [Step("addDevice", (
        Arg.integer(type_code),
        Arg.string(model),
        Arg.double(float(x)),
        Arg.double(float(y)),
    ))]


def remove_device(name: str) -> list[Step]:
    """LogicalWorkspace.removeDevice(QString name) -> bool."""
    return _LW + [Step("removeDevice", (Arg.qstring(name),))]


def rename_device(old: str, new: str) -> list[Step]:
    """Device.setName(QString name)."""
    return device(old) + [Step("setName", (Arg.qstring(new),))]


def skip_boot(name: str) -> list[Step]:
    return device(name) + [Step("skipBoot")]


def is_booting(name: str) -> list[Step]:
    return device(name) + [Step("isBooting")]


def console_prompt(name: str) -> list[Step]:
    return device(name) + [Step("getCommandLine"), Step("getPrompt")]


def console_enter_raw(name: str, text: str) -> list[Step]:
    """TerminalLine.enterCommand(string) -> void (para contestar al diálogo inicial)."""
    return device(name) + [Step("getCommandLine"), Step("enterCommand", (Arg.string(text),))]


def connect_ports(dev_a: str, port_a: str, dev_b: str, port_b: str, cable_code: int) -> list[Step]:
    """LogicalWorkspace.createLink(QString dev1, string port1, QString dev2, string port2, int ConnectType) -> bool."""
    return _LW + [Step("createLink", (
        Arg.qstring(dev_a),
        Arg.string(port_a),
        Arg.qstring(dev_b),
        Arg.string(port_b),
        Arg.integer(cable_code),
    ))]


def delete_link(dev: str, port: str) -> list[Step]:
    """LogicalWorkspace.deleteLink(QString dev, string port) -> bool."""
    return _LW + [Step("deleteLink", (Arg.qstring(dev), Arg.string(port)))]


def device_enter_command(dev: str, command: str, mode: str = "enable") -> list[Step]:
    """Device.enterCommand(string command, string mode) -> Pair(int status, string output).
    ¡Método directo y síncrono en Device! `mode` puede ser 'user', 'enable', 'global' o '' (actual).
    """
    return device(dev) + [Step("enterCommand", (Arg.string(command), Arg.string(mode)))]


def device_count() -> list[Step]:
    return [Step("network"), Step("getDeviceCount")]


def device_attr(index: int, attr: str) -> list[Step]:
    return device_at(index) + [Step(attr)]


def device_attr_by_name(name: str, attr: str) -> list[Step]:
    return device(name) + [Step(attr)]


def port_count(dev: str) -> list[Step]:
    return device(dev) + [Step("getPortCount")]


def port_attr_at(dev: str, index: int, attr: str) -> list[Step]:
    return device(dev) + [Step("getPortAt", (Arg.integer(index),)), Step(attr)]


def port_step(dev: str, port_name: str) -> list[Step]:
    """Device.getPort(string portName)."""
    return device(dev) + [Step("getPort", (Arg.string(port_name),))]


def host_set_dhcp(dev: str, port_name: str, enabled: bool) -> list[Step]:
    return port_step(dev, port_name) + [Step("setDhcpClientFlag", (Arg.boolean(enabled),))]


def host_set_device_dhcp(dev: str, enabled: bool) -> list[Step]:
    return device(dev) + [Step("setDhcpFlag", (Arg.boolean(enabled),))]


def host_set_ip_mask(dev: str, port_name: str, ip: str, mask: str) -> list[Step]:
    """HostPort.setIpSubnetMask(IPAddress ip, IPAddress mask)."""
    return port_step(dev, port_name) + [Step("setIpSubnetMask", (Arg.ip(ip), Arg.ip(mask)))]


def host_set_gateway(dev: str, port_name: str, gateway: str) -> list[Step]:
    """Device/HostPort.setDefaultGateway(IPAddress gateway)."""
    return port_step(dev, port_name) + [Step("setDefaultGateway", (Arg.ip(gateway),))]


def host_set_dns(dev: str, port_name: str, dns: str) -> list[Step]:
    """HostPort.setDnsServerIp(IPAddress dns)."""
    return port_step(dev, port_name) + [Step("setDnsServerIp", (Arg.ip(dns),))]


def fast_forward() -> list[Step]:
    """Salta el tiempo en modo Realtime para que converjan STP, DHCP y enrutamiento."""
    return [Step("appWindow"), Step("getRealtimeToolbar"), Step("fastForwardTime")]


def link_count() -> list[Step]:
    return [Step("network"), Step("getLinkCount")]


def link_attr(index: int, attr: str) -> list[Step]:
    return [Step("network"), Step("getLinkAt", (Arg.integer(index),)), Step(attr)]


def link_end_device(index: int, port_getter: str) -> list[Step]:
    return [Step("network"), Step("getLinkAt", (Arg.integer(index),)),
            Step(port_getter), Step("getOwnerDevice"), Step("getName")]


def link_end_port(index: int, port_getter: str) -> list[Step]:
    return [Step("network"), Step("getLinkAt", (Arg.integer(index),)),
            Step(port_getter), Step("getName")]

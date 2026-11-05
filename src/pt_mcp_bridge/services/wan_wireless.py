"""Servicio de Enlaces Inalámbricos (Wi-Fi/WLC) y Enlaces WAN (Frame Relay, PPP, Serial Clock) (SRP)."""
from __future__ import annotations

import json

from pt_mcp_bridge import calls
from pt_mcp_bridge.ipc import PTError
from pt_mcp_bridge.ipc.contracts import IPCTransport
from pt_mcp_bridge.ipc.protocol import Arg, Step
from pt_mcp_bridge.services.base import DomainServiceBase
from pt_mcp_bridge.services.ios_cli import IosCliService


class WanWirelessService(DomainServiceBase):
    """Gestiona WLC, Access Points, SSID, Frame Relay, PPP (PAP/CHAP) y reloj DCE serial."""

    def __init__(self, client: IPCTransport, cli_service: IosCliService) -> None:
        super().__init__(client)
        self._cli = cli_service

    def configure_wlc(self, device: str, management_ip: str = "", management_mask: str = "") -> str:
        device = device.strip()
        if management_ip.strip() and management_mask.strip():
            return self._cli.configure_host(device, ip=management_ip.strip(), mask=management_mask.strip(), port="GigabitEthernet1")
        return json.dumps({"device": device, "status": "ok"}, ensure_ascii=False)

    def configure_ap(self, device: str, ssid: str, port: str = "Port 1",
                     channel: int = 6, auth_type: str = "WPA2-PSK", passphrase: str = "") -> str:
        return self.configure_ssid(device, ssid=ssid, auth_type=auth_type, passphrase=passphrase, channel=channel, port=port)

    def configure_ssid(self, device: str, ssid: str, auth_type: str = "WPA2-PSK",
                       passphrase: str = "", channel: int = 6, port: str = "Port 1") -> str:
        device = device.strip()
        pstep = calls.port_step(device, port)
        self._run(f"ssid {device}:{port}={ssid}", pstep + [Step("setSsid", (Arg.string(ssid.strip()),))])
        self._run(f"chan {device}:{port}={channel}", pstep + [Step("setStandardChannel", (Arg.integer(int(channel)),))])
        return json.dumps({
            "device": device,
            "port": port,
            "ssid": ssid,
            "channel": int(channel),
            "auth_type": auth_type,
            "passphrase_set": bool(passphrase),
        }, ensure_ascii=False)

    def configure_frame_relay(self, device: str, interface: str, dlci: int = 102,
                              ip: str = "", mask: str = "", encapsulation: str = "ietf") -> str:
        cmds = [
            f"interface {interface.strip()}",
            f"encapsulation frame-relay {encapsulation.strip()}".strip(),
        ]
        if ip.strip() and mask.strip():
            cmds.append(f"ip address {ip.strip()} {mask.strip()}")
        if int(dlci) > 0:
            cmds.append(f"frame-relay interface-dlci {int(dlci)}")
        cmds.append("no shutdown")
        return self._cli.configure_ios(device, cmds, save=True)

    def configure_ppp(self, device: str, interface: str, auth: str = "chap",
                      username: str = "", password: str = "",
                      ip: str = "", mask: str = "") -> str:
        cmds: list[str] = []
        if username.strip() and password.strip():
            cmds.append(f"username {username.strip()} password {password.strip()}")
        cmds.extend([
            f"interface {interface.strip()}",
            "encapsulation ppp",
        ])
        if ip.strip() and mask.strip():
            cmds.append(f"ip address {ip.strip()} {mask.strip()}")
        if auth.strip():
            cmds.append(f"ppp authentication {auth.strip()}")
        cmds.append("no shutdown")
        return self._cli.configure_ios(device, cmds, save=True)

    def configure_serial_clock(self, device: str, interface: str, clock_rate: int = 64000) -> str:
        device, interface = device.strip(), interface.strip()
        try:
            self._run(f"setClockRate {device}:{interface}={clock_rate}", calls.set_port_clock_rate(device, interface, int(clock_rate)))
        except PTError:
            pass
        return self._cli.configure_ios(device, [f"interface {interface}", f"clock rate {int(clock_rate)}", "no shutdown"], save=True)

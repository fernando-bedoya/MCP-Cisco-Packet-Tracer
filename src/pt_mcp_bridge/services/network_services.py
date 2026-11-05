"""Servicio de Servicios de Red: DHCP, DNS, HTTP/HTTPS, FTP, NAT/PAT, NTP, Syslog, SNMP y Email (SRP)."""
from __future__ import annotations

import json

from pt_mcp_bridge import calls
from pt_mcp_bridge.ipc import PTError
from pt_mcp_bridge.ipc.contracts import IPCTransport
from pt_mcp_bridge.ipc.protocol import Arg, Step
from pt_mcp_bridge.services.base import DomainServiceBase
from pt_mcp_bridge.services.ios_cli import IosCliService


class NetworkServicesManager(DomainServiceBase):
    """Gestiona servicios de aplicación e infraestructura en Routers/Switches L3 y Server-PT."""

    def __init__(self, client: IPCTransport, cli_service: IosCliService) -> None:
        super().__init__(client)
        self._cli = cli_service

    def configure_dhcp_server(self, device: str, pool_name: str, network: str, mask: str,
                              default_router: str, dns_server: str = "",
                              excluded_start: str = "", excluded_end: str = "") -> str:
        cmds: list[str] = []
        if excluded_start.strip():
            ex = f"ip dhcp excluded-address {excluded_start.strip()}"
            if excluded_end.strip():
                ex += f" {excluded_end.strip()}"
            cmds.append(ex)
        cmds.extend([
            f"ip dhcp pool {pool_name.strip()}",
            f"network {network.strip()} {mask.strip()}",
            f"default-router {default_router.strip()}",
        ])
        if dns_server.strip():
            cmds.append(f"dns-server {dns_server.strip()}")
        cmds.append("exit")
        return self._cli.configure_ios(device, cmds, save=True)

    def configure_dhcp_relay(self, device: str, interface: str, helper_ip: str) -> str:
        return self._cli.configure_ios(
            device,
            [f"interface {interface.strip()}", f"ip helper-address {helper_ip.strip()}"],
            save=True,
        )

    def configure_dns_server(self, device: str, records: list[dict[str, str]], enabled: bool = True) -> str:
        device = device.strip()
        proc = calls.device_process(device, "DnsServerProcess")
        try:
            self._run(f"dns enable {device}", proc + [Step("setEnable", (Arg.boolean(enabled),))])
            added = []
            for rec in records:
                domain, ip = rec["domain"].strip(), rec["ip"].strip()
                ok = self._run(
                    f"dns add {domain}->{ip}",
                    proc + [Step("addIpAddress", (Arg.string(domain), Arg.ip(ip)))],
                )
                added.append({"domain": domain, "ip": ip, "added": bool(ok)})
            return json.dumps({"device": device, "enabled": enabled, "records": added}, ensure_ascii=False)
        except PTError:
            cmds = ["ip dns server"] if enabled else ["no ip dns server"]
            for rec in records:
                cmds.append(f"ip host {rec['domain'].strip()} {rec['ip'].strip()}")
            return self._cli.configure_ios(device, cmds, save=True)

    def configure_http_server(self, device: str, enabled: bool = True,
                              https: bool = False, index_html: str = "") -> str:
        device = device.strip()
        http_proc = calls.device_process(device, "HttpServerProcess")
        self._run(f"http enable {device}", http_proc + [Step("setEnable", (Arg.boolean(enabled),))])
        if https:
            https_proc = calls.device_process(device, "HttpsServerProcess")
            try:
                self._run(f"https enable {device}", https_proc + [Step("setHttpsEnable", (Arg.boolean(True),))])
            except PTError:
                pass
        if index_html:
            self._run(
                f"http index.html {device}",
                http_proc + [Step("setPageContents", (Arg.string("index.html"), Arg.string(index_html)))],
            )
        return json.dumps({"device": device, "http_enabled": enabled, "https": https}, ensure_ascii=False)

    def configure_ftp_server(self, device: str, enabled: bool = True,
                             username: str = "", password: str = "",
                             permissions: str = "RWADN") -> str:
        device = device.strip()
        ftp_proc = calls.device_process(device, "FtpServerProcess")
        self._run(f"ftp enable {device}", ftp_proc + [Step("setEnabled", (Arg.boolean(enabled),))])
        if username.strip() and password.strip():
            mgr = ftp_proc + [Step("getFtpUserAccountManager")]
            self._run(
                f"ftp addUser {username}",
                mgr + [Step("addFtpUser", (
                    Arg.string(username.strip()),
                    Arg.string(password.strip()),
                    Arg.string(permissions.strip()),
                ))],
            )
        return json.dumps({"device": device, "ftp_enabled": enabled, "user": username or None}, ensure_ascii=False)

    def configure_nat(self, device: str, mode: str = "pat",
                      inside_interfaces: list[str] | None = None,
                      outside_interface: str = "",
                      inside_network: str = "", inside_wildcard: str = "0.0.0.255",
                      static_local: str = "", static_global: str = "",
                      pool_name: str = "NAT_POOL", pool_start: str = "",
                      pool_end: str = "", netmask: str = "255.255.255.0") -> str:
        cmds: list[str] = []
        for intf in inside_interfaces or []:
            cmds.extend([f"interface {intf.strip()}", "ip nat inside", "exit"])
        if outside_interface.strip():
            cmds.extend([f"interface {outside_interface.strip()}", "ip nat outside", "exit"])

        m = mode.lower().strip()
        if m == "static":
            cmds.append(f"ip nat inside source static {static_local.strip()} {static_global.strip()}")
        elif m == "dynamic":
            cmds.extend([
                f"access-list 1 permit {inside_network.strip()} {inside_wildcard.strip()}",
                f"ip nat pool {pool_name.strip()} {pool_start.strip()} {pool_end.strip()} netmask {netmask.strip()}",
                f"ip nat inside source list 1 pool {pool_name.strip()}",
            ])
        else:
            cmds.extend([
                f"access-list 1 permit {inside_network.strip()} {inside_wildcard.strip()}",
                f"ip nat inside source list 1 interface {outside_interface.strip()} overload",
            ])
        return self._cli.configure_ios(device, cmds, save=True)

    def configure_ntp(self, device: str, server_ip: str = "", master_stratum: int = 0) -> str:
        cmds: list[str] = []
        if server_ip.strip():
            cmds.append(f"ntp server {server_ip.strip()}")
        if int(master_stratum) > 0:
            cmds.append(f"ntp master {int(master_stratum)}")
        if not cmds:
            proc = calls.device_process(device.strip(), "NtpServerProcess")
            self._run(f"ntp enable {device}", proc + [Step("setEnabled", (Arg.boolean(True),))])
            return json.dumps({"device": device, "ntp_server_enabled": True}, ensure_ascii=False)
        return self._cli.configure_ios(device, cmds, save=True)

    def configure_syslog(self, device: str, server_ip: str = "",
                         trap_level: str = "informational", enable_server: bool = False) -> str:
        if enable_server and not server_ip.strip():
            proc = calls.device_process(device.strip(), "SyslogServer")
            self._run(f"syslog enable {device}", proc + [Step("setEnable", (Arg.boolean(True),))])
            return json.dumps({"device": device, "syslog_server_enabled": True}, ensure_ascii=False)
        cmds = [
            "logging on",
            "service timestamps log datetime msec",
            f"logging host {server_ip.strip()}",
            f"logging trap {trap_level.strip()}",
        ]
        return self._cli.configure_ios(device, cmds, save=True)

    def configure_snmp(self, device: str, ro_community: str = "public",
                       rw_community: str = "private", location: str = "",
                       contact: str = "") -> str:
        cmds: list[str] = []
        if ro_community.strip():
            cmds.append(f"snmp-server community {ro_community.strip()} RO")
        if rw_community.strip():
            cmds.append(f"snmp-server community {rw_community.strip()} RW")
        if location.strip():
            cmds.append(f"snmp-server location {location.strip()}")
        if contact.strip():
            cmds.append(f"snmp-server contact {contact.strip()}")
        return self._cli.configure_ios(device, cmds, save=True)

    def configure_email_server(self, device: str, domain: str,
                               users: list[dict[str, str]]) -> str:
        device = device.strip()
        proc = calls.device_process(device, "EmailServer")
        self._run(f"email domain {device}={domain}", proc + [Step("updateAllAccounts", (Arg.string(domain.strip()),))])
        created = []
        for u in users:
            uname, pwd = u["username"].strip(), u["password"].strip()
            ok = self._run(
                f"email addUser {uname}",
                proc + [Step("addUser", (Arg.string(uname), Arg.string(pwd)))],
            )
            created.append({"username": uname, "added": bool(ok)})
        return json.dumps({"device": device, "domain": domain, "users": created}, ensure_ascii=False)

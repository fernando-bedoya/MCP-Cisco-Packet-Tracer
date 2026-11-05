"""Servicio de Seguridad de Red y Túneles VPN/GRE (SRP)."""
from __future__ import annotations

import json

from pt_mcp_bridge.ipc.contracts import IPCTransport
from pt_mcp_bridge.services.base import DomainServiceBase
from pt_mcp_bridge.services.ios_cli import IosCliService


class SecurityService(DomainServiceBase):
    """Gestiona ACLs, acceso SSH, AAA (RADIUS/TACACS+), endurecimiento de consola y túneles IPsec/GRE."""

    def __init__(self, client: IPCTransport, cli_service: IosCliService) -> None:
        super().__init__(client)
        self._cli = cli_service

    def configure_acl(self, device: str, acl_id_or_name: str | int,
                      rules: list[str], extended: bool = False) -> str:
        acl = str(acl_id_or_name).strip()
        if acl.isdigit():
            cmds = [f"access-list {acl} {r.strip()}" for r in rules if r.strip()]
        else:
            kind = "extended" if extended else "standard"
            cmds = [f"ip access-list {kind} {acl}"] + [r.strip() for r in rules if r.strip()] + ["exit"]
        return self._cli.configure_ios(device, cmds, save=True)

    def apply_acl(self, device: str, interface: str, acl_id_or_name: str | int,
                  direction: str = "in") -> str:
        dir_clean = "out" if direction.lower().strip() == "out" else "in"
        cmds = [
            f"interface {interface.strip()}",
            f"ip access-group {str(acl_id_or_name).strip()} {dir_clean}",
        ]
        return self._cli.configure_ios(device, cmds, save=True)

    def configure_ssh(self, device: str, domain_name: str, username: str,
                      password: str, rsa_modulus: int = 1024, ssh_version: int = 2) -> str:
        cmds = [
            f"hostname {device.strip()}",
            f"ip domain-name {domain_name.strip()}",
            f"username {username.strip()} privilege 15 secret {password.strip()}",
            f"ip ssh version {int(ssh_version)}",
            "line vty 0 15",
            "transport input ssh",
            "login local",
            "exit",
        ]
        res = json.loads(self._cli.configure_ios(device, cmds, save=False))
        self._cli.send_cli(device, f"crypto key generate rsa\n{int(rsa_modulus)}\n", mode="global")
        self._cli.send_cli(device, "write memory", mode="enable")
        return json.dumps({
            "device": device,
            "ssh_configured": True,
            "rsa_modulus": int(rsa_modulus),
            "base": res,
        }, ensure_ascii=False)

    def configure_aaa(self, device: str, server_ip: str, server_key: str,
                      protocol: str = "radius", local_fallback: bool = True) -> str:
        proto = "tacacs+" if "tacacs" in protocol.lower() else "radius"
        fallback = " local" if local_fallback else ""
        if proto == "radius":
            srv_cmds = [f"radius-server host {server_ip.strip()} key {server_key.strip()}"]
        else:
            srv_cmds = [f"tacacs-server host {server_ip.strip()} key {server_key.strip()}"]
        cmds = [
            "aaa new-model",
            *srv_cmds,
            f"aaa authentication login default group {proto}{fallback}",
        ]
        return self._cli.configure_ios(device, cmds, save=True)

    def secure_device(self, device: str, enable_secret: str, console_password: str = "",
                      vty_password: str = "", banner_motd: str = "Authorized Access Only",
                      encrypt_passwords: bool = True, exec_timeout_min: int = 5) -> str:
        cmds = [
            f"enable secret {enable_secret.strip()}",
            "no ip domain-lookup",
        ]
        if encrypt_passwords:
            cmds.append("service password-encryption")
        if banner_motd.strip():
            cmds.append(f"banner motd #{banner_motd.strip()}#")
        if console_password.strip():
            cmds.extend([
                "line console 0",
                f"password {console_password.strip()}",
                "login",
                f"exec-timeout {int(exec_timeout_min)} 0",
                "logging synchronous",
                "exit",
            ])
        if vty_password.strip():
            cmds.extend([
                "line vty 0 15",
                f"password {vty_password.strip()}",
                "login",
                f"exec-timeout {int(exec_timeout_min)} 0",
                "exit",
            ])
        return self._cli.configure_ios(device, cmds, save=True)

    def configure_vpn_ipsec(self, device: str, peer_ip: str, pre_shared_key: str,
                            local_network: str, local_wildcard: str,
                            remote_network: str, remote_wildcard: str,
                            outside_interface: str) -> str:
        cmds = [
            "crypto isakmp policy 10",
            "encryption aes",
            "hash sha",
            "authentication pre-share",
            "group 2",
            "exit",
            f"crypto isakmp key {pre_shared_key.strip()} address {peer_ip.strip()}",
            "crypto ipsec transform-set VPN-SET esp-aes esp-sha-hmac",
            f"access-list 110 permit ip {local_network.strip()} {local_wildcard.strip()} {remote_network.strip()} {remote_wildcard.strip()}",
            "crypto map VPN-MAP 10 ipsec-isakmp",
            f"set peer {peer_ip.strip()}",
            "set transform-set VPN-SET",
            "match address 110",
            "exit",
            f"interface {outside_interface.strip()}",
            "crypto map VPN-MAP",
        ]
        return self._cli.configure_ios(device, cmds, save=True)

    def configure_gre(self, device: str, tunnel_number: int, tunnel_ip: str,
                      tunnel_mask: str, source_ip_or_intf: str, destination_ip: str) -> str:
        cmds = [
            f"interface Tunnel{int(tunnel_number)}",
            f"ip address {tunnel_ip.strip()} {tunnel_mask.strip()}",
            f"tunnel source {source_ip_or_intf.strip()}",
            f"tunnel destination {destination_ip.strip()}",
            "no shutdown",
        ]
        return self._cli.configure_ios(device, cmds, save=True)

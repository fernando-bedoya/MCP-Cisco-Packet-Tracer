"""Servidor MCP: expone el catálogo completo de herramientas de Packet Tracer sobre PacketTracerService."""
from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from pt_mcp_bridge import config
from pt_mcp_bridge.ipc import PTError
from pt_mcp_bridge.service import PacketTracerService, ValidationError


def _safe(fn: Callable[[], str]) -> str:
    """Convierte errores esperados en texto claro para el LLM."""
    try:
        return fn()
    except (PTError, ValidationError) as exc:
        return f"ERROR: {exc}"


MCP_INSTRUCTIONS = """
REGLA DE VELOCIDAD OBLIGATORIA PARA EL AGENTE DE IA:
1. Cuando el usuario pida crear o configurar una topología con 3 o más dispositivos (por ejemplo: 30 PCs, varios switches, routers, DHCP y enrutamiento), PROHIBIDO llamar a `cpt_add_device`, `cpt_connect_ports` o `cpt_configure_host` uno por uno. Hacer 50-100 llamadas individuales tarda minutos y pide demasiadas confirmaciones.
2. SIEMPRE ejecuta toda la construcción y configuración en UNA SOLA LLAMADA usando `cpt_generate_lab` o `cpt_batch`:
   - En `cpt_generate_lab(spec)` puedes declarar:
     * `devices`: lista de routers/switches/servidores/cloud (`[{"name": "R1", "kind": "router", "x": 250, "y": 120}, ...]`).
     * `device_groups`: creación masiva instantánea de hosts con auto-cableado y DHCP, ej.:
       `[{"prefix": "PC", "kind": "pc", "count": 30, "dhcp": true, "connect_to": ["SW1", "SW2", "SW3"]}]`
       (reparte y conecta automáticamente los 30 PCs a los puertos libres de SW1, SW2 y SW3 en 1 segundo).
     * `links`: enlaces entre equipos; puedes usar `{"from": "R1", "to": "SW1"}` o `"port": "auto"` para elegir el siguiente puerto libre sin consultar `cpt_list_ports`.
     * `ios_configs`: diccionario `{"R1": ["interface GigabitEthernet0/0", "ip address ...", "no shutdown", ...], "R2": [...]}` con todos los comandos IOS de cada router/switch en un solo lote.
     * `dhcp_pools` y `static_routes`: configuración declarativa de servidores DHCP y rutas.
     * `fast_forward`: `true` (por defecto) para que STP y DHCP converjan al instante.
""".strip()


def build_mcp(service: PacketTracerService, host: str = config.DEFAULT_MCP_HOST,
              port: int = config.DEFAULT_MCP_PORT):
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations

    mcp = FastMCP("el-arriero-mcp", instructions=MCP_INSTRUCTIONS, host=host, port=port)
    safe_annotations = ToolAnnotations(destructiveHint=False, openWorldHint=False)
    orig_tool = mcp.tool

    def _non_destructive_tool(*args: Any, **kwargs: Any):
        kwargs.setdefault("annotations", safe_annotations)
        return orig_tool(*args, **kwargs)

    mcp.tool = _non_destructive_tool  # type: ignore[method-assign]

    # =========================================================================
    # BASE & TOPOLOGÍA (14 herramientas originales + 12 de topología/dispositivos)
    # =========================================================================
    @mcp.tool()
    def cpt_add_device(name: str, device_type: str = "router", model: str = "",
                       x: int = 200, y: int = 200) -> str:
        """Agrega un único nodo al espacio de trabajo de Packet Tracer.
        IMPORTANTE: Si necesitas crear 3 o más equipos, NO llames a esta herramienta en bucle; usa `cpt_generate_lab` (con `devices` o `device_groups`) o `cpt_batch` en una sola llamada.
        - device_type: router | switch | multi_layer_switch | switch3650 | pc | laptop | server | hub | cloud | ap | wireless_router | printer | asa
        - model: modelo exacto de PT (ej. '2911', '1941', '2960-24TT', '3560-24PS', 'PC-PT', 'Server-PT'); si se deja vacío usa el predeterminado del tipo."""
        return _safe(lambda: service.add_device(name, device_type, model, x, y))

    @mcp.tool()
    def cpt_remove_device(name: str) -> str:
        """Elimina un dispositivo del espacio de trabajo por su nombre."""
        return _safe(lambda: service.remove_device(name))

    @mcp.tool()
    def cpt_move_device(name: str, x: int, y: int) -> str:
        """Reposiciona un dispositivo en las coordenadas (x, y) del lienzo lógico."""
        return _safe(lambda: service.move_device(name, x, y))

    @mcp.tool()
    def cpt_rename_device(old_name: str, new_name: str, sync_hostname: bool = True) -> str:
        """Cambia el nombre visible de un dispositivo y opcionalmente su hostname IOS."""
        return _safe(lambda: service.rename_device(old_name, new_name, sync_hostname))

    @mcp.tool()
    def cpt_clone_device(source_name: str, new_name: str, x: int = 300, y: int = 300) -> str:
        """Duplica un dispositivo junto con su modelo y configuración actual en las coordenadas (x, y)."""
        return _safe(lambda: service.clone_device(source_name, new_name, x, y))

    @mcp.tool()
    def cpt_connect_ports(device_a: str, port_a: str = "auto", device_b: str = "", port_b: str = "auto",
                          cable: str = "auto") -> str:
        """Conecta dos interfaces físicas mediante un cable (`port_a` y `port_b` pueden ser `'auto'` para elegir el siguiente puerto libre automáticamente).
        IMPORTANTE: Para conectar múltiples enlaces a la vez, usa `cpt_generate_lab` o `cpt_batch` en una sola llamada.
        - cable: auto | straight | cross | crossover | serial | console | rollover | fiber | phone | coaxial | usb"""
        return _safe(lambda: service.connect_ports(device_a, port_a, device_b, port_b, cable))

    @mcp.tool()
    def cpt_disconnect_ports(device: str, port: str) -> str:
        """Elimina el enlace conectado al puerto indicado de un dispositivo."""
        return _safe(lambda: service.disconnect_ports(device, port))

    @mcp.tool()
    def cpt_set_port_state(device: str, port: str, enabled: bool = True) -> str:
        """Activa (`no shutdown`) o desactiva (`shutdown`) administrativamente un puerto."""
        return _safe(lambda: service.set_port_state(device, port, enabled))

    @mcp.tool()
    def cpt_add_module(device: str, slot: str, module_name: str,
                       module_type: str = "PT_ROUTER_MODULE") -> str:
        """Instala un módulo de hardware (ej. 'HWIC-2T', 'NM-4E') apagando y encendiendo el equipo automáticamente."""
        return _safe(lambda: service.add_module(device, slot, module_name, module_type))

    @mcp.tool()
    def cpt_power_device(device: str, power_on: bool = True) -> str:
        """Enciende o apaga físicamente un dispositivo."""
        return _safe(lambda: service.power_device(device, power_on))

    @mcp.tool()
    def cpt_add_note(text: str, x: int = 100, y: int = 100, z: float = 1.0) -> str:
        """Agrega una etiqueta o nota de texto en las coordenadas (x, y) del lienzo."""
        return _safe(lambda: service.add_note(text, x, y, z))

    @mcp.tool()
    def cpt_group_devices(devices: list[str], cluster_name: str = "") -> str:
        """Agrupa visualmente un conjunto de dispositivos en un clúster dentro del lienzo."""
        return _safe(lambda: service.group_devices(devices, cluster_name))

    @mcp.tool()
    def cpt_layout_auto(columns: int = 4, start_x: int = 160, start_y: int = 140,
                        spacing_x: int = 210, spacing_y: int = 160) -> str:
        """Organiza automáticamente todos los dispositivos del lienzo por jerarquía (WAN -> Routers -> Switches -> Hosts)."""
        return _safe(lambda: service.layout_auto(columns, start_x, start_y, spacing_x, spacing_y))

    @mcp.tool()
    def cpt_export_topology_json(include_configs: bool = True) -> str:
        """Exporta toda la topología (nodos, coordenadas, enlaces, IPs y running-configs) en formato JSON."""
        return _safe(lambda: service.export_topology_json(include_configs))

    @mcp.tool()
    def cpt_import_topology_json(topology_json: dict[str, Any] | str, clear_existing: bool = False) -> str:
        """Reconstruye una topología completa (dispositivos, enlaces e IPs) desde un objeto o cadena JSON."""
        return _safe(lambda: service.import_topology_json(topology_json, clear_existing))

    @mcp.tool()
    def cpt_send_cli_command(device: str, command: str, mode: str = "") -> str:
        """Ejecuta uno o varios comandos (separados por salto de línea) en la consola Cisco IOS de un router o switch."""
        return _safe(lambda: service.send_cli(device, command, mode))

    @mcp.tool()
    def cpt_configure_ios(device: str, commands: list[str], save: bool = True) -> str:
        """Aplica una lista de comandos de configuración IOS entrando a `configure terminal`, con auto-recuperación de submodos y guardado `write memory`."""
        return _safe(lambda: service.configure_ios(device, commands, save))

    @mcp.tool()
    def cpt_configure_host(device: str, ip: str = "", mask: str = "", gateway: str = "",
                           dns: str = "", dhcp: bool = False, port: str = "FastEthernet0") -> str:
        """Configura IPv4 estática (ip, mask, gateway, dns) o activa DHCP (`dhcp=True`) en un PC, Laptop o Server."""
        return _safe(lambda: service.configure_host(device, ip, mask, gateway, dns, dhcp, port))

    @mcp.tool()
    def cpt_list_ports(device: str) -> str:
        """Lista todas las interfaces de un dispositivo con su estado (up/protocol_up), IP y máscara."""
        return _safe(lambda: service.list_ports(device))

    @mcp.tool()
    def cpt_fast_forward() -> str:
        """Pulsa el botón 'Fast Forward Time' en Packet Tracer para que STP, DHCP y rutas converjan de inmediato."""
        return _safe(service.fast_forward)

    @mcp.tool()
    def cpt_get_topology() -> str:
        """Lee todos los dispositivos y enlaces (cables) actualmente presentes en el espacio de trabajo."""
        return _safe(service.topology)

    @mcp.tool()
    def cpt_raw_ipc(root: str, steps: list[dict[str, Any]]) -> str:
        """Invoca cualquier método de la API IPC de Packet Tracer validando los tipos contra el índice oficial (`ipc_index.json`)."""
        return _safe(lambda: service.raw_ipc_call(root, steps))

    @mcp.tool()
    def cpt_save_file() -> str:
        """Guarda los cambios directamente en el archivo .pkt o .pka abierto en Packet Tracer."""
        return _safe(service.save_file)

    @mcp.tool()
    def cpt_get_instructions() -> str:
        """Lee el texto e instrucciones completas de la ventana de actividad (.pka) de Packet Tracer."""
        return _safe(service.get_instructions)

    @mcp.tool()
    def cpt_ping(device: str, target_ip: str) -> str:
        """Ejecuta un ping desde un router, switch o host hacia una dirección IP de destino y devuelve el resultado."""
        return _safe(lambda: service.ping(device, target_ip))

    @mcp.tool()
    def cpt_audit_network() -> str:
        """Audita de forma completa e instantánea toda la red (todos los routers, interfaces, rutas y hosts con sus IPs)."""
        return _safe(service.audit_network)

    # =========================================================================
    # CAPA 2 - SWITCHING (13-20)
    # =========================================================================
    @mcp.tool()
    def cpt_create_vlan(device: str, vlan_id: int, name: str = "") -> str:
        """Crea una VLAN en un switch con su ID numérico y nombre opcional."""
        return _safe(lambda: service.create_vlan(device, vlan_id, name))

    @mcp.tool()
    def cpt_assign_vlan_port(device: str, port: str, vlan_id: int, voice_vlan_id: int = 0) -> str:
        """Configura un puerto de switch en modo acceso y lo asigna a `vlan_id` (y `voice_vlan_id` opcional)."""
        return _safe(lambda: service.assign_vlan_port(device, port, vlan_id, voice_vlan_id))

    @mcp.tool()
    def cpt_configure_trunk(device: str, port: str, native_vlan: int = 0,
                            allowed_vlans: str = "", encapsulation_dot1q: bool = False) -> str:
        """Configura un puerto troncal 802.1Q con VLAN nativa y lista de VLANs permitidas."""
        return _safe(lambda: service.configure_trunk(device, port, native_vlan, allowed_vlans, encapsulation_dot1q))

    @mcp.tool()
    def cpt_configure_etherchannel(device: str, ports: list[str], channel_group: int = 1,
                                   mode: str = "active", trunk: bool = True) -> str:
        """Agrupa múltiples puertos físicos en un Port-channel (LACP: active/passive, PAgP: desirable/auto, o 'on')."""
        return _safe(lambda: service.configure_etherchannel(device, ports, channel_group, mode, trunk))

    @mcp.tool()
    def cpt_configure_stp(device: str, mode: str = "rapid-pvst", vlan_range: str = "1",
                          priority: int = 32768, portfast_ports: list[str] | None = None,
                          bpduguard: bool = False) -> str:
        """Configura Spanning Tree Protocol (modo, prioridad por VLAN, PortFast y BPDU Guard)."""
        return _safe(lambda: service.configure_stp(device, mode, vlan_range, priority, portfast_ports, bpduguard))

    @mcp.tool()
    def cpt_configure_port_security(device: str, port: str, maximum: int = 1,
                                    violation: str = "restrict", mac_sticky: bool = True,
                                    static_mac: str = "") -> str:
        """Habilita Port Security en una interfaz de switch (máximo de MACs, modo de violación y sticky MAC)."""
        return _safe(lambda: service.configure_port_security(device, port, maximum, violation, mac_sticky, static_mac))

    @mcp.tool()
    def cpt_show_mac_table(device: str) -> str:
        """Consulta y parsea a JSON la tabla de direcciones MAC (`show mac-address-table`) de un switch."""
        return _safe(lambda: service.show_mac_table(device))

    @mcp.tool()
    def cpt_configure_vtp(device: str, mode: str = "server", domain: str = "",
                          password: str = "", version: int = 2) -> str:
        """Configura VLAN Trunking Protocol (VTP server/client/transparent, dominio y contraseña)."""
        return _safe(lambda: service.configure_vtp(device, mode, domain, password, version))

    # =========================================================================
    # CAPA 3 - ENRUTAMIENTO (21-30)
    # =========================================================================
    @mcp.tool()
    def cpt_configure_static_route(device: str, network: str, mask: str,
                                   next_hop_or_interface: str, admin_distance: int = 0) -> str:
        """Agrega una ruta estática IPv4 (`ip route <network> <mask> <next_hop> [distance]`)."""
        return _safe(lambda: service.configure_static_route(device, network, mask, next_hop_or_interface, admin_distance))

    @mcp.tool()
    def cpt_configure_ospf(device: str, process_id: int = 1,
                           networks: list[dict[str, Any]] | None = None,
                           router_id: str = "", passive_interfaces: list[str] | None = None,
                           default_originate: bool = False) -> str:
        """Configura OSPFv2. `networks` es una lista de `{'network': '...', 'wildcard': '...', 'area': 0}`."""
        return _safe(lambda: service.configure_ospf(device, process_id, networks, router_id, passive_interfaces, default_originate))

    @mcp.tool()
    def cpt_configure_eigrp(device: str, as_number: int = 100,
                            networks: list[str] | None = None,
                            no_auto_summary: bool = True,
                            passive_interfaces: list[str] | None = None) -> str:
        """Configura el protocolo de enrutamiento EIGRP con su número de sistema autónomo."""
        return _safe(lambda: service.configure_eigrp(device, as_number, networks, no_auto_summary, passive_interfaces))

    @mcp.tool()
    def cpt_configure_rip(device: str, networks: list[str] | None = None,
                          version: int = 2, no_auto_summary: bool = True,
                          default_originate: bool = False) -> str:
        """Configura el protocolo de enrutamiento RIPv2."""
        return _safe(lambda: service.configure_rip(device, networks, version, no_auto_summary, default_originate))

    @mcp.tool()
    def cpt_configure_bgp(device: str, as_number: int,
                          neighbors: list[dict[str, Any]],
                          networks: list[dict[str, str]] | None = None,
                          router_id: str = "") -> str:
        """Configura BGP (`neighbors`: `[{'ip': '...', 'remote_as': 65002}]`, `networks`: `[{'network': '...', 'mask': '...'}]`)."""
        return _safe(lambda: service.configure_bgp(device, as_number, neighbors, networks, router_id))

    @mcp.tool()
    def cpt_configure_intervlan(device: str, parent_interface: str,
                                subinterfaces: list[dict[str, Any]]) -> str:
        """Configura Router-on-a-Stick (`subinterfaces`: `[{'vlan': 10, 'ip': '192.168.10.1', 'mask': '255.255.255.0', 'native': False}]`)."""
        return _safe(lambda: service.configure_intervlan(device, parent_interface, subinterfaces))

    @mcp.tool()
    def cpt_configure_svi(device: str, vlan_id: int, ip: str, mask: str,
                          enable_routing: bool = True, helper_address: str = "") -> str:
        """Configura una interfaz virtual SVI (`interface Vlan<id>`) y `ip routing` en un switch multicapa."""
        return _safe(lambda: service.configure_svi(device, vlan_id, ip, mask, enable_routing, helper_address))

    @mcp.tool()
    def cpt_configure_ipv6(device: str, interface: str, ipv6_address: str,
                           enable_unicast_routing: bool = True, link_local: str = "",
                           static_routes: list[dict[str, str]] | None = None) -> str:
        """Configura direccionamiento IPv6, `ipv6 unicast-routing` y rutas estáticas IPv6 opcionales."""
        return _safe(lambda: service.configure_ipv6(device, interface, ipv6_address, enable_unicast_routing, link_local, static_routes))

    @mcp.tool()
    def cpt_configure_hsrp(device: str, interface: str, group: int,
                           virtual_ip: str, priority: int = 100, preempt: bool = True) -> str:
        """Configura redundancia de primer salto HSRP (`standby`) en una interfaz."""
        return _safe(lambda: service.configure_hsrp(device, interface, group, virtual_ip, priority, preempt))

    @mcp.tool()
    def cpt_configure_vrrp(device: str, interface: str, group: int,
                           virtual_ip: str, priority: int = 100, preempt: bool = True) -> str:
        """Configura redundancia de primer salto VRRP en una interfaz."""
        return _safe(lambda: service.configure_vrrp(device, interface, group, virtual_ip, priority, preempt))

    @mcp.tool()
    def cpt_show_routing_table(device: str) -> str:
        """Consulta `show ip route` y devuelve las rutas parseadas a JSON estructurado."""
        return _safe(lambda: service.show_routing_table(device))

    # =========================================================================
    # SERVICIOS (31-38)
    # =========================================================================
    @mcp.tool()
    def cpt_configure_dhcp_server(device: str, pool_name: str, network: str, mask: str,
                                  default_router: str, dns_server: str = "",
                                  excluded_start: str = "", excluded_end: str = "") -> str:
        """Configura un pool de servidor DHCPv4 y rangos excluidos en un router o switch L3."""
        return _safe(lambda: service.configure_dhcp_server(device, pool_name, network, mask, default_router, dns_server, excluded_start, excluded_end))

    @mcp.tool()
    def cpt_configure_dhcp_relay(device: str, interface: str, helper_ip: str) -> str:
        """Configura el agente de retransmisión DHCP (`ip helper-address`) en una interfaz."""
        return _safe(lambda: service.configure_dhcp_relay(device, interface, helper_ip))

    @mcp.tool()
    def cpt_configure_dns_server(device: str, records: list[dict[str, str]], enabled: bool = True) -> str:
        """Configura registros DNS (`[{'domain': '...', 'ip': '...'}]`) en un Server-PT o router IOS."""
        return _safe(lambda: service.configure_dns_server(device, records, enabled))

    @mcp.tool()
    def cpt_configure_http_server(device: str, enabled: bool = True,
                                  https: bool = False, index_html: str = "") -> str:
        """Activa el servidor HTTP/HTTPS de un Server-PT y opcionalmente actualiza `index.html`."""
        return _safe(lambda: service.configure_http_server(device, enabled, https, index_html))

    @mcp.tool()
    def cpt_configure_ftp_server(device: str, enabled: bool = True,
                                 username: str = "", password: str = "",
                                 permissions: str = "RWADN") -> str:
        """Activa el servidor FTP de un Server-PT y agrega una cuenta de usuario."""
        return _safe(lambda: service.configure_ftp_server(device, enabled, username, password, permissions))

    @mcp.tool()
    def cpt_configure_nat(device: str, mode: str = "pat",
                          inside_interfaces: list[str] | None = None,
                          outside_interface: str = "",
                          inside_network: str = "", inside_wildcard: str = "0.0.0.255",
                          static_local: str = "", static_global: str = "",
                          pool_name: str = "NAT_POOL", pool_start: str = "",
                          pool_end: str = "", netmask: str = "255.255.255.0") -> str:
        """Configura NAT estático (`mode='static'`), dinámico (`mode='dynamic'`) o PAT con sobrecarga (`mode='pat'`)."""
        return _safe(lambda: service.configure_nat(
            device, mode, inside_interfaces, outside_interface, inside_network, inside_wildcard,
            static_local, static_global, pool_name, pool_start, pool_end, netmask,
        ))

    @mcp.tool()
    def cpt_configure_ntp(device: str, server_ip: str = "", master_stratum: int = 0) -> str:
        """Configura sincronización horaria NTP (cliente `ntp server`, maestro `ntp master` o proceso de Server-PT)."""
        return _safe(lambda: service.configure_ntp(device, server_ip, master_stratum))

    @mcp.tool()
    def cpt_configure_syslog(device: str, server_ip: str = "",
                             trap_level: str = "informational", enable_server: bool = False) -> str:
        """Configura envío de registros Syslog a un servidor remoto o activa el receptor Syslog en un Server-PT."""
        return _safe(lambda: service.configure_syslog(device, server_ip, trap_level, enable_server))

    @mcp.tool()
    def cpt_configure_snmp(device: str, ro_community: str = "public",
                           rw_community: str = "private", location: str = "",
                           contact: str = "") -> str:
        """Configura comunidades SNMP de lectura (RO) y escritura (RW) en un dispositivo IOS."""
        return _safe(lambda: service.configure_snmp(device, ro_community, rw_community, location, contact))

    @mcp.tool()
    def cpt_configure_email_server(device: str, domain: str,
                                   users: list[dict[str, str]]) -> str:
        """Configura el dominio SMTP/POP3 y las cuentas de correo (`[{'username': '...', 'password': '...'}]`) en un Server-PT."""
        return _safe(lambda: service.configure_email_server(device, domain, users))

    # =========================================================================
    # SEGURIDAD (39-44)
    # =========================================================================
    @mcp.tool()
    def cpt_configure_acl(device: str, acl_id_or_name: str,
                          rules: list[str], extended: bool = False) -> str:
        """Crea una lista de control de acceso (ACL numerada o nombrada, estándar o extendida)."""
        return _safe(lambda: service.configure_acl(device, acl_id_or_name, rules, extended))

    @mcp.tool()
    def cpt_apply_acl(device: str, interface: str, acl_id_or_name: str,
                      direction: str = "in") -> str:
        """Aplica una ACL a una interfaz en sentido entrante (`in`) o saliente (`out`)."""
        return _safe(lambda: service.apply_acl(device, interface, acl_id_or_name, direction))

    @mcp.tool()
    def cpt_configure_ssh(device: str, domain_name: str, username: str,
                          password: str, rsa_modulus: int = 1024, ssh_version: int = 2) -> str:
        """Configura acceso seguro por SSH (dominio, usuario local, par de llaves RSA y líneas VTY)."""
        return _safe(lambda: service.configure_ssh(device, domain_name, username, password, rsa_modulus, ssh_version))

    @mcp.tool()
    def cpt_configure_aaa(device: str, server_ip: str, server_key: str,
                          protocol: str = "radius", local_fallback: bool = True) -> str:
        """Configura autenticación centralizada AAA con servidor RADIUS o TACACS+."""
        return _safe(lambda: service.configure_aaa(device, server_ip, server_key, protocol, local_fallback))

    @mcp.tool()
    def cpt_secure_device(device: str, enable_secret: str, console_password: str = "",
                          vty_password: str = "", banner_motd: str = "Authorized Access Only",
                          encrypt_passwords: bool = True, exec_timeout_min: int = 5) -> str:
        """Aplica endurecimiento básico (enable secret, service password-encryption, banner MOTD y líneas console/VTY)."""
        return _safe(lambda: service.secure_device(device, enable_secret, console_password, vty_password, banner_motd, encrypt_passwords, exec_timeout_min))

    @mcp.tool()
    def cpt_configure_vpn_ipsec(device: str, peer_ip: str, pre_shared_key: str,
                                local_network: str, local_wildcard: str,
                                remote_network: str, remote_wildcard: str,
                                outside_interface: str) -> str:
        """Configura un túnel VPN Site-to-Site IPsec (ISAKMP Fase 1, Transform-Set Fase 2, ACL de tráfico interesante y Crypto Map)."""
        return _safe(lambda: service.configure_vpn_ipsec(
            device, peer_ip, pre_shared_key, local_network, local_wildcard,
            remote_network, remote_wildcard, outside_interface,
        ))

    @mcp.tool()
    def cpt_configure_gre(device: str, tunnel_number: int, tunnel_ip: str,
                          tunnel_mask: str, source_ip_or_intf: str, destination_ip: str) -> str:
        """Configura una interfaz de túnel GRE punto a punto (`interface Tunnel<n>`)."""
        return _safe(lambda: service.configure_gre(device, tunnel_number, tunnel_ip, tunnel_mask, source_ip_or_intf, destination_ip))

    # =========================================================================
    # WIRELESS Y WAN (45-48)
    # =========================================================================
    @mcp.tool()
    def cpt_configure_wlc(device: str, management_ip: str = "", management_mask: str = "") -> str:
        """Configura una controladora inalámbrica (WLC) en Packet Tracer."""
        return _safe(lambda: service.configure_wlc(device, management_ip, management_mask))

    @mcp.tool()
    def cpt_configure_ap(device: str, ssid: str, port: str = "Port 1",
                         channel: int = 6, auth_type: str = "WPA2-PSK", passphrase: str = "") -> str:
        """Configura un punto de acceso inalámbrico (Access Point)."""
        return _safe(lambda: service.configure_ap(device, ssid, port, channel, auth_type, passphrase))

    @mcp.tool()
    def cpt_configure_ssid(device: str, ssid: str, auth_type: str = "WPA2-PSK",
                           passphrase: str = "", channel: int = 6, port: str = "Port 1") -> str:
        """Configura SSID y canal de radio en una interfaz inalámbrica de AP o router inalámbrico."""
        return _safe(lambda: service.configure_ssid(device, ssid, auth_type, passphrase, channel, port))

    @mcp.tool()
    def cpt_configure_frame_relay(device: str, interface: str, dlci: int = 102,
                                  ip: str = "", mask: str = "", encapsulation: str = "ietf") -> str:
        """Configura encapsulación WAN Frame Relay y su DLCI en una interfaz serial."""
        return _safe(lambda: service.configure_frame_relay(device, interface, dlci, ip, mask, encapsulation))

    @mcp.tool()
    def cpt_configure_ppp(device: str, interface: str, auth: str = "chap",
                          username: str = "", password: str = "",
                          ip: str = "", mask: str = "") -> str:
        """Configura encapsulación WAN PPP con autenticación CHAP o PAP en una interfaz serial."""
        return _safe(lambda: service.configure_ppp(device, interface, auth, username, password, ip, mask))

    @mcp.tool()
    def cpt_configure_serial_clock(device: str, interface: str, clock_rate: int = 64000) -> str:
        """Configura la velocidad de reloj (`clock rate`) en el extremo DCE de un enlace serial."""
        return _safe(lambda: service.configure_serial_clock(device, interface, clock_rate))

    # =========================================================================
    # VERIFICACIÓN Y DIAGNÓSTICO (49-57)
    # =========================================================================
    @mcp.tool()
    def cpt_traceroute(device: str, target_ip: str) -> str:
        """Ejecuta un `traceroute` hacia `target_ip` y devuelve la lista de saltos parseada a JSON."""
        return _safe(lambda: service.traceroute(device, target_ip))

    @mcp.tool()
    def cpt_test_connectivity_matrix(devices: list[str] | None = None,
                                     targets: list[str] | None = None) -> str:
        """Ejecuta una matriz de pruebas de ping entre múltiples dispositivos e IPs destino."""
        return _safe(lambda: service.test_connectivity_matrix(devices, targets))

    @mcp.tool()
    def cpt_verify_vlans(device: str) -> str:
        """Verifica y devuelve en JSON todas las VLANs activas y sus puertos asociados en un switch."""
        return _safe(lambda: service.verify_vlans(device))

    @mcp.tool()
    def cpt_verify_trunks(device: str) -> str:
        """Verifica y devuelve en JSON los enlaces troncales (`show interfaces trunk`) de un switch."""
        return _safe(lambda: service.verify_trunks(device))

    @mcp.tool()
    def cpt_diff_config(device: str, baseline: str = "") -> str:
        """Compara `running-config` contra `startup-config` (o contra un texto `baseline`) en formato diff unificado."""
        return _safe(lambda: service.diff_config(device, baseline))

    @mcp.tool()
    def cpt_snapshot_config(name: str = "default") -> str:
        """Guarda una instantánea en memoria de toda la topología y configuraciones bajo el nombre indicado."""
        return _safe(lambda: service.snapshot_config(name))

    @mcp.tool()
    def cpt_restore_config(name: str = "default") -> str:
        """Restaura una instantánea de topología y configuración previamente guardada."""
        return _safe(lambda: service.restore_config(name))

    @mcp.tool()
    def cpt_find_misconfigurations() -> str:
        """Analiza toda la red buscando direcciones IP duplicadas y puertas de enlace fuera de subred."""
        return _safe(service.find_misconfigurations)

    @mcp.tool()
    def cpt_capture_packets(steps: int = 5, reset_first: bool = False) -> str:
        """Avanza `steps` pasos en el modo Simulación y captura los eventos de paquetes en tránsito."""
        return _safe(lambda: service.capture_packets(steps, reset_first))

    @mcp.tool()
    def cpt_send_pdu(source_device: str, dest_device: str) -> str:
        """Dispara una unidad de datos de protocolo (Simple PDU) entre dos equipos en el lienzo."""
        return _safe(lambda: service.send_pdu(source_device, dest_device))

    @mcp.tool()
    def cpt_get_event_list(limit: int = 50) -> str:
        """Obtiene la lista de tramas/eventos registrados en el panel de simulación de Packet Tracer."""
        return _safe(lambda: service.get_event_list(limit))

    # =========================================================================
    # LABORATORIOS Y CALIFICACIÓN ACADÉMICA (58-63)
    # =========================================================================
    @mcp.tool()
    def cpt_check_activity() -> str:
        """Consulta el porcentaje de completitud y el tiempo transcurrido en una actividad `.pka`."""
        return _safe(service.check_activity)

    @mcp.tool()
    def cpt_list_activity_checks() -> str:
        """Obtiene el desglose de ítems evaluados, puntaje actual y árbol de evaluación de una actividad `.pka`."""
        return _safe(service.list_activity_checks)

    @mcp.tool()
    def cpt_generate_lab(spec: dict[str, Any]) -> str:
        """HERRAMIENTA PREFERIDA DE ALTA VELOCIDAD: Construye y configura una red completa en UNA SOLA LLAMADA (tarda segundos en vez de minutos y evita confirmaciones repetidas).
        Campos soportados en `spec`:
        - `devices`: `[{'name': 'R1', 'kind': 'router', 'x': 250, 'y': 120}, {'name': 'SW1', 'kind': 'switch', 'x': 200, 'y': 260}, ...]` (en hosts puedes incluir `'dhcp': True` o `'ip'`, `'mask'`, `'gateway'`, `'dns'`).
        - `device_groups`: creación masiva de PCs/hosts con auto-cableado, ej:
          `[{'prefix': 'PC', 'kind': 'pc', 'count': 30, 'dhcp': True, 'connect_to': ['SW1', 'SW2', 'SW3']}]`
        - `links`: `[{'from': 'R1', 'from_port': 'GigabitEthernet0/0', 'to': 'SW1', 'to_port': 'GigabitEthernet0/1'}, ...]` (puedes usar `'auto'` en los puertos).
        - `ios_configs`: `{'R1': ['interface GigabitEthernet0/0', 'ip address ...', 'no shutdown'], ...}`
        - `dhcp_pools`: `[{'device': 'R1', 'pool_name': 'LAN1', 'network': '192.168.1.0', 'mask': '255.255.255.0', 'default_router': '192.168.1.1', 'dns_server': '8.8.8.8', 'excluded_addresses': ['192.168.1.1']}]`
        - `static_routes`: `[{'device': 'R1', 'prefix': '0.0.0.0', 'mask': '0.0.0.0', 'next_hop': '10.0.0.2'}]`
        - `fast_forward`: `True` (por defecto converge STP y DHCP al finalizar)."""
        return _safe(lambda: service.generate_lab(spec))

    @mcp.tool()
    def cpt_backup_all_configs(output_dir: str = "backups") -> str:
        """Respalda en disco (`output_dir`) la topología JSON y los archivos `.cfg` de todos los routers y switches."""
        return _safe(lambda: service.backup_all_configs(output_dir))

    @mcp.tool()
    def cpt_apply_config_bundle(input_dir: str = "backups") -> str:
        """Aplica los archivos `.cfg` de un directorio a los dispositivos correspondientes del lienzo."""
        return _safe(lambda: service.apply_config_bundle(input_dir))

    @mcp.tool()
    def cpt_generate_docs() -> str:
        """Genera documentación técnica en Markdown con tabla de direccionamiento e inventario más diagrama Mermaid."""
        return _safe(service.generate_docs)

    # =========================================================================
    # META-HERRAMIENTAS DE ESCALADO (64-67)
    # =========================================================================
    @mcp.tool()
    def cpt_search_methods(query: str, class_name: str = "", limit: int = 30) -> str:
        """Busca entre los 2.068 métodos de `ipc_index.json` por palabra clave o clase y devuelve sus firmas."""
        return _safe(lambda: service.search_methods(query, class_name, limit))

    @mcp.tool()
    def cpt_describe_method(class_name: str, method_name: str) -> str:
        """Devuelve la firma detallada, tipos de parámetros, herencia y sobrecargas de un método IPC concreto."""
        return _safe(lambda: service.describe_method(class_name, method_name))

    @mcp.tool()
    def cpt_batch(operations: list[dict[str, Any]], stop_on_error: bool = False) -> str:
        """HERRAMIENTA DE EJECUCIÓN EN LOTE: Ejecuta decenas de operaciones (`[{'tool': 'cpt_...', 'args': {...}}]`) en UNA SOLA llamada MCP para máxima velocidad y sin confirmaciones individuales."""
        return _safe(lambda: service.batch(operations, stop_on_error))

    @mcp.tool()
    def cpt_run_macro(macro_name: str, params: dict[str, Any] | None = None) -> str:
        """Ejecuta una receta/macro predefinida (ej. `office_3vlans_roas`, `wan_ospf_pair`, `mobile_lte_core`)."""
        return _safe(lambda: service.run_macro(macro_name, params))

    # =========================================================================
    # REDES MÓVILES Y CELULARES (3G/4G/LTE, HANDOVER Y BLUETOOTH/BLE)
    # =========================================================================
    @mcp.tool()
    def cpt_add_mobile_device(name: str, role: str = "smartphone",
                              model: str = "", x: int = 250, y: int = 250) -> str:
        """Agrega un nodo del ecosistema de redes móviles (`smartphone`, `tablet`, `cell_tower`, `central_office_server`, `coaxial_splitter`, `lap`)."""
        return _safe(lambda: service.add_mobile_device(name, role, model, x, y))

    @mcp.tool()
    def cpt_connect_cell_tower_to_co(cell_tower: str, co_server: str,
                                     co_port: str = "Coaxial0",
                                     tower_port: str = "Coaxial0",
                                     backbone_router: str = "",
                                     router_port: str = "GigabitEthernet0/0") -> str:
        """Conecta una antena `Cell Tower` con el `Central Office Server` mediante cable coaxial (`Coaxial0..5`) y opcionalmente el puerto `Backbone` hacia un router."""
        return _safe(lambda: service.connect_cell_tower_to_co(
            cell_tower, co_server, co_port, tower_port, backbone_router, router_port,
        ))

    @mcp.tool()
    def cpt_configure_cellular_interface(device: str, dhcp: bool = True,
                                         ip: str = "", mask: str = "", gateway: str = "",
                                         dns: str = "", port: str = "3G/4G Cell1",
                                         disable_wifi: bool = True,
                                         pap_chap_user: str = "", pap_chap_password: str = "",
                                         auth_mode: str = "chap") -> str:
        """Configura la interfaz celular (`3G/4G Cell1`) de un Smartphone o Tablet (DHCP/estático, credenciales PAP/CHAP y desactivación de `Wireless0` para evitar conflicto de ruta)."""
        return _safe(lambda: service.configure_cellular_interface(
            device, dhcp, ip, mask, gateway, dns, port, disable_wifi,
            pap_chap_user, pap_chap_password, auth_mode,
        ))

    @mcp.tool()
    def cpt_configure_mobile_wifi_toggle(device: str, active_radio: str = "cellular") -> str:
        """Conmuta el radio activo de un Smartphone o Tablet entre red celular (`active_radio='cellular'`) y Wi-Fi (`active_radio='wifi'`)."""
        return _safe(lambda: service.configure_mobile_wifi_toggle(device, active_radio))

    @mcp.tool()
    def cpt_deploy_cellular_topology(co_server: str = "CO-Core",
                                     isp_router: str = "R-ISP",
                                     cell_towers: int = 2,
                                     smartphones: int = 2,
                                     tablets: int = 1,
                                     backbone_subnet: str = "172.16.0.0",
                                     backbone_gateway: str = "172.16.0.1",
                                     backbone_mask: str = "255.255.255.0",
                                     dns_ip: str = "8.8.8.8") -> str:
        """Despliega automáticamente una arquitectura celular 3G/4G/LTE completa (Router ISP con DHCP <-> Central Office Server <-> N Cell Towers por cable coaxial <-> Smartphones y Tablets)."""
        return _safe(lambda: service.deploy_cellular_topology(
            co_server, isp_router, cell_towers, smartphones, tablets,
            backbone_subnet, backbone_gateway, backbone_mask, dns_ip,
        ))

    @mcp.tool()
    def cpt_simulate_mobile_handover(device: str, start_x: int, start_y: int,
                                     end_x: int, end_y: int, steps: int = 4,
                                     ping_target: str = "") -> str:
        """Simula el desplazamiento físico y handover (cambio de celda entre antenas) de un Smartphone o Tablet desde `(start_x, start_y)` hasta `(end_x, end_y)`."""
        return _safe(lambda: service.simulate_mobile_handover(
            device, start_x, start_y, end_x, end_y, steps, ping_target,
        ))

    @mcp.tool()
    def cpt_set_mobile_velocity(device: str, vx: float = 0.0, vy: float = 0.0) -> str:
        """Asigna un vector de velocidad de desplazamiento autónomo `(vx, vy)` a un dispositivo móvil en el lienzo."""
        return _safe(lambda: service.set_mobile_velocity(device, vx, vy))

    @mcp.tool()
    def cpt_configure_bluetooth(device: str, enabled: bool = True,
                                discoverable: bool = True, pair_mac: str = "") -> str:
        """Configura el módulo Bluetooth (`BluetoothManager`) en un Smartphone, Tablet, Laptop o SBC (visibilidad, broadcast y emparejamiento por MAC)."""
        return _safe(lambda: service.configure_bluetooth(device, enabled, discoverable, pair_mac))

    @mcp.tool()
    def cpt_configure_ble_beacon(device: str, enabled: bool = True,
                                 beacon_uuid: str = "{00000000-0000-0000-0000-000000000001}",
                                 beacon_data: str = "Caldas-BLE-Beacon",
                                 frequency_ms: int = 1000) -> str:
        """Configura la emisión de balizas Bluetooth Low Energy (BLE Beacon) en un equipo móvil o IoT."""
        return _safe(lambda: service.configure_ble_beacon(
            device, enabled, beacon_uuid, beacon_data, frequency_ms,
        ))

    @mcp.tool()
    def cpt_audit_mobile_network() -> str:
        """Audita el segmento de redes móviles: Central Office Servers, Cell Towers, enlaces coaxiales y estado de los radios `3G/4G Cell1` y `Wireless0` en Smartphones y Tablets."""
        return _safe(service.audit_mobile_network)

    return mcp


class McpServerThread(threading.Thread):
    """Servidor MCP streamable-http en segundo plano."""

    def __init__(self, service: PacketTracerService, host: str, port: int) -> None:
        super().__init__(daemon=True, name="mcp-server")
        self._service, self.host, self.port = service, host, port

    def run(self) -> None:
        log = self._service._client.log
        try:
            log("info", f"Servidor MCP en http://{self.host}:{self.port}/mcp")
            build_mcp(self._service, self.host, self.port).run(transport="streamable-http")
        except Exception as exc:  # noqa: BLE001
            log("error", f"Servidor MCP detenido: {exc}")

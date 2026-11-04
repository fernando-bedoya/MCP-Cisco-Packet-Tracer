# Reglas de Automatización de Cisco Packet Tracer (MCPCPT)

Este proyecto conecta el agente AI con Cisco Packet Tracer en tiempo real mediante el protocolo binario PTMP en el puerto `39000`.

## Principios de Ejecución Rápida (Sin fricción ni confirmaciones)

## Catálogo de Herramientas Listas para Usar

Todas estas operaciones están implementadas y verificadas directamente sobre el servidor MCP `packet-tracer`:

1. **Topología y Auditoría Instantánea**:
   - `cpt_get_topology`: Lee en 1 llamada todos los dispositivos y cables del canvas.
   - `cpt_audit_network`: Audita de una sola vez el estado de interfaces, IPs, máscaras y tablas de enrutamiento de todos los routers y hosts.
   - `cpt_get_instructions`: Extrae las instrucciones completas de la ventana de actividad (.pka).

2. **Creación y Enlaces**:
   - `cpt_add_device(name, device_type, model, x, y)`: Agrega routers (1941, 2911), switches (2960-24TT, 3560-24PS), PCs, servers, etc. y salta automáticamente el diálogo inicial.
   - `cpt_remove_device(name)`: Elimina un nodo.
   - `cpt_connect_ports(dev_a, port_a, dev_b, port_b, cable)`: Conecta con cable straight, cross, serial, fiber o console.

3. **Configuración de Dispositivos y Redes**:
   - `cpt_configure_ios(device, commands, save=True)`: Aplica listas de comandos IOS en routers/switches con auto-recuperación de submodos (`config-if`, `config-router`) y guarda con `write memory`.
     * *VLANs y Trunks*: `vlan 10`, `switchport mode trunk`, `switchport access vlan 10`.
     * *Enrutamiento*: OSPF (`router ospf 1`), RIP, EIGRP, o rutas estáticas (`ip route ...`).
     * *Router-on-a-Stick*: `interface Gi0/0.10`, `encapsulation dot1Q 10`, `ip address ...`.
     * *DHCP Pools*: `ip dhcp pool ...`, `network ...`, `default-router ...`, `ip dhcp excluded-address ...`.
     * *NAT / PAT*: `ip nat inside`, `ip nat outside`, `ip nat inside source list ...`.
     * *ACLs*: `access-list 10 permit ...`, `ip access-group ...`.
   - `cpt_configure_host(device, ip, mask, gateway, dns, dhcp)`: Configura PCs, Laptops y Servidores (estático o DHCP).
   - `cpt_fast_forward()`: Acelera el reloj de simulación de PT para convergencia inmediata de STP, ARP y enrutamiento.

4. **Verificación y Persistencia**:
   - `cpt_ping(device, target_ip)`: Prueba de conectividad punto a punto o extremo a extremo.
   - `cpt_save_file()`: Guarda los cambios directamente en el archivo `.pkt` / `.pka` abierto en Packet Tracer.


2. **Operaciones por Terminal (si fuera necesario)**:
   - Usa el módulo precompilado: `.venv/bin/python -m pt_mcp_bridge.quick <accion>` (`summary`, `save`, `ff`, `instructions`, `cli <dev> <cmd>`).
   - No crees scripts temporales sobre la marcha ni uses `BypassSandbox` repetitivo.

3. **Protocolo y Conexión IPC**:
   - Puerto IPC: `127.0.0.1:39000`
   - Identidad autenticada: `dev.pktctl` / MD5 (`pt-mcp-bridge.pta`)
   - Packet Tracer requiere que la opción de IPC esté en *Always listen on start* en `Extensions -> IPC -> Options`.

4. **Sintaxis Cisco IOS en `cpt_configure_ios`**:
   - `service.configure_ios` cuenta con recuperación automática ante submodos (`config-if`, `config-router`, etc.).
   - Aplica bloques completos de configuración y guarda con `write memory` automáticamente.

5. **Convergencia**:
   - Tras cambios de enlaces o direccionamiento IP, invoca siempre `cpt_fast_forward()` 3 a 5 veces para que el protocolo STP (Spanning-Tree), ARP y las rutas converjan inmediatamente.

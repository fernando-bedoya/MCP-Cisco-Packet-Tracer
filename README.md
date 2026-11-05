# El Arriero MCP

**Puente de integración entre el protocolo MCP (*Model Context Protocol*) y Cisco Packet Tracer**

![Licencia MIT](https://img.shields.io/badge/Licencia-MIT-green.svg)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)
![Alcance](https://img.shields.io/badge/Alcance-Acad%C3%A9mico%20%7C%20Universidad%20de%20Caldas-informational.svg)

---

## Alcance del Proyecto

**El Arriero MCP** es un proyecto de carácter **académico y experimental** desarrollado en el marco de la **Universidad de Caldas** (Manizales, Caldas, Colombia). Su propósito es investigar y facilitar la automatización de laboratorios de redes de computadores permitiendo que agentes de Inteligencia Artificial compatibles con el estándar **Model Context Protocol (MCP)** interactúen en tiempo real con el motor de simulación de **Cisco Packet Tracer**.

> **Nota académica:** Este software ha sido diseñado con fines educativos, de docencia e investigación experimental en ingeniería de redes y sistemas distribuidos. No constituye un producto oficial de Cisco Systems, Inc.

---

## Arquitectura del Sistema

Cisco Packet Tracer expone un canal de comunicación entre procesos (**IPC**) sobre un socket TCP local (por defecto `127.0.0.1:39000`). Sin embargo, dicho canal no emplea HTTP ni JSON, sino el protocolo binario/delimitado propietario **PTMP (*Packet Tracer Messaging Protocol*)**, el cual requiere:

1. **Encapsulamiento por longitud**: Cada trama se transmite precedida por su tamaño en bytes en ASCII decimal y delimitadores nulos (`<length>\0<body>`).
2. **Negociación y autenticación criptográfica**: Handshake de sesión de múltiples etapas (`HELLO` → `HELLO_REPLY` → `APP_ID` → `CHALLENGE` → `AUTH` con digest **MD5** usando una firma ExApp `.pta` registrada).
3. **Invocación tipada del árbol de objetos C++/Qt**: Encadenamiento de métodos internos (`appWindow`, `network`, `getLogicalWorkspace`, `getDevice`, `enterCommand`) codificando explícitamente los descriptores numéricos de tipo (`QString=9`, `string=8`, `int=4`, `double=7`, `IPAddress=10`, `Pair=14`, etc.).

```text
+---------------------------+        MCP (Streamable HTTP / STDIO)        +-----------------------------------+
|      Agente / Cliente     |  <=======================================>  |           El Arriero MCP          |
| (Claude, Cursor, Cline,   |          http://127.0.0.1:8765/mcp          |  - Servidor FastMCP (14 tools)    |
|  Antigravity, Windsurf)   |                o pipe STDIO                 |  - Capa de Dominio (Service)      |
+---------------------------+                                             |  - Consola Gráfica PyQt6          |
                                                                          +-----------------+-----------------+
                                                                                            |
                                                                                            | Socket TCP (127.0.0.1:39000)
                                                                                            | Protocolo PTMP + Auth MD5 (.pta)
                                                                                            v
                                                                          +-----------------------------------+
                                                                          |        Cisco Packet Tracer        |
                                                                          |   Motor IPC / Espacio de Trabajo  |
                                                                          +-----------------------------------+
```

### Módulos principales (`src/pt_mcp_bridge/`)

| Módulo | Responsabilidad |
| :--- | :--- |
| `ipc/contracts.py` | Contratos segregados (`IPCLogger`, `IPCInvoker`, `IPCConnectionLifecycle`, `IPCTransport`, `IndexRepository` y `JsonIndexRepository`) siguiendo **ISP** y **DIP**. |
| `ipc/protocol.py` | Codificación y decodificación pura de tramas PTMP (`FrameParser`, tipos primitivos de Qt, digest MD5 y validación de límites de trama). |
| `ipc/client.py` | Cliente TCP *thread-safe* con manejo de timeouts de conexión/petición, cierre no bloqueante y reconexión exponencial (`IPCTransport`). |
| `calls.py` | Constructores de cadenas de pasos (`Step`) para el modelo de objetos de Packet Tracer y resolución automática de cableado según normas CCNA. |
| `services/` | Paquete de 10 servicios de dominio desacoplados bajo principios **SOLID** (`IosCliService`, `TopologyService`, `SwitchingService`, `RoutingService`, `NetworkServicesManager`, `SecurityService`, `WanWirelessService`, `DiagnosticsService`, `AcademicLabService`, `MobileNetworkService`, `MetaCatalogService` y `MacroRegistry`). |
| `service.py` | Fachada unificada (`PacketTracerService`) que compone los servicios de dominio e inyecta `IPCTransport` e `IndexRepository` para las **99 herramientas MCP**. |
| `mcp_server/server.py` | Adaptador MCP (`FastMCP`) capaz de operar por transporte `streamable-http` o `stdio`. |
| `gui/` | Interfaz gráfica en PyQt6 para monitoreo de tramas TX/RX en tiempo real, medición de latencia IPC y control de conexión. |
| `config.py` | Gestión centralizada de configuración mediante variables de entorno (`.env`) con valores por defecto seguros (`127.0.0.1`). |

---

## Catálogo de Herramientas MCP (99 Herramientas por Dominio)

El servidor publica **99 herramientas** bajo el prefijo `cpt_*`, diseñadas para cubrir desde operaciones físicas hasta protocolos avanzados, redes móviles celulares y autodescubrimiento de los **2.068 métodos** del motor IPC:

1. **Topología y Dispositivos (20 herramientas)**:
   - `cpt_get_topology`, `cpt_add_device`, `cpt_remove_device`, `cpt_move_device`, `cpt_rename_device`, `cpt_clone_device`, `cpt_connect_ports`, `cpt_disconnect_ports`, `cpt_list_ports`, `cpt_set_port_state`, `cpt_add_module`, `cpt_power_device`, `cpt_add_note`, `cpt_group_devices`, `cpt_layout_auto`, `cpt_export_topology_json`, `cpt_import_topology_json`, `cpt_configure_host`, `cpt_send_cli_command`, `cpt_configure_ios`.
2. **Capa 2 — Switching (8 herramientas)**:
   - `cpt_create_vlan`, `cpt_assign_vlan_port`, `cpt_configure_trunk`, `cpt_configure_etherchannel`, `cpt_configure_stp`, `cpt_configure_port_security`, `cpt_show_mac_table`, `cpt_configure_vtp`.
3. **Capa 3 — Enrutamiento (11 herramientas)**:
   - `cpt_configure_static_route`, `cpt_configure_ospf`, `cpt_configure_eigrp`, `cpt_configure_rip`, `cpt_configure_bgp`, `cpt_configure_intervlan`, `cpt_configure_svi`, `cpt_configure_ipv6`, `cpt_configure_hsrp`, `cpt_configure_vrrp`, `cpt_show_routing_table`.
4. **Servicios de Red (10 herramientas)**:
   - `cpt_configure_dhcp_server`, `cpt_configure_dhcp_relay`, `cpt_configure_dns_server`, `cpt_configure_http_server`, `cpt_configure_ftp_server`, `cpt_configure_nat`, `cpt_configure_ntp`, `cpt_configure_syslog`, `cpt_configure_snmp`, `cpt_configure_email_server`.
5. **Seguridad y VPN (7 herramientas)**:
   - `cpt_configure_acl`, `cpt_apply_acl`, `cpt_configure_ssh`, `cpt_configure_aaa`, `cpt_secure_device`, `cpt_configure_vpn_ipsec`, `cpt_configure_gre`.
6. **Wireless y WAN (6 herramientas)**:
   - `cpt_configure_wlc`, `cpt_configure_ap`, `cpt_configure_ssid`, `cpt_configure_frame_relay`, `cpt_configure_ppp`, `cpt_configure_serial_clock`.
7. **Verificación, Simulación y Diagnóstico (15 herramientas)**:
   - `cpt_ping`, `cpt_traceroute`, `cpt_test_connectivity_matrix`, `cpt_fast_forward`, `cpt_audit_network`, `cpt_verify_vlans`, `cpt_verify_trunks`, `cpt_diff_config`, `cpt_snapshot_config`, `cpt_restore_config`, `cpt_find_misconfigurations`, `cpt_capture_packets`, `cpt_send_pdu`, `cpt_get_event_list`, `cpt_save_file`.
8. **Laboratorios Académicos y Calificación `.pka` (7 herramientas)**:
   - `cpt_get_instructions`, `cpt_check_activity`, `cpt_list_activity_checks`, `cpt_generate_lab`, `cpt_backup_all_configs`, `cpt_apply_config_bundle`, `cpt_generate_docs`.
9. **Meta-Herramientas y Escalado Dinámico (5 herramientas)**:
   - `cpt_search_methods`, `cpt_describe_method`, `cpt_batch`, `cpt_run_macro`, `cpt_raw_ipc`.
10. **Redes Móviles y Celulares — 3G/4G/LTE, Handover y Bluetooth/BLE (10 herramientas)**:
   - `cpt_add_mobile_device`, `cpt_connect_cell_tower_to_co`, `cpt_configure_cellular_interface`, `cpt_configure_mobile_wifi_toggle`, `cpt_deploy_cellular_topology`, `cpt_simulate_mobile_handover`, `cpt_set_mobile_velocity`, `cpt_configure_bluetooth`, `cpt_configure_ble_beacon`, `cpt_audit_mobile_network`.

---

## Requisitos Previos

- **Cisco Packet Tracer**: Versión **8.2.x** o **9.0+** instalada localmente con el servicio IPC habilitado.
- **Sistema Operativo**:
  - **Linux**: Debian 12+, Ubuntu 22.04+, Linux Mint 21+ o distribuciones equivalentes con servidor gráfico X11/Wayland (paquete del sistema `libxcb-cursor0` requerido por Qt6).
  - **Windows**: Windows 10 / 11 (64 bits) ejecutando Python 3.10+ nativo o mediante WSL2 con reenvío local.
- **Runtime de Ejecución**: **Python 3.10 o superior** (`python3`, `pip` y `venv`).

---

## Instalación y Ejecución

### Opción A (Recomendada — Cero dependencias): Instalador autónomo `.deb`

El paquete **[`el-arriero-mcp_1.0.0_amd64.deb`](el-arriero-mcp_1.0.0_amd64.deb)** (disponible tanto en la sección **Releases** de GitHub como en el proyecto) ya trae todo comprimido en un solo ejecutable autónomo (Python, PyQt6, QtSvg, FastMCP, el índice IPC, las 99 herramientas y el archivo `.pta`), configura automáticamente los permisos de `/opt/pt/extensions` y no entra en conflicto con repositorios externos de `apt`:

1. Haz **doble clic** sobre `el-arriero-mcp_1.0.0_amd64.deb` o instálalo directamente con `dpkg` / `apt`:
   ```bash
   sudo dpkg -i el-arriero-mcp_1.0.0_amd64.deb
   ```
2. Abre **El Arriero MCP** desde tu menú de aplicaciones o ejecutando `el-arriero-mcp` en la terminal.

#### Publicación de nuevas versiones en GitHub Releases
Para publicar una nueva versión del instalador `.deb` en la pestaña **Releases** de GitHub de forma automatizada:
```bash
./packaging/publish_release.sh 1.0.0
```
También se incluye el workflow de integración continua [`.github/workflows/release.yml`](.github/workflows/release.yml), que ejecuta `ruff` + `pytest`, compila el `.deb` y publica el Release automáticamente al subir cualquier tag `v*` (ej. `git tag v1.0.0 && git push origin v1.0.0`).

### Opción B: Desde código fuente

#### En Linux (instalación automatizada)

```bash
git clone https://github.com/ucaldas/el-arriero-mcp.git
cd el-arriero-mcp
./install.sh
```

#### Instalación manual multiplataforma (Linux / Windows)

```bash
git clone https://github.com/ucaldas/el-arriero-mcp.git
cd el-arriero-mcp

# Crear y activar entorno virtual
python3 -m venv .venv
source .venv/bin/activate        # En Windows PowerShell: .\.venv\Scripts\Activate.ps1

# Instalar el proyecto y sus dependencias
pip install --upgrade pip
pip install -e .
```

### 2. Configuración opcional de variables de entorno

El proyecto emplea por defecto los endpoints estándar locales (`127.0.0.1:39000` para el IPC de Packet Tracer y `127.0.0.1:8765` para el servidor MCP). Si deseas personalizarlos:

```bash
cp .env.example .env
```

Variables soportadas en `.env`:

| Variable | Valor por defecto | Descripción |
| :--- | :--- | :--- |
| `PT_HOST` | `127.0.0.1` | Dirección IP del socket IPC de Cisco Packet Tracer |
| `PT_PORT` | `39000` | Puerto TCP del servicio IPC en Packet Tracer |
| `MCP_HOST` | `127.0.0.1` | Host de escucha para el servidor MCP HTTP |
| `MCP_PORT` | `8765` | Puerto TCP del servidor MCP HTTP |
| `PT_CONNECT_TIMEOUT_S` | `5.0` | Timeout de conexión TCP inicial (segundos) |
| `PT_REQUEST_TIMEOUT_S` | `15.0` | Timeout de respuesta por operación IPC (segundos) |

### 3. Registro único de permisos ExApp en Cisco Packet Tracer (`.pta`)

Por seguridad, Packet Tracer restringe las llamadas IPC externas que modifican la topología o acceden a la CLI hasta que se autoriza la firma `.pta` del puente:

1. Abre **Cisco Packet Tracer**.
2. Dirígete a **Extensions → IPC → Configure Apps...**
3. Haz clic en **Add...** y selecciona el archivo **`pt-mcp-bridge.pta`** ubicado en la raíz de este repositorio.
4. En la pestaña **Options**, verifica que esté marcada la casilla **Always listen on start** en el puerto `39000`.
5. Pulsa **Ok** y cierra Packet Tracer normalmente (**File → Exit**) una vez para persistir el registro.

### 4. Levantar la aplicación

#### Modo Interfaz Gráfica + Servidor MCP HTTP (`http://127.0.0.1:8765/mcp`)

```bash
el-arriero-mcp
# O directamente desde el entorno virtual:
.venv/bin/el-arriero-mcp
```

#### Modo Headless por consola (`--stdio`)

```bash
el-arriero-mcp --stdio
```

#### Configuración en clientes MCP

- **Clientes HTTP (`mcp_config.json` / `mcp.json`)**:
  ```json
  {
    "mcpServers": {
      "packet-tracer": {
        "serverUrl": "http://127.0.0.1:8765/mcp"
      }
    }
  }
  ```

- **Clientes STDIO (Claude Desktop / Claude Code / CLI)**:
  ```json
  {
    "mcpServers": {
      "packet-tracer": {
        "command": "el-arriero-mcp",
        "args": ["--stdio"]
      }
    }
  }
  ```

---

## Verificación y Pruebas

Para ejecutar la suite de pruebas unitarias (con simulador PTMP integrado) y el análisis estático de código:

```bash
.venv/bin/pytest -B -o cache_dir=/tmp/pytest_cache -v
.venv/bin/ruff check --no-cache src tests tools
```

---

## Licencia

Este proyecto se distribuye bajo la **Licencia MIT**. Consulta el archivo [`LICENSE`](LICENSE) para conocer el texto legal completo.

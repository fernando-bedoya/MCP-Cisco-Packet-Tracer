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
| `ipc/protocol.py` | Codificación y decodificación pura de tramas PTMP (`FrameParser`, tipos primitivos de Qt, digest MD5 y validación de límites de trama). |
| `ipc/client.py` | Cliente TCP *thread-safe* con manejo de timeouts de conexión/petición, cierre no bloqueante y reconexión exponencial (`IPCTransport`). |
| `calls.py` | Constructores de cadenas de pasos (`Step`) para el modelo de objetos de Packet Tracer y resolución automática de cableado según normas CCNA. |
| `service.py` | Lógica de dominio para las 14 herramientas, recuperación automática de submodos de consola Cisco IOS (`config-if`, `config-router`) e índice IPC (`ipc_index.json`). |
| `mcp_server/server.py` | Adaptador MCP (`FastMCP`) capaz de operar por transporte `streamable-http` o `stdio`. |
| `gui/` | Interfaz gráfica en PyQt6 para monitoreo de tramas TX/RX en tiempo real, medición de latencia IPC y control de conexión. |
| `config.py` | Gestión centralizada de configuración mediante variables de entorno (`.env`) con valores por defecto seguros (`127.0.0.1`). |

---

## Herramientas MCP Expuestas

El puente publica **14 herramientas** bajo el prefijo `cpt_*`:

- **`cpt_get_topology`**: Inventario completo de nodos en el lienzo, coordenadas, modelos y enlaces cableados.
- **`cpt_add_device` / `cpt_remove_device`**: Creación y eliminación de routers, switches, PCs, servidores, laptops, nubes y puntos de acceso, omitiendo automáticamente el arranque IOS (`skipBoot`).
- **`cpt_connect_ports`**: Tendido de enlaces físicos (`auto`, `straight`, `cross`, `serial`, `fiber`, `console`, `coaxial`, `octal`, `usb`).
- **`cpt_list_ports`**: Consulta de interfaces de un equipo con estado físico/protocolo, dirección IPv4 y máscara.
- **`cpt_configure_ios`**: Ejecución transaccional de bloques de comandos Cisco IOS en modo de configuración global con salida automática de submodos y guardado en NVRAM (`write memory`).
- **`cpt_send_cli_command`**: Envío directo de comandos de verificación o configuración a la consola IOS (`show ip route`, `show running-config`, `show vlan brief`, etc.).
- **`cpt_configure_host`**: Asignación de direccionamiento IPv4 estático (IP, máscara, puerta de enlace, DNS) o habilitación de cliente DHCP en equipos finales.
- **`cpt_ping`**: Prueba de conectividad ICMP desde un host o enrutador hacia una dirección IP destino.
- **`cpt_fast_forward`**: Adelanto del reloj de simulación en modo *Realtime* para converger STP, ARP, DHCP y protocolos de enrutamiento.
- **`cpt_audit_network`**: Auditoría integral de la topología (interfaces, direccionamiento y tablas de enrutamiento de todos los dispositivos en una sola operación).
- **`cpt_get_instructions`**: Extracción en texto plano del enunciado de laboratorios `.pka` o `.pkt`.
- **`cpt_save_file`**: Guardado del archivo activo en Cisco Packet Tracer.
- **`cpt_raw_ipc`**: Invocación directa de cualquiera de los 2.068 métodos del índice interno de Packet Tracer (`ipc_index.json`).

---

## Requisitos Previos

- **Cisco Packet Tracer**: Versión **8.2.x** o **9.0+** instalada localmente con el servicio IPC habilitado.
- **Sistema Operativo**:
  - **Linux**: Debian 12+, Ubuntu 22.04+, Linux Mint 21+ o distribuciones equivalentes con servidor gráfico X11/Wayland (paquete del sistema `libxcb-cursor0` requerido por Qt6).
  - **Windows**: Windows 10 / 11 (64 bits) ejecutando Python 3.10+ nativo o mediante WSL2 con reenvío local.
- **Runtime de Ejecución**: **Python 3.10 o superior** (`python3`, `pip` y `venv`).

---

## Instalación y Ejecución

### 1. Clonar el repositorio e instalar dependencias

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

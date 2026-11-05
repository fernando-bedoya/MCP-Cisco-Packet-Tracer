"""Ventana principal PyQt6 de El Arriero MCP con identidad visual de Caldas, Colombia."""
from __future__ import annotations

import sys
import threading
from pathlib import Path

from PyQt6.QtCore import QObject, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from pt_mcp_bridge import config
from pt_mcp_bridge.gui import icons, theme
from pt_mcp_bridge.ipc import ClientEvents, ConnectionState, PTClient, PTError
from pt_mcp_bridge.mcp_server import McpServerThread
from pt_mcp_bridge.service import PacketTracerService

S = ConnectionState
SIDEBAR_W = 156
TOPBAR_H = 56


class _Bus(QObject):
    """Puente thread-safe desde hilos de red hacia el hilo principal de Qt."""

    log = pyqtSignal(str, str)
    state = pyqtSignal(str)
    latency = pyqtSignal(float)


class _BackdropWidget(QWidget):
    """Lienzo raíz que dibuja la fotografía compuesta de Caldas y las divisiones sobrias."""

    def __init__(self, bg_pixmap: QPixmap) -> None:
        super().__init__()
        self._bg = bg_pixmap

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height()

        # 1. Fondo negro carbón base (#0B0B0B)
        painter.fillRect(0, 0, w, h, QColor("#0B0B0B"))

        # 2. Fotografía compuesta de Caldas (escalada cubriendo el lienzo, alineada a derecha/abajo)
        if not self._bg.isNull():
            scaled = self._bg.scaled(
                w,
                h,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            sx = max(0, scaled.width() - w)
            sy = max(0, (scaled.height() - h) // 2)
            painter.drawPixmap(QRect(0, 0, w, h), scaled, QRect(sx, sy, w, h))

        # 3. Barra superior sobria (#0E0E0E con línea divisoria #2A2A2A)
        painter.fillRect(0, 0, w, TOPBAR_H, QColor(12, 12, 12, 235))
        painter.setPen(QPen(QColor("#282828"), 1))
        painter.drawLine(0, TOPBAR_H - 1, w, TOPBAR_H - 1)

        # 4. Barra lateral izquierda (semi-transparente abajo para lucir la planta de café)
        painter.fillRect(0, TOPBAR_H, SIDEBAR_W, h - TOPBAR_H, QColor(11, 11, 11, 105))
        painter.setPen(QPen(QColor("#262626"), 1))
        painter.drawLine(SIDEBAR_W, TOPBAR_H, SIDEBAR_W, h)
        painter.end()


class MainWindow(QMainWindow):
    def __init__(self, mcp_port: int) -> None:
        super().__init__()
        self._mcp_url = f"http://{config.DEFAULT_MCP_HOST}:{mcp_port}/mcp"
        self._tx_count = 0
        self._rx_count = 0
        self._last_ping_ms: float | None = None

        self.setWindowTitle(theme.APP_TITLE)
        self.resize(1024, 682)
        self.setMinimumSize(860, 560)
        self.setStyleSheet(theme.STYLESHEET)

        self._bus = _Bus()
        self._client = PTClient(
            ClientEvents(
                on_log=self._bus.log.emit,
                on_state=lambda s: self._bus.state.emit(s.value),
            )
        )
        self._client.auto_reconnect = True
        self._bus.log.connect(self._append_log)
        self._bus.state.connect(lambda v: self._set_state(S(v)))
        self._bus.latency.connect(self._set_latency)

        self._build_ui()
        self._set_state(S.DISCONNECTED)
        McpServerThread(PacketTracerService(self._client), config.DEFAULT_MCP_HOST, mcp_port).start()

    # -- construcción de interfaz --------------------------------------
    def _build_ui(self) -> None:
        bg_pix = QPixmap(str(theme.asset_path("caldas_bg.jpg")))
        root = _BackdropWidget(bg_pix)
        root_v = QVBoxLayout(root)
        root_v.setContentsMargins(0, 0, 0, 0)
        root_v.setSpacing(0)

        # 1. Barra superior (56 px)
        root_v.addWidget(self._build_topbar())

        # 2. Cuerpo: Barra lateral (156 px) + Área principal apilada
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        body.addWidget(self._build_sidebar())

        self._pages = QStackedWidget()
        self._pages.addWidget(self._build_home_page())
        self._pages.addWidget(self._build_tutorial_page())
        self._pages.addWidget(self._build_settings_page())
        self._pages.addWidget(self._build_about_page())
        body.addWidget(self._pages, stretch=1)

        root_v.addLayout(body, stretch=1)
        self.setCentralWidget(root)

        self._switch_page(0)

    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(TOPBAR_H)
        h = QHBoxLayout(bar)
        h.setContentsMargins(20, 0, 20, 0)
        h.setSpacing(12)

        logo = QLabel()
        logo.setPixmap(icons.svg_pixmap(icons.LOGO_MOUNTAINS_SVG, 42, 24))

        title = QLabel(theme.APP_TITLE)
        title.setObjectName("topTitle")

        sep = QFrame()
        sep.setObjectName("topSeparator")
        sep.setFixedSize(1, 18)

        sub = QLabel(theme.APP_SUBTITLE)
        sub.setObjectName("topSubtitle")

        h.addWidget(logo)
        h.addWidget(title)
        h.addSpacing(4)
        h.addWidget(sep)
        h.addSpacing(4)
        h.addWidget(sub)
        h.addStretch()
        return bar

    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setFixedWidth(SIDEBAR_W)
        v = QVBoxLayout(side)
        v.setContentsMargins(10, 16, 10, 14)
        v.setSpacing(6)

        self._btn_nav_home = QPushButton("  Inicio")
        self._btn_nav_tutorial = QPushButton("  Tutorial")
        self._btn_nav_settings = QPushButton("  Ajustes")
        self._btn_nav_about = QPushButton("  Acerca de")

        self._nav_buttons = [
            (self._btn_nav_home, icons.HOME_SVG, 0),
            (self._btn_nav_tutorial, icons.BOOK_SVG, 1),
            (self._btn_nav_settings, icons.SETTINGS_SVG, 2),
            (self._btn_nav_about, icons.INFO_SVG, 3),
        ]
        for btn, _svg, idx in self._nav_buttons:
            btn.setIconSize(QSize(18, 18))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, i=idx: self._switch_page(i))
            v.addWidget(btn)

        # Espacio transparente inferior donde luce la planta de café real
        v.addStretch(1)

        # Estado inferior e identificación de versión
        status_box = QVBoxLayout()
        status_box.setContentsMargins(6, 0, 6, 0)
        status_box.setSpacing(2)

        status_row = QHBoxLayout()
        status_row.setSpacing(7)
        self._side_dot = QLabel("●")
        self._side_lbl = QLabel("Listo")
        self._side_lbl.setObjectName("sidebarStatus")
        status_row.addWidget(self._side_dot)
        status_row.addWidget(self._side_lbl)
        status_row.addStretch()

        ver_lbl = QLabel(theme.APP_VERSION)
        ver_lbl.setObjectName("sidebarVersion")

        status_box.addLayout(status_row)
        status_box.addWidget(ver_lbl)
        v.addLayout(status_box)
        return side

    def _build_home_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(20, 22, 24, 12)
        v.setSpacing(14)

        # 1. Encabezado Hero con icono de laptop/red y título
        hero = QHBoxLayout()
        hero.setContentsMargins(12, 8, 12, 8)
        hero.setSpacing(18)

        laptop_icon = QLabel()
        laptop_icon.setPixmap(icons.svg_pixmap(icons.HERO_LAPTOP_SVG, 66, 48))

        hero_text = QVBoxLayout()
        hero_text.setSpacing(3)
        h_title = QLabel(theme.APP_TITLE)
        h_title.setObjectName("heroTitle")
        h_desc = QLabel(theme.HERO_DESCRIPTION)
        h_desc.setObjectName("heroDesc")
        hero_text.addWidget(h_title)
        hero_text.addWidget(h_desc)

        hero.addWidget(laptop_icon)
        hero.addLayout(hero_text)
        hero.addStretch()
        v.addLayout(hero)

        # 2. Panel de conexión
        conn_panel = QFrame()
        conn_panel.setObjectName("connectionPanel")
        conn_h = QHBoxLayout(conn_panel)
        conn_h.setContentsMargins(18, 14, 18, 14)
        conn_h.setSpacing(18)

        # Columna Host
        host_col = QVBoxLayout()
        host_col.setSpacing(6)
        host_hdr = QHBoxLayout()
        host_hdr.setSpacing(6)
        host_ico = QLabel()
        host_ico.setPixmap(icons.svg_pixmap(icons.HOST_SVG, 15, 15))
        host_lbl = QLabel("Host")
        host_lbl.setObjectName("fieldLabel")
        host_hdr.addWidget(host_ico)
        host_hdr.addWidget(host_lbl)
        host_hdr.addStretch()

        self._host = QLineEdit(config.DEFAULT_PT_HOST)
        self._host.setFixedSize(172, 36)
        host_col.addLayout(host_hdr)
        host_col.addWidget(self._host)

        # Columna Puerto IPC
        port_col = QVBoxLayout()
        port_col.setSpacing(6)
        port_hdr = QHBoxLayout()
        port_hdr.setSpacing(6)
        port_ico = QLabel()
        port_ico.setPixmap(icons.svg_pixmap(icons.PLUG_SVG, 15, 15))
        port_lbl = QLabel("Puerto IPC")
        port_lbl.setObjectName("fieldLabel")
        port_hdr.addWidget(port_ico)
        port_hdr.addWidget(port_lbl)
        port_hdr.addStretch()

        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(config.DEFAULT_PT_PORT)
        self._port.setFixedSize(162, 36)
        port_col.addLayout(port_hdr)
        port_col.addWidget(self._port)

        # Separador vertical
        divider = QFrame()
        divider.setObjectName("panelDivider")
        divider.setFixedSize(1, 50)

        # Botón Conectar y Botón Limpiar
        self._btn_connect = QPushButton("  Conectar a Packet Tracer")
        self._btn_connect.setIconSize(QSize(15, 15))
        self._btn_connect.setFixedHeight(44)
        self._btn_connect.setMinimumWidth(226)
        self._btn_connect.setCursor(Qt.CursorShape.PointingHandCursor)

        self._btn_clear = QPushButton("  Limpiar")
        self._btn_clear.setObjectName("clearBtn")
        self._btn_clear.setIcon(icons.svg_icon(icons.BROOM_SVG, 16))
        self._btn_clear.setIconSize(QSize(16, 16))
        self._btn_clear.setFixedHeight(44)
        self._btn_clear.setMinimumWidth(112)
        self._btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)

        conn_h.addLayout(host_col)
        conn_h.addLayout(port_col)
        conn_h.addSpacing(6)
        conn_h.addWidget(divider)
        conn_h.addStretch()
        conn_h.addWidget(self._btn_connect)
        conn_h.addWidget(self._btn_clear)
        v.addWidget(conn_panel)

        # 3. Consola de registros ("Registro")
        console_panel = QFrame()
        console_panel.setObjectName("consolePanel")
        console_v = QVBoxLayout(console_panel)
        console_v.setContentsMargins(10, 8, 10, 8)
        console_v.setSpacing(4)

        console_hdr = QHBoxLayout()
        console_hdr.setContentsMargins(6, 0, 4, 0)
        lbl_reg = QLabel("Registro")
        lbl_reg.setObjectName("consoleHeader")

        self._btn_tutorial_quick = QPushButton("📖 Tutorial y Ayuda")
        self._btn_tutorial_quick.setObjectName("smallActionBtn")
        self._btn_tutorial_quick.setCursor(Qt.CursorShape.PointingHandCursor)

        self._btn_test = QPushButton("Ping IPC")
        self._btn_test.setObjectName("smallActionBtn")
        self._btn_test.setCursor(Qt.CursorShape.PointingHandCursor)

        self._btn_pta = QPushButton("Permisos .pta")
        self._btn_pta.setObjectName("smallActionBtn")
        self._btn_pta.setCursor(Qt.CursorShape.PointingHandCursor)

        console_hdr.addWidget(lbl_reg)
        console_hdr.addStretch()
        console_hdr.addWidget(self._btn_tutorial_quick)
        console_hdr.addWidget(self._btn_test)
        console_hdr.addWidget(self._btn_pta)

        self._console = QPlainTextEdit(readOnly=True)
        self._console.setObjectName("console")
        font = QFont("JetBrains Mono", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._console.setFont(font)
        self._console.setMaximumBlockCount(5000)

        console_v.addLayout(console_hdr)
        console_v.addWidget(self._console, stretch=1)
        v.addWidget(console_panel, stretch=1)

        # 4. Barra inferior técnica (URL MCP + Copiar + TX | RX | Ping)
        footer = QHBoxLayout()
        footer.setContentsMargins(4, 0, 4, 0)
        footer.setSpacing(10)

        self._endpoint_lbl = QLabel(f"MCP: {self._mcp_url}")
        self._endpoint_lbl.setObjectName("footerText")

        self._btn_copy = QPushButton("Copiar URL")
        self._btn_copy.setObjectName("smallActionBtn")
        self._btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)

        self._stats_lbl = QLabel()
        self._stats_lbl.setObjectName("footerText")
        self._update_stats()

        footer.addWidget(self._endpoint_lbl)
        footer.addWidget(self._btn_copy)
        footer.addStretch()
        footer.addWidget(self._stats_lbl)
        v.addLayout(footer)

        # Conexión de señales de botones
        self._btn_connect.clicked.connect(self._toggle)
        self._btn_clear.clicked.connect(self._clear_console)
        self._btn_tutorial_quick.clicked.connect(lambda: self._switch_page(1))
        self._btn_test.clicked.connect(self._test)
        self._btn_pta.clicked.connect(self._show_pta_help)
        self._btn_copy.clicked.connect(self._copy_mcp_url)
        return page

    def _build_tutorial_page(self) -> QWidget:
        """Construye la guía interactiva paso a paso y diccionario de errores en lenguaje sencillo."""
        scroll = QScrollArea()
        scroll.setObjectName("tutorialScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        container.setObjectName("tutorialContainer")
        v = QVBoxLayout(container)
        v.setContentsMargins(24, 22, 24, 24)
        v.setSpacing(16)

        # --- TARJETA 1: BOSQUEJO DEL FUNCIONAMIENTO ---
        card_flow = QFrame()
        card_flow.setObjectName("infoCard")
        cf_v = QVBoxLayout(card_flow)
        cf_v.setContentsMargins(22, 18, 22, 18)
        cf_v.setSpacing(10)

        t_flow = QLabel("1. ¿Cómo funciona El Arriero MCP? (Bosquejo sencillo)")
        t_flow.setObjectName("topTitle")

        b_flow = QLabel(
            "Imagina que <b>Cisco Packet Tracer</b> y tu <b>Inteligencia Artificial</b> hablan idiomas distintos. "
            "<b>El Arriero MCP</b> actúa como un <b>traductor en tiempo real</b> entre los dos:<br><br>"
            "<span style='color:#70B77E; font-weight:700;'>"
            "  [ 1. Tú le pides algo a la IA ]  ───►  [ 2. El Arriero MCP traduce la orden ]  ───►  [ 3. Packet Tracer arma la red ]"
            "</span><br><br>"
            "• <b>Paso A (Tu petición):</b> Le escribes en español normal a tu asistente de IA (por ejemplo: "
            "<i>\"Crea una red con 2 routers, un switch, 3 computadores y configúrales salida a internet\"</i>).<br>"
            "• <b>Paso B (El puente):</b> Este programa recibe la instrucción por su canal local "
            "(<code>http://127.0.0.1:8765/mcp</code>) y la convierte en órdenes para el simulador.<br>"
            "• <b>Paso C (El resultado):</b> Ves aparecer en tu pantalla de Packet Tracer los equipos, los cables "
            "conectados y las configuraciones aplicadas automáticamente."
        )
        b_flow.setWordWrap(True)
        cf_v.addWidget(t_flow)
        cf_v.addWidget(b_flow)
        v.addWidget(card_flow)

        # --- TARJETA 2: CÓMO SE INSTALA Y CÓMO SE MANEJA PASO A PASO ---
        card_steps = QFrame()
        card_steps.setObjectName("infoCard")
        cs_v = QVBoxLayout(card_steps)
        cs_v.setContentsMargins(22, 18, 22, 18)
        cs_v.setSpacing(12)

        t_steps = QLabel("2. Guía paso a paso: Configuración e Inicio Rápido")
        t_steps.setObjectName("topTitle")

        pta_path = config.pta_file_path()
        b_steps = QLabel(
            "<b style='color:#70B77E;'>PASO 1: Dar permiso en Cisco Packet Tracer (Solo se hace la primera vez)</b><br>"
            "Por seguridad, Packet Tracer pide que autorices este programa una única vez:<br>"
            "  1. Abre <b>Cisco Packet Tracer</b> e inicia sesión normalmente.<br>"
            "  2. En el menú superior entra en: <b>Extensions</b> → <b>IPC</b> → <b>Configure Apps...</b><br>"
            "  3. Si en la lista ya ves <i>PT-MCP-Bridge</i> de una instalación anterior, selecciónalo y pulsa <b>Remove</b>.<br>"
            "  4. Pulsa el botón <b>Add...</b> y selecciona el archivo de permiso:<br>"
            f"     <span style='color:#C8B88A; font-family:monospace;'>{pta_path}</span><br>"
            "  5. En esa misma ventana abre la pestaña <b>Options</b>, marca la casilla <b>Always listen on start</b> "
            "(puerto <code>39000</code>) y pulsa <b>Ok</b>.<br><br>"
            "<b style='color:#70B77E;'>PASO 2: Conectar El Arriero MCP con Packet Tracer</b><br>"
            "  1. Ve a la pestaña <b>Inicio</b> de este programa (arriba a la izquierda).<br>"
            "  2. Deja el Host en <code>127.0.0.1</code> y el Puerto IPC en <code>39000</code>.<br>"
            "  3. Haz clic en <b>Conectar a Packet Tracer</b>. El indicador inferior izquierdo pasará a "
            "<span style='color:#70B77E;'>● En línea</span>.<br><br>"
            "<b style='color:#70B77E;'>PASO 3: Vincular tu Asistente de Inteligencia Artificial</b><br>"
            f"  • Copia la dirección <code>{self._mcp_url}</code> (con el botón de abajo o desde la barra inferior) "
            "y agrégala como servidor MCP en tu asistente (Claude, Cursor, Antigravity, Windsurf, etc.)."
        )
        b_steps.setWordWrap(True)

        btn_row = QHBoxLayout()
        btn_copy_pta = QPushButton("1. Copiar ruta del permiso (.pta) y reparar")
        btn_copy_pta.setObjectName("clearBtn")
        btn_copy_pta.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy_pta.clicked.connect(self._show_pta_help)

        btn_copy_url = QPushButton("2. Copiar dirección para tu IA")
        btn_copy_url.setObjectName("clearBtn")
        btn_copy_url.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy_url.clicked.connect(self._copy_mcp_url)

        btn_row.addWidget(btn_copy_pta)
        btn_row.addWidget(btn_copy_url)
        btn_row.addStretch()

        cs_v.addWidget(t_steps)
        cs_v.addWidget(b_steps)
        cs_v.addLayout(btn_row)
        v.addWidget(card_steps)

        # --- TARJETA 3: ERRORES FRECUENTES Y SIGNIFICADO DE CADA CÓDIGO ---
        card_err = QFrame()
        card_err.setObjectName("infoCard")
        ce_v = QVBoxLayout(card_err)
        ce_v.setContentsMargins(22, 18, 22, 18)
        ce_v.setSpacing(10)

        t_err = QLabel("3. Solución de Errores Frecuentes y Qué Significa Cada Código")
        t_err.setObjectName("topTitle")

        b_err = QLabel(
            "<b style='color:#D16D6A;'>● Error en Packet Tracer: \"An error occurred importing this application's meta file\"</b><br>"
            "<b>¿Qué significa?:</b> Packet Tracer intentó copiar el archivo de permiso <code>.pta</code> a su carpeta interna, "
            "pero ya había un archivo viejo con el mismo nombre o la carpeta tenía candado de administrador.<br>"
            "<b>Cómo solucionarlo:</b> En la ventana <i>Configure Apps</i> de Packet Tracer, si ya aparece <i>PT-MCP-Bridge</i>, "
            "selecciónalo y pulsa <b>Remove</b>; luego haz clic en el botón <b>\"1. Copiar ruta del permiso (.pta) y reparar\"</b> "
            "de arriba y vuelve a darle a <b>Add...</b>.<br><br>"
            "<b style='color:#D4A359;'>● Error en consola: \"Connection refused\" o el estado cambia a \"Error\"</b><br>"
            "<b>¿Qué significa?:</b> El Arriero MCP intentó comunicarse por el puerto <code>39000</code>, pero Packet Tracer "
            "no respondió.<br>"
            "<b>Cómo solucionarlo:</b> Verifica que <b>Cisco Packet Tracer esté abierto</b> y que hayas realizado el <b>Paso 1</b>.<br><br>"
            "<b style='color:#D4A359;'>● Error: \"createLink devolvió false\" al conectar un cable</b><br>"
            "<b>¿Qué significa?:</b> Se intentó conectar un cable en un enchufe (puerto) que ya estaba ocupado por otro cable "
            "o que no existe en ese modelo de equipo.<br><br>"
            "<b style='color:#70B77E;'>● ¿Qué significan las etiquetas y códigos que ves en el cuadro de \"Registro\"?</b><br>"
            "  • <b>[INFO] (Verde):</b> Todo marcha bien (el servidor encendió o la conexión fue exitosa).<br>"
            "  • <b>[MCP] (Dorado):</b> Muestra la acción que tu Inteligencia Artificial está ejecutando en ese instante.<br>"
            "  • <b>TX y RX:</b> <code>TX</code> cuenta cuántas órdenes se han enviado a Packet Tracer y <code>RX</code> cuántas "
            "respuestas han regresado.<br>"
            "  • <b>status: ok (Código 0):</b> El router o switch aceptó y guardó la orden correctamente.<br>"
            "  • <b>status: ambiguous (Código 1):</b> Palabra escrita a medias; el equipo no supo cuál comando elegir.<br>"
            "  • <b>status: invalid (Código 2):</b> Ese comando no aplica para ese modelo de equipo o modo actual.<br>"
            "  • <b>status: incomplete (Código 3):</b> A la orden le faltaron datos (por ejemplo, faltó escribir la dirección IP).<br>"
            "  • <b>status: not_implemented (Código 4):</b> Es una función avanzada que el simulador Packet Tracer no incluye."
        )
        b_err.setWordWrap(True)

        ce_v.addWidget(t_err)
        ce_v.addWidget(b_err)
        v.addWidget(card_err)
        v.addStretch()

        scroll.setWidget(container)
        return scroll

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(14)

        card = QFrame()
        card.setObjectName("infoCard")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(22, 20, 22, 20)
        cv.setSpacing(14)

        title = QLabel("Ajustes y Diagnóstico IPC")
        title.setObjectName("topTitle")
        cv.addWidget(title)

        self._chk_reconnect = QCheckBox("Reconexión automática si Cisco Packet Tracer se reinicia")
        self._chk_reconnect.setChecked(self._client.auto_reconnect)
        self._chk_reconnect.setStyleSheet("color: #E5E5E5; font-size: 13px;")
        self._chk_reconnect.toggled.connect(self._on_reconnect_toggled)
        cv.addWidget(self._chk_reconnect)

        pta_path = config.pta_file_path()
        pta_lbl = QLabel(
            f"<b>Archivo ExApp firmado (.pta):</b><br>"
            f"<span style='color:#929292; font-family:monospace;'>{pta_path}</span>"
        )
        pta_lbl.setWordWrap(True)
        cv.addWidget(pta_lbl)

        btn_row = QHBoxLayout()
        btn_ping = QPushButton("Ejecutar Ping IPC")
        btn_ping.setObjectName("clearBtn")
        btn_ping.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ping.clicked.connect(self._test)

        btn_pta = QPushButton("Instrucciones de registro .pta")
        btn_pta.setObjectName("clearBtn")
        btn_pta.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_pta.clicked.connect(self._show_pta_help)

        btn_row.addWidget(btn_ping)
        btn_row.addWidget(btn_pta)
        btn_row.addStretch()
        cv.addLayout(btn_row)

        v.addWidget(card)
        v.addStretch()
        return page

    def _build_about_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(14)

        card = QFrame()
        card.setObjectName("infoCard")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(22, 20, 22, 20)
        cv.setSpacing(10)

        title = QLabel(f"{theme.APP_TITLE} — {theme.APP_SUBTITLE}")
        title.setObjectName("topTitle")

        body = QLabel(
            f"<b>Versión:</b> {theme.APP_VERSION}<br>"
            "<b>Alcance:</b> Proyecto académico y experimental<br>"
            "<b>Institución:</b> Universidad de Caldas (Caldas, Colombia)<br>"
            "<b>Licencia:</b> MIT<br><br>"
            "<span style='color:#929292;'>"
            "Puente nativo para Linux que conecta cualquier agente de Inteligencia Artificial "
            "compatible con Model Context Protocol (MCP) directamente con el motor IPC (PTMP) "
            "de Cisco Packet Tracer.<br><br>"
            "Identidad visual inspirada en el paisaje cafetero, los atardeceres y la arquitectura "
            "tradicional del departamento de Caldas."
            "</span>"
        )
        body.setWordWrap(True)

        cv.addWidget(title)
        cv.addWidget(body)
        v.addWidget(card)
        v.addStretch()
        return page

    # -- navegación y estado -------------------------------------------
    def _switch_page(self, index: int) -> None:
        self._pages.setCurrentIndex(index)
        for btn, svg_tpl, idx in self._nav_buttons:
            active = idx == index
            color = "#E5E5E5" if active else "#929292"
            btn.setObjectName("navBtnActive" if active else "navBtn")
            btn.setIcon(icons.svg_icon(svg_tpl.format(color=color), 18))
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _on_reconnect_toggled(self, checked: bool) -> None:
        self._client.auto_reconnect = checked

    def _append_log(self, level: str, msg: str) -> None:
        if level == "tx":
            self._tx_count += 1
            self._update_stats()
        elif level == "rx":
            self._rx_count += 1
            self._update_stats()

        self._console.appendHtml(theme.format_log_html(level, msg))
        self._console.moveCursor(QTextCursor.MoveOperation.End)

    def _set_latency(self, ms: float) -> None:
        self._last_ping_ms = ms
        self._update_stats()

    def _update_stats(self) -> None:
        ping_str = f"{self._last_ping_ms:.1f} ms" if self._last_ping_ms is not None else "--"
        self._stats_lbl.setText(f"TX: {self._tx_count}  |  RX: {self._rx_count}  |  Ping: {ping_str}")

    def _clear_console(self) -> None:
        self._console.clear()
        self._tx_count = 0
        self._rx_count = 0
        self._update_stats()

    def _copy_mcp_url(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._mcp_url)
        self._btn_copy.setText("Copiado ✓")
        QTimer.singleShot(1500, lambda: self._btn_copy.setText("Copiar URL"))

    def _set_state(self, state: ConnectionState) -> None:
        dot_color, label = theme.STATE_SIDEBAR[state]
        self._side_dot.setStyleSheet(f"color:{dot_color}; font-size:14px;")
        self._side_lbl.setText(label)

        active = state in (S.ONLINE, S.CONNECTING)
        self._btn_connect.setEnabled(state is not S.CONNECTING)
        if active:
            self._btn_connect.setText("  Desconectar")
            self._btn_connect.setIcon(icons.svg_icon(icons.STOP_SVG, 15))
            self._btn_connect.setObjectName("disconnectBtn")
        else:
            self._btn_connect.setText("  Conectar a Packet Tracer")
            self._btn_connect.setIcon(icons.svg_icon(icons.PLAY_SVG, 15))
            self._btn_connect.setObjectName("connectBtn")
        self._btn_connect.style().unpolish(self._btn_connect)
        self._btn_connect.style().polish(self._btn_connect)

        self._btn_test.setEnabled(state is S.ONLINE)
        editable = state in (S.DISCONNECTED, S.ERROR)
        self._host.setEnabled(editable)
        self._port.setEnabled(editable)

    def _toggle(self) -> None:
        if self._client.state in (S.ONLINE, S.CONNECTING):
            self._client.auto_reconnect = False
            self._spawn(self._client.disconnect)
            return
        host = self._host.text().strip() or config.DEFAULT_PT_HOST
        port = self._port.value()
        self._client.auto_reconnect = self._chk_reconnect.isChecked()

        def work() -> None:
            try:
                self._client.connect(host, port)
            except PTError:
                pass

        self._spawn(work)

    def _test(self) -> None:
        def work() -> None:
            try:
                ms = self._client.ping()
                self._bus.latency.emit(ms)
                self._client.log("info", f"Ping IPC exitoso: {ms:.1f} ms")
            except PTError as exc:
                self._client.log("error", f"Ping fallido: {exc}")

        self._spawn(work)

    def _show_pta_help(self) -> None:
        pta = config.pta_file_path()
        # Limpiar copias residuales en ~/pt/extensions o /opt/pt/extensions que bloquean QFile::copy en Packet Tracer
        for ext_dir in (Path.home() / "pt" / "extensions", Path("/opt/pt/extensions")):
            stale = ext_dir / "pt-mcp-bridge.pta"
            try:
                if stale.exists() and stale.resolve() != pta.resolve():
                    stale.unlink()
            except OSError:
                pass

        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(str(pta))

        QMessageBox.information(
            self,
            "Registro único de permisos ExApp en Packet Tracer",
            "Para que Packet Tracer autorice crear equipos, conectar cables y usar la CLI:\n\n"
            "1. En Cisco Packet Tracer abre: Extensions → IPC → Configure Apps...\n"
            "2. Si ya aparece 'PT-MCP-Bridge' en la lista, selecciónalo y pulsa 'Remove'.\n"
            "3. Pulsa 'Add...' y pega la ruta (ya fue copiada a tu portapapeles):\n"
            f"   {pta}\n"
            "4. Pulsa 'Ok' y vuelve a conectar.\n\n"
            "Nota: Si aparece 'Error Importing App Meta File', ejecuta una vez en terminal:\n"
            "sudo chmod -R a+rwX /opt/pt/extensions && sudo rm -f /opt/pt/extensions/pt-mcp-bridge.pta",
        )

    @staticmethod
    def _spawn(fn) -> None:
        threading.Thread(target=fn, daemon=True).start()

    def closeEvent(self, event) -> None:
        self._client.auto_reconnect = False
        self._client.disconnect(quiet=True)
        super().closeEvent(event)


def run_gui(mcp_port: int = config.DEFAULT_MCP_PORT) -> int:
    app = QApplication(sys.argv)
    window = MainWindow(mcp_port)
    window.show()
    return app.exec()

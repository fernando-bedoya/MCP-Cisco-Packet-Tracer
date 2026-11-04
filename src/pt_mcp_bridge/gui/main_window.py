"""Ventana principal PyQt6 de TraceLink con identidad visual de Caldas, Colombia."""
from __future__ import annotations

import sys
import threading

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
        self._btn_nav_settings = QPushButton("  Ajustes")
        self._btn_nav_about = QPushButton("  Acerca de")

        self._nav_buttons = [
            (self._btn_nav_home, icons.HOME_SVG, 0),
            (self._btn_nav_settings, icons.SETTINGS_SVG, 1),
            (self._btn_nav_about, icons.INFO_SVG, 2),
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

        self._btn_test = QPushButton("Ping IPC")
        self._btn_test.setObjectName("smallActionBtn")
        self._btn_test.setCursor(Qt.CursorShape.PointingHandCursor)

        self._btn_pta = QPushButton("Permisos .pta")
        self._btn_pta.setObjectName("smallActionBtn")
        self._btn_pta.setCursor(Qt.CursorShape.PointingHandCursor)

        console_hdr.addWidget(lbl_reg)
        console_hdr.addStretch()
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
        self._btn_test.clicked.connect(self._test)
        self._btn_pta.clicked.connect(self._show_pta_help)
        self._btn_copy.clicked.connect(self._copy_mcp_url)
        return page

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
        QMessageBox.information(
            self,
            "Registro único de permisos ExApp en Packet Tracer",
            "Para que Packet Tracer autorice crear equipos, conectar cables y usar la CLI:\n\n"
            "1. En Cisco Packet Tracer abre: Extensions → IPC → Configure Apps...\n"
            "2. Pulsa 'Add...' y selecciona:\n"
            f"   {pta}\n"
            "3. Pulsa 'Ok' y vuelve a conectar.\n\n"
            "Nota: Cierra Packet Tracer (File → Exit) una vez para guardar el registro.",
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

"""Ventana principal PyQt6. Solo presentación: la lógica vive en ipc/ y service."""
from __future__ import annotations

import html
import sys
import threading
import time

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from pt_mcp_bridge import config
from pt_mcp_bridge.ipc import ClientEvents, ConnectionState, PTClient, PTError
from pt_mcp_bridge.mcp_server import McpServerThread
from pt_mcp_bridge.service import PacketTracerService

S = ConnectionState
LOG_COLORS = {"info": "#9aa0a6", "tx": "#4fc3f7", "rx": "#81c784", "mcp": "#ffb74d",
              "warn": "#fff176", "error": "#e57373"}
LOG_TAGS = {"tx": "→ PT", "rx": "← PT", "mcp": "MCP", "info": "INFO", "warn": "WARN", "error": "ERR"}
STATE_UI = {S.DISCONNECTED: ("#757575", "Desconectado"), S.CONNECTING: ("#fbc02d", "Conectando…"),
            S.ONLINE: ("#43a047", "En línea"), S.ERROR: ("#e53935", "Error")}


class _Bus(QObject):
    """Puente hilo→GUI (las señales Qt son thread-safe)."""
    log = pyqtSignal(str, str)
    state = pyqtSignal(str)


class MainWindow(QMainWindow):
    def __init__(self, mcp_port: int) -> None:
        super().__init__()
        self.setWindowTitle("PT-MCP-Bridge")
        self.resize(900, 560)

        self._bus = _Bus()
        self._client = PTClient(ClientEvents(
            on_log=self._bus.log.emit, on_state=lambda s: self._bus.state.emit(s.value)))
        self._client.auto_reconnect = True
        self._bus.log.connect(self._append_log)
        self._bus.state.connect(lambda v: self._set_state(S(v)))

        self._build_ui(mcp_port)
        self._set_state(S.DISCONNECTED)
        McpServerThread(PacketTracerService(self._client), config.DEFAULT_MCP_HOST, mcp_port).start()

    def _build_ui(self, mcp_port: int) -> None:
        self._host = QLineEdit(config.DEFAULT_PT_HOST)
        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(config.DEFAULT_PT_PORT)
        self._btn = QPushButton()
        self._btn_test = QPushButton("Test IPC")
        self._btn_pta = QPushButton("Permisos ExApp (.pta)")
        self._led, self._lbl = QLabel("●"), QLabel()
        self._console = QPlainTextEdit(readOnly=True)
        self._console.setFont(QFont("monospace", 9))
        self._console.setMaximumBlockCount(5000)
        self._console.setStyleSheet("background:#1e1e1e;")
        clear = QPushButton("Limpiar")
        clear.clicked.connect(self._console.clear)

        top = QHBoxLayout()
        for w in (QLabel("Host:"), self._host, QLabel("Puerto IPC:"), self._port, self._btn,
                  self._btn_test, self._btn_pta, self._led, self._lbl):
            top.addWidget(w)
        top.addStretch()
        top.addWidget(clear)
        root = QVBoxLayout()
        root.addLayout(top)
        root.addWidget(self._console)
        central = QWidget()
        central.setLayout(root)
        self.setCentralWidget(central)
        self.statusBar().showMessage(f"MCP: http://{config.DEFAULT_MCP_HOST}:{mcp_port}/mcp")

        self._btn.clicked.connect(self._toggle)
        self._btn_test.clicked.connect(self._test)
        self._btn_pta.clicked.connect(self._show_pta_help)

    # -- slots ---------------------------------------------------------
    def _append_log(self, level: str, msg: str) -> None:
        color = LOG_COLORS.get(level, "#ddd")
        text = html.escape(msg).replace("\n", "<br>")
        self._console.appendHtml(
            f'<span style="color:{color}">[{time.strftime("%H:%M:%S")}] '
            f'<b>{LOG_TAGS.get(level, level)}</b> {text}</span>')
        self._console.moveCursor(QTextCursor.MoveOperation.End)

    def _set_state(self, state: ConnectionState) -> None:
        color, text = STATE_UI[state]
        self._led.setStyleSheet(f"color:{color}; font-size:20px;")
        self._lbl.setText(text)
        self._btn.setEnabled(state is not S.CONNECTING)
        self._btn_test.setEnabled(state is S.ONLINE)
        self._btn.setText("Desconectar" if state in (S.ONLINE, S.CONNECTING) else "Conectar a Cisco PT")
        editable = state in (S.DISCONNECTED, S.ERROR)
        self._host.setEnabled(editable)
        self._port.setEnabled(editable)

    def _toggle(self) -> None:
        if self._client.state in (S.ONLINE, S.CONNECTING):
            self._client.auto_reconnect = False
            self._spawn(self._client.disconnect)
            return
        host, port = self._host.text().strip() or config.DEFAULT_PT_HOST, self._port.value()
        self._client.auto_reconnect = True

        def work() -> None:
            try:
                self._client.connect(host, port)
            except PTError:
                pass  # ya registrado en el log
        self._spawn(work)

    def _test(self) -> None:
        def work() -> None:
            try:
                self._client.log("info", f"Test OK: PT respondió en {self._client.ping():.1f} ms")
            except PTError as exc:
                self._client.log("error", f"Test fallido: {exc}")
        self._spawn(work)

    def _show_pta_help(self) -> None:
        pta = config.pta_file_path()
        QMessageBox.information(
            self,
            "Registro único de permisos ExApp en Packet Tracer",
            "Para que Packet Tracer autorice agregar routers, conectar cables y usar la CLI "
            "(privilegios CHANGE_NETWORK_INFO / GET_NETWORK_INFO), registra una sola vez el "
            "archivo firmado que ya está en tu carpeta:\n\n"
            "1. En Cisco Packet Tracer abre: Extensions → IPC → Configure Apps...\n"
            "2. Pulsa el botón 'Add...' y selecciona:\n"
            f"   {pta}\n"
            "3. Pulsa 'Ok' y vuelve a pulsar 'Conectar a Cisco PT'.\n\n"
            "Nota: Cierra Packet Tracer normalmente (File → Exit) una vez para que guarde el registro.",
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

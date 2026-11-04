"""Tema visual sobrio inspirado en Caldas, Colombia (paleta carbón #0B0B0B / #151515 / #70B77E)."""
from __future__ import annotations

import html
import sys
import time
from pathlib import Path

from pt_mcp_bridge.ipc import ConnectionState

S = ConnectionState

APP_TITLE = "El Arriero MCP"
APP_SUBTITLE = "MCP Bridge · Universidad de Caldas"
HERO_DESCRIPTION = "Conecta tu MCP con Cisco Packet Tracer de forma rápida y sencilla."
APP_VERSION = "v1.0.0"

# Paleta sobria sin saturación ni neón
ACCENT_GREEN = "#70B77E"
TEXT_PRIMARY = "#E5E5E5"
TEXT_SECONDARY = "#929292"

LOG_COLORS: dict[str, str] = {
    "info": "#70B77E",
    "tx": "#A8C5B0",
    "rx": "#70B77E",
    "mcp": "#C8B88A",
    "warn": "#D4A359",
    "error": "#D16D6A",
}

LOG_TAGS: dict[str, str] = {
    "tx": "TX",
    "rx": "RX",
    "mcp": "MCP",
    "info": "INFO",
    "warn": "WARN",
    "error": "ERR",
}

# (dot_color, label)
STATE_SIDEBAR: dict[ConnectionState, tuple[str, str]] = {
    S.DISCONNECTED: ("#70B77E", "Listo"),
    S.CONNECTING: ("#D4A359", "Conectando…"),
    S.ONLINE: ("#70B77E", "En línea"),
    S.ERROR: ("#D16D6A", "Error"),
}


def asset_path(filename: str) -> Path:
    """Localiza un recurso gráfico tanto en código fuente como en binario PyInstaller o .deb."""
    candidates = [
        Path(__file__).resolve().parent / "assets" / filename,
    ]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.insert(0, Path(meipass) / "pt_mcp_bridge" / "gui" / "assets" / filename)
    for path in candidates:
        if path.is_file():
            return path
    return candidates[-1]


STYLESHEET = """
QMainWindow {
    background-color: #0B0B0B;
    color: #E5E5E5;
    font-family: "Inter", "Segoe UI", "Ubuntu", "Cantarell", sans-serif;
    font-size: 13px;
}

QLabel {
    background: transparent;
    color: #E5E5E5;
}

QLabel#topTitle {
    color: #E5E5E5;
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 0.2px;
}

QLabel#topSubtitle {
    color: #929292;
    font-size: 13px;
    font-weight: 400;
}

QLabel#heroTitle {
    color: #E5E5E5;
    font-size: 27px;
    font-weight: 700;
    letter-spacing: 0.2px;
}

QLabel#heroDesc {
    color: #B0B0B0;
    font-size: 13px;
    font-weight: 400;
}

QLabel#fieldLabel {
    color: #B8B8B8;
    font-size: 12px;
    font-weight: 500;
}

QLabel#consoleHeader {
    color: #929292;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.4px;
}

QLabel#footerText {
    color: #929292;
    font-size: 12px;
}

QLabel#sidebarStatus {
    color: #B8B8B8;
    font-size: 12px;
    font-weight: 500;
}

QLabel#sidebarVersion {
    color: #6E6E6E;
    font-size: 11px;
}

QFrame#topSeparator, QFrame#panelDivider {
    background-color: #303030;
}

QFrame#connectionPanel {
    background-color: rgba(21, 21, 21, 155);
    border: 1px solid #303030;
    border-radius: 8px;
}

QFrame#consolePanel {
    background-color: rgba(11, 11, 11, 145);
    border: 1px solid #303030;
    border-radius: 8px;
}

QFrame#infoCard {
    background-color: rgba(21, 21, 21, 215);
    border: 1px solid #303030;
    border-radius: 8px;
}

QPushButton#navBtn {
    background-color: transparent;
    color: #929292;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 9px 12px;
    text-align: left;
    font-size: 13px;
    font-weight: 500;
}

QPushButton#navBtn:hover {
    background-color: rgba(28, 28, 28, 160);
    color: #E5E5E5;
}

QPushButton#navBtnActive {
    background-color: rgba(28, 28, 28, 220);
    color: #E5E5E5;
    border: 1px solid #303030;
    border-radius: 6px;
    padding: 9px 12px;
    text-align: left;
    font-size: 13px;
    font-weight: 600;
}

QLineEdit, QSpinBox {
    background-color: rgba(11, 11, 11, 235);
    color: #E5E5E5;
    border: 1px solid #303030;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 15px;
    selection-background-color: #303030;
}

QLineEdit:focus, QSpinBox:focus {
    border: 1px solid #525252;
}

QLineEdit:disabled, QSpinBox:disabled {
    color: #6E6E6E;
    background-color: rgba(15, 15, 15, 180);
    border-color: #242424;
}

QSpinBox::up-button, QSpinBox::down-button {
    width: 0px;
    border: none;
}

QPushButton#connectBtn {
    background-color: rgba(28, 28, 28, 215);
    color: #E5E5E5;
    border: 1px solid #484848;
    border-radius: 6px;
    padding: 9px 20px;
    font-size: 13px;
    font-weight: 500;
}

QPushButton#connectBtn:hover {
    background-color: rgba(38, 38, 38, 235);
    border-color: #626262;
}

QPushButton#disconnectBtn {
    background-color: rgba(24, 34, 26, 225);
    color: #E5E5E5;
    border: 1px solid #70B77E;
    border-radius: 6px;
    padding: 9px 20px;
    font-size: 13px;
    font-weight: 500;
}

QPushButton#disconnectBtn:hover {
    background-color: rgba(32, 46, 35, 240);
}

QPushButton#clearBtn {
    background-color: rgba(28, 28, 28, 215);
    color: #E5E5E5;
    border: 1px solid #3A3A3A;
    border-radius: 6px;
    padding: 9px 16px;
    font-size: 13px;
    font-weight: 500;
}

QPushButton#clearBtn:hover {
    background-color: rgba(38, 38, 38, 235);
    border-color: #525252;
}

QPushButton#smallActionBtn {
    background-color: rgba(28, 28, 28, 190);
    color: #B8B8B8;
    border: 1px solid #303030;
    border-radius: 5px;
    padding: 3px 10px;
    font-size: 11px;
}

QPushButton#smallActionBtn:hover {
    background-color: rgba(40, 40, 40, 230);
    color: #E5E5E5;
    border-color: #454545;
}

QPushButton#smallActionBtn:disabled {
    color: #555555;
    border-color: #222222;
}

QPlainTextEdit#console {
    background: transparent;
    color: #E5E5E5;
    border: none;
    padding: 4px 8px;
    selection-background-color: #303030;
}

QMessageBox {
    background-color: #151515;
    color: #E5E5E5;
}
"""


def format_log_html(level: str, msg: str) -> str:
    """Formatea cada línea de consola al estilo exacto de la referencia:
    `● [15:54:08] [INFO] Servidor MCP en http://127.0.0.1:8765/mcp`
    """
    color = LOG_COLORS.get(level, ACCENT_GREEN)
    tag = LOG_TAGS.get(level, level.upper())
    ts = time.strftime("%H:%M:%S")
    safe_msg = html.escape(msg).replace("\n", "<br>")
    return (
        f'<span style="color:{color};">●</span> '
        f'<span style="color:#929292;">[{ts}]</span> '
        f'<span style="color:{color}; font-weight:600;">[{tag}]</span> '
        f'<span style="color:#E5E5E5;">{safe_msg}</span>'
    )

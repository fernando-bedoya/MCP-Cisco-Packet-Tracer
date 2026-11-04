"""Iconos vectoriales lineales (SVG -> QIcon / QPixmap) fieles al diseño de referencia."""
from __future__ import annotations

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QIcon, QImage, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer


def svg_pixmap(svg: str, width: int, height: int) -> QPixmap:
    """Renderiza una cadena SVG en un QPixmap con antialiasing."""
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    img = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter)
    painter.end()
    return QPixmap.fromImage(img)


def svg_icon(svg: str, size: int = 20) -> QIcon:
    return QIcon(svg_pixmap(svg, size, size))


# 1. Logo superior de montañas (Caldas)
LOGO_MOUNTAINS_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 28" fill="none">
  <path d="M3 25 L17 6 L27 19 L34 10 L45 25 Z" stroke="#E5E5E5" stroke-width="2.2" stroke-linejoin="round"/>
  <path d="M12 13 L17 17 L22 14" stroke="#E5E5E5" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M30 16 L34 19 L38 16" stroke="#E5E5E5" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""

# 2. Icono Hero: Laptop con red de nodos
HERO_LAPTOP_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 68 50" fill="none">
  <rect x="10" y="5" width="48" height="32" rx="2.5" stroke="#E5E5E5" stroke-width="2.5"/>
  <path d="M3 41 H65" stroke="#E5E5E5" stroke-width="2.8" stroke-linecap="round"/>
  <path d="M6 45 H62" stroke="#E5E5E5" stroke-width="2.0" stroke-linecap="round"/>
  <circle cx="34" cy="14" r="2.3" fill="#E5E5E5"/>
  <circle cx="26" cy="25" r="2.3" fill="#E5E5E5"/>
  <circle cx="40" cy="24" r="2.3" fill="#E5E5E5"/>
  <path d="M34 16 L27 24 M34 16 L39 23 M28 25 L38 24" stroke="#E5E5E5" stroke-width="1.7" stroke-linecap="round"/>
</svg>
"""

# 3. Navegación lateral: Inicio, Ajustes, Acerca de
HOME_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <path d="M3 10.5 L12 3 L21 10.5 V20 A1 1 0 0 1 20 21 H14.5 V14.5 H9.5 V21 H4 A1 1 0 0 1 3 20 Z"
        fill="{color}" stroke="{color}" stroke-width="1.5" stroke-linejoin="round"/>
</svg>
"""

SETTINGS_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <circle cx="12" cy="12" r="3.2" stroke="{color}" stroke-width="1.8"/>
  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33
           1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06
           a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09
           A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9
           a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06
           a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9c.26.604.852.997 1.51 1H21a2 2 0 1 1 0 4h-.09
           a1.65 1.65 0 0 0-1.51 1z" stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""

INFO_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <circle cx="12" cy="12" r="9" stroke="{color}" stroke-width="1.8"/>
  <path d="M12 11 V16" stroke="{color}" stroke-width="1.8" stroke-linecap="round"/>
  <circle cx="12" cy="7.5" r="1.1" fill="{color}"/>
</svg>
"""

# 4. Iconos de campos: Host (base de datos/servidor) y Puerto IPC (conector)
HOST_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="none">
  <ellipse cx="10" cy="4.5" rx="6.5" ry="2.5" stroke="#B5B5B5" stroke-width="1.4"/>
  <path d="M3.5 4.5 V15.5 C3.5 16.9 6.4 18 10 18 C13.6 18 16.5 16.9 16.5 15.5 V4.5" stroke="#B5B5B5" stroke-width="1.4"/>
  <path d="M3.5 10 C3.5 11.4 6.4 12.5 10 12.5 C13.6 12.5 16.5 11.4 16.5 10" stroke="#B5B5B5" stroke-width="1.4"/>
</svg>
"""

PLUG_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="none">
  <path d="M7 2.5 V6.5 M13 2.5 V6.5" stroke="#B5B5B5" stroke-width="1.5" stroke-linecap="round"/>
  <path d="M4.5 6.5 H15.5 V10.5 C15.5 13.5 13 15.5 10 15.5 C7 15.5 4.5 13.5 4.5 10.5 Z" stroke="#B5B5B5" stroke-width="1.4" stroke-linejoin="round"/>
  <path d="M10 15.5 V18.5" stroke="#B5B5B5" stroke-width="1.5" stroke-linecap="round"/>
</svg>
"""

# 5. Iconos de botones: Play, Stop y Escoba (Limpiar)
PLAY_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="none">
  <path d="M5 3.8 L16 10 L5 16.2 Z" fill="#E5E5E5" stroke="#E5E5E5" stroke-width="1.2" stroke-linejoin="round"/>
</svg>
"""

STOP_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="none">
  <rect x="4.5" y="4.5" width="11" height="11" rx="1.8" fill="#70B77E"/>
</svg>
"""

BROOM_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 22 22" fill="none">
  <path d="M18.5 3.5 L11.5 10.5" stroke="#E5E5E5" stroke-width="1.9" stroke-linecap="round"/>
  <path d="M9.2 8.8 L13.2 12.8 L8.2 18.5 C6.2 17.5 4.5 15.8 3.5 13.8 Z"
        fill="#E5E5E5" stroke="#E5E5E5" stroke-width="1.2" stroke-linejoin="round"/>
  <path d="M5.5 15.5 L7.5 13.5 M7 17 L9 15" stroke="#1C1C1C" stroke-width="1.2" stroke-linecap="round"/>
</svg>
"""

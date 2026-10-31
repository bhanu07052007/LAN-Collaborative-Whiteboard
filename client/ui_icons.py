"""
UI Icons Generator for Collaborative Whiteboard.
Renders crisp vector QIcons using PySide6 QPainter and QPainterPath.
Ensures zero external asset dependencies, zero network requests, and razor-sharp
rendering across all display scaling settings and resolutions.
"""

from typing import Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap


def _create_base_pixmap(size: int = 24) -> Tuple[QPixmap, QPainter]:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    return pixmap, painter


def get_app_icon(size: int = 48) -> QIcon:
    pixmap, p = _create_base_pixmap(size)
    # Rounded gradient-style background
    rect = QRectF(2, 2, size - 4, size - 4)
    p.setPen(QPen(QColor("#7C3AED"), 2))
    p.setBrush(QBrush(QColor("#594BFA")))
    p.drawRoundedRect(rect, 10, 10)

    # Stylized whiteboard easel / pen symbol
    p.setPen(QPen(QColor("#FFFFFF"), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    # Frame
    p.drawLine(QPointF(size * 0.25, size * 0.3), QPointF(size * 0.75, size * 0.3))
    p.drawLine(QPointF(size * 0.25, size * 0.3), QPointF(size * 0.25, size * 0.7))
    p.drawLine(QPointF(size * 0.75, size * 0.3), QPointF(size * 0.75, size * 0.7))
    p.drawLine(QPointF(size * 0.25, size * 0.7), QPointF(size * 0.75, size * 0.7))
    # Diagonal pen crossing
    p.setPen(QPen(QColor("#38BDF8"), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(size * 0.4, size * 0.6), QPointF(size * 0.65, size * 0.35))
    p.end()
    return QIcon(pixmap)


def _render_tool_pixmap(tool_name: str, color: str = "#172B4D", size: int = 24) -> QPixmap:
    pixmap, p = _create_base_pixmap(size)
    c = QColor(color)
    pen = QPen(c, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    name = tool_name.lower().replace(" ", "_")

    if name == "select":
        # Arrow cursor pointer
        path = QPainterPath()
        path.moveTo(size * 0.25, size * 0.18)
        path.lineTo(size * 0.25, size * 0.78)
        path.lineTo(size * 0.45, size * 0.60)
        path.lineTo(size * 0.68, size * 0.82)
        path.lineTo(size * 0.78, size * 0.72)
        path.lineTo(size * 0.55, size * 0.50)
        path.lineTo(size * 0.78, size * 0.48)
        path.closeSubpath()
        p.setBrush(QBrush(c))
        p.drawPath(path)

    elif name == "pen":
        # Pencil angled at 45 deg
        path = QPainterPath()
        path.moveTo(size * 0.72, size * 0.22)
        path.lineTo(size * 0.82, size * 0.32)
        path.lineTo(size * 0.38, size * 0.76)
        path.lineTo(size * 0.22, size * 0.82)
        path.lineTo(size * 0.28, size * 0.66)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(size * 0.64, size * 0.30), QPointF(size * 0.74, size * 0.40))

    elif name == "eraser":
        # Angled eraser
        path = QPainterPath()
        path.moveTo(size * 0.35, size * 0.25)
        path.lineTo(size * 0.75, size * 0.25)
        path.lineTo(size * 0.65, size * 0.78)
        path.lineTo(size * 0.25, size * 0.78)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(size * 0.30, size * 0.52), QPointF(size * 0.70, size * 0.52))

    elif name == "line":
        # Diagonal straight line with terminal dots
        p.drawLine(QPointF(size * 0.22, size * 0.78), QPointF(size * 0.78, size * 0.22))
        p.setBrush(QBrush(c))
        p.drawEllipse(QPointF(size * 0.22, size * 0.78), 2.2, 2.2)
        p.drawEllipse(QPointF(size * 0.78, size * 0.22), 2.2, 2.2)

    elif name == "rectangle":
        p.drawRoundedRect(QRectF(size * 0.2, size * 0.22, size * 0.6, size * 0.56), 2, 2)

    elif name == "circle":
        p.drawEllipse(QRectF(size * 0.2, size * 0.2, size * 0.6, size * 0.6))

    elif name == "text":
        p.setFont(QFont("Segoe UI", int(size * 0.62), QFont.Weight.Bold))
        p.setPen(c)
        p.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "T")

    elif name in ("sticky_notes", "sticky"):
        # Sticky note with folded bottom-right corner
        path = QPainterPath()
        path.moveTo(size * 0.2, size * 0.2)
        path.lineTo(size * 0.8, size * 0.2)
        path.lineTo(size * 0.8, size * 0.62)
        path.lineTo(size * 0.62, size * 0.8)
        path.lineTo(size * 0.2, size * 0.8)
        path.closeSubpath()
        p.drawPath(path)
        # Folded triangle
        p.drawLine(QPointF(size * 0.62, size * 0.62), QPointF(size * 0.8, size * 0.62))
        p.drawLine(QPointF(size * 0.62, size * 0.62), QPointF(size * 0.62, size * 0.8))

    elif name == "laser_pen":
        # Magic wand / laser beam
        p.drawLine(QPointF(size * 0.25, size * 0.75), QPointF(size * 0.65, size * 0.35))
        p.setBrush(QBrush(c))
        p.drawEllipse(QPointF(size * 0.75, size * 0.25), 3, 3)

    elif name == "laser_pointer":
        # Target crosshairs
        p.drawEllipse(QRectF(size * 0.25, size * 0.25, size * 0.5, size * 0.5))
        p.drawLine(QPointF(size * 0.5, size * 0.12), QPointF(size * 0.5, size * 0.3))
        p.drawLine(QPointF(size * 0.5, size * 0.7), QPointF(size * 0.5, size * 0.88))
        p.drawLine(QPointF(size * 0.12, size * 0.5), QPointF(size * 0.3, size * 0.5))
        p.drawLine(QPointF(size * 0.7, size * 0.5), QPointF(size * 0.88, size * 0.5))

    elif name == "undo":
        # Curved counter-clockwise arrow
        path = QPainterPath()
        path.moveTo(size * 0.75, size * 0.65)
        path.cubicTo(size * 0.75, size * 0.35, size * 0.45, size * 0.35, size * 0.32, size * 0.45)
        p.drawPath(path)
        # Arrowhead
        p.drawLine(QPointF(size * 0.32, size * 0.45), QPointF(size * 0.45, size * 0.35))
        p.drawLine(QPointF(size * 0.32, size * 0.45), QPointF(size * 0.42, size * 0.58))

    elif name == "redo":
        # Curved clockwise arrow
        path = QPainterPath()
        path.moveTo(size * 0.25, size * 0.65)
        path.cubicTo(size * 0.25, size * 0.35, size * 0.55, size * 0.35, size * 0.68, size * 0.45)
        p.drawPath(path)
        # Arrowhead
        p.drawLine(QPointF(size * 0.68, size * 0.45), QPointF(size * 0.55, size * 0.35))
        p.drawLine(QPointF(size * 0.68, size * 0.45), QPointF(size * 0.58, size * 0.58))

    elif name in ("clear", "clear_canvas", "delete", "trash"):
        # Trash bin
        p.drawLine(QPointF(size * 0.25, size * 0.35), QPointF(size * 0.75, size * 0.35))
        p.drawLine(QPointF(size * 0.4, size * 0.25), QPointF(size * 0.6, size * 0.25))
        path = QPainterPath()
        path.moveTo(size * 0.3, size * 0.35)
        path.lineTo(size * 0.35, size * 0.8)
        path.lineTo(size * 0.65, size * 0.8)
        path.lineTo(size * 0.7, size * 0.35)
        p.drawPath(path)

    elif name in ("export", "export_png"):
        # Image / download frame
        p.drawRoundedRect(QRectF(size * 0.2, size * 0.2, size * 0.6, size * 0.6), 2, 2)
        p.drawLine(QPointF(size * 0.5, size * 0.32), QPointF(size * 0.5, size * 0.58))
        p.drawLine(QPointF(size * 0.38, size * 0.48), QPointF(size * 0.5, size * 0.58))
        p.drawLine(QPointF(size * 0.62, size * 0.48), QPointF(size * 0.5, size * 0.58))

    elif name == "history":
        # Clock / timeline
        p.drawEllipse(QRectF(size * 0.2, size * 0.2, size * 0.6, size * 0.6))
        p.drawLine(QPointF(size * 0.5, size * 0.5), QPointF(size * 0.5, size * 0.32))
        p.drawLine(QPointF(size * 0.5, size * 0.5), QPointF(size * 0.65, size * 0.5))

    elif name in ("file_sharing", "share_file", "file"):
        # Document sheet
        path = QPainterPath()
        path.moveTo(size * 0.28, size * 0.2)
        path.lineTo(size * 0.62, size * 0.2)
        path.lineTo(size * 0.75, size * 0.33)
        path.lineTo(size * 0.75, size * 0.8)
        path.lineTo(size * 0.28, size * 0.8)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(size * 0.38, size * 0.45), QPointF(size * 0.65, size * 0.45))
        p.drawLine(QPointF(size * 0.38, size * 0.58), QPointF(size * 0.65, size * 0.58))

    elif name == "zoom_in":
        p.drawLine(QPointF(size * 0.5, size * 0.28), QPointF(size * 0.5, size * 0.72))
        p.drawLine(QPointF(size * 0.28, size * 0.5), QPointF(size * 0.72, size * 0.5))

    elif name == "zoom_out":
        p.drawLine(QPointF(size * 0.28, size * 0.5), QPointF(size * 0.72, size * 0.5))

    elif name == "fit_screen":
        # 4 corner brackets
        s = size
        p.drawLine(QPointF(s * 0.25, s * 0.38), QPointF(s * 0.25, s * 0.25))
        p.drawLine(QPointF(s * 0.25, s * 0.25), QPointF(s * 0.38, s * 0.25))
        p.drawLine(QPointF(s * 0.62, s * 0.25), QPointF(s * 0.75, s * 0.25))
        p.drawLine(QPointF(s * 0.75, s * 0.25), QPointF(s * 0.75, s * 0.38))
        p.drawLine(QPointF(s * 0.25, s * 0.62), QPointF(s * 0.25, s * 0.75))
        p.drawLine(QPointF(s * 0.25, s * 0.75), QPointF(s * 0.38, s * 0.75))
        p.drawLine(QPointF(s * 0.62, s * 0.75), QPointF(s * 0.75, s * 0.75))
        p.drawLine(QPointF(s * 0.75, s * 0.75), QPointF(s * 0.75, s * 0.62))

    elif name in ("chat", "group_chat"):
        path = QPainterPath()
        path.moveTo(size * 0.2, size * 0.25)
        path.lineTo(size * 0.8, size * 0.25)
        path.lineTo(size * 0.8, size * 0.68)
        path.lineTo(size * 0.45, size * 0.68)
        path.lineTo(size * 0.3, size * 0.82)
        path.lineTo(size * 0.3, size * 0.68)
        path.lineTo(size * 0.2, size * 0.68)
        path.closeSubpath()
        p.drawPath(path)

    elif name in ("participants", "users"):
        # Two stylized people
        p.drawEllipse(QRectF(size * 0.25, size * 0.22, size * 0.26, size * 0.26))
        path1 = QPainterPath()
        path1.moveTo(size * 0.15, size * 0.75)
        path1.cubicTo(size * 0.15, size * 0.55, size * 0.6, size * 0.55, size * 0.6, size * 0.75)
        p.drawPath(path1)

    elif name == "send":
        # Paper airplane
        path = QPainterPath()
        path.moveTo(size * 0.2, size * 0.5)
        path.lineTo(size * 0.8, size * 0.2)
        path.lineTo(size * 0.5, size * 0.8)
        path.lineTo(size * 0.42, size * 0.58)
        path.closeSubpath()
        p.setBrush(QBrush(c))
        p.drawPath(path)

    elif name == "end_meeting":
        # Phone end handset / stop
        rect = QRectF(size * 0.25, size * 0.38, size * 0.5, size * 0.24)
        p.drawRoundedRect(rect, 3, 3)

    elif name == "leave":
        # Door with arrow
        p.drawRect(QRectF(size * 0.2, size * 0.2, size * 0.35, size * 0.6))
        p.drawLine(QPointF(size * 0.45, size * 0.5), QPointF(size * 0.8, size * 0.5))
        p.drawLine(QPointF(size * 0.68, size * 0.38), QPointF(size * 0.8, size * 0.5))
        p.drawLine(QPointF(size * 0.68, size * 0.62), QPointF(size * 0.8, size * 0.5))

    p.end()
    return pixmap


def get_tool_icon(tool_name: str, color: str = "#172B4D", size: int = 24) -> QIcon:
    """Returns a crisp vector QIcon for the requested tool with active state support."""
    icon = QIcon()
    off_pix = _render_tool_pixmap(tool_name, color, size)
    icon.addPixmap(off_pix, QIcon.Mode.Normal, QIcon.State.Off)
    on_pix = _render_tool_pixmap(tool_name, "#FFFFFF", size)
    icon.addPixmap(on_pix, QIcon.Mode.Normal, QIcon.State.On)
    return icon

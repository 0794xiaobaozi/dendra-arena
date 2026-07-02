"""
应用图标：程序化生成 LiveFreeze logo，用于窗口左上角与任务栏。
"""
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QPen, QBrush
from PySide6.QtCore import Qt, QRect, QSize


def create_app_icon() -> QIcon:
    """生成带 LF 标识的方形 logo，多尺寸供标题栏/任务栏使用。"""
    icon = QIcon()
    for size in (16, 32, 48, 64, 128, 256):
        icon.addPixmap(_draw_logo_pixmap(size), QIcon.Mode.Normal, QIcon.State.Off)
    return icon


def _draw_logo_pixmap(size: int) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    margin = max(1, size // 8)
    rect = pix.rect().adjusted(margin, margin, -margin, -margin)
    # 背景圆角矩形：深色
    painter.setPen(QPen(QColor(40, 44, 52), 0))
    painter.setBrush(QBrush(QColor(40, 44, 52)))
    painter.drawRoundedRect(rect, size // 6, size // 6)
    # 文字 "LF"
    painter.setPen(QColor(120, 200, 180))
    font = QFont("Segoe UI", max(8, size // 4), QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "LF")
    painter.end()
    return pix

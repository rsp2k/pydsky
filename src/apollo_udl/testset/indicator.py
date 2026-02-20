"""Hardware-style illuminated indicator lamp widget."""

import enum

from qtpy.QtWidgets import QWidget
from qtpy.QtGui import QPainter, QRadialGradient, QColor, QBrush
from qtpy.QtCore import Qt, QPointF, Signal


class IndicatorColor(enum.Enum):
    """Standard indicator lamp colors matching Apollo MOCR palette."""

    GREEN = "#28C83C"
    RED = "#DC3232"
    AMBER = "#FFC828"
    BLUE = "#5588AA"
    GOLD = "#CC9933"


OFF_COLOR = QColor("#3C3732")
BEZEL_COLOR = QColor("#1a1a1e")


class IndicatorLight(QWidget):
    """Circular illuminated indicator with glow effect.

    Renders as a hardware-style lamp: when lit, a radial gradient fills
    the lamp with a soft outer glow.  When off, a dark neutral tone.
    """

    clicked = Signal()

    def __init__(self, parent=None, *, color=IndicatorColor.GREEN, diameter=16):
        super().__init__(parent)
        self._color = color
        self._on = False
        self._diameter = diameter
        margin = max(diameter // 3, 4)
        self.setFixedSize(diameter + margin * 2, diameter + margin * 2)

    def set_on(self, on):
        if on != self._on:
            self._on = on
            self.update()

    def set_color(self, color):
        if color != self._color:
            self._color = color
            self.update()

    @property
    def is_on(self):
        return self._on

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx = self.width() / 2.0
        cy = self.height() / 2.0
        center = QPointF(cx, cy)
        r = self._diameter / 2.0

        if self._on:
            color = QColor(self._color.value)

            # Outer glow
            glow = QRadialGradient(center, r * 1.6)
            glow.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), 50))
            glow.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
            p.setBrush(QBrush(glow))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(center, r * 1.6, r * 1.6)

            # Lit lamp body
            highlight = QPointF(cx - r * 0.25, cy - r * 0.25)
            lamp = QRadialGradient(highlight, r * 1.1)
            lamp.setColorAt(0.0, color.lighter(160))
            lamp.setColorAt(0.45, color)
            lamp.setColorAt(1.0, color.darker(140))
            p.setBrush(QBrush(lamp))
        else:
            # Unlit lamp body
            highlight = QPointF(cx - r * 0.2, cy - r * 0.2)
            lamp = QRadialGradient(highlight, r * 1.1)
            lamp.setColorAt(0.0, OFF_COLOR.lighter(130))
            lamp.setColorAt(1.0, OFF_COLOR.darker(130))
            p.setBrush(QBrush(lamp))

        # Bezel ring
        p.setPen(BEZEL_COLOR)
        p.drawEllipse(center, r, r)

        # Specular highlight (lit only)
        if self._on:
            spec_center = QPointF(cx - r * 0.3, cy - r * 0.35)
            spec = QRadialGradient(spec_center, r * 0.35)
            spec.setColorAt(0.0, QColor(255, 255, 255, 90))
            spec.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setBrush(QBrush(spec))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(spec_center, r * 0.35, r * 0.35)

    def mousePressEvent(self, event):
        self.clicked.emit()

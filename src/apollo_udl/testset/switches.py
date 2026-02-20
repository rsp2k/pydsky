"""Hardware-style rotary selector switch widget."""

import math

from qtpy.QtWidgets import QWidget
from qtpy.QtGui import QPainter, QPen, QRadialGradient, QColor, QBrush, QFont
from qtpy.QtCore import Qt, QPointF, QRectF, Signal


class RotaryKnob(QWidget):
    """Two-or-more-position rotary selector with metallic knob rendering.

    Positions are distributed across a 120-degree arc at the top of
    the knob.  Click anywhere on the widget to advance to the next
    position.  The ``rotated`` signal emits the new position index.
    """

    rotated = Signal(int)

    def __init__(self, parent=None, *, positions=None, diameter=64):
        super().__init__(parent)
        self._positions = positions or ["A", "B"]
        self._current = 0
        self._diameter = diameter
        # Widget width accommodates labels on both sides
        self.setFixedSize(diameter + 80, diameter + 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    @property
    def position(self):
        return self._current

    def set_position(self, idx):
        if 0 <= idx < len(self._positions) and idx != self._current:
            self._current = idx
            self.update()
            self.rotated.emit(idx)

    def mousePressEvent(self, event):
        nxt = (self._current + 1) % len(self._positions)
        self.set_position(nxt)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0 - 2
        r = self._diameter / 2.0

        n = len(self._positions)
        angles = self._position_angles(n)

        # Base plate (recessed ring)
        p.setBrush(QColor("#1a1a1e"))
        p.setPen(QColor("#444"))
        p.drawEllipse(QPointF(cx, cy), r + 5, r + 5)

        # Knob body (metallic gradient)
        knob_hl = QPointF(cx - r * 0.15, cy - r * 0.15)
        knob_grad = QRadialGradient(knob_hl, r * 1.2)
        knob_grad.setColorAt(0.0, QColor("#606068"))
        knob_grad.setColorAt(0.4, QColor("#44444a"))
        knob_grad.setColorAt(1.0, QColor("#28282c"))
        p.setBrush(QBrush(knob_grad))
        p.setPen(QColor("#555"))
        p.drawEllipse(QPointF(cx, cy), r, r)

        # Pointer line to current position
        angle_rad = math.radians(angles[self._current])
        px = cx + (r - 7) * math.cos(angle_rad)
        py = cy - (r - 7) * math.sin(angle_rad)

        pen = QPen(QColor("#FFC828"), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(cx, cy), QPointF(px, py))

        # Pointer dot at center
        p.setBrush(QColor("#FFC828"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), 3, 3)

        # Position tick marks and labels
        label_font = QFont("monospace", 9, QFont.Weight.Bold)
        p.setFont(label_font)

        for i, label in enumerate(self._positions):
            a = math.radians(angles[i])
            # Tick mark at edge of base plate
            tx = cx + (r + 3) * math.cos(a)
            ty = cy - (r + 3) * math.sin(a)
            tick_pen = QPen(QColor("#888"), 2)
            tick_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(tick_pen)
            ex = cx + (r + 8) * math.cos(a)
            ey = cy - (r + 8) * math.sin(a)
            p.drawLine(QPointF(tx, ty), QPointF(ex, ey))

            # Label beyond tick
            lx = cx + (r + 22) * math.cos(a)
            ly = cy - (r + 22) * math.sin(a)
            rect = QRectF(lx - 20, ly - 9, 40, 18)

            if i == self._current:
                p.setPen(QColor("#FFC828"))
            else:
                p.setPen(QColor("#888"))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)

    @staticmethod
    def _position_angles(n):
        """Return angles (degrees, standard math convention) for n positions.

        Positions span a 120-degree arc centered at 90 degrees (straight up).
        For 2 positions: 150 (upper-left) and 30 (upper-right).
        """
        if n == 1:
            return [90.0]
        arc = 120.0
        start = 90.0 + arc / 2.0  # leftmost position
        step = arc / (n - 1)
        return [start - i * step for i in range(n)]

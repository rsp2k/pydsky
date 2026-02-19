from qtpy.QtWidgets import QWidget
from qtpy.QtGui import QPainter, QRadialGradient, QColor, QBrush
from qtpy.QtCore import QPointF

class Lamp(QWidget):
    def __init__(self, parent, pix, x, y, w, h, on, bulbs=0):
        super().__init__(parent)
        self._pix = pix
        self._x = x
        self._y = y
        self._w = w
        self._h = h
        self._on = on
        self._bulbs = bulbs
        self._setup_ui()
        self._flash = False

    def set_on(self, on):
        if on != self._on:
            self._on = on
            self.update()

    def set_flash(self, flash):
        if flash != self._flash:
            self._flash = flash
            if self._on:
                self.update()

    def _setup_ui(self):
        self.setFixedSize(self._w, self._h)

    def paintEvent(self, event):
        p = QPainter(self)
        if self._on and not self._flash:
            p.drawPixmap(0, 0, self._pix, self._x, self._y, self._w, self._h)
            if self._bulbs > 0:
                self._draw_bulb_hotspots(p)

    def _draw_bulb_hotspots(self, p):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cy = self._h / 2.0
        radius = self._h * 0.55
        spacing = self._w / (self._bulbs + 1)

        for i in range(self._bulbs):
            cx = spacing * (i + 1)
            gradient = QRadialGradient(QPointF(cx, cy), radius)
            gradient.setColorAt(0.0, QColor(255, 255, 255, 160))
            gradient.setColorAt(0.3, QColor(255, 255, 255, 80))
            gradient.setColorAt(0.7, QColor(255, 255, 255, 20))
            gradient.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setBrush(QBrush(gradient))
            p.setPen(QColor(0, 0, 0, 0))
            p.drawEllipse(QPointF(cx, cy), radius, radius)

"""Apollo UDL Network Relay -- Mission Control GUI panel."""

from datetime import datetime

from qtpy.QtWidgets import (
    QMainWindow,
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QTextEdit,
)
from qtpy.QtGui import QFont, QTextCursor
from qtpy.QtCore import Qt, QTimer

from ..testset.indicator import IndicatorLight, IndicatorColor
from ..testset.switches import RotaryKnob

# ── design tokens ─────────────────────────────────────────────

PANEL_BG = "#2d2d32"
FRAME_BG = "#252528"
LOG_BG = "#1a1a1e"
CM_ACCENT = "#5588AA"
LM_ACCENT = "#CC9933"
HEADER_COLOR = "#888"
DATA_COLOR = "#DDD"
DIM_COLOR = "#666"
DIVIDER_COLOR = "#444"

POLL_INTERVAL_MS = 200
MAX_LOG_LINES = 500


class RelayPanel(QMainWindow):
    """Mission Control GUI for the Apollo UDL Network Relay.

    Polls ``relay.status()`` every 200 ms and drains the event buffer
    to update vehicle indicators, ground-client lights, packet counters,
    and the activity log.
    """

    PANEL_WIDTH = 660
    PANEL_HEIGHT = 540

    def __init__(self, relay, parent=None):
        super().__init__(parent)
        self._relay = relay
        self.setWindowTitle("Apollo UDL Network Relay")
        self.setFixedSize(self.PANEL_WIDTH, self.PANEL_HEIGHT)
        self.setStyleSheet(f"QMainWindow{{background-color:{PANEL_BG};}}")

        central = QWidget()
        self.setCentralWidget(central)
        self._root = QVBoxLayout(central)
        self._root.setContentsMargins(20, 16, 20, 12)
        self._root.setSpacing(0)

        self._build_title()
        self._build_vehicle_frames()
        self._build_controls_row()
        self._build_packet_counter()
        self._build_activity_log()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_relay)
        self._timer.start(POLL_INTERVAL_MS)

    # ── title ─────────────────────────────────────────────────

    def _build_title(self):
        title = QLabel("APOLLO  UDL  NETWORK  RELAY")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color:{HEADER_COLOR}; font-size:13px; font-weight:bold;"
            "letter-spacing:4px; padding:4px 0 10px 0;"
        )
        self._root.addWidget(title)

        div = self._make_divider()
        self._root.addWidget(div)
        self._root.addSpacing(12)

    # ── vehicle status frames ─────────────────────────────────

    def _build_vehicle_frames(self):
        row = QHBoxLayout()
        row.setSpacing(16)

        self._cm_indicator = IndicatorLight(color=IndicatorColor.RED, diameter=14)
        self._cm_status_lbl = QLabel("DISCONNECTED")
        self._cm_addr_lbl = QLabel("")
        self._cm_rx_lbl = QLabel("RX: 0")
        self._cm_tx_lbl = QLabel("TX: 0")
        cm_frame = self._make_vehicle_frame(
            "CM",
            CM_ACCENT,
            self._cm_indicator,
            self._cm_status_lbl,
            self._cm_addr_lbl,
            self._cm_rx_lbl,
            self._cm_tx_lbl,
        )
        row.addWidget(cm_frame)

        self._lm_indicator = IndicatorLight(color=IndicatorColor.RED, diameter=14)
        self._lm_status_lbl = QLabel("DISCONNECTED")
        self._lm_addr_lbl = QLabel("")
        self._lm_rx_lbl = QLabel("RX: 0")
        self._lm_tx_lbl = QLabel("TX: 0")
        lm_frame = self._make_vehicle_frame(
            "LM",
            LM_ACCENT,
            self._lm_indicator,
            self._lm_status_lbl,
            self._lm_addr_lbl,
            self._lm_rx_lbl,
            self._lm_tx_lbl,
        )
        row.addWidget(lm_frame)

        self._root.addLayout(row)
        self._root.addSpacing(14)

    def _make_vehicle_frame(self, label, accent, indicator, status_lbl, addr_lbl, rx_lbl, tx_lbl):
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame{{background-color:{FRAME_BG};"
            f"border:1px solid #3a3a3e; border-top:3px solid {accent};"
            "border-radius:3px;}}"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        # Header row: indicator + vehicle name
        header = QHBoxLayout()
        header.addWidget(indicator)
        header.addSpacing(4)

        name_lbl = QLabel(label)
        name_lbl.setStyleSheet(f"color:{accent}; font-size:14px; font-weight:bold; border:none;")
        header.addWidget(name_lbl)
        header.addStretch()

        status_lbl.setStyleSheet(
            f"color:{DIM_COLOR}; font-size:10px; font-family:monospace; border:none;"
        )
        header.addWidget(status_lbl)
        layout.addLayout(header)

        # Address
        addr_lbl.setStyleSheet(
            f"color:{DIM_COLOR}; font-size:10px; font-family:monospace; border:none;"
        )
        layout.addWidget(addr_lbl)

        # Packet counts
        counts = QHBoxLayout()
        rx_lbl.setStyleSheet(
            f"color:{DATA_COLOR}; font-size:11px; font-family:monospace; border:none;"
        )
        tx_lbl.setStyleSheet(
            f"color:{DATA_COLOR}; font-size:11px; font-family:monospace; border:none;"
        )
        counts.addWidget(rx_lbl)
        counts.addSpacing(12)
        counts.addWidget(tx_lbl)
        counts.addStretch()
        layout.addLayout(counts)

        return frame

    # ── controls row: vehicle selector + ground clients ───────

    def _build_controls_row(self):
        row = QHBoxLayout()
        row.setSpacing(20)

        # Vehicle selector
        sel_frame = QFrame()
        sel_frame.setStyleSheet(
            f"QFrame{{background-color:{FRAME_BG};"
            "border:1px solid #3a3a3e; border-radius:3px;}}"
        )
        sel_layout = QVBoxLayout(sel_frame)
        sel_layout.setContentsMargins(12, 8, 12, 8)
        sel_layout.setSpacing(6)

        sel_header = self._make_section_header("VEHICLE SELECT")
        sel_header.setStyleSheet(sel_header.styleSheet() + " border:none;")
        sel_layout.addWidget(sel_header)

        self._knob = RotaryKnob(positions=["CM", "LM"], diameter=56)
        self._knob.rotated.connect(self._on_vehicle_select)
        knob_row = QHBoxLayout()
        knob_row.addStretch()
        knob_row.addWidget(self._knob)
        knob_row.addStretch()
        sel_layout.addLayout(knob_row)

        row.addWidget(sel_frame)

        # Ground clients
        gc_frame = QFrame()
        gc_frame.setStyleSheet(
            f"QFrame{{background-color:{FRAME_BG};"
            "border:1px solid #3a3a3e; border-radius:3px;}}"
        )
        gc_layout = QVBoxLayout(gc_frame)
        gc_layout.setContentsMargins(12, 8, 12, 8)
        gc_layout.setSpacing(6)

        gc_header = self._make_section_header("GROUND CLIENTS")
        gc_header.setStyleSheet(gc_header.styleSheet() + " border:none;")
        gc_layout.addWidget(gc_header)

        self._gc_indicators = []
        grid = QGridLayout()
        grid.setSpacing(6)
        for i in range(6):
            indicator = IndicatorLight(color=IndicatorColor.AMBER, diameter=14)
            grid.addWidget(indicator, 0, i, Qt.AlignmentFlag.AlignCenter)
            self._gc_indicators.append(indicator)
            num = QLabel(str(i + 1))
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            num.setStyleSheet(
                f"color:{DIM_COLOR}; font-size:9px; font-family:monospace; border:none;"
            )
            grid.addWidget(num, 1, i, Qt.AlignmentFlag.AlignCenter)
        gc_layout.addLayout(grid)
        gc_layout.addStretch()

        row.addWidget(gc_frame, stretch=1)
        self._root.addLayout(row)
        self._root.addSpacing(10)

    # ── packet counter ────────────────────────────────────────

    def _build_packet_counter(self):
        row = QHBoxLayout()
        header = self._make_section_header("PACKETS ROUTED")
        row.addWidget(header)
        row.addSpacing(16)

        self._routed_lbl = QLabel("0")
        self._routed_lbl.setStyleSheet(
            f"color:{DATA_COLOR}; font-size:16px; font-family:monospace; font-weight:bold;"
        )
        row.addWidget(self._routed_lbl)
        row.addStretch()
        self._root.addLayout(row)
        self._root.addSpacing(8)

    # ── activity log ──────────────────────────────────────────

    def _build_activity_log(self):
        header = self._make_section_header("ACTIVITY LOG")
        self._root.addWidget(header)
        self._root.addSpacing(4)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("monospace", 10))
        self._log.setStyleSheet(
            f"QTextEdit{{background-color:{LOG_BG}; color:#AAA;"
            "border:1px solid #3a3a3e; border-radius:2px; padding:6px;}}"
        )
        self._log.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._root.addWidget(self._log, stretch=1)

    # ── polling ───────────────────────────────────────────────

    def _poll_relay(self):
        s = self._relay.status()

        # CM status
        cm = s["cm"]
        self._update_vehicle(
            cm,
            self._cm_indicator,
            self._cm_status_lbl,
            self._cm_addr_lbl,
            self._cm_rx_lbl,
            self._cm_tx_lbl,
        )

        # LM status
        lm = s["lm"]
        self._update_vehicle(
            lm,
            self._lm_indicator,
            self._lm_status_lbl,
            self._lm_addr_lbl,
            self._lm_rx_lbl,
            self._lm_tx_lbl,
        )

        # Ground clients
        gc_count = s["ground_clients"]
        for i, ind in enumerate(self._gc_indicators):
            ind.set_on(i < gc_count)

        # Packet counter
        self._routed_lbl.setText(f'{s["total_routed"]:,}')

        # Drain events → activity log
        for ts, msg in self._relay.drain_events():
            stamp = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
            self._log.append(f"{stamp}  {msg}")

        # Trim old log entries to bound memory usage
        doc = self._log.document()
        while doc.blockCount() > MAX_LOG_LINES:
            cursor = QTextCursor(doc.begin())
            cursor.movePosition(QTextCursor.MoveOperation.NextBlock, QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            cursor.deleteChar()  # remove the trailing newline

        # Auto-scroll
        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._log.setTextCursor(cursor)

    @staticmethod
    def _update_vehicle(vdata, indicator, status_lbl, addr_lbl, rx_lbl, tx_lbl):
        if vdata["connected"]:
            indicator.set_color(IndicatorColor.GREEN)
            indicator.set_on(True)
            status_lbl.setText("CONNECTED")
            status_lbl.setStyleSheet(
                "color:#66CC66; font-size:10px; font-family:monospace; border:none;"
            )
        else:
            indicator.set_color(IndicatorColor.RED)
            indicator.set_on(True)
            status_lbl.setText("DISCONNECTED")
            status_lbl.setStyleSheet(
                f"color:{DIM_COLOR}; font-size:10px; font-family:monospace; border:none;"
            )
        addr_lbl.setText(f'{vdata["host"]}:{vdata["port"]}')
        rx_lbl.setText(f'RX: {vdata["rx"]:,}')
        tx_lbl.setText(f'TX: {vdata["tx"]:,}')

    # ── vehicle selector ──────────────────────────────────────

    def _on_vehicle_select(self, position):
        vehicle = "CM" if position == 0 else "LM"
        self._relay.select_vehicle(vehicle)

    # ── helpers ───────────────────────────────────────────────

    @staticmethod
    def _make_section_header(text):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color:{HEADER_COLOR}; font-size:9px; font-weight:bold;"
            "letter-spacing:1px;"
        )
        return lbl

    @staticmethod
    def _make_divider():
        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet(f"background-color:{DIVIDER_COLOR};")
        return div

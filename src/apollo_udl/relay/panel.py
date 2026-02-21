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
from .server import FILTER_CM, FILTER_LM, FILTER_CYCLE, MAX_GROUND_CLIENTS

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

# Filter → indicator color mapping (CM = blue, LM = gold, matching vehicle accents)
FILTER_COLORS = {
    FILTER_CM: IndicatorColor.BLUE,
    FILTER_LM: IndicatorColor.GOLD,
}

POLL_INTERVAL_MS = 200
MAX_LOG_LINES = 500


class RelayPanel(QMainWindow):
    """Mission Control GUI for the Apollo UDL Network Relay.

    Polls ``relay.status()`` every 200 ms and drains the event buffer
    to update vehicle indicators, ground-client lights, packet counters,
    and the activity log.

    Each vehicle has an independent downlink enable toggle (click to
    toggle on/off).  Uplink routing follows the per-client filter --
    each client talks to the vehicle matching its port assignment.
    """

    PANEL_WIDTH = 660
    PANEL_HEIGHT = 560

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

        # CM frame
        self._cm_conn_ind = IndicatorLight(color=IndicatorColor.RED, diameter=14)
        self._cm_enable_ind = IndicatorLight(color=IndicatorColor.GREEN, diameter=12)
        self._cm_enable_ind.set_on(True)
        self._cm_enable_ind.clicked.connect(lambda: self._toggle_vehicle("CM"))
        self._cm_enable_lbl = QLabel("ENABLED")
        self._cm_status_lbl = QLabel("DISCONNECTED")
        self._cm_addr_lbl = QLabel("")
        self._cm_rx_lbl = QLabel("RX: 0")
        self._cm_tx_lbl = QLabel("TX: 0")
        cm_frame = self._make_vehicle_frame(
            "CM", CM_ACCENT,
            self._cm_conn_ind, self._cm_enable_ind, self._cm_enable_lbl,
            self._cm_status_lbl, self._cm_addr_lbl, self._cm_rx_lbl, self._cm_tx_lbl,
        )
        row.addWidget(cm_frame)

        # LM frame
        self._lm_conn_ind = IndicatorLight(color=IndicatorColor.RED, diameter=14)
        self._lm_enable_ind = IndicatorLight(color=IndicatorColor.GREEN, diameter=12)
        self._lm_enable_ind.set_on(True)
        self._lm_enable_ind.clicked.connect(lambda: self._toggle_vehicle("LM"))
        self._lm_enable_lbl = QLabel("ENABLED")
        self._lm_status_lbl = QLabel("DISCONNECTED")
        self._lm_addr_lbl = QLabel("")
        self._lm_rx_lbl = QLabel("RX: 0")
        self._lm_tx_lbl = QLabel("TX: 0")
        lm_frame = self._make_vehicle_frame(
            "LM", LM_ACCENT,
            self._lm_conn_ind, self._lm_enable_ind, self._lm_enable_lbl,
            self._lm_status_lbl, self._lm_addr_lbl, self._lm_rx_lbl, self._lm_tx_lbl,
        )
        row.addWidget(lm_frame)

        self._root.addLayout(row)
        self._root.addSpacing(14)

    def _make_vehicle_frame(
        self, label, accent,
        conn_ind, enable_ind, enable_lbl,
        status_lbl, addr_lbl, rx_lbl, tx_lbl,
    ):
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame{{background-color:{FRAME_BG};"
            f"border:1px solid #3a3a3e; border-top:3px solid {accent};"
            "border-radius:3px;}}"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        # Header row: connection indicator + vehicle name + status
        header = QHBoxLayout()
        header.addWidget(conn_ind)
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

        # Enable toggle row: clickable indicator + label
        enable_row = QHBoxLayout()
        enable_row.addWidget(enable_ind)
        enable_row.addSpacing(4)
        enable_lbl.setStyleSheet(
            "color:#66CC66; font-size:9px; font-family:monospace;"
            "font-weight:bold; border:none;"
        )
        enable_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        enable_ind.setCursor(Qt.CursorShape.PointingHandCursor)
        enable_row.addWidget(enable_lbl)
        enable_row.addStretch()

        addr_lbl.setStyleSheet(
            f"color:{DIM_COLOR}; font-size:10px; font-family:monospace; border:none;"
        )
        enable_row.addWidget(addr_lbl)
        layout.addLayout(enable_row)

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

    # ── controls row: ground clients ────────────────────────────

    def _build_controls_row(self):
        row = QHBoxLayout()
        row.setSpacing(20)

        # Ground clients (filter-aware interactive slots)
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
        self._gc_filter_lbls = []
        self._gc_cids = [None] * MAX_GROUND_CLIENTS
        grid = QGridLayout()
        grid.setSpacing(6)
        for i in range(MAX_GROUND_CLIENTS):
            indicator = IndicatorLight(color=IndicatorColor.BLUE, diameter=14)
            indicator.setCursor(Qt.CursorShape.PointingHandCursor)
            slot = i  # capture for lambda
            indicator.clicked.connect(lambda s=slot: self._cycle_client_filter(s))
            grid.addWidget(indicator, 0, i, Qt.AlignmentFlag.AlignCenter)
            self._gc_indicators.append(indicator)
            num = QLabel(str(i + 1))
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            num.setStyleSheet(
                f"color:{DIM_COLOR}; font-size:9px; font-family:monospace; border:none;"
            )
            grid.addWidget(num, 1, i, Qt.AlignmentFlag.AlignCenter)
            filt_lbl = QLabel("")
            filt_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            filt_lbl.setStyleSheet(
                f"color:{DIM_COLOR}; font-size:8px; font-family:monospace; border:none;"
            )
            grid.addWidget(filt_lbl, 2, i, Qt.AlignmentFlag.AlignCenter)
            self._gc_filter_lbls.append(filt_lbl)
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
            self._cm_conn_ind,
            self._cm_enable_ind,
            self._cm_enable_lbl,
            self._cm_status_lbl,
            self._cm_addr_lbl,
            self._cm_rx_lbl,
            self._cm_tx_lbl,
        )

        # LM status
        lm = s["lm"]
        self._update_vehicle(
            lm,
            self._lm_conn_ind,
            self._lm_enable_ind,
            self._lm_enable_lbl,
            self._lm_status_lbl,
            self._lm_addr_lbl,
            self._lm_rx_lbl,
            self._lm_tx_lbl,
        )

        # Ground clients -- map server client list to panel slots
        clients = s["ground_clients"]
        self._gc_cids = [None] * MAX_GROUND_CLIENTS
        for i in range(MAX_GROUND_CLIENTS):
            if i < len(clients):
                c = clients[i]
                self._gc_cids[i] = c["cid"]
                filt = c["filter"]
                self._gc_indicators[i].set_color(FILTER_COLORS.get(filt, IndicatorColor.BLUE))
                self._gc_indicators[i].set_on(True)
                self._gc_filter_lbls[i].setText(filt)
                color = CM_ACCENT if filt == FILTER_CM else LM_ACCENT
                self._gc_filter_lbls[i].setStyleSheet(
                    f"color:{color}; font-size:8px; font-family:monospace; border:none;"
                )
            else:
                self._gc_indicators[i].set_on(False)
                self._gc_filter_lbls[i].setText("")

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
            cursor.deleteChar()

        # Auto-scroll
        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._log.setTextCursor(cursor)

    @staticmethod
    def _update_vehicle(
        vdata, conn_ind, enable_ind, enable_lbl,
        status_lbl, addr_lbl, rx_lbl, tx_lbl,
    ):
        # Connection indicator (read-only)
        if vdata["connected"]:
            conn_ind.set_color(IndicatorColor.GREEN)
            conn_ind.set_on(True)
            status_lbl.setText("CONNECTED")
            status_lbl.setStyleSheet(
                "color:#66CC66; font-size:10px; font-family:monospace; border:none;"
            )
        else:
            conn_ind.set_color(IndicatorColor.RED)
            conn_ind.set_on(True)
            status_lbl.setText("DISCONNECTED")
            status_lbl.setStyleSheet(
                f"color:{DIM_COLOR}; font-size:10px; font-family:monospace; border:none;"
            )

        # Enable toggle (reflects server state)
        if vdata["enabled"]:
            enable_ind.set_color(IndicatorColor.GREEN)
            enable_ind.set_on(True)
            enable_lbl.setText("ENABLED")
            enable_lbl.setStyleSheet(
                "color:#66CC66; font-size:9px; font-family:monospace;"
                "font-weight:bold; border:none;"
            )
        else:
            enable_ind.set_on(False)
            enable_lbl.setText("DISABLED")
            enable_lbl.setStyleSheet(
                f"color:{DIM_COLOR}; font-size:9px; font-family:monospace;"
                "font-weight:bold; border:none;"
            )

        addr_lbl.setText(f'{vdata["host"]}:{vdata["port"]}')
        rx_lbl.setText(f'RX: {vdata["rx"]:,}')
        tx_lbl.setText(f'TX: {vdata["tx"]:,}')

    # ── vehicle enable toggles ────────────────────────────────

    def _toggle_vehicle(self, name):
        s = self._relay.status()
        vdata = s["cm"] if name == "CM" else s["lm"]
        if vdata["enabled"]:
            self._relay.disable_vehicle(name)
        else:
            self._relay.enable_vehicle(name)

    # ── ground client filter cycling ─────────────────────────

    def _cycle_client_filter(self, slot):
        cid = self._gc_cids[slot] if slot < len(self._gc_cids) else None
        if cid is None:
            return
        # Find current filter from the last status snapshot
        s = self._relay.status()
        for c in s["ground_clients"]:
            if c["cid"] == cid:
                cur = c["filter"]
                idx = FILTER_CYCLE.index(cur) if cur in FILTER_CYCLE else 0
                nxt = FILTER_CYCLE[(idx + 1) % len(FILTER_CYCLE)]
                self._relay.set_client_filter(cid, nxt)
                break

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

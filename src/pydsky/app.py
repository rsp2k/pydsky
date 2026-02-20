#!/usr/bin/env python3
import argparse
import sys
from qtpy.QtWidgets import (
    QApplication, QMainWindow, QStyleOption, QStyle,
    QFrame, QVBoxLayout, QLabel,
)
from qtpy.QtGui import QPainter, QPixmap
from qtpy.QtCore import Qt, QTimer
from qtpy.QtNetwork import QTcpSocket

from . import resources
from .lamp import Lamp
from .seven_segment import SevenSegment
from .sign import Sign
from .button import Button

RECONNECT_MS = 100
RELAY_PORT = 19900

VEHICLE_COLORS = {
    'CM': '#5588AA',
    'LM': '#CC9933',
}

KEY_NAMES = {
    0b10001: 'VERB', 0b11111: 'NOUN', 0b11010: '+', 0b11011: '-',
    0b10000: '0', 0b00001: '1', 0b00010: '2', 0b00011: '3',
    0b00100: '4', 0b00101: '5', 0b00110: '6', 0b00111: '7',
    0b01000: '8', 0b01001: '9', 0b11110: 'CLR', 0b11001: 'KEY REL',
    0b11100: 'ENTR', 0b10010: 'RSET',
}

class DSKY(QMainWindow):
    def __init__(self, parent, host='localhost', port=19697, vehicle=None, software=None):
        super().__init__(parent)

        self._host = host
        self._port = port

        if vehicle is None:
            self._vehicle = 'LM' if port == 19797 else 'CM'
        else:
            self._vehicle = vehicle.upper()

        if software is None:
            self._software = 'Luminary099' if self._vehicle == 'LM' else 'Colossus249'
        else:
            self._software = software

        self._accent = VEHICLE_COLORS.get(self._vehicle, '#5588AA')
        self.setWindowTitle(f'pyDSKY \u2014 {self._vehicle} ({self._software})')

        self._packets_rx = 0
        self._packets_tx = 0
        self._last_key_name = '\u2014'
        self._upl_act_on = False
        self._com_act_on = False
        self._is_connected = False

        self._setup_ui()
        self._build_side_panel()

        self._packet = [0, 0, 0, 0]
        self._packet_idx = 0

        self._socket = QTcpSocket(self)
        self._socket.readyRead.connect(self._read_data)
        self._socket.connected.connect(self._on_connected)
        self._socket.disconnected.connect(self._on_disconnected)
        self._socket.errorOccurred.connect(self._on_socket_error)
        self._connect_to_vagc()

    def _on_connected(self):
        self._is_connected = True
        self._update_conn_status()

    def _on_disconnected(self):
        self._is_connected = False
        self._update_conn_status()
        self._schedule_reconnect()

    def _schedule_reconnect(self):
        QTimer.singleShot(RECONNECT_MS, self._connect_to_vagc)

    def _on_socket_error(self, error):
        if error != QTcpSocket.SocketError.ConnectionRefusedError:
            return
        self._schedule_reconnect()

    def _connect_to_vagc(self):
        if self._socket.state() != QTcpSocket.SocketState.UnconnectedState:
            return
        self._socket.connectToHost(self._host, self._port)

    def _read_data(self):
        while not self._socket.atEnd():
            data = bytes(self._socket.readAll())
            for byte in data:

                if (byte & 0xC0) == 0:
                    self._packet_idx = 0

                if (self._packet_idx > 0) or (byte & 0xC0) == 0:
                    self._packet[self._packet_idx] = byte
                    self._packet_idx += 1
                    if self._packet_idx >= len(self._packet):
                        self._handle_packet(self._packet)
                        self._packet_idx = 0

    def _form_packet(self, channel, value):
        packet = [0]*4

        packet[0] = channel >> 3
        packet[1] = 0x40 | ((channel << 3) & 0x38) | ((value >> 12) & 0x07)
        packet[2] = 0x80 | ((value >> 6) & 0x3F)
        packet[3] = 0xc0 | (value & 0x3F)

        return bytes(packet)

    def _handle_packet(self, packet):
        if (packet[0] & 0xC0) != 0x00:
            return
        if (packet[1] & 0xC0) != 0x40:
            return
        if (packet[2] & 0xC0) != 0x80:
            return
        if (packet[3] & 0xC0) != 0xC0:
            return

        self._packets_rx += 1
        self._update_packet_counts()

        channel = ((packet[0] & 0x1F) << 3) | ((packet[1] >> 3) & 0x07)
        value = ((packet[1] << 12) & 0x7000) | ((packet[2] << 6) & 0x0FC0) | (packet[3] & 0x003F);

        if channel == 0o10:
            relay = (value >> 11) & 0x0F
            relay_value = value & 0o3777

            if relay == 1:
                self._sign3.set_minus_bit((relay_value >> 10) & 0o1)
                self._reg3[3].set_relay_bits((relay_value >> 5) & 0o37)
                self._reg3[4].set_relay_bits((relay_value >> 0) & 0o37)
            elif relay == 2:
                self._sign3.set_plus_bit((relay_value >> 10) & 0o1)
                self._reg3[1].set_relay_bits((relay_value >> 5) & 0o37)
                self._reg3[2].set_relay_bits((relay_value >> 0) & 0o37)
            elif relay == 3:
                self._reg2[4].set_relay_bits((relay_value >> 5) & 0o37)
                self._reg3[0].set_relay_bits((relay_value >> 0) & 0o37)
            elif relay == 4:
                self._sign2.set_minus_bit((relay_value >> 10) & 0o1)
                self._reg2[2].set_relay_bits((relay_value >> 5) & 0o37)
                self._reg2[3].set_relay_bits((relay_value >> 0) & 0o37)
            elif relay == 5:
                self._sign2.set_plus_bit((relay_value >> 10) & 0o1)
                self._reg2[0].set_relay_bits((relay_value >> 5) & 0o37)
                self._reg2[1].set_relay_bits((relay_value >> 0) & 0o37)
            elif relay == 6:
                self._sign1.set_minus_bit((relay_value >> 10) & 0o1)
                self._reg1[3].set_relay_bits((relay_value >> 5) & 0o37)
                self._reg1[4].set_relay_bits((relay_value >> 0) & 0o37)
            elif relay == 7:
                self._sign1.set_plus_bit((relay_value >> 10) & 0o1)
                self._reg1[1].set_relay_bits((relay_value >> 5) & 0o37)
                self._reg1[2].set_relay_bits((relay_value >> 0) & 0o37)
            elif relay == 8:
                self._reg1[0].set_relay_bits((relay_value >> 0) & 0o37)
            elif relay == 9:
                self._noun[0].set_relay_bits((relay_value >> 5) & 0o37)
                self._noun[1].set_relay_bits((relay_value >> 0) & 0o37)
            elif relay == 10:
                self._verb[0].set_relay_bits((relay_value >> 5) & 0o37)
                self._verb[1].set_relay_bits((relay_value >> 0) & 0o37)
            elif relay == 11:
                self._prog[0].set_relay_bits((relay_value >> 5) & 0o37)
                self._prog[1].set_relay_bits((relay_value >> 0) & 0o37)
            elif relay == 12:
                self._prio_disp.set_on((relay_value >> 0) & 0o1)
                self._no_dap.set_on((relay_value >> 1) & 0o1)
                self._vel.set_on((relay_value >> 2) & 0o1)
                self._no_att.set_on((relay_value >> 3) & 0o1)
                self._alt.set_on((relay_value >> 4) & 0o1)
                self._gimbal_lock.set_on((relay_value >> 5) & 0o1)
                self._tracker.set_on((relay_value >> 7) & 0o1)
                self._prog_alarm.set_on((relay_value >> 8) & 0o1)

        elif channel == 0o11:
            self._upl_act_on = bool((value >> 2) & 0o1)
            self._com_act_on = bool((value >> 1) & 0o1)
            self._upl_act.set_on((value >> 2) & 0o1)
            self._com_act.set_on((value >> 1) & 0o1)
            self._update_indicators()

        elif channel == 0o163:
            self._temp.set_on((value >> 3) & 0o1)
            self._key_rel.set_on((value >> 4) & 0o1)
            self._opr_err.set_on((value >> 6) & 0o1)
            self._restart.set_on((value >> 7) & 0o1)
            self._stby.set_on((value >> 8) & 0o1)

            vnflash = ((value >> 5) & 0o1) ^ 1
            self._verb[0].set_on(vnflash)
            self._verb[1].set_on(vnflash)
            self._noun[0].set_on(vnflash)
            self._noun[1].set_on(vnflash)

    def _setup_ui(self):
        self.setObjectName('DSKY')
        self.setWindowFlags(Qt.WindowType.Window)
        self.setFixedSize(700, 580)
        self.setStyleSheet(
            'DSKY{background-color: #2a2a30;'
            'background-image: url(:/resources/dsky.png);'
            'background-repeat: no-repeat;}'
        )

        el_pix = QPixmap(':/resources/el.png')
        lamp_pix = QPixmap(':/resources/lamps.png')

        self._com_act = Lamp(self, el_pix, 0, 1, 65, 61, False)
        self._com_act.move(285, 36)
        self._perms = self._create_permanent_segments(el_pix)
        self._prog = self._create_mode(el_pix, 394, 60)
        self._verb = self._create_mode(el_pix, 287, 129)
        self._noun = self._create_mode(el_pix, 394, 129)
        self._sign1, self._reg1 = self._create_reg(el_pix, 287, 184)
        self._sign2, self._reg2 = self._create_reg(el_pix, 287, 239)
        self._sign3, self._reg3 = self._create_reg(el_pix, 287, 294)

        self._but_verb = self._create_button(8, 404, 0b10001) # VERB
        self._but_noun = self._create_button(8, 474, 0b11111) # NOUN
        self._but_plus = self._create_button(78, 369, 0b11010) # +
        self._but_minus = self._create_button(78, 439, 0b11011) # -
        self._but_0 = self._create_button(78,509, 0b10000) # 0
        self._but_7 = self._create_button(148, 369, 0b00111) # 7
        self._but_4 = self._create_button(148, 439, 0b00100) # 4
        self._but_1 = self._create_button(148, 509, 0b00001) # 1
        self._but_8 = self._create_button(218, 369, 0b01000) # 8
        self._but_5 = self._create_button(218, 439, 0b00101) # 5
        self._but_2 = self._create_button(218, 509, 0b00010) # 2
        self._but_9 = self._create_button(288, 369, 0b01001) # 9
        self._but_6 = self._create_button(288, 439, 0b00110) # 6
        self._but_3 = self._create_button(288, 509, 0b00011) # 3
        self._but_clr = self._create_button(359, 369, 0b11110) # CLR
        self._but_pro = self._create_button(359, 439, None) # PRO
        self._but_key_rel = self._create_button(359, 509, 0b11001) # KEY REL
        self._but_enter = self._create_button(429, 404, 0b11100) # ENTER
        self._but_reset = self._create_button(429, 474, 0b10010) # RESET

        self._upl_act = Lamp(self, lamp_pix, 0, 0, 78, 37, False, bulbs=3)
        self._upl_act.move(45, 34)
        self._no_att = Lamp(self, lamp_pix, 0, 38, 78, 37, False, bulbs=3)
        self._no_att.move(45, 77)
        self._stby = Lamp(self, lamp_pix, 0, 76, 78, 37, False, bulbs=3)
        self._stby.move(45, 120)
        self._key_rel = Lamp(self, lamp_pix, 0, 114, 78, 37, False, bulbs=3)
        self._key_rel.move(45, 163)
        self._opr_err = Lamp(self, lamp_pix, 0, 152, 78, 37, False, bulbs=3)
        self._opr_err.move(45, 206)
        self._prio_disp = Lamp(self, lamp_pix, 0, 190, 78, 37, False, bulbs=3)
        self._prio_disp.move(45, 249)
        self._no_dap = Lamp(self, lamp_pix, 0, 228, 78, 37, False, bulbs=3)
        self._no_dap.move(45, 292)

        self._temp = Lamp(self, lamp_pix, 79, 0, 78, 37, False, bulbs=3)
        self._temp.move(134, 34)
        self._gimbal_lock = Lamp(self, lamp_pix, 79, 38, 78, 37, False, bulbs=3)
        self._gimbal_lock.move(134, 77)
        self._prog_alarm = Lamp(self, lamp_pix, 79, 76, 78, 37, False, bulbs=3)
        self._prog_alarm.move(134, 120)
        self._restart = Lamp(self, lamp_pix, 79, 114, 78, 37, False, bulbs=3)
        self._restart.move(134, 163)
        self._tracker = Lamp(self, lamp_pix, 79, 152, 78, 37, False, bulbs=3)
        self._tracker.move(134, 206)
        self._alt = Lamp(self, lamp_pix, 79, 190, 78, 37, False, bulbs=3)
        self._alt.move(134, 249)
        self._vel = Lamp(self, lamp_pix, 79, 228, 78, 37, False, bulbs=3)
        self._vel.move(134, 292)

    def _create_reg(self, el_pix, col, row):
        digits = []

        sign = Sign(self, el_pix)
        sign.move(col, row + 6)

        for i in range(5):
            ss = SevenSegment(self, el_pix)
            ss.move(col + 18 + 30*i, row)
            digits.append(ss)

        return sign, digits

    def _create_mode(self, el_pix, col, row):
        digits = []
        for i in range(2):
            ss = SevenSegment(self, el_pix)
            ss.move(col + 30*i, row)
            digits.append(ss)

        return digits

    def _create_permanent_segments(self, el_pix):
        perms = []

        # PROG
        el = Lamp(self, el_pix, 66, 0, 64, 19, True)
        el.move(393, 37)
        perms.append(el)

        # VERB
        el = Lamp(self, el_pix, 66, 41, 64, 20, True)
        el.move(286, 106)
        perms.append(el)

        # NOUN
        el = Lamp(self, el_pix, 66, 20, 64, 20, True)
        el.move(393, 106)
        perms.append(el)

        for i in range(3):
            el = Lamp(self, el_pix, 0, 63, 142, 5, True)
            el.move(305, 170+i*55)
            perms.append(el)

        return perms

    def _create_button(self, x, y, keycode):
        b = Button(self)
        b.setFixedSize(63, 63)
        b.move(x, y)
        b.setStyleSheet('QPushButton{background-color:rgba(0,0,0,0);border:0px;} QPushButton:pressed{background-color:rgba(0,0,0,60);}')
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.setAutoRepeat(False)
        if keycode is None:
            b.pressed.connect(lambda: self._send_proceed(1))
            b.released.connect(lambda: self._send_proceed(0))
        else:
            b.pressed.connect(lambda k=keycode:
                self._send_key(k))

        return b

    # ── side panel ───────────────────────────────────────────────

    def _build_side_panel(self):
        accent = self._accent

        panel = QFrame(self)
        panel.setObjectName('side_panel')
        panel.setGeometry(500, 0, 200, 580)
        panel.setStyleSheet(
            f'QFrame#side_panel{{'
            f'background-color:#2a2a30;'
            f'border-left:4px solid {accent};'
            f'}}'
        )

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 16, 8, 8)
        layout.setSpacing(2)

        # Vehicle designation
        lbl = QLabel(self._vehicle)
        lbl.setStyleSheet(f'color:{accent}; font-size:18px; font-weight:bold;')
        layout.addWidget(lbl)

        # Software name — split "Colossus249" → "COLOSSUS 249"
        sw = self._software
        for i, c in enumerate(sw):
            if c.isdigit():
                sw = f'{sw[:i]} {sw[i:]}'
                break
        lbl = QLabel(sw.upper())
        lbl.setStyleSheet('color:#999; font-size:11px;')
        layout.addWidget(lbl)

        layout.addSpacing(6)
        layout.addWidget(self._make_divider())
        layout.addSpacing(6)

        # Connection
        layout.addWidget(self._make_section_header('CONNECTION'))
        self._lbl_conn = QLabel('\u25CB  DISCONNECTED')
        self._lbl_conn.setStyleSheet('color:#CC6666; font-size:11px; font-family:monospace;')
        layout.addWidget(self._lbl_conn)
        lbl = QLabel(f'{self._host}:{self._port}')
        lbl.setStyleSheet('color:#777; font-size:10px; font-family:monospace;')
        layout.addWidget(lbl)

        layout.addSpacing(6)
        layout.addWidget(self._make_divider())
        layout.addSpacing(6)

        # Packets
        layout.addWidget(self._make_section_header('PACKETS'))
        self._lbl_rx = QLabel('RX:  0')
        self._lbl_rx.setStyleSheet('color:#DDD; font-size:11px; font-family:monospace;')
        layout.addWidget(self._lbl_rx)
        self._lbl_tx = QLabel('TX:  0')
        self._lbl_tx.setStyleSheet('color:#DDD; font-size:11px; font-family:monospace;')
        layout.addWidget(self._lbl_tx)

        layout.addSpacing(6)
        layout.addWidget(self._make_divider())
        layout.addSpacing(6)

        # Uplink
        layout.addWidget(self._make_section_header('UPLINK'))
        self._lbl_last_key = QLabel('Last:  \u2014')
        self._lbl_last_key.setStyleSheet('color:#DDD; font-size:11px; font-family:monospace;')
        layout.addWidget(self._lbl_last_key)
        self._lbl_upl = QLabel('UPL ACT:  \u25CB')
        self._lbl_upl.setStyleSheet('color:#777; font-size:11px; font-family:monospace;')
        layout.addWidget(self._lbl_upl)
        self._lbl_com = QLabel('COM ACT:  \u25CB')
        self._lbl_com.setStyleSheet('color:#777; font-size:11px; font-family:monospace;')
        layout.addWidget(self._lbl_com)

        layout.addSpacing(6)
        layout.addWidget(self._make_divider())
        layout.addSpacing(6)

        # Relay
        layout.addWidget(self._make_section_header('RELAY'))
        relay_text = 'via RELAY :19900' if self._port == RELAY_PORT else 'DIRECT'
        lbl = QLabel(relay_text)
        lbl.setStyleSheet('color:#DDD; font-size:11px; font-family:monospace;')
        layout.addWidget(lbl)

        layout.addStretch()

    def _make_section_header(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet('color:#777; font-size:9px; font-weight:bold; letter-spacing:1px;')
        return lbl

    def _make_divider(self):
        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet('background-color:#444;')
        return div

    def _update_conn_status(self):
        if self._is_connected:
            self._lbl_conn.setText('\u25CF  CONNECTED')
            self._lbl_conn.setStyleSheet('color:#66CC66; font-size:11px; font-family:monospace;')
        else:
            self._lbl_conn.setText('\u25CB  DISCONNECTED')
            self._lbl_conn.setStyleSheet('color:#CC6666; font-size:11px; font-family:monospace;')

    def _update_packet_counts(self):
        self._lbl_rx.setText(f'RX:  {self._packets_rx:,}')
        self._lbl_tx.setText(f'TX:  {self._packets_tx:,}')

    def _update_indicators(self):
        if self._upl_act_on:
            self._lbl_upl.setText('UPL ACT:  \u25CF')
            self._lbl_upl.setStyleSheet('color:#DDD; font-size:11px; font-family:monospace;')
        else:
            self._lbl_upl.setText('UPL ACT:  \u25CB')
            self._lbl_upl.setStyleSheet('color:#777; font-size:11px; font-family:monospace;')
        if self._com_act_on:
            self._lbl_com.setText('COM ACT:  \u25CF')
            self._lbl_com.setStyleSheet('color:#DDD; font-size:11px; font-family:monospace;')
        else:
            self._lbl_com.setText('COM ACT:  \u25CB')
            self._lbl_com.setStyleSheet('color:#777; font-size:11px; font-family:monospace;')

    # ── key transmission ──────────────────────────────────────

    def _send_key(self, keycode):
        if self._socket.state() == QTcpSocket.SocketState.ConnectedState:
            self._socket.write(self._form_packet(0o15, keycode))
            self._packets_tx += 1
            self._update_packet_counts()
            self._lbl_last_key.setText(f'Last:  {KEY_NAMES.get(keycode, "?")}')

    def _send_proceed(self, p):
        if self._socket.state() == QTcpSocket.SocketState.ConnectedState:
            self._socket.write(self._form_packet(0o432, 0o20000) +
                               self._form_packet(0o32, 0o20000 if p else 0))
            if p:
                self._packets_tx += 1
                self._update_packet_counts()
                self._lbl_last_key.setText('Last:  PRO')

    def paintEvent(self, event):
        opt = QStyleOption()
        opt.initFrom(self)
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt, p, self)

    def keyPressEvent(self, event):
        if event.isAutoRepeat():
            return
        key = event.key()
        self._set_key_down(key, True)

    def keyReleaseEvent(self, event):
        if event.isAutoRepeat():
            return
        key = event.key()
        self._set_key_down(key, False)

    def _set_key_down(self, key, down):
        but = None

        if key == Qt.Key.Key_V:
            but = self._but_verb
        elif key == Qt.Key.Key_N:
            but = self._but_noun
        elif key == Qt.Key.Key_Plus or key == Qt.Key.Key_Equal:
            but = self._but_plus
        elif key == Qt.Key.Key_Minus:
            but = self._but_minus
        elif key == Qt.Key.Key_0:
            but = self._but_0
        elif key == Qt.Key.Key_1:
            but = self._but_1
        elif key == Qt.Key.Key_2:
            but = self._but_2
        elif key == Qt.Key.Key_3:
            but = self._but_3
        elif key == Qt.Key.Key_4:
            but = self._but_4
        elif key == Qt.Key.Key_5:
            but = self._but_5
        elif key == Qt.Key.Key_6:
            but = self._but_6
        elif key == Qt.Key.Key_7:
            but = self._but_7
        elif key == Qt.Key.Key_8:
            but = self._but_8
        elif key == Qt.Key.Key_9:
            but = self._but_9
        elif key == Qt.Key.Key_C:
            but = self._but_clr
        elif key == Qt.Key.Key_P:
            but = self._but_pro
        elif key == Qt.Key.Key_K:
            but = self._but_key_rel
        elif key == Qt.Key.Key_E:
            but = self._but_enter
        elif key == Qt.Key.Key_R:
            but = self._but_reset

        if but is None:
            return

        if down:
            but.press()
        else:
            but.release()

def main():
    ap = argparse.ArgumentParser(description='Apollo DSKY emulator')
    ap.add_argument('--host', default='localhost', help='yaAGC host (default: localhost)')
    ap.add_argument('--port', type=int, default=19697, help='yaAGC port (default: 19697)')
    ap.add_argument('--vehicle', choices=['CM', 'LM', 'cm', 'lm'], default=None,
                    help='Vehicle designation (default: auto-detect from port)')
    ap.add_argument('--software', default=None,
                    help='AGC software name (default: inferred from vehicle)')
    args = ap.parse_args()

    app = QApplication(sys.argv)
    window = DSKY(None, host=args.host, port=args.port,
                  vehicle=args.vehicle, software=args.software)
    window.show()
    app.exec()


if __name__ == '__main__':
    main()


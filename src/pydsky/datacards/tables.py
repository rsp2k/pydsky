"""Table widgets for the DSKY data cards — cream paper aesthetic.

Custom QWidget rows in QScrollArea for full printed-card control.
Each row = QFrame + QHBoxLayout of QLabels.
"""

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

# Design tokens — evokes original Delco card stock
CARD_BG = "#F5F0E8"
ALT_ROW = "#EDE8E0"
RULE_COLOR = "#C8BDA8"
SECTION_BG = "#E8E3DB"
TEXT_PRIMARY = "#2C2C2C"
TEXT_HEADER = "#5A4A3A"
TEXT_DIM = "#8A7A6A"
FONT_FAMILY = "'Courier Prime', 'Courier New', monospace"


class CardTable(QWidget):
    """Base scrollable table with cream paper aesthetic."""

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background: {CARD_BG}; }}"
            f"QScrollBar:vertical {{ background: {CARD_BG}; width: 8px; }}"
            f"QScrollBar::handle:vertical {{ background: {RULE_COLOR}; border-radius: 4px; min-height: 20px; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
        )

        self._content = QWidget()
        self._content.setStyleSheet(f"background: {CARD_BG};")
        self._rows = QVBoxLayout(self._content)
        self._rows.setContentsMargins(8, 4, 8, 4)
        self._rows.setSpacing(0)

        self._scroll.setWidget(self._content)
        outer.addWidget(self._scroll)
        self._row_idx = 0

    def _label(self, text, width=0, color=TEXT_PRIMARY, bold=False, size=10):
        """Create a styled monospace QLabel."""
        lbl = QLabel(text)
        weight = "bold" if bold else "normal"
        lbl.setStyleSheet(
            f"font-family: {FONT_FAMILY}; font-size: {size}px; "
            f"color: {color}; font-weight: {weight}; "
            f"background: transparent; padding: 0; margin: 0;"
        )
        if width:
            lbl.setFixedWidth(width)
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return lbl

    def _add_header(self, specs):
        """Add column header row. specs = [(text, width), ...], width=0 stretches."""
        row = QFrame()
        row.setStyleSheet(f"background: {SECTION_BG}; border-bottom: 1px solid {RULE_COLOR};")
        row.setFixedHeight(22)
        h = QHBoxLayout(row)
        h.setContentsMargins(4, 2, 4, 2)
        h.setSpacing(6)
        for text, width in specs:
            lbl = self._label(text, width, TEXT_HEADER, bold=True, size=9)
            if width:
                h.addWidget(lbl)
            else:
                h.addWidget(lbl, 1)
        self._rows.addWidget(row)

    def _add_section(self, title):
        """Add a section divider with title."""
        row = QFrame()
        row.setStyleSheet(
            f"background: {SECTION_BG}; "
            f"border-top: 1px solid {RULE_COLOR}; border-bottom: 1px solid {RULE_COLOR};"
        )
        row.setFixedHeight(20)
        h = QHBoxLayout(row)
        h.setContentsMargins(4, 2, 4, 2)
        h.addWidget(self._label(f"\u2014 {title} \u2014", 0, TEXT_HEADER, bold=True, size=9))
        self._rows.addWidget(row)

    def _add_row(self, specs, alt=False):
        """Add data row. specs = [(text, width, color), ...], width=0 stretches."""
        bg = ALT_ROW if alt else CARD_BG
        row = QFrame()
        row.setStyleSheet(f"background: {bg}; border-bottom: 1px solid {RULE_COLOR};")
        row.setMinimumHeight(18)
        h = QHBoxLayout(row)
        h.setContentsMargins(4, 1, 4, 1)
        h.setSpacing(6)
        for text, width, color in specs:
            lbl = self._label(text, width, color)
            if width:
                h.addWidget(lbl)
            else:
                lbl.setWordWrap(True)
                h.addWidget(lbl, 1)
        self._rows.addWidget(row)
        self._row_idx += 1

    def _finalize(self):
        """Push rows to the top."""
        self._rows.addStretch(1)


class VerbTable(CardTable):
    """Two-column verb table: regular (V00-V39) + extended (V40-V99)."""

    def __init__(self, verbs, parent=None):
        super().__init__(parent)
        cw = 45
        self._add_header([("CODE", cw), ("DESCRIPTION", 0)])

        self._add_section("REGULAR VERBS (V00\u2013V39)")
        for v in verbs["regular"]:
            alt = self._row_idx % 2 == 1
            self._add_row([(f"V{v['code']}", cw, TEXT_DIM), (v["desc"], 0, TEXT_PRIMARY)], alt)

        self._row_idx = 0
        self._add_section("EXTENDED VERBS (V40\u2013V99)")
        for v in verbs["extended"]:
            alt = self._row_idx % 2 == 1
            self._add_row([(f"V{v['code']}", cw, TEXT_DIM), (v["desc"], 0, TEXT_PRIMARY)], alt)

        self._finalize()


class NounTable(CardTable):
    """Multi-column noun table with register sub-rows for scaling info."""

    def __init__(self, nouns, parent=None):
        super().__init__(parent)
        code_w, comp_w, restr_w = 40, 28, 22
        self._add_header([("CODE", code_w), ("C", comp_w), ("DESCRIPTION", 0), ("R", restr_w)])

        for noun in nouns:
            alt = self._row_idx % 2 == 1
            bg = ALT_ROW if alt else CARD_BG
            comp_str = str(noun["comp"]) if noun["comp"] else ""

            # Primary row: code | comp | description | restriction
            self._add_row([
                (f"N{noun['code']}", code_w, TEXT_DIM),
                (comp_str, comp_w, TEXT_DIM),
                (noun["desc"], 0, TEXT_PRIMARY),
                (noun["restr"], restr_w, TEXT_DIM),
            ], alt)

            # Register sub-rows (indented, dimmer, smaller)
            for i, scale in enumerate(noun.get("scales", [])):
                sub = QFrame()
                sub.setStyleSheet(f"background: {bg};")
                sub.setFixedHeight(15)
                h = QHBoxLayout(sub)
                h.setContentsMargins(4, 0, 4, 0)
                h.setSpacing(6)
                h.addSpacing(code_w)
                h.addWidget(self._label(f"R{i + 1}", comp_w, TEXT_DIM, size=9))
                h.addWidget(self._label(scale, 0, TEXT_DIM, size=9), 1)
                h.addSpacing(restr_w)
                self._rows.addWidget(sub)

        self._finalize()


class ProgramTable(CardTable):
    """Program table grouped by mission phase."""

    def __init__(self, programs, parent=None):
        super().__init__(parent)
        cw = 40
        self._add_header([("CODE", cw), ("DESCRIPTION", 0)])

        current_group = None
        for p in programs:
            if p.get("group") != current_group:
                current_group = p["group"]
                self._add_section(current_group)
                self._row_idx = 0
            alt = self._row_idx % 2 == 1
            self._add_row([(f"P{p['code']}", cw, TEXT_DIM), (p["desc"], 0, TEXT_PRIMARY)], alt)

        self._finalize()


class AlarmTable(CardTable):
    """Alarm code table with POODOO/BAILOUT severity indicators."""

    def __init__(self, alarms, parent=None):
        super().__init__(parent)
        code_w, sev_w = 55, 58
        self._add_header([("CODE", code_w), ("DESCRIPTION", 0), ("TYPE", sev_w)])

        for a in alarms:
            alt = self._row_idx % 2 == 1
            sev = a.get("severity", "")
            sev_color = "#AA3333" if sev == "POODOO" else "#AA6633" if sev == "BAILOUT" else TEXT_DIM
            self._add_row([
                (a["code"], code_w, TEXT_DIM),
                (a["desc"], 0, TEXT_PRIMARY),
                (sev, sev_w, sev_color),
            ], alt)

        self._finalize()


class RoutineTable(CardTable):
    """Two-column routine table."""

    def __init__(self, routines, parent=None):
        super().__init__(parent)
        cw = 40
        self._add_header([("CODE", cw), ("DESCRIPTION", 0)])

        for r in routines:
            alt = self._row_idx % 2 == 1
            self._add_row([(f"R{r['code']}", cw, TEXT_DIM), (r["desc"], 0, TEXT_PRIMARY)], alt)

        self._finalize()

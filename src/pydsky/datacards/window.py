"""Main window for the DSKY data cards companion."""

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QFrame, QLabel, QMainWindow, QTabWidget, QVBoxLayout, QWidget

from pydsky.datacards.data import get_data
from pydsky.datacards.tables import (
    CARD_BG,
    FONT_FAMILY,
    AlarmTable,
    NounTable,
    ProgramTable,
    RoutineTable,
    VerbTable,
)

TITLE_BG = "#4A4440"
TITLE_TEXT = "#F5F0E8"
CM_ACCENT = "#5588AA"
LM_ACCENT = "#CC9933"


class DataCardWindow(QMainWindow):
    """Tabbed reference window — faithful to the original Delco data cards."""

    def __init__(self, vehicle, software):
        super().__init__()
        accent = CM_ACCENT if vehicle == "CM" else LM_ACCENT

        self.setWindowTitle(f"DATA CARDS \u2014 {vehicle} {software}")
        self.setFixedSize(420, 640)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Dark title strip
        title = QLabel(f"  APOLLO {vehicle} DATA CARDS")
        title.setFixedHeight(30)
        title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        title.setStyleSheet(
            f"background: {TITLE_BG}; color: {TITLE_TEXT}; "
            f"font-family: {FONT_FAMILY}; font-size: 12px; "
            f"font-weight: bold; letter-spacing: 2px;"
        )
        layout.addWidget(title)

        # Software version sub-line (vehicle accent color)
        sub = QLabel(f"  {software}")
        sub.setFixedHeight(16)
        sub.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        sub.setStyleSheet(
            f"background: {TITLE_BG}; color: {accent}; "
            f"font-family: {FONT_FAMILY}; font-size: 9px; "
            f"letter-spacing: 1px;"
        )
        layout.addWidget(sub)

        # Vehicle accent stripe
        stripe = QFrame()
        stripe.setFixedHeight(3)
        stripe.setStyleSheet(f"background: {accent};")
        layout.addWidget(stripe)

        # Assemble data for this vehicle
        data = get_data(vehicle, software)

        # Tabbed interface
        tabs = QTabWidget()
        tabs.setStyleSheet(
            f"QTabWidget::pane {{ border: none; background: {CARD_BG}; }}"
            f"QTabBar {{ background: {CARD_BG}; }}"
            f"QTabBar::tab {{"
            f"  background: #E8E3DB; color: #5A4A3A;"
            f"  padding: 5px 10px; margin-right: 1px;"
            f"  font-family: {FONT_FAMILY}; font-size: 9px;"
            f"  font-weight: bold; letter-spacing: 1px;"
            f"  border: none; border-bottom: 2px solid transparent;"
            f"}}"
            f"QTabBar::tab:selected {{"
            f"  background: {CARD_BG}; color: #2C2C2C;"
            f"  border-bottom: 2px solid {accent};"
            f"}}"
            f"QTabBar::tab:hover {{ background: #EDE8E0; }}"
        )

        tabs.addTab(VerbTable(data["verbs"]), "VERBS")
        tabs.addTab(NounTable(data["nouns"]), "NOUNS")
        tabs.addTab(ProgramTable(data["programs"]), "PROGRAMS")
        tabs.addTab(AlarmTable(data["alarms"]), "ALARMS")
        tabs.addTab(RoutineTable(data["routines"]), "ROUTINES")

        layout.addWidget(tabs)

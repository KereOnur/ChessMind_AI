"""Shared visual language for the German NeuroChess setup interface."""
from PySide6.QtWidgets import QWidget

STYLE = '''
QDialog { background: #0b1525; color: #edf3ff; }
QLineEdit, QComboBox { background: #17283f; color: #edf3ff; border: 1px solid #42658b; border-radius: 6px; padding: 7px; }
QComboBox QAbstractItemView { background: #14233a; color: #edf3ff; selection-background-color: #237ce5; }

QFrame#playerBar { background: #101e30; border: 1px solid #2a4059; border-radius: 8px; }
QLabel#playerName { font-size: 13px; font-weight: 600; }
QLabel#staticClock { font-family: Menlo; font-size: 23px; font-weight: 700; color: #f0f7ff; }
QLabel#captureCaption { color: #a8bad0; font-size: 10px; }
QLabel#moveExample { color: #d5e6fb; font-size: 12px; }
QLabel#previewTitle { font-size: 23px; font-weight: 700; }
QLabel#previewBanner { color: #8ce4ff; background: #10263a; border: 1px solid #285779; border-radius: 7px; padding: 7px 10px; font-size: 12px; font-weight: 600; }

QMainWindow, QStackedWidget, QWidget#pageCanvas {
    background: #080f1d; color: #edf3ff;
}
QScrollArea { background: #080f1d; border: none; }
QLabel { color: #edf3ff; background: transparent; }
QLabel#eyebrow { color: #61aaff; font-size: 11px; font-weight: 700; letter-spacing: 2px; }
QLabel#brand { color: #f3f7ff; font-size: 46px; font-weight: 700; letter-spacing: -1px; }
QLabel#pageTitle { font-size: 34px; font-weight: 700; letter-spacing: -0.5px; }
QLabel#subtitle { color: #9aacc5; font-size: 14px; }
QLabel#smallText { color: #91a4be; font-size: 12px; }
QLabel#cardTitle { font-size: 23px; font-weight: 700; }
QLabel#cardDescription { color: #b0bfd2; font-size: 14px; }
QLabel#cardAction { color: #78b7ff; font-size: 13px; font-weight: 600; }
QLabel#navTitle { font-size: 17px; font-weight: 600; }
QLabel#navSubtitle { color: #92a6c1; font-size: 12px; }
QLabel#notice { color: #b9cdeb; font-size: 13px; padding: 12px;
    background: #111f34; border: 1px solid #263d5b; border-radius: 10px; }
QFrame#heroPanel { background: #0d1829; border: 1px solid #20324c; border-radius: 22px; }
QLabel#heroTitle { font-size: 31px; font-weight: 650; }
QLabel#chip { color: #8fc2ff; font-size: 12px; padding: 8px 12px;
    background: #112945; border: 1px solid #244a71; border-radius: 8px; }
QPushButton { color: #dbe9fc; background: #122039; border: 1px solid #2a405e;
    border-radius: 11px; padding: 12px 20px; font-size: 14px; font-weight: 600; }
QPushButton:hover { background: #192e4b; border-color: #529ef5; }
QPushButton:pressed { background: #0e1b30; }
QPushButton:focus { border: 2px solid #82bdff; }
QPushButton#primaryButton { color: #fff; background: #237ce5; border-color: #388ff3; }
QPushButton#primaryButton:hover { background: #338df4; }
QPushButton#primaryButton:pressed { background: #1c67c0; }
QPushButton#primaryButton:disabled { background: #1b2b40; color: #8c9eb8; border-color: #2b3d55; }
QPushButton#backButton { color: #adc6e6; background: transparent; border-color: #293d56; }
QPushButton#navButton { background: #101d30; border: 1px solid #20344f;
    border-radius: 12px; padding: 15px 17px; text-align: left; }
QPushButton#navButton:hover { background: #162c48; border-color: #3c8ceb; }
QPushButton#navButton[primary="true"] { background: #2078e1; border-color: #429bff; }
QPushButton#navButton[primary="true"]:hover { background: #2c89f4; }
QPushButton#navButton[primary="true"] QLabel#navSubtitle { color: #e0edff; }
QPushButton#opponentCard, QPushButton#colorCard { background: #101d30;
    border: 1px solid #2b3e57; border-radius: 17px; padding: 0px; }
QPushButton#opponentCard:hover, QPushButton#colorCard:hover { border: 1px solid #63adff; background: #14243a; }
QPushButton#opponentCard[selected="true"], QPushButton#colorCard[selected="true"] {
    border: 2px solid #429bff; background: #132942; }
QFrame#summaryPanel { background: #101e32; border: 1px solid #294463; border-radius: 18px; }
QLabel#summaryValue { font-size: 21px; font-weight: 600; }
QScrollBar:vertical { background: #0b1525; width: 9px; margin: 3px 0; }
QScrollBar::handle:vertical { background: #324e70; min-height: 36px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
'''


def set_selected(widget: QWidget, selected: bool) -> None:
    widget.setProperty('selected', selected)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()

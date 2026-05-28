"""
setup.py: Launch configuration dialog.

User picks which books to monitor (any two or more) and sets total bet size.
"""

import platform

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QLineEdit, QApplication, QWidget,
)
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QFont, QIntValidator

BG      = '#080808'
RAISED  = '#161616'
BORDER  = '#1e1e1e'
BORDER2 = '#2a2a2a'

WHITE   = '#ffffff'
CREAM   = '#f0ede8'
GREY1   = '#bbbbbb'
GREY2   = '#666666'
GREY3   = '#333333'

GREEN   = '#00e676'
RED     = '#ff3b3b'

_SYS  = 'Darwin' if platform.system() == 'Darwin' else 'other'
_SANS = 'SF Pro Display' if _SYS == 'Darwin' else 'Helvetica Neue'
_MONO = 'SF Mono'        if _SYS == 'Darwin' else 'Menlo'


def _font(size=11, weight=QFont.Normal, mono=False) -> QFont:
    f = QFont(_MONO if mono else _SANS)
    f.setPointSize(size)
    f.setWeight(weight)
    return f

BOOKS = [
    {'id': 'pinnacle',   'label': 'Pinnacle',   'abbr': 'PIN', 'default': True},
    {'id': 'betmgm',     'label': 'BetMGM',     'abbr': 'MGM', 'default': True},
    {'id': 'draftkings', 'label': 'DraftKings', 'abbr': 'DK',  'default': False},
    {'id': 'thescore',   'label': 'theScore',   'abbr': 'tS',  'default': False},
    {'id': 'betway',     'label': 'Betway',     'abbr': 'BW',  'default': False},
    {'id': 'fanduel',    'label': 'FanDuel',    'abbr': 'FD',  'default': False},
    {'id': 'bet365',     'label': 'bet365',     'abbr': '365', 'default': False},
]

class BookCard(QPushButton):

    def __init__(self, book: dict):
        super().__init__()
        self.book_id   = book['id']
        self._selected = book['default']
        self._err      = False

        self.setFixedSize(92, 68)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)

        col = QVBoxLayout(self)
        col.setContentsMargins(6, 8, 6, 8)
        col.setSpacing(4)
        col.setAlignment(Qt.AlignCenter)

        self._abbr_lbl = QLabel(book['abbr'])
        self._abbr_lbl.setAlignment(Qt.AlignCenter)
        self._abbr_lbl.setFont(_font(13, QFont.Bold, mono=True))
        col.addWidget(self._abbr_lbl)

        self._name_lbl = QLabel(book['label'])
        self._name_lbl.setAlignment(Qt.AlignCenter)
        self._name_lbl.setFont(_font(8))
        col.addWidget(self._name_lbl)

        self._refresh()
        self.clicked.connect(self._toggle)

    def _toggle(self):
        self._selected = not self._selected
        self._err      = False
        self._refresh()

    def _refresh(self):
        if self._err:
            self.setStyleSheet(
                f'QPushButton {{'
                f'  background: {BG}; border: 1px solid rgba(255,59,59,0.6);'
                f'  border-radius: 4px;'
                f'}}'
            )
            self._abbr_lbl.setStyleSheet(f'color: {GREY2}; background: transparent;')
            self._name_lbl.setStyleSheet(f'color: {GREY3}; background: transparent;')

        elif self._selected:
            self.setStyleSheet(
                f'QPushButton {{'
                f'  background: {CREAM}; border: none; border-radius: 4px;'
                f'}}'
            )
            self._abbr_lbl.setStyleSheet('color: #111111; background: transparent;')
            self._name_lbl.setStyleSheet('color: #333333; background: transparent;')

        else:
            self.setStyleSheet(
                f'QPushButton {{'
                f'  background: {RAISED}; border: 1px solid {BORDER2};'
                f'  border-radius: 4px;'
                f'}}'
                f'QPushButton:hover {{ border-color: {GREY2}; }}'
            )
            self._abbr_lbl.setStyleSheet(f'color: {GREY2}; background: transparent;')
            self._name_lbl.setStyleSheet(f'color: {GREY3}; background: transparent;')

    def mark_error(self):
        self._err = True
        self._refresh()

    @property
    def selected(self) -> bool:
        return self._selected

class SetupDialog(QDialog):

    _STYLE = f"""
        QDialog {{
            background: {BG};
            border: 1px solid {BORDER2};
            border-radius: 6px;
        }}
        QLineEdit {{
            background: {RAISED};
            border: 1px solid {BORDER2};
            border-radius: 4px;
            color: {WHITE};
            padding: 7px 12px;
            font-family: '{_MONO}';
            font-size: 14px;
        }}
        QLineEdit:focus {{ border-color: {WHITE}; }}
    """

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setStyleSheet(self._STYLE)
        self.setFixedWidth(420)

        self._drag_pos: QPoint | None = None
        self.result_config: dict | None = None

        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
        root.addWidget(self._build_body())

    def _build_header(self):
        hdr = QWidget()
        hdr.setFixedHeight(38)
        hdr.setStyleSheet(
            f'background: {BG}; border-bottom: 1px solid {BORDER}; '
            f'border-radius: 6px 6px 0 0;'
        )
        row = QHBoxLayout(hdr)
        row.setContentsMargins(16, 0, 16, 0)
        row.setSpacing(0)

        dot = QLabel('●')
        dot.setFont(_font(7))
        dot.setStyleSheet(f'color: {GREEN}; background: transparent;')
        row.addWidget(dot)
        row.addSpacing(8)

        title = QLabel('ARB SCANNER')
        title.setFont(_font(10, QFont.DemiBold))
        title.setStyleSheet(
            f'color: {GREY2}; letter-spacing: 2px; font-weight: 600; background: transparent;'
        )
        row.addWidget(title)
        row.addStretch()

        sub = QLabel('Setup')
        sub.setFont(_font(9))
        sub.setStyleSheet(f'color: {GREY3}; background: transparent;')
        row.addWidget(sub)

        return hdr

    def _build_body(self):
        body = QWidget()
        body.setStyleSheet(f'background: {BG}; border-radius: 0 0 6px 6px;')
        col = QVBoxLayout(body)
        col.setContentsMargins(20, 20, 20, 20)
        col.setSpacing(18)

        col.addWidget(self._section_label('BOOKS  ·  select 2 or more'))

        self._book_cards = []
        grid = QGridLayout()
        grid.setSpacing(6)
        for idx, book in enumerate(BOOKS):
            card = BookCard(book)
            self._book_cards.append(card)
            grid.addWidget(card, idx // 4, idx % 4)
        col.addLayout(grid)

        self._error_lbl = QLabel('Select at least 2 books')
        self._error_lbl.setFont(_font(9))
        self._error_lbl.setStyleSheet(f'color: {RED}; background: transparent;')
        self._error_lbl.hide()
        col.addWidget(self._error_lbl)

        div = QWidget()
        div.setFixedHeight(1)
        div.setStyleSheet(f'background: {BORDER};')
        col.addWidget(div)

        col.addWidget(self._section_label('TOTAL BET SIZE'))
        stake_row = QHBoxLayout()
        stake_row.setSpacing(8)

        dollar = QLabel('$')
        dollar.setFont(_font(14, QFont.Medium, mono=True))
        dollar.setStyleSheet(f'color: {GREY1}; background: transparent;')

        self._stake_input = QLineEdit('100')
        self._stake_input.setValidator(QIntValidator(1, 100000))
        self._stake_input.setFixedWidth(110)
        self._stake_input.setFont(_font(14, mono=True))

        hint = QLabel('split across both sides')
        hint.setFont(_font(9))
        hint.setStyleSheet(f'color: {GREY2}; background: transparent;')

        stake_row.addWidget(dollar)
        stake_row.addWidget(self._stake_input)
        stake_row.addSpacing(10)
        stake_row.addWidget(hint)
        stake_row.addStretch()
        col.addLayout(stake_row)

        self._start_btn = QPushButton('START SCANNING')
        self._start_btn.setFixedHeight(42)
        self._start_btn.setCursor(Qt.PointingHandCursor)
        self._start_btn.setFocusPolicy(Qt.NoFocus)
        self._start_btn.setFont(_font(11, QFont.Bold))
        self._start_btn.setStyleSheet(f"""
            QPushButton {{
                background: {WHITE}; color: #080808;
                border: none; border-radius: 4px;
                font-size: 11px; font-weight: 700;
                letter-spacing: 2px;
            }}
            QPushButton:hover   {{ background: {CREAM}; }}
            QPushButton:pressed {{ background: #d0cdc8; }}
        """)
        self._start_btn.clicked.connect(self._on_start)
        col.addWidget(self._start_btn)

        return body

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(_font(9, QFont.DemiBold))
        lbl.setStyleSheet(f'color: {GREY2}; letter-spacing: 1.5px; background: transparent;')
        return lbl

    def _on_start(self):
        selected = [c.book_id for c in self._book_cards if c.selected]
        if len(selected) < 2:
            self._error_lbl.show()
            for card in self._book_cards:
                if not card.selected:
                    card.mark_error()
            self.adjustSize()
            return

        self._error_lbl.hide()
        try:
            stake = int(self._stake_input.text())
        except ValueError:
            stake = 100

        self.result_config = {'books': selected, 'total_stake': float(stake)}
        self.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPos() - self._drag_pos)

    def mouseReleaseEvent(self, _event):
        self._drag_pos = None
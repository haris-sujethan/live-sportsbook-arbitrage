"""
gui.py — Minimal dark overlay. Black/white with green/yellow indicator only.
"""

import platform

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QPushButton, QApplication, QSizePolicy,
)
from PyQt5.QtCore import Qt, QPoint, QTimer, pyqtSlot
from PyQt5.QtGui import QFont

from worker import State


# ─── Palette ──────────────────────────────────────────────────────────────────

BG       = '#080808'
SURFACE  = '#101010'
RAISED   = '#161616'
BORDER   = '#1e1e1e'
BORDER2  = '#2a2a2a'

WHITE    = '#ffffff'
GREY1    = '#bbbbbb'
GREY2    = '#666666'
GREY3    = '#333333'

GREEN    = '#00e676'
YELLOW   = '#ffd000'
RED      = '#ff3b3b'

GREEN_BG  = 'rgba(0,230,118,0.07)'
GREEN_BDR = 'rgba(0,230,118,0.25)'


# ─── Book metadata ─────────────────────────────────────────────────────────────

_BOOK_META = {
    'pinnacle':   {'name': 'Pinnacle',   'abbr': 'PIN'},
    'betmgm':     {'name': 'BetMGM',     'abbr': 'MGM'},
    'draftkings': {'name': 'DraftKings', 'abbr': 'DK'},
    'thescore':   {'name': 'theScore',   'abbr': 'tS'},
    'betway':     {'name': 'Betway',     'abbr': 'BW'},
    'fanduel':    {'name': 'FanDuel',    'abbr': 'FD'},
    'bet365':     {'name': 'bet365',     'abbr': '365'},
}

def _book_name(b: str) -> str:
    return _BOOK_META.get(b.lower(), {}).get('name', b.capitalize())

def _book_abbr(b: str) -> str:
    return _BOOK_META.get(b.lower(), {}).get('abbr', b[:3].upper())


# ─── Typography ───────────────────────────────────────────────────────────────

_SYS   = 'Darwin' if platform.system() == 'Darwin' else 'other'
_SANS  = 'SF Pro Display'  if _SYS == 'Darwin' else 'Helvetica Neue'
_MONO  = 'SF Mono'         if _SYS == 'Darwin' else 'Menlo'

def _f(size=11, w=QFont.Normal, mono=False) -> QFont:
    f = QFont(_MONO if mono else _SANS)
    f.setPointSize(size)
    f.setWeight(w)
    return f

def L(text='', size=11, color=WHITE, w=QFont.Normal, mono=False, align=None) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(_f(size, w, mono))
    lbl.setStyleSheet(f'color: {color}; background: transparent;')
    if align is not None:
        lbl.setAlignment(align)
    return lbl

def hline(color=BORDER) -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setFrameShadow(QFrame.Plain)
    f.setFixedHeight(1)
    f.setStyleSheet(f'background: {color}; border: none;')
    return f


# ─── Main window ──────────────────────────────────────────────────────────────

class ArbOverlay(QMainWindow):

    _STYLE = f"""
        QMainWindow {{ background: {BG}; }}
        #central {{
            background: {BG};
            border: 1px solid {BORDER2};
            border-radius: 4px;
        }}
        #close_btn {{
            background: transparent;
            color: {GREY3};
            border: none;
            font-size: 13px;
            padding: 0;
        }}
        #close_btn:hover {{ color: {GREY2}; }}
    """

    def __init__(self, config: dict | None = None):
        super().__init__()
        cfg = config or {}
        self._total_stake:  float = float(cfg.get('total_stake', 100.0))
        self._config_books: list  = cfg.get('books', ['betmgm'])

        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setStyleSheet(self._STYLE)
        self.setFixedWidth(440)

        self._drag_pos: QPoint | None = None
        self._current_state = State.WAITING
        self._pulse_phase   = True

        self._build()
        self._position()

        self._pulse_tmr = QTimer(self)
        self._pulse_tmr.timeout.connect(self._tick_pulse)
        self._pulse_tmr.start(700)

        self._update_secs = 0
        self._update_tmr = QTimer(self)
        self._update_tmr.timeout.connect(self._tick_update)
        self._update_tmr.start(1000)

        # Re-apply NSFloatingWindowLevel every second.
        # macOS resets window levels when you switch apps; this restores it.
        # setLevel_ does NOT steal focus or intercept clicks — safe to run frequently.
        self._top_tmr = QTimer(self)
        self._top_tmr.timeout.connect(self._set_macos_level)
        self._top_tmr.start(1000)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(200, self._set_macos_level)

    def _set_macos_level(self):
        if platform.system() != 'Darwin':
            return
        try:
            import ctypes, ctypes.util
            lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library('objc'))

            lib.sel_registerName.restype  = ctypes.c_void_p
            lib.sel_registerName.argtypes = [ctypes.c_char_p]

            # [nsView window]
            lib.objc_msgSend.restype  = ctypes.c_void_p
            lib.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            ns_view   = ctypes.c_void_p(int(self.winId()))
            ns_window = ctypes.c_void_p(
                lib.objc_msgSend(ns_view, lib.sel_registerName(b'window'))
            )
            if not ns_window:
                return

            # Prevent NSPanel from auto-hiding when our app loses focus.
            # Qt.Tool creates an NSPanel whose hidesOnDeactivate is YES by default —
            # that is exactly why the window vanishes the moment you click Chrome.
            lib.objc_msgSend.restype  = None
            lib.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool]
            lib.objc_msgSend(ns_window,
                             lib.sel_registerName(b'setHidesOnDeactivate:'),
                             ctypes.c_bool(False))

            # Keep window above normal app windows (NSFloatingWindowLevel = 3).
            lib.objc_msgSend.restype  = None
            lib.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
            lib.objc_msgSend(ns_window, lib.sel_registerName(b'setLevel:'), ctypes.c_long(3))
        except Exception:
            pass


    def _position(self):
        screen = QApplication.desktop().availableGeometry()
        self.move(screen.width() - self.width() - 20, 40)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        central = QWidget()
        central.setObjectName('central')
        self.setCentralWidget(central)
        self._root = QVBoxLayout(central)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(0)

        self._build_header()
        self._build_match()
        self._build_overview()
        self._build_arb()
        self._build_status()
        self._build_footer()
        self._show_waiting()

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self):
        hdr = QWidget()
        hdr.setFixedHeight(36)
        hdr.setStyleSheet(f'background: {BG}; border-bottom: 1px solid {BORDER};')

        row = QHBoxLayout(hdr)
        row.setContentsMargins(14, 0, 12, 0)
        row.setSpacing(0)

        self._pulse_dot = L('●', 7, YELLOW)
        row.addWidget(self._pulse_dot)
        row.addSpacing(8)

        title = L('ARB SCANNER', 9, GREY2, QFont.DemiBold)
        title.setStyleSheet(
            f'color: {GREY2}; letter-spacing: 2px; font-weight: 600; background: transparent;'
        )
        row.addWidget(title)
        row.addStretch()

        self._status_lbl = L('WAITING', 9, GREY2, QFont.Medium, mono=True)
        self._status_lbl.setStyleSheet(
            f'color: {GREY2}; font-size: 9px; letter-spacing: 1px; background: transparent;'
        )
        row.addWidget(self._status_lbl)
        row.addSpacing(10)

        btn = QPushButton('✕')
        btn.setObjectName('close_btn')
        btn.setFixedSize(16, 16)
        btn.clicked.connect(self.close)
        row.addWidget(btn)

        self._root.addWidget(hdr)

    # ── Match ─────────────────────────────────────────────────────────────────

    def _build_match(self):
        self._match_w = QWidget()
        self._match_w.setStyleSheet(f'background: {BG};')
        col = QVBoxLayout(self._match_w)
        col.setContentsMargins(16, 14, 16, 12)
        col.setSpacing(6)

        names = QHBoxLayout()
        names.setSpacing(0)

        self._p1_lbl = L('', 17, WHITE, QFont.Bold)
        self._p1_lbl.setMaximumWidth(152)
        self._p1_lbl.setWordWrap(False)

        vs = L('vs', 9, GREY3, align=Qt.AlignCenter)
        vs.setFixedWidth(28)

        self._p2_lbl = L('', 17, WHITE, QFont.Bold)
        self._p2_lbl.setAlignment(Qt.AlignRight)
        self._p2_lbl.setMaximumWidth(152)

        names.addWidget(self._p1_lbl, 1)
        names.addWidget(vs)
        names.addWidget(self._p2_lbl, 1)
        col.addLayout(names)

        meta = QHBoxLayout()
        self._live_dot = L('● LIVE', 8, RED)
        self._live_dot.setStyleSheet(
            f'color: {RED}; font-size: 8px; font-weight: 700; '
            f'letter-spacing: 1px; background: transparent;'
        )
        self._meta_lbl = L('', 8, GREY2, mono=True)
        meta.addWidget(self._live_dot)
        meta.addSpacing(8)
        meta.addWidget(self._meta_lbl)
        meta.addStretch()
        col.addLayout(meta)

        self._root.addWidget(self._match_w)
        self._match_div = hline()
        self._root.addWidget(self._match_div)

    # ── All-books overview grid ───────────────────────────────────────────────

    def _build_overview(self):
        self._ov_w = QWidget()
        self._ov_w.setStyleSheet(f'background: {BG};')
        col = QVBoxLayout(self._ov_w)
        col.setContentsMargins(16, 10, 16, 10)
        col.setSpacing(3)

        # Player-name header row
        hrow = QHBoxLayout()
        hrow.setSpacing(4)
        blank = QWidget(); blank.setFixedWidth(42)
        blank.setStyleSheet('background: transparent;')
        hrow.addWidget(blank)
        self._ov_p1_hdr = L('—', 9, GREY2, align=Qt.AlignCenter)
        self._ov_p2_hdr = L('—', 9, GREY2, align=Qt.AlignCenter)
        hrow.addWidget(self._ov_p1_hdr, 1)
        hrow.addWidget(self._ov_p2_hdr, 1)
        col.addLayout(hrow)

        col.addSpacing(4)
        col.addWidget(hline(BORDER))
        col.addSpacing(2)

        # One row per configured book
        self._ov_rows: dict[str, dict] = {}
        for book in self._config_books:
            row = self._make_ov_row(book)
            self._ov_rows[book] = row
            col.addLayout(row['layout'])
            col.addSpacing(3)

        self._root.addWidget(self._ov_w)
        self._ov_div = hline()
        self._root.addWidget(self._ov_div)

    def _make_ov_row(self, book_id: str) -> dict:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        abbr = L(_book_abbr(book_id), 9, GREY3, mono=True)
        abbr.setFixedWidth(38)
        abbr.setStyleSheet(
            f'color: {GREY3}; font-size: 9px; font-weight: 700; '
            f'letter-spacing: 1px; background: transparent;'
        )

        p1_cell, p1_lbl = self._make_ov_cell()
        p2_cell, p2_lbl = self._make_ov_cell()

        row.addWidget(abbr)
        row.addWidget(p1_cell, 1)
        row.addWidget(p2_cell, 1)

        return {'layout': row, 'abbr': abbr,
                'p1_cell': p1_cell, 'p1_lbl': p1_lbl,
                'p2_cell': p2_cell, 'p2_lbl': p2_lbl}

    def _make_ov_cell(self):
        cell = QWidget()
        cell.setFixedHeight(32)
        cl = QVBoxLayout(cell)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        lbl = L('—', 13, GREY3, QFont.Medium, mono=True, align=Qt.AlignCenter)
        cl.addWidget(lbl)
        cell.setStyleSheet(
            f'background: {RAISED}; border-radius: 3px; border: 1px solid {BORDER};'
        )
        return cell, lbl

    def _update_overview(self, data: dict):
        all_books = data.get('all_books', {})
        ea        = data.get('entry_a', {})
        arb       = data.get('arb')
        book_a    = data.get('book_a', '')
        book_b    = data.get('book_b', '')

        # Column headers — last name of each player
        self._ov_p1_hdr.setText(_last(ea.get('p1_name', '')) or '—')
        self._ov_p2_hdr.setText(_last(ea.get('p2_name', '')) or '—')

        # Which book+side to highlight green
        hl = {}   # book_id → (hl_p1: bool, hl_p2: bool)
        if arb:
            if arb.get('pinnacle_side') == 'home':
                hl[book_a] = (True,  False)
                hl[book_b] = (False, True)
            else:
                hl[book_a] = (False, True)
                hl[book_b] = (True,  False)

        for book, row in self._ov_rows.items():
            entry  = all_books.get(book)
            hl_p1, hl_p2 = hl.get(book, (False, False))

            if entry:
                row['abbr'].setStyleSheet(
                    f'color: {WHITE}; font-size: 9px; font-weight: 700; '
                    f'letter-spacing: 1px; background: transparent;'
                )
                row['p1_lbl'].setText(_fmt(entry.get('p1_odds')))
                row['p2_lbl'].setText(_fmt(entry.get('p2_odds')))
            else:
                row['abbr'].setStyleSheet(
                    f'color: {GREY3}; font-size: 9px; font-weight: 700; '
                    f'letter-spacing: 1px; background: transparent;'
                )
                row['p1_lbl'].setText('—')
                row['p2_lbl'].setText('—')
                hl_p1 = hl_p2 = False

            def _cell_style(hl_flag):
                if hl_flag:
                    return (f'background: {GREEN_BG}; border-radius: 3px; '
                            f'border: 1px solid {GREEN_BDR};')
                return f'background: {RAISED}; border-radius: 3px; border: 1px solid {BORDER};'

            def _lbl_color(hl_flag):
                return GREEN if hl_flag else (WHITE if entry else GREY3)

            row['p1_cell'].setStyleSheet(_cell_style(hl_p1))
            row['p2_cell'].setStyleSheet(_cell_style(hl_p2))
            row['p1_lbl'].setStyleSheet(f'color: {_lbl_color(hl_p1)}; background: transparent;')
            row['p2_lbl'].setStyleSheet(f'color: {_lbl_color(hl_p2)}; background: transparent;')

    # ── Arb alert ─────────────────────────────────────────────────────────────

    def _build_arb(self):
        self._arb_w = QWidget()
        self._arb_w.setStyleSheet(f'background: {BG};')
        outer = QVBoxLayout(self._arb_w)
        outer.setContentsMargins(16, 8, 16, 12)
        outer.setSpacing(0)

        box = QWidget()
        box.setStyleSheet(
            f'background: {GREEN_BG}; '
            f'border: 1px solid {GREEN_BDR}; '
            f'border-radius: 3px;'
        )
        box_col = QVBoxLayout(box)
        box_col.setContentsMargins(12, 10, 12, 10)
        box_col.setSpacing(8)

        top = QHBoxLayout()
        arb_tag = L('ARB', 8, GREEN, QFont.Bold)
        arb_tag.setStyleSheet(
            f'color: {GREEN}; font-size: 8px; font-weight: 700; '
            f'letter-spacing: 2px; background: transparent;'
        )
        self._margin_lbl = L('+0.000%', 13, GREEN, QFont.Bold, mono=True)
        top.addWidget(arb_tag)
        top.addStretch()
        top.addWidget(self._margin_lbl)
        box_col.addLayout(top)

        box_col.addWidget(hline(GREEN_BDR))

        self._arb_row1 = self._make_arb_row()
        self._arb_row2 = self._make_arb_row()
        box_col.addLayout(self._arb_row1['layout'])
        box_col.addLayout(self._arb_row2['layout'])

        box_col.addWidget(hline(GREEN_BDR))

        ret_row = QHBoxLayout()
        ret_lbl = L('RETURN', 8, GREEN, mono=True)
        ret_lbl.setStyleSheet(
            f'color: {GREEN}; font-size: 8px; letter-spacing: 1px; '
            f'font-weight: 600; background: transparent;'
        )
        self._profit_lbl = L('$0.00', 15, GREEN, QFont.Bold, mono=True)
        ret_row.addWidget(ret_lbl)
        ret_row.addStretch()
        ret_row.addWidget(self._profit_lbl)
        box_col.addLayout(ret_row)

        self._stake_lbl = L('', 8, GREEN, mono=True, align=Qt.AlignCenter)
        self._stake_lbl.setStyleSheet(
            f'color: {GREEN}88; font-size: 8px; background: transparent;'
        )
        box_col.addWidget(self._stake_lbl)

        outer.addWidget(box)
        self._root.addWidget(self._arb_w)

    def _make_arb_row(self) -> dict:
        row = QHBoxLayout()
        row.setSpacing(0)

        book_lbl = L('', 9, WHITE, mono=True)
        book_lbl.setFixedWidth(34)
        book_lbl.setStyleSheet(
            f'color: {WHITE}; font-size: 9px; font-weight: 700; '
            f'letter-spacing: 1px; background: transparent;'
        )

        player = L('', 11, WHITE)
        player.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # Odds and stake shown right-aligned with fixed widths so they line up
        price = L('', 12, GREEN, QFont.Bold, mono=True, align=Qt.AlignRight)
        price.setFixedWidth(60)

        sep = L('·', 9, GREY3, align=Qt.AlignCenter)
        sep.setFixedWidth(16)

        stake = L('', 11, WHITE, QFont.Medium, mono=True, align=Qt.AlignRight)
        stake.setFixedWidth(54)

        row.addWidget(book_lbl)
        row.addWidget(player)
        row.addStretch()
        row.addWidget(price)
        row.addWidget(sep)
        row.addWidget(stake)

        return {'layout': row, 'book': book_lbl, 'player': player,
                'price': price, 'stake': stake}

    # ── Status ────────────────────────────────────────────────────────────────

    def _build_status(self):
        self._status_w = QWidget()
        self._status_w.setStyleSheet(f'background: {BG};')
        col = QVBoxLayout(self._status_w)
        col.setContentsMargins(16, 16, 16, 16)
        col.setSpacing(12)

        self._status_msg = L('', 12, GREY1, QFont.Medium, align=Qt.AlignCenter)
        self._status_msg.setWordWrap(True)
        col.addWidget(self._status_msg)

        self._book_rows: dict[str, dict] = {}
        for book in self._config_books:
            row = self._make_book_status_row(book)
            self._book_rows[book] = row
            col.addLayout(row['layout'])

        self._root.addWidget(self._status_w)

    def _make_book_status_row(self, book_id: str) -> dict:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)

        dot    = L('○', 9, GREY3)
        badge  = L(_book_abbr(book_id), 9, GREY2, mono=True)
        badge.setStyleSheet(
            f'color: {GREY2}; font-size: 9px; font-weight: 700; '
            f'letter-spacing: 1px; background: transparent;'
        )
        name   = L(_book_name(book_id), 11, GREY1)
        status = L('waiting', 9, GREY3, mono=True, align=Qt.AlignRight)
        status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        row.addWidget(dot)
        row.addSpacing(6)
        row.addWidget(badge)
        row.addSpacing(5)
        row.addWidget(name)
        row.addStretch()
        row.addWidget(status)

        return {'layout': row, 'dot': dot, 'name': name,
                'badge': badge, 'status': status}

    def _update_book_row(self, row: dict, detected: bool):
        if detected:
            row['dot'].setText('●')
            row['dot'].setStyleSheet(f'color: {GREEN}; background: transparent;')
            row['status'].setText('live')
            row['status'].setStyleSheet(f'color: {GREEN}; font-size: 9px; background: transparent;')
        else:
            row['dot'].setText('○')
            row['dot'].setStyleSheet(f'color: {GREY3}; background: transparent;')
            row['status'].setText('waiting')
            row['status'].setStyleSheet(f'color: {GREY3}; font-size: 9px; background: transparent;')

    # ── Footer ────────────────────────────────────────────────────────────────

    def _build_footer(self):
        ftr = QWidget()
        ftr.setFixedHeight(26)
        ftr.setStyleSheet(f'background: {BG}; border-top: 1px solid {BORDER};')

        row = QHBoxLayout(ftr)
        row.setContentsMargins(14, 0, 14, 0)
        row.setSpacing(0)

        for i, book in enumerate(self._config_books):
            chip = QLabel(_book_abbr(book))
            chip.setStyleSheet(
                f'color: {GREY2}; font-size: 7px; font-weight: 700; '
                f'letter-spacing: 1px; border: 1px solid {BORDER2}; '
                f'border-radius: 2px; padding: 1px 4px; background: transparent;'
            )
            row.addWidget(chip)
            if i < len(self._config_books) - 1:
                row.addSpacing(4)

        row.addStretch()

        self._update_lbl = L('—', 8, GREY3, mono=True)
        row.addWidget(self._update_lbl)

        self._root.addWidget(ftr)

    # ── State switching ───────────────────────────────────────────────────────

    def _hide_all(self):
        for w in (self._match_w, self._match_div,
                  self._ov_w,    self._ov_div,
                  self._arb_w,   self._status_w):
            w.hide()

    @pyqtSlot(str, dict)
    def on_update(self, state: str, data: dict):
        self._current_state = state
        self._update_secs   = 0
        if   state == State.WAITING:   self._show_waiting()
        elif state == State.PARTIAL:   self._show_partial(data)
        elif state == State.MISMATCH:  self._show_mismatch(data)
        elif state == State.SCANNING:  self._show_scanning(data)
        elif state == State.ARB_FOUND: self._show_arb(data)
        self.adjustSize()

    def _set_header(self, text: str, color: str):
        self._status_lbl.setText(text)
        self._status_lbl.setStyleSheet(
            f'color: {color}; font-size: 9px; letter-spacing: 1px; background: transparent;'
        )

    def _show_waiting(self):
        self._hide_all()
        self._status_w.show()
        self._set_header('WAITING', GREY2)
        names = '  ·  '.join(_book_abbr(b) for b in self._config_books)
        self._status_msg.setText(f'Open {names}\non the same live match')
        self._status_msg.setStyleSheet(f'color: {GREY2}; background: transparent;')
        for row in self._book_rows.values():
            self._update_book_row(row, False)

    def _show_partial(self, data: dict):
        self._hide_all()
        self._status_w.show()
        self._set_header('PARTIAL', GREY1)
        self._status_msg.setText('Waiting for all books…')
        self._status_msg.setStyleSheet(f'color: {GREY2}; background: transparent;')
        bs = data.get('books_status', {})
        for book, row in self._book_rows.items():
            self._update_book_row(row, bs.get(book, False))

    def _show_mismatch(self, data: dict):
        self._hide_all()
        self._status_w.show()
        self._set_header('MISMATCH', GREY1)
        self._status_msg.setText('Different matches — sync tabs')
        self._status_msg.setStyleSheet(f'color: {GREY2}; background: transparent;')
        for row in self._book_rows.values():
            self._update_book_row(row, True)

    def _show_scanning(self, data: dict):
        self._hide_all()
        self._match_w.show(); self._match_div.show()
        self._ov_w.show();    self._ov_div.show()
        self._set_header('SCANNING', GREY1)
        self._fill_match(data)
        self._update_overview(data)

    def _show_arb(self, data: dict):
        self._hide_all()
        self._match_w.show(); self._match_div.show()
        self._ov_w.show();    self._ov_div.show()
        self._arb_w.show()
        self._set_header('ARB FOUND', GREEN)
        self._fill_match(data)
        self._update_overview(data)
        self._fill_arb(data)

    # ── Data filling ──────────────────────────────────────────────────────────

    def _fill_match(self, data: dict):
        ea = data.get('entry_a', {})
        self._p1_lbl.setText(_shorten(ea.get('p1_name', '?')))
        self._p2_lbl.setText(_shorten(ea.get('p2_name', '?')))

    def _fill_arb(self, data: dict):
        arb    = data.get('arb', {})
        stakes = arb.get('stakes') or {}   # kelly_stakes can return None
        book_a = data.get('book_a', '')
        book_b = data.get('book_b', '')

        self._margin_lbl.setText(f"+{arb.get('margin', 0) * 100:.3f}%")

        a_player = arb.get('book_a_player', '')
        b_player = arb.get('book_b_player', '')
        a_price  = arb.get('pinnacle_price', 0)
        b_price  = arb.get('soft_price', 0)
        stake_a  = stakes.get('stake_a', 0)
        stake_b  = stakes.get('stake_b', 0)

        self._arb_row1['book'].setText(_book_abbr(book_a))
        self._arb_row1['player'].setText(_last(a_player))
        self._arb_row1['price'].setText(_fmt(a_price))
        self._arb_row1['stake'].setText(f'${stake_a}' if stake_a else '—')

        self._arb_row2['book'].setText(_book_abbr(book_b))
        self._arb_row2['player'].setText(_last(b_player))
        self._arb_row2['price'].setText(_fmt(b_price))
        self._arb_row2['stake'].setText(f'${stake_b}' if stake_b else '—')

        profit = stakes.get('profit', 0)
        total  = stakes.get('total', 0)
        ret    = stakes.get('return', 0)
        self._stake_lbl.setText(
            f'${total} staked  ·  +${profit:.2f} profit'
        )
        self._profit_lbl.setText(f'${ret:.2f}')

    # ── Timers ────────────────────────────────────────────────────────────────

    def _tick_pulse(self):
        self._pulse_phase = not self._pulse_phase
        color   = GREEN if self._current_state == State.ARB_FOUND else YELLOW
        opacity = '1.0' if self._pulse_phase else '0.2'
        self._pulse_dot.setStyleSheet(
            f'color: {color}; font-size: 7px; background: transparent; opacity: {opacity};'
        )

    def _tick_update(self):
        self._update_secs += 1
        s = self._update_secs
        self._update_lbl.setText(f'{s}s ago')

    # ── Drag ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(e.globalPos() - self._drag_pos)

    def mouseReleaseEvent(self, _e):
        self._drag_pos = None


# ─── Utilities ────────────────────────────────────────────────────────────────

def _fmt(val, book_id: str = '') -> str:
    """Convert internal decimal odds to American format for display."""
    if val is None:
        return '—'
    try:
        d = float(val)
    except Exception:
        return '—'
    if d < 1.01:
        return '—'
    if d >= 2.0:
        return f'+{round((d - 1) * 100)}'
    return f'{round(-100 / (d - 1))}'


def _shorten(name: str, max_len: int = 15) -> str:
    if len(name) <= max_len:
        return name
    parts = name.split()
    if len(parts) >= 2:
        return f'{parts[0][0]}. {parts[-1]}'
    return name[:max_len]


def _last(name: str) -> str:
    parts = name.strip().split()
    return parts[-1] if parts else name

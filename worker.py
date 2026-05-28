"""
worker.py: Background monitoring thread.

Runs an aiohttp HTTP server on localhost:8765 that receives data POSTed
by the Chrome extension, then evaluates arb and emits Qt signals to the GUI.

All books are treated equally. Any two selected books with data for the same
match are compared for arb. Pinnacle is not mandatory.

"""

import asyncio
import json
import re
import time

from aiohttp import web
from PyQt5.QtCore import QThread, pyqtSignal

from pinnacle import extract_matchup_id, parse_matchup_details, parse_straight_response
from arb import find_best_arb


# Name matching helpers

def _names_match(name_a: str, name_b: str) -> bool:
    if not name_a or not name_b:
        return False
    if _extract_last(name_a) == _extract_last(name_b):
        return True
    def _sig_words(n: str) -> set:
        n = re.sub(r'\s*\([^)]*\)', '', n.strip().lower())
        return {w.rstrip('.') for w in n.split() if len(w.rstrip('.')) >= 4}
    return bool(_sig_words(name_a) & _sig_words(name_b))


def _extract_last(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r'\s*\([^)]*\)', '', name).strip()  
    if ',' in name:
        name = name[:name.index(',')].strip()           
    if '/' in name:
        name = name.split('/')[-1].strip()        
    parts = name.replace('.', '').split()
    substantive = [p for p in parts if len(p) > 1]
    return substantive[-1] if substantive else (parts[-1] if parts else '')


def _make_entry(match_id: str, p1_name: str, p1_odds: float,
                p2_name: str, p2_odds: float) -> dict:
    return {
        'match_id': match_id,
        'p1_name':  p1_name,
        'p1_odds':  p1_odds,
        'p2_name':  p2_name,
        'p2_odds':  p2_odds,
    }


class State:
    WAITING   = 'waiting'
    PARTIAL   = 'partial'
    MISMATCH  = 'mismatch'
    SCANNING  = 'scanning'
    ARB_FOUND = 'arb_found'


class WorkerThread(QThread):
    """
    Runs an asyncio event loop in a background QThread.
    Emits `update(state, data)` whenever arb state changes.
    """

    update = pyqtSignal(str, dict)

    def __init__(self, config: dict | None = None):
        super().__init__()
        cfg = config or {}
        self._total_stake:    float = float(cfg.get('total_stake', 100.0))
        self._selected_books: list  = cfg.get('books', ['pinnacle', 'betmgm'])

        self._running = False
        self._loop:   asyncio.AbstractEventLoop | None = None
        self._runner: web.AppRunner | None = None

        # Unified per-book cache: book → match_id → unified entry
        self._book_caches: dict[str, dict] = {
            b: {} for b in ['pinnacle', 'betmgm', 'thescore', 'draftkings', 'betway', 'fanduel', 'bet365']
        }

        # Pinnacle intermediate state (REST and DOM arrive separately)
        self._pinnacle_matchup_id: str | None  = None
        self._pinnacle_details:    dict | None = None
        self._pinnacle_odds:       dict | None = None

        self._last_state:       str | None   = None
        self._last_logged_odds: tuple | None = None

    # Thread entry point

    def run(self):
        self._running = True
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        except Exception as e:
            print(f'[worker] fatal error: {e}')
        finally:
            self._loop.close()

    def stop(self):
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    async def _main(self):
        app = web.Application()
        app.router.add_post('/', self._handle_post)
        app.router.add_route('OPTIONS', '/', self._handle_options)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, 'localhost', 8765)

        try:
            await site.start()
            print('[worker] Listening on http://localhost:8765')
            print(f'[worker] Monitoring: {", ".join(self._selected_books)}')
        except OSError as e:
            print(f'[worker] Cannot bind port 8765: {e}')
            print('[worker] Is another instance already running?')
            return

        self._emit(State.WAITING, {})

        try:
            while self._running:
                await asyncio.sleep(0.5)
        finally:
            await self._runner.cleanup()

    # HTTP handlers

    async def _handle_options(self, _request: web.Request) -> web.Response:
        return web.Response(headers={
            'Access-Control-Allow-Origin':  '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
        })

    async def _handle_post(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.Response(status=400, text='bad json')

        msg_type = data.get('type', '')

        if msg_type == 'betmgm':
            # WebSocket game updates fire for many isMain=true markets, not only
            # Match Winner. Using them overwrites the correct DOM odds with the
            # wrong market. The betmgmMonitor DOM reader (betmgm_dom_odds) is the
            # authoritative source — skip WebSocket odds entirely.
            pass

        elif msg_type == 'betmgm_dom_odds':
            await self._handle_dom_odds(data, 'betmgm', 'fixtureId')

        elif msg_type == 'pinnacle_dom_odds':
            matchup_id = data.get('matchup_id', '') or self._pinnacle_matchup_id or ''
            try:
                parsed    = json.loads(data.get('body', '{}'))
                home_odds = float(parsed['home_odds'])
                away_odds = float(parsed['away_odds'])
            except Exception:
                return _ok()
            if home_odds < 1.01 or away_odds < 1.01:
                return _ok()

            if matchup_id and matchup_id != self._pinnacle_matchup_id:
                self._pinnacle_matchup_id = matchup_id
                self._pinnacle_details    = None
                self._book_caches['pinnacle'].clear()

            home_name = (parsed.get('home_name') or '').strip()
            away_name = (parsed.get('away_name') or '').strip()
            if home_name and away_name and not self._pinnacle_details:
                self._pinnacle_details = {'home_name': home_name, 'away_name': away_name}
                print(f'[worker] Pinnacle names (DOM): {home_name} vs {away_name}')

            odds = {'home': {'odds_decimal': home_odds}, 'away': {'odds_decimal': away_odds}}
            prev = self._pinnacle_odds
            self._pinnacle_odds = odds
            if not prev or prev['home']['odds_decimal'] != home_odds or prev['away']['odds_decimal'] != away_odds:
                print(f'[worker] Pinnacle DOM odds: {matchup_id} home={home_odds:.3f} away={away_odds:.3f}')

            self._sync_pinnacle_cache()
            await self._evaluate()

        elif msg_type == 'pinnacle_details':
            matchup_id = data.get('matchup_id', '') or self._pinnacle_matchup_id or ''
            if matchup_id:
                details = parse_matchup_details(data.get('body', ''), matchup_id)
                if details:
                    self._pinnacle_details = details
                    print(f'[worker] Pinnacle details: {details["home_name"]} vs {details["away_name"]}')
                    self._sync_pinnacle_cache()
                    await self._evaluate()

        elif msg_type in ('pinnacle_ws_markets', 'pinnacle_odds'):
            matchup_id = data.get('matchup_id', '') or self._pinnacle_matchup_id or ''
            odds = parse_straight_response(data.get('body', ''), matchup_id)
            if odds:
                if matchup_id != self._pinnacle_matchup_id:
                    self._pinnacle_matchup_id = matchup_id
                    self._pinnacle_details    = None
                prev = self._pinnacle_odds
                self._pinnacle_odds = odds
                if not prev or prev['home']['odds_decimal'] != odds['home']['odds_decimal']:
                    print(f'[worker] Pinnacle odds: {matchup_id} '
                          f'home={odds["home"]["odds_decimal"]:.3f} '
                          f'away={odds["away"]["odds_decimal"]:.3f}')
                self._sync_pinnacle_cache()
                await self._evaluate()

        elif msg_type == 'pinnacle_url':
            new_id = extract_matchup_id(data.get('url', ''))
            if new_id and new_id != self._pinnacle_matchup_id:
                print(f'[worker] Pinnacle URL → new matchup={new_id}')
                self._pinnacle_matchup_id = new_id
                self._pinnacle_details    = None
                self._pinnacle_odds       = None
                self._book_caches['pinnacle'].clear()

        elif msg_type == 'thescore_dom_odds':
            await self._handle_dom_odds(data, 'thescore', 'matchId')

        elif msg_type == 'draftkings_dom_odds':
            await self._handle_dom_odds(data, 'draftkings', 'eventId')

        elif msg_type == 'betway_dom_odds':
            await self._handle_dom_odds(data, 'betway', 'eventId')

        elif msg_type == 'fanduel_dom_odds':
            await self._handle_dom_odds(data, 'fanduel', 'eventId')

        elif msg_type == 'bet365_dom_odds':
            await self._handle_dom_odds(data, 'bet365', 'eventId')

        else:
            if msg_type not in ('', 'ping'):
                print(f'[worker] Unknown message type: {msg_type}')

        return _ok()

    async def _handle_dom_odds(self, data: dict, book: str, id_key: str):
        try:
            parsed  = json.loads(data.get('body', '{}'))
            mid     = str(parsed.get(id_key, ''))
            p1_name = (parsed.get('p1_name') or '').strip()
            p2_name = (parsed.get('p2_name') or '').strip()
            p1_odds = float(parsed.get('p1_odds', 0))
            p2_odds = float(parsed.get('p2_odds', 0))
        except Exception:
            return
        if p1_odds < 1.01 or p2_odds < 1.01 or not mid:
            return

        entry = _make_entry(mid, p1_name, p1_odds, p2_name, p2_odds)
        prev  = self._book_caches[book].get(mid)
        if not prev or prev['p1_odds'] != p1_odds or prev['p2_odds'] != p2_odds:
            print(f'[worker] {book.capitalize()} odds: {p1_name} {p1_odds:.2f} / {p2_name} {p2_odds:.2f}')
        self._store(book, entry)
        await self._evaluate()

    def _store(self, book: str, entry: dict):
        self._book_caches[book][entry['match_id']] = entry

    def _sync_pinnacle_cache(self):
        """Combine _pinnacle_details + _pinnacle_odds into the unified book cache."""
        if not self._pinnacle_details or not self._pinnacle_odds:
            return
        mid   = self._pinnacle_matchup_id or 'pinnacle'
        entry = _make_entry(
            mid,
            self._pinnacle_details['home_name'],
            self._pinnacle_odds['home']['odds_decimal'],
            self._pinnacle_details['away_name'],
            self._pinnacle_odds['away']['odds_decimal'],
        )
        self._book_caches['pinnacle'][mid] = entry

    # Arb evaluation

    async def _evaluate(self):
        """Compare all pairs of selected books. Emit the best arb found."""
        books_with_data = [b for b in self._selected_books if self._book_caches.get(b)]
        books_status    = {b: b in books_with_data for b in self._selected_books}

        if len(books_with_data) < 1:
            self._emit(State.WAITING, {})
            return

        if len(books_with_data) < 2:
            self._emit(State.PARTIAL, {'books_status': books_status})
            return

        # Compare all book pairs; pick the best arb (or best match if no arb)
        best_arb     = None
        best_book_a  = None
        best_book_b  = None
        best_entry_a = None
        best_entry_b = None

        book_list = list(books_with_data)
        for i in range(len(book_list)):
            for j in range(i + 1, len(book_list)):
                ba, bb = book_list[i], book_list[j]
                ea, eb = self._find_pair(ba, bb)
                if ea is None:
                    continue

                arb = find_best_arb(ea['p1_odds'], ea['p2_odds'],
                                    eb['p1_odds'], eb['p2_odds'],
                                    self._total_stake)

                if best_entry_a is None:
                    best_book_a, best_book_b = ba, bb
                    best_entry_a, best_entry_b = ea, eb

                if arb and (best_arb is None or arb['margin'] > best_arb['margin']):
                    best_arb = arb
                    best_book_a, best_book_b = ba, bb
                    best_entry_a, best_entry_b = ea, eb

        if best_entry_a is None:
            self._emit(State.PARTIAL, {'books_status': books_status})
            return

        ea, eb = best_entry_a, best_entry_b
        odds_key = (ea['p1_odds'], ea['p2_odds'], eb['p1_odds'], eb['p2_odds'])
        if odds_key != self._last_logged_odds:
            self._last_logged_odds = odds_key
            print(f'[worker] {best_book_a} {ea["p1_name"]} vs {ea["p2_name"]} '
                  f'↔ {best_book_b} {eb["p1_name"]} vs {eb["p2_name"]} '
                  f'a={ea["p1_odds"]:.3f}/{ea["p2_odds"]:.3f} '
                  f'b={eb["p1_odds"]:.3f}/{eb["p2_odds"]:.3f}')

        # Align every selected book's latest entry to the reference order (entry_a).
        all_books: dict = {}
        for book in self._selected_books:
            cache = self._book_caches.get(book)
            if not cache:
                continue
            entries = list(cache.values())
            if not entries:
                continue
            e = dict(entries[-1])
            # Swap p1/p2 if this book's p1 matches the reference p2
            if (e.get('p1_name') and ea.get('p1_name') and
                    _names_match(e.get('p1_name', ''), ea.get('p2_name', '')) and
                    _names_match(e.get('p2_name', ''), ea.get('p1_name', ''))):
                e['p1_name'], e['p2_name'] = e['p2_name'], e['p1_name']
                e['p1_odds'], e['p2_odds'] = e['p2_odds'], e['p1_odds']
            all_books[book] = e

        base_data = {
            'book_a':   best_book_a,
            'book_b':   best_book_b,
            'entry_a':  ea,
            'entry_b':  eb,
            'all_books': all_books,
        }

        if best_arb:
            if best_arb['pinnacle_side'] == 'home':
                best_arb['book_a_player'] = ea['p1_name']
                # If book_b has no names, use book_a's opposite player
                best_arb['book_b_player'] = eb['p2_name'] or ea['p2_name']
            else:
                best_arb['book_a_player'] = ea['p2_name']
                best_arb['book_b_player'] = eb['p1_name'] or ea['p1_name']
            base_data['arb'] = best_arb
            self._emit(State.ARB_FOUND, base_data)
        else:
            self._emit(State.SCANNING, base_data)

    def _find_pair(self, book_a: str, book_b: str) -> tuple[dict | None, dict | None]:
        """
        Find entries in book_a and book_b that cover the same match.
        Tries name matching first; falls back to most-recent entries per book
        when names are unavailable (user is assumed to be on the same match).
        """
        cache_a = list(self._book_caches[book_a].values())
        cache_b = list(self._book_caches[book_b].values())
        if not cache_a or not cache_b:
            return None, None

        # Try name matching when both books have names
        for ea in cache_a:
            for eb in cache_b:
                if not ea['p1_name'] or not eb['p1_name']:
                    continue
                if (_names_match(ea['p1_name'], eb['p1_name']) and
                        _names_match(ea['p2_name'], eb['p2_name'])):
                    return ea, eb
                if (_names_match(ea['p1_name'], eb['p2_name']) and
                        _names_match(ea['p2_name'], eb['p1_name'])):
                    eb_aligned = {**eb,
                                  'p1_name': eb['p2_name'], 'p1_odds': eb['p2_odds'],
                                  'p2_name': eb['p1_name'], 'p2_odds': eb['p1_odds']}
                    return ea, eb_aligned

        # Fallback: names unavailable, pair most-recent entries as-is.
        # No mathematical alignment: caller receives raw entries and is responsible
        # for knowing the user has both books open on the same match.
        return cache_a[-1], cache_b[-1]

    def _emit(self, state: str, data: dict):
        # Only dedup WAITING — PARTIAL must always fire so the GUI updates
        # when books_status changes (e.g. second book comes online).
        if state == self._last_state and state == State.WAITING:
            return
        self._last_state = state
        self.update.emit(state, data)


def _ok() -> web.Response:
    return web.Response(text='ok', headers={'Access-Control-Allow-Origin': '*'})
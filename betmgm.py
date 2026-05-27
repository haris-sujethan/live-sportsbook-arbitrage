"""
betmgm.py — BetMGM odds extraction via JavaScript injection.

Instead of hooking the CDP Network domain (which causes severe page lag),
we inject a lightweight JavaScript snippet into the BetMGM tab before the
page loads. That snippet intercepts BetMGM's SignalR WebSocket at the JS
level and stores the latest Match winner payload in window.__arb_betmgm.

Python then reads that global every 500 ms via Runtime.evaluate — zero
network overhead, zero browser slowdown.
"""


# Injected into the BetMGM tab via Page.addScriptToEvaluateOnNewDocument.
# Runs before any page script, so it intercepts the WebSocket constructor.
BETMGM_INJECT_JS = r"""
(function() {
    var _Orig = window.WebSocket;
    window.WebSocket = function(url, protocols) {
        var ws = (arguments.length === 1)
            ? new _Orig(url)
            : new _Orig(url, protocols);
        if (typeof url === 'string' && url.indexOf('cds-push') !== -1) {
            ws.addEventListener('message', function(evt) {
                try {
                    var d = JSON.parse(evt.data);
                    var arg = d && d.arguments && d.arguments[0];
                    if (arg && arg.messageType === 'GameUpdate') {
                        var pl = arg.payload;
                        var game = pl && pl.game;
                        if (game && game.isMain === true &&
                                game.name && game.name.value === 'Match winner') {
                            window.__arb_betmgm = pl;
                        }
                    }
                } catch(e) {}
            });
        }
        return ws;
    };
    window.WebSocket.CONNECTING = _Orig.CONNECTING;
    window.WebSocket.OPEN       = _Orig.OPEN;
    window.WebSocket.CLOSING    = _Orig.CLOSING;
    window.WebSocket.CLOSED     = _Orig.CLOSED;
    window.WebSocket.prototype  = _Orig.prototype;
})();
"""


def parse_betmgm_payload(payload: dict) -> dict | None:
    """
    Parse a BetMGM GameUpdate payload (isMain=True, any sport).
    Takes the first two visible results as player1/player2.
    """
    if not isinstance(payload, dict):
        return None

    game = payload.get('game', {})
    if not isinstance(game, dict):
        return None

    results = game.get('results', [])
    if not isinstance(results, list):
        return None

    visible = [r for r in results if r.get('visibility') == 'Visible']
    if len(visible) < 2:
        return None

    r1, r2    = visible[0], visible[1]
    fixture_id = payload.get('fixtureId', '')

    return {
        'source':     'betmgm',
        'fixture_id': str(fixture_id),
        'game_id':    game.get('id'),
        'player1': {
            'name':          _safe_str(r1.get('name', {}).get('value', '')),
            'odds_decimal':  float(r1.get('odds', 0)),
            'odds_american': r1.get('americanOdds'),
        },
        'player2': {
            'name':          _safe_str(r2.get('name', {}).get('value', '')),
            'odds_decimal':  float(r2.get('odds', 0)),
            'odds_american': r2.get('americanOdds'),
        },
    }


def _safe_str(val) -> str:
    if val is None:
        return ''
    return str(val).strip()

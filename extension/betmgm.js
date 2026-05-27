/**
 * betmgm.js — MAIN world content script.
 * Intercepts BetMGM's SignalR WebSocket AND initial REST API calls.
 *
 * WebSocket (cds-push): live updates, uses \x1e SignalR frame delimiter.
 * REST API (cds-api):   initial page odds on load — same game structure.
 */
(function () {
    'use strict';

    console.log('[Arb Scanner] betmgm.js loaded on', window.location.href);

    // ── Shared game processor ─────────────────────────────────────────────────

    function processGame(fixtureId, game) {
        if (!game || game.isMain !== true) return;

        var results = game.results || [];
        var visible = results.filter(function (r) { return r.visibility === 'Visible'; });
        if (visible.length < 2) return;

        var gameName = (game.name && game.name.value) || '?';
        console.log('[Arb Scanner] game isMain=true "' + gameName + '" fixture=' + fixtureId);

        window.postMessage({
            __arb:   true,
            type:    'betmgm',
            payload: { fixtureId: fixtureId, game: game },
        }, '*');
    }

    // Recursively find all {fixtureId, game} pairs in a REST response object.
    // Depth-limited to avoid blowing the stack on large payloads.
    function scanForGames(obj, depth) {
        if (!obj || typeof obj !== 'object' || depth > 8) return;
        if (Array.isArray(obj)) {
            for (var i = 0; i < obj.length; i++) scanForGames(obj[i], depth + 1);
            return;
        }
        if (obj.fixtureId) {
            // WebSocket shape: {fixtureId, game}
            if (obj.game) {
                processGame(obj.fixtureId, obj.game);
            }
            // REST shape: {fixtureId, games: [...]}
            if (Array.isArray(obj.games)) {
                for (var j = 0; j < obj.games.length; j++) {
                    processGame(obj.fixtureId, obj.games[j]);
                }
            }
            // Don't recurse further into this object — fixtureId is a terminal node
            return;
        }
        var keys = Object.keys(obj);
        for (var k = 0; k < keys.length; k++) {
            scanForGames(obj[keys[k]], depth + 1);
        }
    }

    // ── WebSocket intercept (live updates) ────────────────────────────────────

    var _Orig = window.WebSocket;

    window.WebSocket = function (url, protocols) {
        var ws = (arguments.length === 1)
            ? new _Orig(url)
            : new _Orig(url, protocols);

        if (typeof url === 'string' && url.indexOf('cds-push') !== -1) {
            console.log('[Arb Scanner] Hooked BetMGM WebSocket:', url);

            ws.addEventListener('message', function (evt) {
                var frames = evt.data.split('\x1e');
                for (var i = 0; i < frames.length; i++) {
                    var frame = frames[i].trim();
                    if (!frame) continue;
                    try {
                        var d = JSON.parse(frame);
                        var arg = d && d.arguments && d.arguments[0];
                        if (!arg || arg.messageType !== 'GameUpdate') continue;
                        var pl = arg.payload;
                        if (pl) processGame(pl.fixtureId, pl.game);
                    } catch (e) {}
                }
            });
        }

        return ws;
    };

    window.WebSocket.CONNECTING = _Orig.CONNECTING;
    window.WebSocket.OPEN       = _Orig.OPEN;
    window.WebSocket.CLOSING    = _Orig.CLOSING;
    window.WebSocket.CLOSED     = _Orig.CLOSED;
    window.WebSocket.prototype  = _Orig.prototype;

    // ── Fetch intercept (initial page odds) ───────────────────────────────────

    var _origFetch = window.fetch;

    window.fetch = function (input, init) {
        var url = (typeof input === 'string') ? input
                : (input instanceof Request)  ? input.url : '';
        var p = _origFetch.apply(this, arguments);

        if (url.indexOf('cds-api') !== -1) {
            p.then(function (resp) {
                if (!resp.ok) return;
                resp.clone().json().then(function (data) {
                    scanForGames(data, 0);
                }).catch(function () {});
            }).catch(function () {});
        }

        return p;
    };

    // ── XHR intercept (fallback) ──────────────────────────────────────────────

    var _origOpen = XMLHttpRequest.prototype.open;
    var _origSend = XMLHttpRequest.prototype.send;

    XMLHttpRequest.prototype.open = function (method, url) {
        this._arbUrl = (typeof url === 'string') ? url : '';
        return _origOpen.apply(this, arguments);
    };

    XMLHttpRequest.prototype.send = function () {
        if ((this._arbUrl || '').indexOf('cds-api') !== -1) {
            var xhr = this;
            xhr.addEventListener('load', function () {
                if (xhr.status !== 200) return;
                try {
                    var data = JSON.parse(xhr.responseText);
                    scanForGames(data, 0);
                } catch (e) {}
            });
        }
        return _origSend.apply(this, arguments);
    };
}());

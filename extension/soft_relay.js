/**
 * soft_relay.js — ISOLATED world bridge for theScore and DraftKings tabs.
 * Same queue+reconnect design as relay.js / pinnacle_relay.js.
 */
(function () {
    var port        = null;
    var pending     = {};
    var _connecting = false;

    var SOFT_TYPES = {
        'thescore_dom_odds':    true,
        'draftkings_dom_odds':  true,
        'betway_dom_odds':      true,
        'fanduel_dom_odds':     true,
        'bet365_dom_odds':      true,
    };

    function flush() {
        if (!port) { connect(); return; }
        var types = Object.keys(pending);
        for (var i = 0; i < types.length; i++) {
            var t = types[i];
            try {
                port.postMessage(pending[t]);
                delete pending[t];
            } catch (e) {
                port = null;
                setTimeout(connect, 200);
                return;
            }
        }
    }

    function connect() {
        if (_connecting) return;
        _connecting = true;
        try {
            port = chrome.runtime.connect({ name: 'arb-soft' });
            _connecting = false;
            port.onDisconnect.addListener(function () {
                port = null;
                setTimeout(connect, 500);
            });
            flush();
        } catch (e) {
            _connecting = false;
            port = null;
            setTimeout(connect, 1000);
        }
    }

    connect();

    window.addEventListener('message', function (evt) {
        if (evt.source !== window) return;
        if (!evt.data || !evt.data.__arb) return;
        if (!SOFT_TYPES[evt.data.type]) return;

        pending[evt.data.type] = evt.data;
        flush();
    });
}());

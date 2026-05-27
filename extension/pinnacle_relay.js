/**
 * pinnacle_relay.js — ISOLATED world bridge for Pinnacle tab.
 *
 * Relays window.postMessage events from pinnacle.js (and the injected
 * pinnacleMonitor) through a long-lived port to background.js.
 */
(function () {
    var port        = null;
    var pending     = {};
    var _connecting = false;

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
            port = chrome.runtime.connect({ name: 'arb-pinnacle' });
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
        var t = evt.data.type;
        if (t !== 'pinnacle_odds' &&
            t !== 'pinnacle_details' &&
            t !== 'pinnacle_url' &&
            t !== 'pinnacle_ws_markets' &&
            t !== 'pinnacle_dom_odds') return;

        pending[t] = evt.data;
        flush();
    });
}());

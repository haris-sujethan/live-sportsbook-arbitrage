/**
 * background.js — Extension service worker.
 *
 * Owns Pinnacle tab detection and live odds monitoring:
 *   - Scans for existing Pinnacle match tabs on startup
 *   - Injects a self-contained price monitor into each tab's MAIN world
 *     via chrome.scripting.executeScript (bypasses content-script timing issues)
 *   - The injected monitor uses MutationObserver on buttons → fires the instant
 *     React patches any price element after a WebSocket update
 *   - 2-second heartbeat re-sends last known odds to Python so Python attaches
 *     within ≤2s regardless of when it was started
 *
 * BetMGM relay is unchanged: relay.js content script ports messages here.
 */

const SERVER = 'http://localhost:8765';

var _lastPinnacleOdds   = null;   // cached for heartbeat
var _lastBetMGMOdds     = null;
var _lastThescoreOdds   = null;
var _lastDraftkingsOdds = null;
var _lastBetwayOdds     = null;
var _lastFanduelOdds    = null;
var _lastBet365Odds     = null;

// ── POST to Python ────────────────────────────────────────────────────────────

function postToPython(msg) {
    fetch(SERVER, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(msg),
    }).catch(function () {});
}

// ── Heartbeat ─────────────────────────────────────────────────────────────────
// Sends last-known odds every 2 s so Python always attaches within 2 s of start.

setInterval(function () {
    if (_lastPinnacleOdds)   postToPython(_lastPinnacleOdds);
    if (_lastBetMGMOdds)     postToPython(_lastBetMGMOdds);
    if (_lastThescoreOdds)   postToPython(_lastThescoreOdds);
    if (_lastDraftkingsOdds) postToPython(_lastDraftkingsOdds);
    if (_lastBetwayOdds)     postToPython(_lastBetwayOdds);
    if (_lastFanduelOdds)    postToPython(_lastFanduelOdds);
    if (_lastBet365Odds)     postToPython(_lastBet365Odds);
}, 2000);

// ── Tab detection ─────────────────────────────────────────────────────────────

function isPinnacleMatch(url) {
    return url && url.includes('pinnacle.ca') && /\/\d{7,12}\//.test(url);
}

function isBetMGMEvent(url) {
    return url && url.includes('betmgm.ca') && url.includes('/events/');
}

function isThescoreEvent(url) {
    return url && url.includes('sportsbook.thescore.bet') && url.includes('/event/');
}

function isDraftkingsEvent(url) {
    return url && url.includes('sportsbook.draftkings.com') && url.includes('/event/');
}

function isBet365Event(url) {
    // bet365.ca is a hash-SPA — any page load is the shell; the monitor checks the hash
    return url && url.includes('bet365.ca');
}

function isBetwayEvent(url) {
    return url && url.includes('betway.ca') && url.includes('/sports/event/');
}

function isFanduelEvent(url) {
    return url && url.includes('fanduel.ca') && /\/[a-z0-9-]+-\d{5,12}(?:\/|$|\?)/i.test(url);
}

function injectIfPinnacleMatch(tabId, url) {
    if (!isPinnacleMatch(url)) return;
    chrome.scripting.executeScript({
        target: { tabId: tabId }, world: 'MAIN', func: pinnacleMonitor,
    }).catch(function () {});
}

function injectIfBetMGMEvent(tabId, url) {
    if (!isBetMGMEvent(url)) return;
    chrome.scripting.executeScript({
        target: { tabId: tabId }, world: 'MAIN', func: betmgmMonitor,
    }).catch(function () {});
}

function injectIfThescoreEvent(tabId, url) {
    if (!isThescoreEvent(url)) return;
    chrome.scripting.executeScript({
        target: { tabId: tabId }, world: 'MAIN', func: thescoreMonitor,
    }).catch(function () {});
}

function injectIfDraftkingsEvent(tabId, url) {
    if (!isDraftkingsEvent(url)) return;
    chrome.scripting.executeScript({
        target: { tabId: tabId }, world: 'MAIN', func: draftkingsMonitor,
    }).catch(function () {});
}

function injectIfBet365Event(tabId, url) {
    if (!isBet365Event(url)) return;
    chrome.scripting.executeScript({
        target: { tabId: tabId }, world: 'MAIN', func: bet365Monitor,
    }).catch(function () {});
}

function injectIfBetwayEvent(tabId, url) {
    if (!isBetwayEvent(url)) return;
    chrome.scripting.executeScript({
        target: { tabId: tabId }, world: 'MAIN', func: betwayMonitor,
    }).catch(function () {});
}

function injectIfFanduelEvent(tabId, url) {
    if (!isFanduelEvent(url)) return;
    chrome.scripting.executeScript({
        target: { tabId: tabId }, world: 'MAIN', func: fanduelMonitor,
    }).catch(function () {});
}

// Scan all already-open tabs when the service worker starts
chrome.tabs.query({}, function (tabs) {
    tabs.forEach(function (tab) {
        if (tab.url) {
            injectIfPinnacleMatch(tab.id, tab.url);
            injectIfBetMGMEvent(tab.id, tab.url);
            injectIfThescoreEvent(tab.id, tab.url);
            injectIfDraftkingsEvent(tab.id, tab.url);
            injectIfBet365Event(tab.id, tab.url);
            injectIfBetwayEvent(tab.id, tab.url);
            injectIfFanduelEvent(tab.id, tab.url);
        }
    });
});

// Watch for navigations
chrome.tabs.onUpdated.addListener(function (tabId, changeInfo, tab) {
    if (changeInfo.status === 'complete' && tab.url) {
        injectIfPinnacleMatch(tabId, tab.url);
        injectIfBetMGMEvent(tabId, tab.url);
        injectIfThescoreEvent(tabId, tab.url);
        injectIfDraftkingsEvent(tabId, tab.url);
        injectIfBet365Event(tabId, tab.url);
        injectIfBetwayEvent(tabId, tab.url);
        injectIfFanduelEvent(tabId, tab.url);
    }
});

// ── Relay from content scripts ────────────────────────────────────────────────

chrome.runtime.onConnect.addListener(function (port) {
    port.onMessage.addListener(function (msg) {
        if (!msg || !msg.__arb) return;

        console.log('[Arb BG] rx:', msg.type, msg.matchup_id || '');

        if (msg.type === 'pinnacle_dom_odds')   _lastPinnacleOdds   = msg;
        if (msg.type === 'betmgm_dom_odds')     _lastBetMGMOdds     = msg;
        if (msg.type === 'thescore_dom_odds')   _lastThescoreOdds   = msg;
        if (msg.type === 'draftkings_dom_odds') _lastDraftkingsOdds = msg;
        if (msg.type === 'betway_dom_odds')     _lastBetwayOdds     = msg;
        if (msg.type === 'fanduel_dom_odds')    _lastFanduelOdds    = msg;
        if (msg.type === 'bet365_dom_odds')     _lastBet365Odds     = msg;

        postToPython(msg);
    });
});

// ── Injected Pinnacle monitor (runs in page MAIN world) ───────────────────────
//
// IMPORTANT: this function is serialised with .toString() and injected into
// the page. It must be entirely self-contained — no references to variables
// or functions outside its own body.

function pinnacleMonitor() {
    // Guard: only inject once per page lifetime (SPA navigations keep window)
    if (window.__arbPinnacleMonitor) return;
    window.__arbPinnacleMonitor = true;

    var _lastKey = '';
    var _debounce = null;

    // ── Price reader ──────────────────────────────────────────────────────────
    //
    // Strategy: read innerText on <button> elements — handles nested spans like
    //   <button><span>1</span><span class="dec">.869</span></button>
    // where textContent/textNode approaches would split "1" and ".869".
    //
    // Match Winner is the first/top market on Pinnacle match pages (always
    // expanded by default). The first two buttons with decimal odds values
    // are home and away Match Winner prices.

    function readPrices() {
        var prices = [];
        var btns = document.querySelectorAll('button');
        for (var i = 0; i < btns.length && prices.length < 4; i++) {
            var text = (btns[i].innerText || '').trim();
            if (!/^\d{1,2}\.\d{2,3}$/.test(text)) continue;
            var val = parseFloat(text);
            if (val >= 1.01 && val <= 50) prices.push(val);
        }

        // Fallback: scan all leaf-level span/div elements for rendered text
        if (prices.length < 2) {
            var els = document.querySelectorAll('span, div, td');
            for (var j = 0; j < els.length && prices.length < 4; j++) {
                if (els[j].children.length > 0) continue;
                var t = (els[j].innerText || '').trim();
                if (!/^\d{1,2}\.\d{2,3}$/.test(t)) continue;
                var v = parseFloat(t);
                if (v >= 1.01 && v <= 50) prices.push(v);
            }
        }

        return prices.length >= 2 ? [prices[0], prices[1]] : null;
    }

    // ── Name reader ───────────────────────────────────────────────────────────
    // Extract player/team names so Python never needs to wait for the REST
    // matchup endpoint.  Sources tried in order: document.title, h1/h2.

    function readNames() {
        // Pinnacle page titles: "PlayerA vs PlayerB | Pinnacle" or
        //                       "PlayerA - PlayerB | Tennis | Pinnacle"
        var sources = [document.title];
        var headings = document.querySelectorAll('h1, h2');
        for (var h = 0; h < headings.length; h++) {
            sources.push((headings[h].innerText || '').trim());
        }

        for (var s = 0; s < sources.length; s++) {
            // Strip known trailing noise ("Betting Odds", "Betting", "Odds") before parsing
            var text = sources[s].replace(/\s+betting\s+odds?\b.*$/i, '').trim();
            // "vs" separator (case-insensitive)
            var m = text.match(/^(.+?)\s+vs\.?\s+(.+?)(?:\s*[|–—]|\s*$)/i);
            if (m) return { home: m[1].trim(), away: m[2].trim() };
            // " - " separator (space-dash-space, not intra-word hyphen)
            var m2 = text.match(/^(.+?)\s+-\s+(.+?)(?:\s*[|–—]|\s*$)/);
            if (m2) return { home: m2[1].trim(), away: m2[2].trim() };
        }
        return null;
    }

    // ── Relay ─────────────────────────────────────────────────────────────────

    function maybeRelay() {
        var prices = readPrices();
        if (!prices) return;

        var names  = readNames();
        var key    = prices[0] + '/' + prices[1];
        if (key === _lastKey) return;
        _lastKey = key;

        var mId = (window.location.href.match(/\/(\d{7,12})\//) || [])[1] || '';

        window.postMessage({
            __arb:      true,
            type:       'pinnacle_dom_odds',
            matchup_id: mId,
            body:       JSON.stringify({
                home_odds: prices[0],
                away_odds: prices[1],
                home_name: names ? names.home : '',
                away_name: names ? names.away : '',
            }),
        }, '*');
    }

    // ── MutationObserver ──────────────────────────────────────────────────────
    // Fires the instant React patches any DOM node (e.g. after a WebSocket
    // price update), giving us the same latency as the page UI.

    new MutationObserver(function () {
        clearTimeout(_debounce);
        _debounce = setTimeout(maybeRelay, 100);
    }).observe(document.body, { subtree: true, childList: true });

    // ── Periodic forced relay ─────────────────────────────────────────────────
    // Resets dedup every 3 s so the background heartbeat always has fresh data
    // to send to Python, even when no odds have changed.

    setInterval(function () {
        _lastKey = '';
        maybeRelay();
    }, 3000);

    // Initial read once the page has settled
    setTimeout(maybeRelay, 800);

    console.log('[Arb Scanner] pinnacleMonitor active');
}

// ── Injected BetMGM monitor (runs in page MAIN world) ────────────────────────
// Same self-contained constraint as pinnacleMonitor above.

function betmgmMonitor() {
    if (window.__arbBetMGMMonitor) return;
    window.__arbBetMGMMonitor = true;

    var _lastKey = '';
    var _debounce = null;

    // ── Name reader ───────────────────────────────────────────────────────────
    // BetMGM titles: "PlayerA vs PlayerB | Sport | BetMGM"
    //            or "PlayerA - PlayerB | ..."

    function readNames() {
        var sources = [document.title];
        var hs = document.querySelectorAll('h1, h2');
        for (var h = 0; h < hs.length; h++) sources.push((hs[h].innerText || '').trim());

        for (var s = 0; s < sources.length; s++) {
            var text = sources[s];
            var m = text.match(/^(.+?)\s+vs\.?\s+(.+?)(?:\s*[|–—]|\s*$)/i);
            if (m) return { p1: m[1].trim(), p2: m[2].trim() };
            var m2 = text.match(/^(.+?)\s+-\s+(.+?)(?:\s*[|–—]|\s*$)/);
            if (m2) return { p1: m2[1].trim(), p2: m2[2].trim() };
        }
        return null;
    }

    // ── Match winner odds reader ──────────────────────────────────────────────
    // Finds the "Match winner" section and returns the first two prices.
    // Handles both decimal (1.85) and American (-150, +105) formats.

    function toDecimal(txt) {
        txt = (txt || '').trim().replace(/[−–—]/g, '-');
        if (/^even$/i.test(txt)) return 2.0;
        if (/^\d{1,3}\.\d{2,3}$/.test(txt)) {
            var d = parseFloat(txt);
            if (d >= 1.01 && d <= 50) return d;
        }
        if (/^[+-]\d{2,5}$/.test(txt)) {
            var a = parseInt(txt, 10);
            return parseFloat((a > 0 ? (a / 100) + 1 : (100 / Math.abs(a)) + 1).toFixed(3));
        }
        return null;
    }

    function _extractPrices(root) {
        var prices = [];
        // Try buttons first — BetMGM renders each outcome as a clickable button.
        // button.innerText concatenates nested spans so "-150" is one string.
        var btns = root.querySelectorAll('button');
        for (var i = 0; i < btns.length && prices.length < 4; i++) {
            var lines = (btns[i].innerText || '').replace(/[−–—]/g, '-')
                            .split(/\n+/).map(function(l) { return l.trim(); }).filter(Boolean);
            for (var j = lines.length - 1; j >= 0; j--) {
                var v = toDecimal(lines[j]);
                if (v !== null) { prices.push(v); break; }
            }
        }
        if (prices.length >= 2) return prices;
        // Fall back to leaf nodes if no usable buttons found
        var els = root.querySelectorAll('*');
        for (var i = 0; i < els.length && prices.length < 4; i++) {
            if (els[i].children.length > 0) continue;
            var v = toDecimal((els[i].innerText || '').trim());
            if (v !== null) prices.push(v);
        }
        return prices;
    }

    function readMatchWinnerOdds() {
        // Find "Match winner" label then walk up to a container with exactly
        // 2–4 prices. NO body-wide fallback — avoids grabbing wrong markets.
        var all = document.querySelectorAll('*');
        for (var i = 0; i < all.length; i++) {
            if (all[i].children.length > 0) continue;
            var label = (all[i].innerText || '').replace(/\s+/g, ' ').toLowerCase().trim();
            if (!label.startsWith('match winner') || label.length > 50) continue;

            var section = all[i].parentElement;
            for (var s = 0; s < 12 && section; s++) {
                var prices = _extractPrices(section);
                if (prices.length >= 2 && prices.length <= 4) return prices.slice(0, 2);
                section = section.parentElement;
            }
        }
        return null;
    }

    // ── Relay ─────────────────────────────────────────────────────────────────

    function maybeRelay() {
        var odds = readMatchWinnerOdds();
        if (!odds) return;
        var names = readNames();

        var key = odds[0] + '/' + odds[1];
        if (key === _lastKey) return;
        _lastKey = key;

        // Extract fixture ID from URL slug: /events/player-name-12345678
        var urlMatch = window.location.href.match(/-(\d{5,12})(?:\/|$|\?|#)/);
        var fixtureId = urlMatch ? urlMatch[1] : 'dom-' + Date.now();

        window.postMessage({
            __arb: true,
            type:  'betmgm_dom_odds',
            body:  JSON.stringify({
                fixtureId: fixtureId,
                p1_name:   names ? names.p1 : '',
                p1_odds:   odds[0],
                p2_name:   names ? names.p2 : '',
                p2_odds:   odds[1],
            }),
        }, '*');
    }

    new MutationObserver(function () {
        clearTimeout(_debounce);
        _debounce = setTimeout(maybeRelay, 100);
    }).observe(document.body, { subtree: true, childList: true });

    setInterval(function () { _lastKey = ''; maybeRelay(); }, 3000);
    setTimeout(maybeRelay, 800);

    console.log('[Arb Scanner] betmgmMonitor active');
}

// ── Injected theScore monitor (runs in page MAIN world) ───────────────────────

function thescoreMonitor() {
    if (window.__arbThescoreMonitor) return;
    window.__arbThescoreMonitor = true;

    var _lastKey  = '';
    var _debounce = null;

    // ── Helpers shared by both new monitors ───────────────────────────────────

    function toDecimal(txt) {
        txt = (txt || '').trim();
        // Normalize Unicode minus sign (U+2212 −) and en/em dashes to ASCII hyphen
        txt = txt.replace(/[−–—]/g, '-');
        if (/^even$/i.test(txt)) return 2.0;
        // Decimal: "1.85", "2.50", "11.00"
        if (/^\d{1,3}\.\d{2,3}$/.test(txt)) {
            var d = parseFloat(txt);
            if (d >= 1.01 && d <= 200) return d;
        }
        // American: "+150", "-110", "EVEN"
        if (/^[+-]\d{2,5}$/.test(txt)) {
            var a = parseInt(txt, 10);
            return parseFloat((a > 0 ? (a / 100) + 1 : (100 / Math.abs(a)) + 1).toFixed(3));
        }
        return null;
    }

    function scanLeaves(root) {
        var prices = [];
        var els = root.querySelectorAll('*');
        for (var i = 0; i < els.length && prices.length < 6; i++) {
            if (els[i].children.length > 0) continue;
            var v = toDecimal(els[i].innerText);
            if (v !== null) prices.push(v);
        }
        return prices;
    }

    var MARKET_LABELS_TS = ['match winner', 'winner', 'moneyline', 'match result', '1x2'];

    // Parse a single outcome button: returns {name, price} or null.
    // theScore buttons look like: "J. Prado\n-450" or "C. Wong\n+300"
    // Lines before the price line are joined as the player name.
    function parseOutcomeButton(btn) {
        var txt = (btn.innerText || '').trim().replace(/[−–—]/g, '-');
        var lines = txt.split('\n').map(function(l) { return l.trim(); }).filter(Boolean);
        var price = null;
        var priceIdx = -1;
        for (var i = lines.length - 1; i >= 0; i--) {
            var v = toDecimal(lines[i]);
            if (v !== null) { price = v; priceIdx = i; break; }
        }
        if (price === null || priceIdx < 0) return null;
        var name = lines.slice(0, priceIdx).join(' ').trim();
        return { name: name, price: price };
    }

    function readMarket() {
        var all = document.querySelectorAll('*');
        for (var i = 0; i < all.length; i++) {
            // Don't skip elements with children — market headings like
            // <h2>Match Winner<span>↑</span></h2> have children too.
            var label = (all[i].innerText || '').toLowerCase().trim();
            var hit = false;
            for (var li = 0; li < MARKET_LABELS_TS.length; li++) {
                var ml = MARKET_LABELS_TS[li];
                if (label.length > ml.length + 12) continue;
                if (label.startsWith(ml)) { hit = true; break; }
            }
            if (!hit) continue;

            var section = all[i].parentElement;
            for (var s = 0; s < 12 && section; s++) {
                var btns = section.querySelectorAll('button');
                var outcomes = [];
                for (var b = 0; b < btns.length && outcomes.length < 4; b++) {
                    var o = parseOutcomeButton(btns[b]);
                    if (o !== null) outcomes.push(o);
                }
                if (outcomes.length >= 2 && outcomes.length <= 4) {
                    return {
                        p1_name: outcomes[0].name, p1_odds: outcomes[0].price,
                        p2_name: outcomes[1].name, p2_odds: outcomes[1].price,
                    };
                }
                section = section.parentElement;
            }
        }
        // Fallback: scan all buttons on page (names may be empty if buttons only show odds)
        var allBtns = document.querySelectorAll('button');
        var fb = [];
        for (var b = 0; b < allBtns.length && fb.length < 4; b++) {
            var o = parseOutcomeButton(allBtns[b]);
            if (o !== null) fb.push(o);
        }
        if (fb.length >= 2) {
            return {
                p1_name: fb[0].name, p1_odds: fb[0].price,
                p2_name: fb[1].name, p2_odds: fb[1].price,
            };
        }
        return null;
    }

    function maybeRelay() {
        var market = readMarket();
        if (!market) return;
        var key = market.p1_odds + '/' + market.p2_odds;
        if (key === _lastKey) return;
        _lastKey = key;

        // theScore event UUID: /event/{uuid}
        var m = window.location.href.match(/\/event\/([0-9a-f-]{8,})/i);
        var matchId = m ? m[1] : 'dom-' + Date.now();

        window.postMessage({
            __arb: true,
            type:  'thescore_dom_odds',
            body:  JSON.stringify({
                matchId:  matchId,
                p1_name:  market.p1_name,
                p1_odds:  market.p1_odds,
                p2_name:  market.p2_name,
                p2_odds:  market.p2_odds,
            }),
        }, '*');
    }

    new MutationObserver(function () {
        clearTimeout(_debounce);
        _debounce = setTimeout(maybeRelay, 100);
    }).observe(document.body, { subtree: true, childList: true });

    setInterval(function () { _lastKey = ''; maybeRelay(); }, 3000);
    setTimeout(maybeRelay, 800);

    console.log('[Arb Scanner] thescoreMonitor active');
}

// ── Injected DraftKings monitor (runs in page MAIN world) ─────────────────────

function draftkingsMonitor() {
    if (window.__arbDraftkingsMonitor) return;
    window.__arbDraftkingsMonitor = true;

    var _lastKey  = '';
    var _debounce = null;

    function toDecimal(txt) {
        txt = (txt || '').trim();
        // Normalize Unicode minus sign (U+2212 −) and en/em dashes to ASCII hyphen
        txt = txt.replace(/[−–—]/g, '-');
        if (/^even$/i.test(txt)) return 2.0;
        if (/^\d{1,3}\.\d{2,3}$/.test(txt)) {
            var d = parseFloat(txt);
            if (d >= 1.01 && d <= 200) return d;
        }
        if (/^[+-]\d{2,5}$/.test(txt)) {
            var a = parseInt(txt, 10);
            return parseFloat((a > 0 ? (a / 100) + 1 : (100 / Math.abs(a)) + 1).toFixed(3));
        }
        return null;
    }

    function scanLeaves(root) {
        var prices = [];
        var els = root.querySelectorAll('*');
        for (var i = 0; i < els.length && prices.length < 6; i++) {
            if (els[i].children.length > 0) continue;
            var v = toDecimal(els[i].innerText);
            if (v !== null) prices.push(v);
        }
        return prices;
    }

    // 'winner' omitted — too broad, matches "Game Winner" / "Set Winner"
    var MARKET_LABELS_DK = ['moneyline', 'match winner', 'match result', 'to win match'];

    // Parse a single outcome button: returns {name, price} or null.
    // DraftKings Moneyline buttons: "Dalibor Svrcina\n-126"
    // Lines before the price line are joined as the player name.
    function parseOutcomeButton(btn) {
        var txt = (btn.innerText || '').trim().replace(/[−–—]/g, '-');
        var lines = txt.split('\n').map(function(l) { return l.trim(); }).filter(Boolean);
        var price = null;
        var priceIdx = -1;
        for (var i = lines.length - 1; i >= 0; i--) {
            var v = toDecimal(lines[i]);
            if (v !== null) { price = v; priceIdx = i; break; }
        }
        if (price === null || priceIdx < 0) return null;
        var name = lines.slice(0, priceIdx).join(' ').trim();
        return { name: name, price: price };
    }

    function readMarket() {
        var all = document.querySelectorAll('*');
        for (var i = 0; i < all.length; i++) {
            // Don't skip elements with children — DraftKings wraps market headers:
            //   <h3>Moneyline<span class="icon">↑</span></h3>
            var label = (all[i].innerText || '').toLowerCase().trim();
            var hit = false;
            for (var li = 0; li < MARKET_LABELS_DK.length; li++) {
                var ml = MARKET_LABELS_DK[li];
                if (label.length > ml.length + 12) continue;
                if (label.startsWith(ml)) { hit = true; break; }
            }
            if (!hit) continue;

            var section = all[i].parentElement;
            for (var s = 0; s < 8 && section; s++) {
                var btns = section.querySelectorAll('button');
                var outcomes = [];
                for (var b = 0; b < btns.length && outcomes.length < 4; b++) {
                    var o = parseOutcomeButton(btns[b]);
                    if (o !== null) outcomes.push(o);
                }
                // Require exactly 2-4 outcomes — guards against grabbing a full multi-market container
                if (outcomes.length >= 2 && outcomes.length <= 4) {
                    return {
                        p1_name: outcomes[0].name, p1_odds: outcomes[0].price,
                        p2_name: outcomes[1].name, p2_odds: outcomes[1].price,
                    };
                }
                section = section.parentElement;
            }
        }
        // Fallback: scan all buttons (names may be empty if buttons only show odds)
        var allBtns = document.querySelectorAll('button');
        var fb = [];
        for (var b = 0; b < allBtns.length && fb.length < 4; b++) {
            var o = parseOutcomeButton(allBtns[b]);
            if (o !== null) fb.push(o);
        }
        if (fb.length >= 2) {
            return {
                p1_name: fb[0].name, p1_odds: fb[0].price,
                p2_name: fb[1].name, p2_odds: fb[1].price,
            };
        }
        return null;
    }

    function maybeRelay() {
        var market = readMarket();
        if (!market) return;
        var key = market.p1_odds + '/' + market.p2_odds;
        if (key === _lastKey) return;
        _lastKey = key;

        // DraftKings event ID: /event/{slug}/{numeric-id}
        var m = window.location.href.match(/\/event\/[^/]+\/(\d{5,12})/);
        var eventId = m ? m[1] : 'dom-' + Date.now();

        window.postMessage({
            __arb: true,
            type:  'draftkings_dom_odds',
            body:  JSON.stringify({
                eventId:  eventId,
                p1_name:  market.p1_name,
                p1_odds:  market.p1_odds,
                p2_name:  market.p2_name,
                p2_odds:  market.p2_odds,
            }),
        }, '*');
    }

    new MutationObserver(function () {
        clearTimeout(_debounce);
        _debounce = setTimeout(maybeRelay, 100);
    }).observe(document.body, { subtree: true, childList: true });

    setInterval(function () { _lastKey = ''; maybeRelay(); }, 3000);
    setTimeout(maybeRelay, 800);

    console.log('[Arb Scanner] draftkingsMonitor active');
}

// ── Injected Betway monitor (runs in page MAIN world) ─────────────────────────

function betwayMonitor() {
    if (window.__arbBetwayMonitor) return;
    window.__arbBetwayMonitor = true;

    var _lastKey  = '';
    var _debounce = null;

    function toDecimal(txt) {
        txt = (txt || '').trim().replace(/[−–—]/g, '-');
        if (/^even$/i.test(txt)) return 2.0;
        if (/^\d{1,3}\.\d{2,3}$/.test(txt)) {
            var d = parseFloat(txt);
            if (d >= 1.01 && d <= 200) return d;
        }
        if (/^[+-]\d{2,5}$/.test(txt)) {
            var a = parseInt(txt, 10);
            return parseFloat((a > 0 ? (a / 100) + 1 : (100 / Math.abs(a)) + 1).toFixed(3));
        }
        return null;
    }

    // Betway market labels — they use "Match Winner" for 2-way markets in tennis
    var MARKET_LABELS_BW = ['match winner', 'winner', 'moneyline', 'to win match', '1x2'];

    // Parse a single outcome button: name on earlier lines, price on last numeric line.
    // Betway buttons are typically: "Player Name\n1.85" (decimal) or "Player Name\n-145" (American)
    function parseOutcomeButton(btn) {
        var txt = (btn.innerText || '').trim().replace(/[−–—]/g, '-');
        var lines = txt.split('\n').map(function(l) { return l.trim(); }).filter(Boolean);
        var price = null;
        var priceIdx = -1;
        for (var i = lines.length - 1; i >= 0; i--) {
            var v = toDecimal(lines[i]);
            if (v !== null) { price = v; priceIdx = i; break; }
        }
        if (price === null || priceIdx < 0) return null;
        var name = lines.slice(0, priceIdx).join(' ').trim();
        return { name: name, price: price };
    }

    // Scan leaf nodes in section for names AND prices in DOM order.
    // Betway separates names and prices into different rows, so no single
    // element ever contains both.  We collect leaves, split into names vs
    // prices (skipping known UI labels), and pair by position.
    // Console-verified DOM order: names appear before prices in the SECTION.
    var BW_UI_SKIP = /^(match winner|match result|winner|moneyline|to win match|1x2|cash out|cashout)$/i;

    function scanNamesAndPrices(section) {
        var els = section.querySelectorAll('*');
        var names = [], prices = [], seen = {};
        for (var i = 0; i < els.length; i++) {
            if (els[i].children.length > 0) continue;   // leaf nodes only
            var t = (els[i].innerText || '').trim().replace(/[−–—]/g, '-');
            if (!t || t.length <= 1) continue;           // skip empty / single-char icons
            var p = toDecimal(t);
            if (p !== null) {
                var pk = 'p' + p.toFixed(3);
                if (!seen[pk]) { seen[pk] = true; prices.push(p); }
            } else if (!BW_UI_SKIP.test(t)) {
                var nk = 'n' + t.toLowerCase();
                if (!seen[nk]) { seen[nk] = true; names.push(t); }
            }
            // Bail early if a wrong (larger) section is being scanned
            if (prices.length > 2 || names.length > 4) return null;
        }
        if (names.length === 2 && prices.length === 2) {
            return { p1_name: names[0], p1_odds: prices[0],
                     p2_name: names[1], p2_odds: prices[1] };
        }
        return null;
    }

    function readMarket() {
        var all = document.querySelectorAll('*');
        for (var i = 0; i < all.length; i++) {
            var label = (all[i].innerText || '').toLowerCase().trim();
            var hit = false;
            for (var li = 0; li < MARKET_LABELS_BW.length; li++) {
                var ml = MARKET_LABELS_BW[li];
                if (label.length > ml.length + 12) continue;
                if (label.startsWith(ml)) { hit = true; break; }
            }
            if (!hit) continue;

            var section = all[i].parentElement;
            for (var s = 0; s < 12 && section; s++) {
                var result = scanNamesAndPrices(section);
                if (result) return result;
                section = section.parentElement;
            }
        }
        // Fallback: scan all buttons then leaves
        var allBtns = document.querySelectorAll('button');
        var fb = [];
        for (var b = 0; b < allBtns.length && fb.length < 4; b++) {
            var o = parseOutcomeButton(allBtns[b]);
            if (o !== null) fb.push(o);
        }
        if (fb.length >= 2) {
            return { p1_name: fb[0].name, p1_odds: fb[0].price,
                     p2_name: fb[1].name, p2_odds: fb[1].price };
        }
        var lf = scanNamesAndPrices(document.body);
        if (lf) return lf;
        return null;
    }

    function maybeRelay() {
        var market = readMarket();
        if (!market) return;
        var key = market.p1_odds + '/' + market.p2_odds;
        if (key === _lastKey) return;
        _lastKey = key;

        var m = window.location.href.match(/\/sports\/event\/(\d+)/);
        var eventId = m ? m[1] : 'dom-' + Date.now();

        window.postMessage({
            __arb: true,
            type:  'betway_dom_odds',
            body:  JSON.stringify({
                eventId:  eventId,
                p1_name:  market.p1_name,
                p1_odds:  market.p1_odds,
                p2_name:  market.p2_name,
                p2_odds:  market.p2_odds,
            }),
        }, '*');
    }

    new MutationObserver(function () {
        clearTimeout(_debounce);
        _debounce = setTimeout(maybeRelay, 100);
    }).observe(document.body, { subtree: true, childList: true });

    setInterval(function () { _lastKey = ''; maybeRelay(); }, 3000);
    setTimeout(maybeRelay, 800);

    console.log('[Arb Scanner] betwayMonitor active');
}

// ── Injected FanDuel monitor (runs in page MAIN world) ────────────────────────

function fanduelMonitor() {
    if (window.__arbFanduelMonitor) return;
    window.__arbFanduelMonitor = true;

    var _lastKey  = '';
    var _debounce = null;

    function toDecimal(txt) {
        txt = (txt || '').trim().replace(/[−–—]/g, '-');
        if (/^even$/i.test(txt)) return 2.0;
        if (/^\d{1,3}\.\d{2,3}$/.test(txt)) {
            var d = parseFloat(txt);
            if (d >= 1.01 && d <= 200) return d;
        }
        if (/^[+-]\d{2,5}$/.test(txt)) {
            var a = parseInt(txt, 10);
            return parseFloat((a > 0 ? (a / 100) + 1 : (100 / Math.abs(a)) + 1).toFixed(3));
        }
        return null;
    }

    // FanDuel URL slug encodes player names reliably:
    //   /tennis/atp-geneva-2026/alex-michelsen-v-learner-tien-35632961
    // Split on -v- to get player slugs, strip trailing numeric event ID.
    function namesFromUrl() {
        var path  = window.location.pathname;
        var slug  = path.split('/').pop().split('?')[0];
        var vIdx  = slug.indexOf('-v-');
        if (vIdx < 0) return null;
        var p1Slug = slug.substring(0, vIdx);
        var rest   = slug.substring(vIdx + 3);
        var idMatch = rest.match(/^(.*?)-(\d{5,12})$/);
        if (!idMatch) return null;
        function titleCase(s) {
            return s.split('-').map(function(w) {
                return w.charAt(0).toUpperCase() + w.slice(1);
            }).join(' ');
        }
        return { p1: titleCase(p1Slug), p2: titleCase(idMatch[1]) };
    }

    // FanDuel event ID is the trailing numeric segment of the URL
    function eventIdFromUrl() {
        var m = window.location.pathname.match(/-(\d{5,12})(?:\/|$|\?)/);
        return m ? m[1] : 'dom-' + Date.now();
    }

    // FanDuel renders outcome cells as <div aria-label="Player Name to win, +280 Odds">
    // — there is no usable innerText on betting buttons. Parse the aria-label directly.
    function readMarket() {
        // Pattern: "{name} to win, {american_odds} Odds"
        var pattern = /^(.+?)\s+to\s+win,\s*([+\-]\d{2,5})\s+odds?$/i;
        var els = document.querySelectorAll('[aria-label]');
        var outcomes = [];
        for (var i = 0; i < els.length && outcomes.length < 4; i++) {
            var lbl = (els[i].getAttribute('aria-label') || '').trim();
            var m = lbl.match(pattern);
            if (!m) continue;
            var price = toDecimal(m[2]);
            if (price !== null) outcomes.push({ name: m[1].trim(), price: price });
        }
        if (outcomes.length >= 2) {
            return {
                p1_name: outcomes[0].name, p1_odds: outcomes[0].price,
                p2_name: outcomes[1].name, p2_odds: outcomes[1].price,
            };
        }
        return null;
    }

    function maybeRelay() {
        var market = readMarket();
        if (!market) return;

        // Names come directly from aria-labels; URL slug fills gaps if somehow empty
        var urlNames = namesFromUrl();
        var p1_name = market.p1_name || (urlNames ? urlNames.p1 : '');
        var p2_name = market.p2_name || (urlNames ? urlNames.p2 : '');

        var key = market.p1_odds + '/' + market.p2_odds;
        if (key === _lastKey) return;
        _lastKey = key;

        window.postMessage({
            __arb: true,
            type:  'fanduel_dom_odds',
            body:  JSON.stringify({
                eventId:  eventIdFromUrl(),
                p1_name:  p1_name,
                p1_odds:  market.p1_odds,
                p2_name:  p2_name,
                p2_odds:  market.p2_odds,
            }),
        }, '*');
    }

    new MutationObserver(function () {
        clearTimeout(_debounce);
        _debounce = setTimeout(maybeRelay, 100);
    }).observe(document.body, { subtree: true, childList: true });

    setInterval(function () { _lastKey = ''; maybeRelay(); }, 3000);
    setTimeout(maybeRelay, 800);

    console.log('[Arb Scanner] fanduelMonitor active');
}

// ── Injected bet365 monitor (runs in page MAIN world) ─────────────────────────
//
// bet365 DOM structure (match winner market):
//   div.gl-Market  (parent row — innerText = "Player Name\n+110\n+110")
//     div.gl-Market (leaf name cell  — innerText = "Player Name")
//     div.gl-Market (leaf odds cell  — innerText = "+110")
//     div.gl-Market (leaf odds cell  — innerText = "+110")
//
// Strategy: scan all [class*="gl-Market"] elements; the first two whose
// first line is a player name (not a market keyword / odds string) and
// whose subsequent lines contain a valid price are the match winner outcomes.
//
// bet365 is a hash-SPA — navigation between events changes window.location.hash
// without a page reload, so we also listen to 'hashchange'.

function bet365Monitor() {
    if (window.__arbBet365Monitor) return;
    window.__arbBet365Monitor = true;

    var _lastKey  = '';
    var _debounce = null;

    function toDecimal(txt) {
        txt = (txt || '').trim().replace(/[−–—]/g, '-');
        if (/^even$/i.test(txt)) return 2.0;
        if (/^\d{1,3}\.\d{2,3}$/.test(txt)) {
            var d = parseFloat(txt);
            if (d >= 1.01 && d <= 200) return d;
        }
        if (/^[+-]\d{2,5}$/.test(txt)) {
            var a = parseInt(txt, 10);
            return parseFloat((a > 0 ? (a / 100) + 1 : (100 / Math.abs(a)) + 1).toFixed(3));
        }
        return null;
    }

    // Words that flag a first line as a market heading, not a player name.
    // Covers bet365 labels: "Money Line", "Point Betting", "Match Winner", "Total Games", etc.
    var SKIP_PREFIX = /^(match|money|point|popular|featured|live|main|set|game|total|over|under|yes|no|correct|best|handicap|spread|quarter|half|period|inning|both|either|draw|tie|to\s|\d)/i;

    function readMarket() {
        var els = document.querySelectorAll('[class*="gl-Market"]');
        var outcomes = [];

        for (var i = 0; i < els.length && outcomes.length < 2; i++) {
            var txt = (els[i].innerText || '').trim().replace(/[−–—]/g, '-');
            var lines = txt.split('\n').map(function(l) { return l.trim(); }).filter(Boolean);

            if (lines.length < 2) continue;

            var name = lines[0];
            if (SKIP_PREFIX.test(name)) continue;        // known market label keyword
            if (name.length > 50) continue;              // no real player name is this long
            if (toDecimal(name) !== null) continue;      // first line is an odds value
            if (name.indexOf(' - ') >= 0) continue;      // "Point Betting - Set 1 Game 3" style labels
            if (/\([^)]+\)/.test(name)) continue;        // "(Svr)", "(ARG)" serve/team markers

            // Take the first valid price on any subsequent line
            var price = null;
            for (var j = 1; j < lines.length; j++) {
                var v = toDecimal(lines[j]);
                if (v !== null) { price = v; break; }
            }
            if (price === null) continue;

            outcomes.push({ name: name, price: price });
        }

        if (outcomes.length >= 2) {
            return {
                p1_name: outcomes[0].name, p1_odds: outcomes[0].price,
                p2_name: outcomes[1].name, p2_odds: outcomes[1].price,
            };
        }
        return null;
    }

    // bet365 encodes the event ID in the URL hash: #/IP/EV151339580655C13
    function eventIdFromHash() {
        var m = window.location.hash.match(/EV(\w+)/i);
        return m ? m[1] : 'dom-' + Date.now();
    }

    function maybeRelay() {
        // Only fire when the hash indicates we're on an in-play or pre-match event
        if (!/EV\w+/i.test(window.location.hash)) return;

        var market = readMarket();
        if (!market) return;

        var key = market.p1_odds + '/' + market.p2_odds;
        if (key === _lastKey) return;
        _lastKey = key;

        window.postMessage({
            __arb: true,
            type:  'bet365_dom_odds',
            body:  JSON.stringify({
                eventId:  eventIdFromHash(),
                p1_name:  market.p1_name,
                p1_odds:  market.p1_odds,
                p2_name:  market.p2_name,
                p2_odds:  market.p2_odds,
            }),
        }, '*');
    }

    new MutationObserver(function () {
        clearTimeout(_debounce);
        _debounce = setTimeout(maybeRelay, 100);
    }).observe(document.body, { subtree: true, childList: true });

    // Hash change = SPA navigation to a different event — reset and re-read
    window.addEventListener('hashchange', function () {
        _lastKey = '';
        setTimeout(maybeRelay, 600);   // wait for content to render
        setTimeout(maybeRelay, 1500);  // second attempt for slow loads
    });

    setInterval(function () { _lastKey = ''; maybeRelay(); }, 3000);
    setTimeout(maybeRelay, 800);

    console.log('[Arb Scanner] bet365Monitor active');
}

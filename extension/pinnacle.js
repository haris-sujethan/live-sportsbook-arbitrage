/**
 * pinnacle.js: MAIN world content script (Pinnacle tab).
 *
 * capture pinnacle_details (player names) from the
 * matchup list REST endpoint, and track the current page URL.
 *
 * Live odds are now handled by the pinnacleMonitor function injected directly
 * by background.js via chrome.scripting.executeScript
 */
(function () {
  "use strict";

  var _cachedMatchupId = null;

  function currentMatchupId() {
    var m = window.location.href.match(/\/(\d{7,12})\/?(?:[?#]|$)/);
    if (m) _cachedMatchupId = m[1];
    return _cachedMatchupId;
  }

  function isPinnacleApi(url) {
    return url.indexOf("api.arcadia.pinnacle.com") !== -1;
  }

  function relay(msgType, body) {
    window.postMessage(
      {
        __arb: true,
        type: msgType,
        matchup_id: currentMatchupId() || "",
        body: body,
      },
      "*",
    );
  }

  // Fetch intercept

  var _origFetch = window.fetch;

  window.fetch = function (input, init) {
    var url =
      typeof input === "string"
        ? input
        : input instanceof Request
          ? input.url
          : "";
    var p = _origFetch.apply(this, arguments);

    if (isPinnacleApi(url) && /\/leagues\/\d+\/matchups/.test(url)) {
      p.then(function (resp) {
        if (resp.ok) {
          resp
            .clone()
            .text()
            .then(function (body) {
              relay("pinnacle_details", body);
            })
            .catch(function () {});
        } else if (resp.status === 304) {
          _origFetch(url.split("?")[0], {
            headers: { Accept: "application/json" },
            cache: "no-store",
          })
            .then(function (r) {
              return r.ok ? r.text() : null;
            })
            .then(function (body) {
              if (body) relay("pinnacle_details", body);
            })
            .catch(function () {});
        }
      }).catch(function () {});
    }

    return p;
  };

  // XHR intercept

  var _origOpen = XMLHttpRequest.prototype.open;
  var _origSend = XMLHttpRequest.prototype.send;

  XMLHttpRequest.prototype.open = function (method, url) {
    this._arbUrl = typeof url === "string" ? url : "";
    return _origOpen.apply(this, arguments);
  };

  XMLHttpRequest.prototype.send = function () {
    var url = this._arbUrl || "";
    if (isPinnacleApi(url) && /\/leagues\/\d+\/matchups/.test(url)) {
      var self = this;
      self.addEventListener("load", function () {
        if (self.status === 200 && self.responseText) {
          relay("pinnacle_details", self.responseText);
        }
      });
    }
    return _origSend.apply(this, arguments);
  };

  // URL tracking

  function sendUrl() {
    window.postMessage(
      {
        __arb: true,
        type: "pinnacle_url",
        url: window.location.href,
      },
      "*",
    );
  }

  sendUrl();
  window.addEventListener("popstate", sendUrl);
  var _lastUrl = location.href;
  setInterval(function () {
    if (location.href !== _lastUrl) {
      _lastUrl = location.href;
      sendUrl();
    }
  }, 1000);

  console.log("[Arb Scanner] pinnacle.js loaded");
})();

"""
pinnacle.py — Pinnacle API client.

Pinnacle serves odds via a REST API at api.arcadia.pinnacle.com.
Cache-Control is max-age=5, so prices update every 5 seconds.

Endpoints used:
  GET /0.1/matchups/{matchupId}
      Returns match details including participant names.

  GET /0.1/matchups/{matchupId}/markets/related/straight
      Returns all straight markets (moneyline, spread, total).
      We filter for: type=moneyline, period=0, isAlternate=False, status=open

The matchupId is a 7-10 digit number found in the Pinnacle page URL.
Example URL: https://www.pinnacle.ca/en/tennis/atp-rome/sinner-vs-ruud/1630966756/
"""

import os
import re
import requests
from dotenv import load_dotenv
from arb import american_to_decimal

load_dotenv()

BASE_URL = 'https://api.arcadia.pinnacle.com/0.1'

_API_KEY = os.environ['PINNACLE_API_KEY']

HEADERS = {
    'Accept':           'application/json',
    'Accept-Language':  'en-US,en;q=0.9',
    'Referer':          'https://www.pinnacle.ca/',
    'X-API-Key':        _API_KEY,
}

TIMEOUT = 5


def extract_matchup_id(url: str) -> str | None:
    """
    Extract the matchupId from a Pinnacle page URL or API URL.

    Handles:
      https://www.pinnacle.ca/en/tennis/atp-rome/sinner-vs-ruud/1630966756/
      https://api.arcadia.pinnacle.com/0.1/matchups/1630966756/markets/...
    """
    if not url:
        return None
    # 7-12 digit number preceded by slash
    matches = re.findall(r'/(\d{7,12})(?:/|$)', url)
    if matches:
        return matches[-1]
    return None


def get_matchup_details(matchup_id: str) -> dict | None:
    """
    Fetch participant names and match metadata for a matchupId.

    Returns:
    {
        'matchup_id': '1630966756',
        'home_name':  'Jannik Sinner',
        'away_name':  'Casper Ruud',
        'league':     'ATP Rome',
        'is_live':    True,
        'sport':      'Tennis',
    }
    """
    url = f'{BASE_URL}/matchups/{matchup_id}'
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code != 200:
            print(f'[pinnacle] matchup details HTTP {resp.status_code} for {matchup_id}')
            return None
        data = resp.json()
    except Exception as e:
        print(f'[pinnacle] matchup details error: {e}')
        return None

    participants = data.get('participants', [])
    if len(participants) < 2:
        return None

    home = next((p for p in participants if p.get('alignment') == 'home'), None)
    away = next((p for p in participants if p.get('alignment') == 'away'), None)

    if not home or not away:
        return None

    league = data.get('league', {})
    sport  = league.get('sport', {})

    return {
        'matchup_id': str(matchup_id),
        'home_name':  home.get('name', ''),
        'away_name':  away.get('name', ''),
        'league':     league.get('name', ''),
        'is_live':    data.get('isLive', False),
        'sport':      sport.get('name', ''),
    }


def get_moneyline(matchup_id: str) -> dict | None:
    """
    Fetch current moneyline odds from Pinnacle for a matchupId.

    We prefer period=0 (full match) over period=1 (current set).

    Returns:
    {
        'source':         'pinnacle',
        'matchup_id':     '1630966756',
        'period':         0,
        'home': {
            'odds_american': -215,
            'odds_decimal':   1.465...,
        },
        'away': {
            'odds_american':  174,
            'odds_decimal':   2.74,
        },
        'version':        3613350834,
    }
    """
    url = f'{BASE_URL}/matchups/{matchup_id}/markets/related/straight'
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code != 200:
            return None
        markets = resp.json()
    except Exception as e:
        print(f'[pinnacle] moneyline error: {e}')
        return None

    if not isinstance(markets, list):
        return None

    # Priority: period 0 full match moneyline, not alternate, status open
    moneyline = _find_moneyline(markets, period=0)
    if not moneyline:
        # Fall back to period 1 (current set) for in-play
        moneyline = _find_moneyline(markets, period=1)
    if not moneyline:
        return None

    prices = moneyline.get('prices', [])
    home_p = next((p for p in prices if p.get('designation') == 'home'), None)
    away_p = next((p for p in prices if p.get('designation') == 'away'), None)

    if not home_p or not away_p:
        return None

    home_am = home_p['price']
    away_am = away_p['price']

    return {
        'source':     'pinnacle',
        'matchup_id': str(matchup_id),
        'period':     moneyline.get('period', 0),
        'home': {
            'odds_american': home_am,
            'odds_decimal':  american_to_decimal(home_am),
        },
        'away': {
            'odds_american': away_am,
            'odds_decimal':  american_to_decimal(away_am),
        },
        'version': moneyline.get('version'),
    }


def parse_matchup_details(body: str, matchup_id: str) -> dict | None:
    """
    Parse league/matchups response (array) or single matchup response (dict).
    Filters to the specific matchup_id when the response is a league-level array.
    """
    import json
    try:
        data = json.loads(body)
    except Exception:
        return None

    # League-level /leagues/{id}/matchups returns a list
    if isinstance(data, list):
        mid_int = int(matchup_id) if matchup_id.isdigit() else None
        data = next((m for m in data if m.get('id') == mid_int), None)
        if not data:
            return None

    participants = data.get('participants', [])
    if len(participants) < 2:
        return None

    home = next((p for p in participants if p.get('alignment') == 'home'), None)
    away = next((p for p in participants if p.get('alignment') == 'away'), None)
    if not home or not away:
        return None

    league = data.get('league', {})
    sport  = league.get('sport', {})

    return {
        'matchup_id': str(matchup_id),
        'home_name':  home.get('name', ''),
        'away_name':  away.get('name', ''),
        'league':     league.get('name', ''),
        'is_live':    data.get('isLive', False),
        'sport':      sport.get('name', ''),
    }


def parse_straight_response(body: str, matchup_id: str) -> dict | None:
    """
    Parse straight markets response — either league-level (array with matchupId
    fields) or matchup-level (array without). Filters by matchup_id when present.
    """
    import json
    try:
        markets = json.loads(body)
    except Exception:
        return None

    if not isinstance(markets, list):
        return None

    mid_int = int(matchup_id) if matchup_id.isdigit() else None

    moneyline = _find_moneyline(markets, period=0, matchup_id=mid_int)
    if not moneyline:
        moneyline = _find_moneyline(markets, period=1, matchup_id=mid_int)
    if not moneyline:
        return None

    prices = moneyline.get('prices', [])
    home_p = next((p for p in prices if p.get('designation') == 'home'), None)
    away_p = next((p for p in prices if p.get('designation') == 'away'), None)

    if not home_p or not away_p:
        return None

    home_am = home_p['price']
    away_am = away_p['price']

    return {
        'source':     'pinnacle',
        'matchup_id': str(matchup_id),
        'period':     moneyline.get('period', 0),
        'home': {
            'odds_american': home_am,
            'odds_decimal':  american_to_decimal(home_am),
        },
        'away': {
            'odds_american': away_am,
            'odds_decimal':  american_to_decimal(away_am),
        },
        'version': moneyline.get('version'),
    }


def _find_moneyline(markets: list, period: int, matchup_id: int | None = None) -> dict | None:
    for m in markets:
        if matchup_id is not None:
            # League-level response: each market has a matchupId field
            if m.get('matchupId') != matchup_id:
                continue
        if (m.get('type') == 'moneyline'
                and m.get('period') == period
                and not m.get('isAlternate', False)
                and m.get('status') == 'open'):
            return m
    return None


def is_pinnacle_url(url: str) -> bool:
    return 'pinnacle.ca' in url or 'arcadia.pinnacle.com' in url


def is_straight_markets_url(url: str) -> bool:
    return 'markets/related/straight' in url

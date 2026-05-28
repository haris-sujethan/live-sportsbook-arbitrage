"""
arb.py: Arbitrage calculation utilities.

"""


def american_to_decimal(american: int) -> float:
    if american > 0:
        return round((american / 100) + 1, 6)
    else:
        return round((100 / abs(american)) + 1, 6)


def decimal_to_american(decimal: float) -> int:
    if decimal >= 2.0:
        return int((decimal - 1) * 100)
    else:
        return int(-100 / (decimal - 1))


def implied(decimal: float) -> float:
    if decimal <= 1.0:
        return 1.0
    return 1.0 / decimal


def arb_margin(price_a: float, price_b: float) -> float:
    """
    Calculate arbitrage margin between two decimal prices.

    price_a = one side on book A (decimal)
    price_b = opposite side on book B (decimal)

    Returns:
        positive float  = profit margin exists
        negative float  = no arb, margin is how far from breakeven
    """
    return 1.0 - (implied(price_a) + implied(price_b))


def kelly_stakes(price_a: float, price_b: float, total: float = 100.0) -> dict:
    """
    Calculate optimal stakes for a guaranteed arb profit.

    price_a  = side A decimal odds (bet on book A)
    price_b  = side B decimal odds (bet on book B)
    total    = total amount to stake across both sides

    Stakes are rounded to whole dollars to avoid cent-precision bets
    that are more likely to trigger limits. 

    Returns dict with stake_a, stake_b, profit, return, margin_pct.
    Returns None if no arb exists.
    """
    imp_a = implied(price_a)
    imp_b = implied(price_b)
    total_imp = imp_a + imp_b

    margin = 1.0 - total_imp
    if margin <= 0:
        return None

    stake_a = int(round(total * (imp_a / total_imp)))
    stake_b = int(round(total * (imp_b / total_imp)))

    actual_total = stake_a + stake_b

    payout_a = stake_a * price_a
    payout_b = stake_b * price_b 
    guaranteed_return = min(payout_a, payout_b)
    profit = guaranteed_return - actual_total

    return {
        'stake_a':    stake_a,
        'stake_b':    stake_b,
        'profit':     round(profit, 2),
        'total':      actual_total,
        'return':     round(guaranteed_return, 2),
        'margin_pct': round(margin * 100, 3),
    }


def find_best_arb(
    pinnacle_home: float,
    pinnacle_away: float,
    soft_home: float,
    soft_away: float,
    total_stake: float = 100.0,
) -> dict | None:
    
    if not all([pinnacle_home, pinnacle_away, soft_home, soft_away]):
        return None
    if any(v <= 1.0 for v in [pinnacle_home, pinnacle_away, soft_home, soft_away]):
        return None

    margin_a = arb_margin(pinnacle_home, soft_away)
    margin_b = arb_margin(pinnacle_away, soft_home)

    best_margin = max(margin_a, margin_b)

    if best_margin <= 0:
        return None

    if margin_a >= margin_b:
        stakes = kelly_stakes(pinnacle_home, soft_away, total_stake)
        return {
            'direction':      'A',
            'pinnacle_side':  'home',
            'soft_side':      'away',
            'pinnacle_price': pinnacle_home,
            'soft_price':     soft_away,
            'margin':         margin_a,
            'stakes':         stakes,
        }
    else:
        stakes = kelly_stakes(pinnacle_away, soft_home, total_stake)
        return {
            'direction':      'B',
            'pinnacle_side':  'away',
            'soft_side':      'home',
            'pinnacle_price': pinnacle_away,
            'soft_price':     soft_home,
            'margin':         margin_b,
            'stakes':         stakes,
        }

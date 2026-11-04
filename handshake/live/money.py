"""Amounts in the words Handshake writes, in the merchant's currency.

The currency comes from the traffic (a checkout response's `currency`) or the
catalogue record. The demo store sends none, and it sells in rupees.
"""

SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥",
           "CAD": "CA$", "AUD": "A$", "SGD": "S$"}
DEFAULT = "INR"


def fmt(amount, currency=None, decimals=2):
    code = (currency or DEFAULT).upper()
    sym = SYMBOLS.get(code, code + " ")
    return f"{sym}{amount:,.{decimals}f}"


def of(*records):
    """The first currency any of these responses or records states."""
    for r in records:
        if isinstance(r, dict) and r.get("currency"):
            return r["currency"]
    return None

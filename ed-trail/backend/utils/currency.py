"""
ED-TRAIL Currency Utilities
INR handling per ed-trail/prd.md Section 3.

Rupees → Paise conversion in ED-TRAIL only.
"""


def rupees_to_paise(rupees: float) -> int:
    """Convert rupees to paise (×100)."""
    return int(round(rupees * 100))


def paise_to_rupees(paise: int) -> float:
    """Convert paise to rupees (÷100)."""
    return paise / 100.0


def format_inr(paise: int) -> str:
    """Format paise as INR display string."""
    rupees = paise_to_rupees(paise)
    return f"₹{rupees:,.2f}"


def validate_amount_rupees(rupees: float) -> bool:
    """Validate rupee amount is positive and reasonable."""
    if rupees < 0:
        return False
    if rupees > 1_000_000_000_000:  # 1 trillion rupee limit
        return False
    return True

"""
Unit conversion utilities for VitaranIQ.
Internal computations:
- Money: Integer paise (₹1 = 100 paise)
- Volume: Integer millilitres (1 Litre = 1000 ml)
"""

def paise_to_inr(paise: int) -> float:
    """Convert integer paise to decimal INR (₹)."""
    return round(paise / 100.0, 2)


def inr_to_paise(inr: float) -> int:
    """Convert decimal INR to integer paise."""
    return int(round(inr * 100))


def ml_to_litres(ml: int) -> float:
    """Convert integer ml to decimal Litres."""
    return round(ml / 1000.0, 3)


def litres_to_ml(litres: float) -> int:
    """Convert decimal Litres to integer ml."""
    return int(round(litres * 1000))

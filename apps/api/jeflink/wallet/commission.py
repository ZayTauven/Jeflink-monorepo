"""Calcul de la commission (spec 005) : fonction pure, en entiers seulement."""

BPS_PER_UNIT = 10_000


def commission_xof(base_xof: int, rate_bps: int, cap_xof: int | None) -> int:
    """``min(base * taux // 10 000, plafond)`` : arrondi à l'entier inférieur, donc en faveur du
    pro. Aucune division réelle (test d'architecture)."""
    for value in (base_xof, rate_bps):
        if type(value) is not int or value < 0:
            raise ValueError("entiers positifs attendus")
    if cap_xof is not None and (type(cap_xof) is not int or cap_xof <= 0):
        raise ValueError("plafond invalide")
    amount = base_xof * rate_bps // BPS_PER_UNIT
    return amount if cap_xof is None else min(amount, cap_xof)

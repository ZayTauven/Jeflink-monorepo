"""Taux de lancement par métier (spec 005, Q1), chargés par ``seed_reference_data``.

Le taux par défaut (10 %, plafond 20 000 F) est posé par la migration 0005. Les métiers où les
pièces pèsent ont un taux plus bas, l'assiette étant le montant total convenu (Q3).
"""

LAUNCH_TRADE_RATES = [
    {"trade": "climatisation", "rate_bps": 700, "cap_xof": 20_000},
    {"trade": "electromenager", "rate_bps": 700, "cap_xof": 20_000},
    {"trade": "plombier", "rate_bps": 700, "cap_xof": 20_000},
]

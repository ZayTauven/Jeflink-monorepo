"""En-tête ``Idempotency-Key`` des créations (demande, devis) : une clé par saisie."""

from drf_spectacular.utils import OpenApiParameter
from rest_framework.request import Request

IDEMPOTENCY_PARAMETER = OpenApiParameter(
    "Idempotency-Key",
    str,
    OpenApiParameter.HEADER,
    required=True,
    description=(
        "Une clé par saisie (22 à 64 caractères : lettres, chiffres, « - », « _ »). "
        "Même clé et même corps : même réponse (200 au rejeu). "
        "Même clé et autre corps : 409 idempotency_key_reused."
    ),
)


def idempotency_key(request: Request) -> str:
    return request.headers.get("Idempotency-Key", "")

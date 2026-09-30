"""Interface d'envoi de SMS (ADR 0008). Aucun domaine n'appelle un fournisseur directement.

Règles pour tout adaptateur :
- ne jamais journaliser le corps HTTP, le texte du SMS ni le numéro complet (S14) ;
- classer chaque échec dans l'une des trois exceptions ; un mauvais classement peut
  provoquer un double envoi ou un code perdu.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class SmsResult:
    gateway: str
    provider_message_id: str
    segments: int
    status: str  # "sent" (accepté par le fournisseur) ou "queued"


class SmsError(Exception):
    """Base des erreurs d'envoi. ``code`` est un code court du fournisseur, sans donnée perso."""

    def __init__(self, code: str = "") -> None:
        super().__init__(code)
        self.code = code


class SmsTransientError(SmsError):
    """Échec sûr et temporaire (réseau, 5xx avant acceptation) : un nouvel essai est permis."""


class SmsAmbiguousError(SmsError):
    """Issue inconnue (délai dépassé après envoi) : pas de nouvel essai, risque de doublon."""


class SmsPermanentError(SmsError):
    """Refus définitif (numéro invalide, expéditeur refusé, crédit épuisé)."""


class SmsGateway(ABC):
    name: str

    @abstractmethod
    def send(self, *, to: str, body: str, idempotency_key: str, sender_id: str) -> SmsResult:
        """Envoie ``body`` à ``to`` (E.164).

        Même ``idempotency_key`` : un seul SMS envoyé, même résultat renvoyé.
        """

"""Adaptateur de développement et de test : n'envoie rien.

Autorisé seulement si ``DJANGO_ENV`` vaut ``local`` ou ``test`` (S23), jamais selon ``DEBUG``.
En ``local``, le SMS s'affiche dans la console du worker pour se connecter sans téléphone.
"""

import sys
import uuid
from dataclasses import dataclass

from django.conf import settings

from jeflink.common.gsm7 import segments

from .base import SmsGateway, SmsResult


@dataclass(frozen=True)
class SentSms:
    to: str
    body: str
    sender_id: str
    result: SmsResult


class FakeSmsGateway(SmsGateway):
    name = "fake"
    # Boîte d'envoi partagée par le processus : lue par les tests, vidée entre deux tests.
    outbox: list[SentSms] = []
    _by_key: dict[str, SmsResult] = {}

    def send(self, *, to: str, body: str, idempotency_key: str, sender_id: str) -> SmsResult:
        if idempotency_key in self._by_key:
            return self._by_key[idempotency_key]
        result = SmsResult(
            gateway=self.name,
            provider_message_id=f"fake-{uuid.uuid4().hex[:12]}",
            segments=segments(body),
            status="sent",
        )
        self._by_key[idempotency_key] = result
        self.outbox.append(SentSms(to=to, body=body, sender_id=sender_id, result=result))
        if settings.DJANGO_ENV == "local":
            # Volontairement hors du logging (qui masquerait le numéro) : poste de dev seulement.
            sys.stdout.write(f"\n[SMS fake → {to}]\n{body}\n\n")
        return result

    @classmethod
    def reset(cls) -> None:
        cls.outbox.clear()
        cls._by_key.clear()

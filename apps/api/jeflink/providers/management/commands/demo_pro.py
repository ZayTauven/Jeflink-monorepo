"""Joue le côté pro en local (spec 003, Q6) : pas d'espace pro web avant l'étape 6.

    manage.py demo_pro list
    manage.py demo_pro quote <request_id> [--pro 1] [--amount 15000] [--day 1] [--period morning]
    manage.py demo_pro autoquote <request_id> [--count 3]
    manage.py demo_pro withdraw <quote_id>
    manage.py demo_pro confirm <booking_id>
    manage.py demo_pro cancel <booking_id> [--reason unavailable] [--note ...]

Refusé hors ``DJANGO_ENV=local``. Il n'agit que par les services, avec les pros ``is_demo``
créés par ``seed_demo_pros`` : mêmes règles que l'API (3 places, devis ``visit``, délais).
"""

import secrets
import uuid
from argparse import ArgumentParser
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from jeflink.bookings.machine import Actor
from jeflink.bookings.models import Booking
from jeflink.bookings.selectors import bookings_for_provider
from jeflink.bookings.services import cancel_booking, confirm_booking
from jeflink.common.dakar import dakar_today
from jeflink.common.errors import DomainError
from jeflink.providers.models import Provider
from jeflink.requests.models import Quote, ServiceRequest
from jeflink.requests.quotes import (
    QuoteInput,
    QuoteLineInput,
    submit_quote,
    withdraw_quote,
)
from jeflink.requests.selectors import quotes_for_provider, requests_for_provider

# Trois propositions de départ : prix et créneaux différents, comme trois vrais pros.
AUTOQUOTE_PLANS = [
    (12_000, 1, "morning", "Remplacement et main-d'œuvre, matériel compris."),
    (18_500, 1, "afternoon", "Intervention complète avec garantie de ma pose."),
    (15_000, 2, "morning", "Je passe après-demain matin, devis ferme."),
]


def demo_providers() -> list[Provider]:
    return list(
        Provider.objects.filter(is_demo=True, status=Provider.Status.VERIFIED).order_by("pk")
    )


def _uuid(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise CommandError("Identifiant invalide (public_id attendu).") from exc


def _key() -> str:
    return secrets.token_urlsafe(24)


class Command(BaseCommand):
    help = "Joue le côté pro en local : list, quote, autoquote, withdraw, confirm, cancel."

    def add_arguments(self, parser: ArgumentParser) -> None:
        sub = parser.add_subparsers(dest="action", required=True)
        sub.add_parser("list", help="Demandes pour les pros de démo, leurs devis et réservations.")
        quote = sub.add_parser("quote", help="Un pro de démo envoie un devis.")
        quote.add_argument("request_id")
        quote.add_argument("--pro", type=int, default=1, help="Numéro du pro de démo (1 à 3).")
        quote.add_argument("--amount", type=int, default=15_000)
        quote.add_argument("--day", type=int, default=1, help="Dans combien de jours (0 à 30).")
        quote.add_argument(
            "--period", default="morning", choices=("morning", "afternoon", "evening")
        )
        quote.add_argument("--visit", action="store_true", help="Devis « Visite seulement ».")
        auto = sub.add_parser("autoquote", help="Les pros de démo envoient chacun un devis.")
        auto.add_argument("request_id")
        auto.add_argument("--count", type=int, default=3)
        withdraw = sub.add_parser("withdraw", help="Retire un devis envoyé.")
        withdraw.add_argument("quote_id")
        confirm = sub.add_parser("confirm", help="Confirme une réservation (accepted → scheduled).")
        confirm.add_argument("booking_id")
        cancel = sub.add_parser("cancel", help="Le pro se désiste.")
        cancel.add_argument("booking_id")
        cancel.add_argument("--reason", default="unavailable")
        cancel.add_argument("--note", default="")

    def handle(self, *args, **options) -> None:
        if settings.DJANGO_ENV != "local":
            raise CommandError("Commande de démonstration : refusée hors DJANGO_ENV=local.")
        pros = demo_providers()
        if not pros:
            raise CommandError("Aucun pro de démo : lancez `manage.py seed_demo_pros`.")
        try:
            getattr(self, f"do_{options['action']}")(pros, options)
        except DomainError as exc:
            raise CommandError(f"{exc.code}") from exc

    # --- Actions -----------------------------------------------------------------------------

    def do_list(self, pros: list[Provider], options: dict) -> None:
        for number, pro in enumerate(pros, start=1):
            self.stdout.write(f"== Pro de démo {number} : {pro.business_name}")
            for request in requests_for_provider(provider=pro)[:20]:
                flag = " urgente" if request.urgent else ""
                self.stdout.write(
                    f"  demande {request.public_id} · {request.trade.slug} · "
                    f"{request.zone.slug} · {request.active_quotes}/3 devis{flag}"
                )
            for quote in quotes_for_provider(provider=pro).order_by("-created_at")[:20]:
                self.stdout.write(
                    f"  devis {quote.public_id} · {quote.status} · {quote.total_xof} XOF · "
                    f"demande {quote.request.public_id}"
                )
            for booking in bookings_for_provider(provider=pro)[:20]:
                self.stdout.write(
                    f"  réservation {booking.public_id} · {booking.status} · "
                    f"échéance {booking.confirm_deadline:%d/%m %H:%M} UTC"
                )

    def _request(self, raw: str) -> ServiceRequest:
        request = ServiceRequest.objects.filter(public_id=_uuid(raw)).first()
        if request is None:
            raise CommandError("Demande introuvable.")
        return request

    def _send(self, pro, request, *, amount, days, period, message, visit=False) -> Quote:
        kind = "visit" if visit else "fixed"
        line = "travel" if visit else "labor"
        content = QuoteInput(
            kind=kind,
            total_xof=amount,
            lines=(QuoteLineInput(line, amount, "Déplacement" if visit else "Intervention"),),
            slot_day=dakar_today(timezone.now()) + timedelta(days=days),
            slot_period=period,
            message=message,
            visit_deductible=visit,
        )
        return submit_quote(
            provider=pro, request=request, content=content, idempotency_key=_key()
        ).quote

    def do_quote(self, pros: list[Provider], options: dict) -> None:
        if not 1 <= options["pro"] <= len(pros):
            raise CommandError(f"--pro : de 1 à {len(pros)}.")
        quote = self._send(
            pros[options["pro"] - 1],
            self._request(options["request_id"]),
            amount=options["amount"],
            days=options["day"],
            period=options["period"],
            message="Devis de démonstration.",
            visit=options["visit"],
        )
        self.stdout.write(f"Devis envoyé : {quote.public_id} ({quote.total_xof} XOF)")

    def do_autoquote(self, pros: list[Provider], options: dict) -> None:
        request = self._request(options["request_id"])
        sent = 0
        for pro, (amount, days, period, message) in zip(
            pros, AUTOQUOTE_PLANS[: options["count"]], strict=False
        ):
            try:
                quote = self._send(
                    pro, request, amount=amount, days=days, period=period, message=message
                )
            except DomainError as exc:
                self.stdout.write(f"  {pro.business_name} : {exc.code}")
                continue
            sent += 1
            self.stdout.write(f"  {pro.business_name} : devis {quote.public_id} ({amount} XOF)")
        self.stdout.write(f"{sent} devis envoyé(s).")

    def do_withdraw(self, pros: list[Provider], options: dict) -> None:
        quote = Quote.objects.filter(
            public_id=_uuid(options["quote_id"]), provider__in=pros
        ).first()
        if quote is None:
            raise CommandError("Devis introuvable parmi ceux des pros de démo.")
        withdraw_quote(quote=quote, provider=quote.provider)
        self.stdout.write("Devis retiré.")

    def _booking(self, raw: str, pros: list[Provider]) -> Booking:
        booking = (
            Booking.objects.filter(public_id=_uuid(raw), provider__in=pros)
            .select_related("provider__owner")
            .first()
        )
        if booking is None:
            raise CommandError("Réservation introuvable parmi celles des pros de démo.")
        return booking

    def do_confirm(self, pros: list[Provider], options: dict) -> None:
        booking = self._booking(options["booking_id"], pros)
        confirmed = confirm_booking(booking=booking, actor=booking.provider.owner)
        self.stdout.write(f"Réservation confirmée : {confirmed.public_id} ({confirmed.status}).")

    def do_cancel(self, pros: list[Provider], options: dict) -> None:
        booking = self._booking(options["booking_id"], pros)
        cancelled = cancel_booking(
            booking=booking,
            actor=booking.provider.owner,
            actor_kind=Actor.PRO,
            reason=options["reason"],
            note=options["note"],
        )
        self.stdout.write(f"Réservation annulée : {cancelled.public_id}.")

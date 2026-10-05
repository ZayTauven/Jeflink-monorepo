"""Joue le côté pro en local (spec 003, Q6) : pas d'espace pro web avant l'étape 6.

    manage.py demo_pro list
    manage.py demo_pro quote <request_id> [--pro 1] [--amount 15000] [--day 1] [--period morning]
    manage.py demo_pro autoquote <request_id> [--count 3]
    manage.py demo_pro withdraw <quote_id>
    manage.py demo_pro confirm <booking_id>
    manage.py demo_pro cancel <booking_id> [--reason unavailable] [--note ...]
    manage.py demo_pro en-route <booking_id>
    manage.py demo_pro arrive <booking_id>
    manage.py demo_pro start <booking_id> [--photo | --pending]
    manage.py demo_pro photo <booking_id> [--phase before|after] [--count 1]
    manage.py demo_pro amend <booking_id> --total 22000 [--reason extra_work]
    manage.py demo_pro complete <booking_id> (--code 1234 | --no-code client_absent)
        [--photo | --pending]
    manage.py demo_pro contest <booking_id> --note "J'étais sur place"
    manage.py demo_pro wallet [--pro 1]
    manage.py demo_pro pay --amount 1500 [--channel wave-demo] [--pro 1]

Refusé hors ``DJANGO_ENV=local``. Il n'agit que par les services, avec les pros ``is_demo``
créés par ``seed_demo_pros`` : mêmes règles que l'API (3 places, devis ``visit``, délais).
"""

import io
import secrets
import uuid
from argparse import ArgumentParser
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from PIL import Image

from jeflink.bookings.machine import Actor
from jeflink.bookings.models import Booking
from jeflink.bookings.selectors import bookings_for_provider
from jeflink.bookings.services import (
    cancel_booking,
    complete_work,
    confirm_booking,
    contest_no_show,
    make_thumbnail,
    mark_arrived,
    mark_en_route,
    propose_amendment,
    start_work,
    upload_photo,
)
from jeflink.common.dakar import dakar_today
from jeflink.common.errors import DomainError
from jeflink.payments.selectors import channel_by_slug, intents_for_provider
from jeflink.payments.services import declare_settlement
from jeflink.providers.models import Provider
from jeflink.requests.models import Quote, ServiceRequest
from jeflink.requests.quotes import (
    QuoteInput,
    QuoteLineInput,
    submit_quote,
    withdraw_quote,
)
from jeflink.requests.selectors import quotes_for_provider, requests_for_provider
from jeflink.wallet.selectors import entries_for_provider, provider_wallet

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


def demo_photo() -> bytes:
    """Une photo factice avec un EXIF et une position GPS (Dakar) : elle prouve, en local, que
    l'API ne stocke jamais la position (spec 004)."""
    image = Image.new("RGB", (2400, 1600), (70, 120, 160))
    exif = Image.Exif()
    exif[0x010F] = "Appareil de démonstration"
    exif[0x8825] = {1: "N", 2: (14.0, 41.0, 30.0), 3: "W", 4: (17.0, 26.0, 0.0)}
    out = io.BytesIO()
    image.save(out, format="JPEG", exif=exif)
    return out.getvalue()


def _key() -> str:
    return secrets.token_urlsafe(24)


class Command(BaseCommand):
    help = (
        "Joue le côté pro en local : list, quote, autoquote, withdraw, confirm, cancel, "
        "en-route, arrive, start, photo, amend, complete, contest, wallet, pay."
    )

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

        for name, help_text in (
            ("en-route", "Le pro part (scheduled → en_route) : le SMS du code part au client."),
            ("arrive", "Le pro est sur place (rattrape en_route si besoin)."),
        ):
            step = sub.add_parser(name, help=help_text)
            step.add_argument("booking_id")
        start = sub.add_parser("start", help="Le pro commence (photo « avant » exigée).")
        start.add_argument("booking_id")
        start.add_argument("--photo", action="store_true", help="Envoie d'abord une photo factice.")
        start.add_argument("--pending", action="store_true", help="photos_pending : sans photo.")
        photo = sub.add_parser("photo", help="Envoie une photo factice (EXIF et GPS à retirer).")
        photo.add_argument("booking_id")
        photo.add_argument("--phase", default="before", choices=("before", "after"))
        photo.add_argument("--count", type=int, default=1)
        amend = sub.add_parser("amend", help="Le pro propose un nouveau prix complet.")
        amend.add_argument("booking_id")
        amend.add_argument("--total", type=int, required=True)
        amend.add_argument(
            "--reason", default="extra_work",
            choices=("visit_diagnosis", "extra_work", "parts", "other"),
        )  # fmt: skip
        amend.add_argument("--note", default="")
        done = sub.add_parser("complete", help="Le pro termine, avec le code ou sans code.")
        done.add_argument("booking_id")
        proof = done.add_mutually_exclusive_group(required=True)
        proof.add_argument("--code", help="Le code de fin lu par le client sur le web.")
        proof.add_argument(
            "--no-code", dest="no_code", help="client_absent, client_no_phone, code_locked…"
        )
        done.add_argument(
            "--photo", action="store_true", help="Envoie d'abord une photo « après »."
        )
        done.add_argument("--pending", action="store_true", help="photos_pending : sans photo.")
        contest = sub.add_parser("contest", help="Le pro conteste un no-show.")
        contest.add_argument("booking_id")
        contest.add_argument("--note", required=True)
        wallet = sub.add_parser("wallet", help="Portefeuille du pro : dette, état, historique.")
        wallet.add_argument("--pro", type=int, default=1)
        pay = sub.add_parser("pay", help="Le pro déclare un règlement (référence factice).")
        pay.add_argument("--amount", type=int, required=True)
        pay.add_argument("--channel", default="wave-demo")
        pay.add_argument("--pro", type=int, default=1)

    def handle(self, *args, **options) -> None:
        if settings.DJANGO_ENV != "local":
            raise CommandError("Commande de démonstration : refusée hors DJANGO_ENV=local.")
        pros = demo_providers()
        if not pros:
            raise CommandError("Aucun pro de démo : lancez `manage.py seed_demo_pros`.")
        try:
            getattr(self, "do_" + options["action"].replace("-", "_"))(pros, options)
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

    # --- Déroulé de l'intervention (spec 004) ---------------------------------------------------

    def _upload(self, booking: Booking, phase: str, count: int = 1) -> None:
        for _ in range(count):
            photo = upload_photo(
                booking=booking,
                actor=booking.provider.owner,
                phase=phase,
                content=demo_photo(),
                idempotency_key=_key(),
            ).photo
            make_thumbnail(photo_public_id=str(photo.public_id))  # sans attendre le worker
            self.stdout.write(f"Photo {phase} envoyée : {photo.public_id} (EXIF et GPS retirés).")

    def do_en_route(self, pros: list[Provider], options: dict) -> None:
        booking = self._booking(options["booking_id"], pros)
        done = mark_en_route(booking=booking, actor=booking.provider.owner)
        self.stdout.write(f"Réservation : {done.status} (notification completion_code.sms émise).")

    def do_arrive(self, pros: list[Provider], options: dict) -> None:
        booking = self._booking(options["booking_id"], pros)
        done = mark_arrived(booking=booking, actor=booking.provider.owner)
        self.stdout.write(f"Réservation : {done.status}.")

    def do_start(self, pros: list[Provider], options: dict) -> None:
        booking = self._booking(options["booking_id"], pros)
        if options["photo"]:
            self._upload(booking, "before")
        done = start_work(
            booking=booking, actor=booking.provider.owner, photos_pending=options["pending"]
        )
        self.stdout.write(f"Réservation : {done.status}.")

    def do_photo(self, pros: list[Provider], options: dict) -> None:
        self._upload(self._booking(options["booking_id"], pros), options["phase"], options["count"])

    def do_amend(self, pros: list[Provider], options: dict) -> None:
        booking = self._booking(options["booking_id"], pros)
        total = options["total"]
        result = propose_amendment(
            booking=booking,
            actor=booking.provider.owner,
            reason=options["reason"],
            note=options["note"],
            lines=(QuoteLineInput("labor", total, "Intervention"),),
            total_xof=total,
            idempotency_key=_key(),
        )
        self.stdout.write(
            f"Avenant proposé : {result.amendment.public_id} "
            f"({result.amendment.previous_amount_xof} → {total} XOF). Le client décide sur le web."
        )

    def do_complete(self, pros: list[Provider], options: dict) -> None:
        booking = self._booking(options["booking_id"], pros)
        if options["photo"]:
            self._upload(booking, "after")
        done = complete_work(
            booking=booking,
            actor=booking.provider.owner,
            code=options["code"],
            no_code_reason=options["no_code"],
            photos_pending=options["pending"],
        )
        self.stdout.write(
            f"Réservation : {done.status} ({done.completion_method}) · "
            f"contestation possible jusqu'à {done.dispute_deadline:%d/%m %H:%M} UTC."
        )

    def do_contest(self, pros: list[Provider], options: dict) -> None:
        booking = self._booking(options["booking_id"], pros)
        contest_no_show(booking=booking, actor=booking.provider.owner, note=options["note"])
        self.stdout.write("No-show contesté : l'Ops tranche.")

    # --- Portefeuille (spec 005) ---------------------------------------------------------------

    def _pro(self, pros: list[Provider], number: int) -> Provider:
        if not 1 <= number <= len(pros):
            raise CommandError(f"--pro : de 1 à {len(pros)}.")
        return pros[number - 1]

    def do_wallet(self, pros: list[Provider], options: dict) -> None:
        pro = self._pro(pros, options["pro"])
        wallet = provider_wallet(pro)
        self.stdout.write(
            f"== {pro.business_name} : doit {wallet.due_xof} XOF · en attente "
            f"{wallet.pending_xof} · dette effective {wallet.effective_due_xof} · {wallet.state}"
        )
        for entry in entries_for_provider(pro)[:10]:
            sign = "+" if entry.side == "debit" else "-"
            self.stdout.write(
                f"  {entry.created_at:%d/%m %H:%M} · {entry.transaction.kind} · "
                f"{sign}{entry.amount_xof} XOF"
            )
        for intent in intents_for_provider(pro)[:10]:
            self.stdout.write(
                f"  règlement {intent.public_id} · {intent.channel.slug} · "
                f"{intent.declared_xof} XOF · {intent.status}"
            )

    def do_pay(self, pros: list[Provider], options: dict) -> None:
        pro = self._pro(pros, options["pro"])
        intent = declare_settlement(
            provider=pro,
            actor=pro.owner,
            channel=channel_by_slug(options["channel"]),
            amount_xof=options["amount"],
            reference=f"DEMO{secrets.token_hex(5).upper()}",
            paid_at=timezone.now(),
            payer_last4="",
            idempotency_key=_key(),
        ).intent
        self.stdout.write(
            f"Règlement déclaré : {intent.public_id} ({intent.declared_xof} XOF). "
            "Le groupe Rapprochement le confirme dans l'admin."
        )

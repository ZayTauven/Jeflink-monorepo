"""Règles métier des demandes. Toute écriture passe par ici ; les vues ne font qu'appeler.

Cycle : open → booked → done, avec annulation possible avant la fin.
"""

from django.db import transaction
from django.db.models import Q
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import Quote, RequestEvent, Review, ServiceRequest

S = ServiceRequest.Status
MAX_QUOTES = 3  # évite la course au moins-disant

TRANSITIONS = {
    S.OPEN: {S.BOOKED, S.CANCELLED},
    S.BOOKED: {S.DONE, S.CANCELLED},
    S.DONE: set(),
    S.CANCELLED: set(),
}

NOTES = {
    S.OPEN: "Demande publiée",
    S.BOOKED: "Devis accepté, pro réservé",
    S.DONE: "Mission terminée",
    S.CANCELLED: "Demande annulée",
}


def transition(req: ServiceRequest, to: str, actor, note: str = "") -> ServiceRequest:
    if to not in TRANSITIONS[req.status]:
        raise ValidationError(
            f"Impossible de passer de « {req.get_status_display()} » à « {S(to).label} »."
        )
    req.status = to
    req.save(update_fields=["status", "pro", "updated_at"])
    RequestEvent.objects.create(request=req, status=to, actor=actor, note=note or NOTES[to])
    return req


# --- Lecture : qui voit quoi -------------------------------------------------------------


def open_requests_for_pro(pro):
    """Demandes ouvertes dans les métiers (et quartiers, s'il en a choisi) du pro."""
    profile = getattr(pro, "pro_profile", None)
    if profile is None:
        return ServiceRequest.objects.none()
    qs = ServiceRequest.objects.filter(status=S.OPEN, trade__in=profile.trades.all())
    if profile.zones.exists():
        qs = qs.filter(zone__in=profile.zones.all())
    return qs


def visible_requests(user):
    if user.is_staff:
        return ServiceRequest.objects.all()
    if user.is_pro:
        mine = Q(pro=user) | Q(quotes__pro=user)
        return ServiceRequest.objects.filter(
            mine | Q(pk__in=open_requests_for_pro(user).values("pk"))
        ).distinct()
    return ServiceRequest.objects.filter(client=user)


# --- Écriture ------------------------------------------------------------------------------


def _locked(req: ServiceRequest) -> ServiceRequest:
    """Relit la demande en base, verrouillée : jamais d'état périmé ni de double action."""
    return ServiceRequest.objects.select_for_update().get(pk=req.pk)


@transaction.atomic
def create_request(client, **data) -> ServiceRequest:
    if client.is_pro:
        raise PermissionDenied("Un compte pro ne publie pas de demande : créez un compte client.")
    if not data["trade"].is_active or not data["zone"].is_active:
        raise ValidationError("Ce métier ou ce quartier n'est pas ouvert pour le moment.")
    req = ServiceRequest.objects.create(client=client, **data)
    RequestEvent.objects.create(request=req, status=S.OPEN, actor=client, note=NOTES[S.OPEN])
    return req


@transaction.atomic
def submit_quote(pro, req: ServiceRequest, amount: int, message: str = "") -> Quote:
    profile = getattr(pro, "pro_profile", None)
    if not pro.is_pro or profile is None:
        raise PermissionDenied("Seul un pro peut envoyer un devis.")
    if not profile.is_verified:
        raise PermissionDenied(
            "Votre profil doit être vérifié par Jeflink avant d'envoyer un devis."
        )
    req = _locked(req)
    if req.status != S.OPEN:
        raise ValidationError("Cette demande ne reçoit plus de devis.")
    if not profile.trades.filter(pk=req.trade_id).exists():
        raise PermissionDenied("Cette demande ne correspond pas à vos métiers.")
    if req.quotes.filter(pro=pro).exists():
        raise ValidationError("Vous avez déjà envoyé un devis pour cette demande.")
    if req.quotes.count() >= MAX_QUOTES:
        raise ValidationError(f"Cette demande a déjà reçu {MAX_QUOTES} devis.")
    if amount <= 0:
        raise ValidationError("Le montant doit être un entier positif en F CFA.")
    return Quote.objects.create(request=req, pro=pro, amount=amount, message=message)


@transaction.atomic
def accept_quote(client, req: ServiceRequest, quote_id: int) -> ServiceRequest:
    req = _locked(req)
    if req.client_id != client.pk:
        raise PermissionDenied("Seul l'auteur de la demande peut choisir un devis.")
    quote = req.quotes.filter(pk=quote_id).first()
    if quote is None:
        raise ValidationError("Devis introuvable pour cette demande.")
    req.pro = quote.pro
    transition(req, S.BOOKED, client, f"Devis de {quote.pro.public_name} accepté")
    quote.status = Quote.Status.ACCEPTED
    quote.save(update_fields=["status"])
    req.quotes.exclude(pk=quote.pk).update(status=Quote.Status.DECLINED)
    return req


@transaction.atomic
def complete(actor, req: ServiceRequest) -> ServiceRequest:
    req = _locked(req)
    if actor.pk not in (req.client_id, req.pro_id):
        raise PermissionDenied("Seuls le client et le pro de la mission peuvent la clôturer.")
    return transition(req, S.DONE, actor)


@transaction.atomic
def cancel(actor, req: ServiceRequest) -> ServiceRequest:
    req = _locked(req)
    if actor.pk != req.client_id:
        raise PermissionDenied("Seul l'auteur de la demande peut l'annuler.")
    return transition(req, S.CANCELLED, actor)


@transaction.atomic
def leave_review(client, req: ServiceRequest, rating: int, comment: str = "") -> Review:
    req = _locked(req)
    if client.pk != req.client_id:
        raise PermissionDenied("Seul le client de la mission peut laisser un avis.")
    if req.status != S.DONE:
        raise ValidationError("On laisse un avis une fois la mission terminée.")
    if hasattr(req, "review"):
        raise ValidationError("Vous avez déjà laissé un avis pour cette mission.")
    return Review.objects.create(request=req, rating=rating, comment=comment)

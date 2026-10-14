"""Règles métier des demandes. Toute écriture passe par ici ; les vues ne font qu'appeler.

Cycle : open → booked → done, avec annulation possible avant la fin. Mission réservée annulée
par le client : booked → cancelling (« Annulation demandée »), puis le support confirme
(cancelled) ou maintient la mission (booked).
"""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import Coupon, Dispute, Quote, RequestEvent, Review, ServiceRequest

S = ServiceRequest.Status
R = ServiceRequest.CancelReason


def platform():
    """Réglages de la plateforme (devis maximum, pause des demandes…), modifiés dans la console."""
    from jeflink.console.models import PlatformSettings

    return PlatformSettings.load()


def max_quotes() -> int:
    """Devis maximum par demande : évite la course au moins-disant (3 par défaut)."""
    return platform().max_quotes


TRANSITIONS = {
    S.OPEN: {S.BOOKED, S.CANCELLED},
    S.BOOKED: {S.DONE, S.CANCELLING, S.CANCELLED},
    S.CANCELLING: {S.BOOKED, S.CANCELLED},
    S.DONE: set(),
    S.CANCELLED: set(),
}

NOTES = {
    S.OPEN: "Demande publiée",
    S.BOOKED: "Devis accepté, pro réservé",
    S.CANCELLING: "Annulation demandée par le client",
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
    qs = ServiceRequest.objects.filter(
        status=S.OPEN, trade__in=profile.trades.all(), client__is_active=True
    )
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
    settings = platform()
    if not settings.accepting_requests:
        raise ValidationError(
            settings.closed_message
            or "Jeflink ne prend pas de nouvelles demandes pour le moment. Revenez bientôt."
        )
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
    if req.status != S.OPEN or not req.client.is_active:
        raise ValidationError("Cette demande ne reçoit plus de devis.")
    if not profile.trades.filter(pk=req.trade_id).exists():
        raise PermissionDenied("Cette demande ne correspond pas à vos métiers.")
    if req.quotes.filter(pro=pro).exists():
        raise ValidationError("Vous avez déjà envoyé un devis pour cette demande.")
    if req.quotes.count() >= (limit := max_quotes()):
        raise ValidationError(f"Cette demande a déjà reçu {limit} devis.")
    if amount <= 0:
        raise ValidationError("Le montant doit être un entier positif en F CFA.")
    return Quote.objects.create(request=req, pro=pro, amount=amount, message=message)


@transaction.atomic
def accept_quote(
    client, req: ServiceRequest, quote_id: int, coupon_code: str = ""
) -> ServiceRequest:
    """Le client choisit un devis (et applique un code promo) : la mission fige ses montants."""
    req = _locked(req)
    if req.client_id != client.pk:
        raise PermissionDenied("Seul l'auteur de la demande peut choisir un devis.")
    quote = req.quotes.select_related("pro__pro_profile").filter(pk=quote_id).first()
    if quote is None or quote.status != Quote.Status.PENDING:
        raise ValidationError("Devis introuvable pour cette demande.")
    if not quote.pro.is_active or not quote.pro.pro_profile.is_verified:
        # Pro suspendu ou dont la vérification a été retirée : on ne le réserve plus.
        raise ValidationError(
            "Ce pro n'est plus disponible sur Jeflink. Choisissez un autre devis."
        )
    # Le code saisi au choix du devis, sinon celui que le client a ajouté à sa demande.
    coupon, discount = check_coupon(coupon_code or req.promo_code, client, req, quote.amount)
    req.pro = quote.pro
    req.price = quote.amount
    req.coupon = coupon
    req.discount = discount
    req.commission_rate = commission_rate_for(req.trade)
    req.commission = percent_of(req.price, req.commission_rate)
    req.save(update_fields=["price", "coupon", "discount", "commission_rate", "commission"])
    note = f"Devis de {quote.pro.public_name} accepté"
    if coupon:
        note += f" (code {coupon.code} : −{xof(discount)})"
    transition(req, S.BOOKED, client, note[:200])
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
def cancel(actor, req: ServiceRequest, reason: str, note: str = "") -> ServiceRequest:
    """Le client annule, avec un motif (« Autre » : précision obligatoire).

    Demande ouverte : annulée tout de suite. Mission réservée : « Annulation demandée » ;
    le support Jeflink rappelle le client, puis confirme l'annulation ou maintient la mission
    (``confirm_cancel`` / ``keep_mission``). D'ici là, la mission reste dans les comptes.
    """
    req = _locked(req)
    if actor.pk != req.client_id:
        raise PermissionDenied("Seul l'auteur de la demande peut l'annuler.")
    if reason not in R.values:
        raise ValidationError({"reason": "Choisissez le motif de l'annulation."})
    note = note.strip()
    if reason == R.OTHER and not note:
        raise ValidationError({"note": "Précisez le motif de l'annulation."})
    if reason == R.PRO and req.status != S.BOOKED:
        raise ValidationError({"reason": "Aucun pro n'est encore réservé sur cette demande."})
    if req.status not in (S.OPEN, S.BOOKED):
        raise ValidationError(f"Impossible d'annuler une demande « {req.get_status_display()} ».")
    # Le motif reste sur la demande (client et équipe) ; l'historique, que voit aussi le pro,
    # garde une note neutre.
    req.cancel_reason, req.cancel_note = reason, note[:300]
    req.save(update_fields=["cancel_reason", "cancel_note", "updated_at"])
    return transition(req, S.CANCELLING if req.status == S.BOOKED else S.CANCELLED, actor)


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


# --- Équipe Jeflink et litiges ---------------------------------------------------------------


@transaction.atomic
def staff_cancel(staff, req: ServiceRequest, reason: str) -> ServiceRequest:
    """L'équipe annule une demande (doublon, abus, client injoignable…). Le motif est journalisé."""
    if not staff.is_staff:
        raise PermissionDenied("Réservé à l'équipe Jeflink.")
    reason = reason.strip()
    if not reason:
        raise ValidationError("Indiquez le motif de l'annulation.")
    req = _locked(req)
    _release_coupon(req)
    return transition(req, S.CANCELLED, staff, f"Annulée par l'équipe : {reason}"[:200])


def _release_coupon(req: ServiceRequest) -> None:
    """Mission annulée : le client retrouve son code promo (il n'en a pas profité)."""
    if req.coupon_id:
        req.coupon, req.discount = None, 0
        req.save(update_fields=["coupon", "discount"])


def _after_call(staff, req: ServiceRequest) -> ServiceRequest:
    if not staff.is_staff:
        raise PermissionDenied("Réservé à l'équipe Jeflink.")
    req = _locked(req)
    if req.status != S.CANCELLING:
        raise ValidationError("Aucune annulation n'attend de confirmation sur cette mission.")
    return req


# Après l'appel du support. Notes neutres dans l'historique (le pro le voit) ; ce que le client
# a dit reste dans le journal de la console (console.services).


@transaction.atomic
def confirm_cancel(staff, req: ServiceRequest) -> ServiceRequest:
    """Le support a rappelé le client : l'annulation est confirmée, la mission sort des comptes."""
    req = _after_call(staff, req)
    _release_coupon(req)
    return transition(req, S.CANCELLED, staff, "Annulation confirmée par Jeflink")


@transaction.atomic
def keep_mission(staff, req: ServiceRequest) -> ServiceRequest:
    """Le support a rappelé le client : la mission est maintenue (le pro reste réservé)."""
    req = _after_call(staff, req)
    # La demande d'annulation est close : son motif ne doit pas resservir plus tard (fin de
    # mission, annulation par l'équipe). Il reste dans le journal de la console.
    req.cancel_reason, req.cancel_note = "", ""
    req.save(update_fields=["cancel_reason", "cancel_note", "updated_at"])
    return transition(req, S.BOOKED, staff, "Mission maintenue après l'appel de Jeflink")


@transaction.atomic
def open_dispute(user, req: ServiceRequest, reason: str, description: str) -> Dispute:
    """Le client, le pro de la mission ou l'équipe signale un problème sur une mission."""
    req = _locked(req)
    if not user.is_staff and user.pk not in (req.client_id, req.pro_id):
        raise PermissionDenied(
            "Seuls le client et le pro de la mission peuvent signaler un problème."
        )
    if req.status not in (S.BOOKED, S.DONE):  # pas pendant une annulation demandée (en pause)
        raise ValidationError("On signale un problème sur une mission réservée ou terminée.")
    if reason not in Dispute.Reason.values:
        raise ValidationError("Motif inconnu.")
    if not description.strip():
        raise ValidationError("Décrivez le problème en quelques mots.")
    if req.disputes.exclude(
        status__in=[Dispute.Status.RESOLVED, Dispute.Status.DISMISSED]
    ).exists():
        raise ValidationError("Un litige est déjà en cours sur cette mission.")
    return Dispute.objects.create(
        request=req, opened_by=user, reason=reason, description=description.strip()
    )


@transaction.atomic
def update_dispute(staff, dispute: Dispute, status: str, resolution: str = "") -> Dispute:
    """L'équipe fait avancer un litige. Clore (résolu, sans suite) exige une décision écrite."""
    if not staff.is_staff:
        raise PermissionDenied("Réservé à l'équipe Jeflink.")
    dispute = Dispute.objects.select_for_update().get(pk=dispute.pk)
    if dispute.is_closed:
        raise ValidationError("Ce litige est clos.")
    if status not in Dispute.Status.values or status == Dispute.Status.OPEN:
        raise ValidationError("Statut de litige invalide.")
    closing = status in (Dispute.Status.RESOLVED, Dispute.Status.DISMISSED)
    if closing and not resolution.strip():
        raise ValidationError("Écrivez la décision avant de clore le litige.")
    dispute.status = status
    dispute.resolution = resolution.strip() or dispute.resolution
    dispute.handled_by = staff
    dispute.closed_at = timezone.now() if closing else None
    dispute.save()
    return dispute


# --- Argent : commission et codes promo --------------------------------------------------------


def xof(amount: int) -> str:
    """« 12 500 F CFA », espaces fines insécables (typographie française)."""
    return f"{amount:,}".replace(",", "\u202f") + "\u00a0F\u00a0CFA"


def percent_of(amount: int, rate: int) -> int:
    """Pourcentage d'un montant en F CFA, arrondi au franc le plus proche, sans float."""
    return (amount * rate + 50) // 100


def _refused(reason: str) -> dict:
    """Erreur sur le champ code promo, avec l'issue : le devis reste disponible sans code."""
    return {"coupon": f"{reason} Vous pouvez choisir ce devis sans code."}


def commission_rate_for(trade) -> int:
    """Taux du métier s'il en a un, sinon le taux par défaut de la plateforme (en %)."""
    if trade.commission_percent is not None:
        return trade.commission_percent
    return platform().default_commission_percent


def coupon_discount(coupon: Coupon, amount: int) -> int:
    """Remise en F CFA entiers, jamais plus que le devis ni que le plafond."""
    if coupon.kind == Coupon.Kind.PERCENT:
        discount = percent_of(amount, coupon.value)
        if coupon.max_discount is not None:
            discount = min(discount, coupon.max_discount)
    else:
        discount = coupon.value
    return max(0, min(discount, amount))


def coupon_uses(coupon: Coupon, client=None):
    """Utilisations comptées : toute réservation qui porte le code, même annulée ensuite par le
    client (sinon réserver, payer la remise sur place puis annuler rendrait le code
    réutilisable). Seule une décision de l'équipe libère le code : `staff_cancel`, ou
    `confirm_cancel` après l'appel du support (qui vérifie que le pro n'est pas passé)."""
    qs = coupon.requests.all()
    return qs.filter(client=client) if client is not None else qs


UNKNOWN_CODE = "Ce code n'est pas reconnu. Vérifiez les lettres."


def normalize_code(code: str) -> str:
    return (code or "").strip().upper()


def coupon_problem(coupon: Coupon, client, req: ServiceRequest, amount: int | None = None):
    """Pourquoi ce code ne s'applique pas (None s'il s'applique). Sans montant : les règles
    qui ne dépendent pas du devis (au moment où le client ajoute le code à sa demande)."""
    now = timezone.now()
    if coupon.starts_at and coupon.starts_at > now:
        return "Ce code n'est pas encore valable."
    if coupon.ends_at and coupon.ends_at < now:
        return "Ce code a expiré."
    if amount is not None and coupon.min_amount and amount < coupon.min_amount:
        return (
            f"Ce code est valable pour un devis d'au moins {xof(coupon.min_amount)}. "
            f"Ce devis est de {xof(amount)}."
        )
    if coupon.trades.exists() and not coupon.trades.filter(pk=req.trade_id).exists():
        return "Ce code n'est pas valable pour ce métier."
    if coupon.zones.exists() and not coupon.zones.filter(pk=req.zone_id).exists():
        return "Ce code n'est pas valable dans ce quartier."
    if coupon.max_uses is not None and coupon_uses(coupon).count() >= coupon.max_uses:
        return "Ce code n'est plus disponible."
    if coupon_uses(coupon, client).count() >= coupon.max_uses_per_client:
        return "Vous avez déjà utilisé ce code."
    if coupon.first_order_only and (
        ServiceRequest.objects.filter(client=client, pro__isnull=False).exclude(pk=req.pk).exists()
    ):
        return "Ce code est réservé à une première mission sur Jeflink."
    return None


def check_coupon(code: str, client, req: ServiceRequest, amount: int):
    """(code promo, remise) si le code s'applique à cette réservation ; sinon un motif clair."""
    code = normalize_code(code)
    if not code:
        return None, 0
    # Verrous (effectifs sous Postgres) : deux réservations simultanées ne dépassent pas les
    # limites du code, ni celles du client.
    coupon = Coupon.objects.select_for_update().filter(code=code, is_active=True).first()
    if coupon is None:
        raise ValidationError(_refused(UNKNOWN_CODE))
    type(client).objects.select_for_update().filter(pk=client.pk).first()
    if problem := coupon_problem(coupon, client, req, amount):
        raise ValidationError(_refused(problem))
    return coupon, coupon_discount(coupon, amount)


@transaction.atomic
def set_promo_code(client, req: ServiceRequest, code: str, field: str = "code") -> ServiceRequest:
    """Le client ajoute (ou retire, code vide) un code promo à sa demande, avant de réserver.
    Vérifié tout de suite pour ce qui ne dépend pas du devis ; le montant minimum l'est sur
    chaque devis (aperçu), puis au moment de réserver."""
    req = _locked(req)
    if req.client_id != client.pk:
        raise PermissionDenied("Seul l'auteur de la demande peut y ajouter un code.")
    if req.status != S.OPEN:
        raise ValidationError({field: "Un code s'ajoute avant de choisir un devis."})
    code = normalize_code(code)
    if code:
        coupon = Coupon.objects.filter(code=code, is_active=True).first()
        problem = UNKNOWN_CODE if coupon is None else coupon_problem(coupon, client, req)
        if problem:
            raise ValidationError({field: problem})
    req.promo_code = code
    req.save(update_fields=["promo_code", "updated_at"])
    return req


def code_preview(req: ServiceRequest, client, amount: int) -> dict | None:
    """Ce que donnerait le code de la demande sur un devis : remise et prix, ou pourquoi non."""
    if not req.promo_code:
        return None
    coupon = Coupon.objects.filter(code=req.promo_code, is_active=True).first()
    problem = "Ce code n'est plus valable." if coupon is None else None
    problem = problem or coupon_problem(coupon, client, req, amount)
    if problem:
        return {"code": req.promo_code, "error": problem}
    discount = coupon_discount(coupon, amount)
    return {"code": coupon.code, "discount": discount, "client_pays": amount - discount}

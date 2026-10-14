"""Actions de l'équipe dans la console. Chacune est journalisée (``AuditLog``).

Les changements de statut d'une demande ou d'un litige restent dans ``jobs.services`` ; ce module
les appelle puis écrit le journal.
"""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import PermissionDenied, ValidationError

from jeflink.accounts.models import ContactMessage, ProProfile, User
from jeflink.catalog.models import Campaign, City, Trade, Zone
from jeflink.jobs import services as jobs
from jeflink.jobs.models import Coupon, Dispute, Quote, Review, ServiceRequest

from .models import AuditLog, PlatformSettings, ProSettlement
from .permissions import can

A = AuditLog.Action


def _staff(user, section: str = "operations"):
    """Garde-fou : action permise au rôle qui couvre la rubrique, même appelée hors des vues."""
    if not can(user, section):
        raise PermissionDenied("Réservé à l'équipe Jeflink, selon le rôle.")


def _withdraw_pending_quotes(pro: User):
    """Les devis en attente d'un pro suspendu ou dé-vérifié ne peuvent plus être choisis."""
    Quote.objects.filter(pro=pro, status=Quote.Status.PENDING).update(status=Quote.Status.DECLINED)


def log(actor, action: str, target_type: str, target_id: int, label: str, details: str = ""):
    return AuditLog.objects.create(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_label=str(label)[:200],
        details=details[:300],
    )


def _required(text: str, message: str) -> str:
    text = (text or "").strip()
    if not text:
        raise ValidationError(message)
    return text


# --- Pros et comptes ---------------------------------------------------------------------------


@transaction.atomic
def verify_pro(staff, profile: ProProfile) -> ProProfile:
    _staff(staff)
    if profile.is_verified:
        raise ValidationError("Ce pro est déjà vérifié.")
    if not profile.trades.exists():
        raise ValidationError("Ce pro n'a déclaré aucun métier : impossible de le vérifier.")
    profile.is_verified = True
    profile.verified_at = timezone.now()
    profile.verification_note = ""
    profile.save(update_fields=["is_verified", "verified_at", "verification_note"])
    log(staff, A.PRO_VERIFY, "pro", profile.user_id, profile.user)
    return profile


@transaction.atomic
def reject_pro(staff, profile: ProProfile, reason: str) -> ProProfile:
    """Refus ou retrait de la vérification : le pro voit le motif dans son espace."""
    _staff(staff)
    reason = _required(reason, "Indiquez ce qui manque au pro pour être vérifié.")
    profile.is_verified = False
    profile.verified_at = None
    profile.verification_note = reason[:300]
    profile.save(update_fields=["is_verified", "verified_at", "verification_note"])
    _withdraw_pending_quotes(profile.user)
    log(staff, A.PRO_REJECT, "pro", profile.user_id, profile.user, reason)
    return profile


def _target_type(user: User) -> str:
    return "pro" if user.is_pro else "client"


@transaction.atomic
def suspend_user(staff, user: User, reason: str) -> User:
    """Suspend un compte : plus de connexion possible, jetons révoqués, devis en attente retirés."""
    _staff(staff)
    reason = _required(reason, "Indiquez le motif de la suspension.")
    if user.is_staff or user.is_superuser:
        raise ValidationError("Un compte de l'équipe ne se suspend pas depuis la console.")
    if not user.is_active:
        raise ValidationError("Ce compte est déjà suspendu.")
    user.is_active = False
    user.suspension_reason = reason[:200]
    user.save(update_fields=["is_active", "suspension_reason"])
    Token.objects.filter(user=user).delete()  # déconnecté partout, tout de suite
    if user.is_pro:
        _withdraw_pending_quotes(user)
    log(staff, A.USER_SUSPEND, _target_type(user), user.pk, user, reason)
    return user


@transaction.atomic
def reactivate_user(staff, user: User) -> User:
    _staff(staff)
    if user.is_staff or user.is_superuser:
        raise ValidationError("Un compte de l'équipe se gère dans Équipe et rôles.")
    if user.is_active:
        raise ValidationError("Ce compte est déjà actif.")
    user.is_active = True
    user.suspension_reason = ""
    user.save(update_fields=["is_active", "suspension_reason"])
    log(staff, A.USER_REACTIVATE, _target_type(user), user.pk, user)
    return user


# --- Demandes et litiges -------------------------------------------------------------------------


def _call_details(req: ServiceRequest, note: str) -> str:
    """Journal : le motif du client, puis ce qu'il a dit au téléphone (note obligatoire)."""
    note = note.strip()
    if not note:
        raise ValidationError("Notez ce que le client a dit au téléphone.")
    return f"{req.get_cancel_reason_display() or 'Motif inconnu'} — {note}"


@transaction.atomic
def confirm_cancel(staff, req: ServiceRequest, note: str) -> ServiceRequest:
    """Le support a rappelé le client et confirme l'annulation (journalisée avec l'appel)."""
    _staff(staff)
    details = _call_details(req, note)
    req = jobs.confirm_cancel(staff, req)
    log(staff, A.CANCEL_CONFIRM, "request", req.pk, f"#{req.pk} {req.title}", details)
    return req


@transaction.atomic
def keep_mission(staff, req: ServiceRequest, note: str) -> ServiceRequest:
    """Le support a rappelé le client : la mission continue (journalisée avec l'appel)."""
    _staff(staff)
    details = _call_details(req, note)
    req = jobs.keep_mission(staff, req)
    log(staff, A.CANCEL_KEEP, "request", req.pk, f"#{req.pk} {req.title}", details)
    return req


@transaction.atomic
def cancel_request(staff, req: ServiceRequest, reason: str) -> ServiceRequest:
    _staff(staff)
    req = jobs.staff_cancel(staff, req, reason)
    log(staff, A.REQUEST_CANCEL, "request", req.pk, f"#{req.pk} {req.title}", reason.strip())
    return req


@transaction.atomic
def set_staff_note(staff, req: ServiceRequest, note: str) -> ServiceRequest:
    _staff(staff)
    req.staff_note = note.strip()
    req.save(update_fields=["staff_note", "updated_at"])
    log(staff, A.REQUEST_NOTE, "request", req.pk, f"#{req.pk} {req.title}")
    return req


def open_dispute(staff, req: ServiceRequest, reason: str, description: str) -> Dispute:
    dispute = jobs.open_dispute(staff, req, reason, description)
    log(
        staff,
        A.DISPUTE_OPEN,
        "dispute",
        dispute.pk,
        f"Litige #{dispute.pk} · #{req.pk} {req.title}",
        dispute.get_reason_display(),
    )
    return dispute


def update_dispute(staff, dispute: Dispute, status: str, resolution: str) -> Dispute:
    dispute = jobs.update_dispute(staff, dispute, status, resolution)
    log(
        staff,
        A.DISPUTE_UPDATE,
        "dispute",
        dispute.pk,
        f"Litige #{dispute.pk} · #{dispute.request_id} {dispute.request.title}",
        f"{dispute.get_status_display()}{' : ' + dispute.resolution if dispute.is_closed else ''}",
    )
    return dispute


# --- Avis et messages ----------------------------------------------------------------------------


def _review_label(review: Review) -> str:
    pro = review.request.pro
    return f"Avis {review.rating}/5 sur {pro.get_full_name() if pro else 'un pro'}"


@transaction.atomic
def hide_review(staff, review: Review, reason: str) -> Review:
    _staff(staff)
    reason = _required(reason, "Indiquez pourquoi l'avis est masqué.")
    if review.is_hidden:
        raise ValidationError("Cet avis est déjà masqué.")
    review.is_hidden = True
    review.hidden_reason = reason[:200]
    review.save(update_fields=["is_hidden", "hidden_reason"])
    log(staff, A.REVIEW_HIDE, "review", review.pk, _review_label(review), reason)
    return review


@transaction.atomic
def show_review(staff, review: Review) -> Review:
    _staff(staff)
    if not review.is_hidden:
        raise ValidationError("Cet avis est déjà visible.")
    review.is_hidden = False
    review.hidden_reason = ""
    review.save(update_fields=["is_hidden", "hidden_reason"])
    log(staff, A.REVIEW_SHOW, "review", review.pk, _review_label(review))
    return review


@transaction.atomic
def set_contact_handled(staff, message: ContactMessage, handled: bool) -> ContactMessage:
    _staff(staff)
    if message.is_handled == handled:
        raise ValidationError("Rien à changer sur ce message.")
    message.is_handled = handled
    message.handled_at = timezone.now() if handled else None
    message.handled_by = staff if handled else None
    message.save(update_fields=["is_handled", "handled_at", "handled_by"])
    action = A.CONTACT_HANDLE if handled else A.CONTACT_REOPEN
    log(staff, action, "contact", message.pk, f"Message de {message.name}")
    return message


# --- Catalogue : métiers et quartiers (jamais supprimés : des demandes y sont liées) -----------


def _unique_slug(model, name: str, exclude_pk=None) -> str:
    base = slugify(name.replace("–", "-")) or "element"
    slug, n = base, 2
    while model.objects.filter(slug=slug).exclude(pk=exclude_pk).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


def _changes(obj, data: dict) -> str:
    """Liste lisible des champs modifiés, pour le journal."""
    changed = [k for k, v in data.items() if getattr(obj, k) != v]
    return ", ".join(str(obj._meta.get_field(k).verbose_name) for k in changed)


@transaction.atomic
def save_trade(staff, data: dict, trade: Trade | None = None) -> Trade:
    _staff(staff, "catalog")
    if trade is None:
        trade = Trade(slug=_unique_slug(Trade, data["name"]))
        details, action = "", A.TRADE_CREATE
    else:
        details, action = _changes(trade, data), A.TRADE_UPDATE
        if not details:
            raise ValidationError("Aucune modification.")
    for key, value in data.items():
        setattr(trade, key, value)
    trade.save()
    log(staff, action, "trade", trade.pk, trade.name, details)
    return trade


@transaction.atomic
def save_zone(staff, data: dict, zone: Zone | None = None) -> Zone:
    _staff(staff, "catalog")
    if zone is None:
        if Zone.objects.filter(name__iexact=data["name"], city=data["city"]).exists():
            raise ValidationError("Ce quartier existe déjà.")
        zone = Zone(slug=_unique_slug(Zone, data["name"]))
        details, action = "", A.ZONE_CREATE
    else:
        details, action = _changes(zone, data), A.ZONE_UPDATE
        if not details:
            raise ValidationError("Aucune modification.")
    for key, value in data.items():
        setattr(zone, key, value)
    zone.save()
    log(staff, action, "zone", zone.pk, f"{zone.name} ({zone.city.name})", details)
    return zone


@transaction.atomic
def save_city(staff, data: dict, city: City | None = None) -> City:
    """Ajouter ou modifier une ville. Fermée : ses quartiers sortent du site et des demandes."""
    _staff(staff, "catalog")
    if city is None:
        if City.objects.filter(name__iexact=data["name"]).exists():
            raise ValidationError("Cette ville existe déjà.")
        city = City(slug=_unique_slug(City, data["name"]))
        details, action = "", A.CITY_CREATE
    else:
        details, action = _changes(city, data), A.CITY_UPDATE
        if not details:
            raise ValidationError("Aucune modification.")
    for key, value in data.items():
        setattr(city, key, value)
    city.save()
    log(staff, action, "city", city.pk, f"{city.name} ({city.get_region_display()})", details)
    return city


# --- Réglages de la plateforme -------------------------------------------------------------------


@transaction.atomic
def update_settings(staff, data: dict) -> PlatformSettings:
    _staff(staff, "admin")
    current = PlatformSettings.load()
    details = _changes(current, data)
    if not details:
        raise ValidationError("Aucune modification.")
    for key, value in data.items():
        setattr(current, key, value)
    current.updated_by = staff
    current.save()
    log(staff, A.SETTINGS_UPDATE, "settings", current.pk, "Réglages de la plateforme", details)
    return current


# --- Équipe ------------------------------------------------------------------------------------


def _supers():
    # Verrouillés : deux retraits simultanés ne peuvent pas laisser l'équipe sans super admin.
    return (
        User.objects.select_for_update()
        .filter(is_staff=True, is_active=True)
        .filter(Q(is_superuser=True) | Q(staff_role=User.StaffRole.SUPER))
    )


def _keep_a_super(member: User):
    if member.console_role == User.StaffRole.SUPER and not _supers().exclude(pk=member.pk).exists():
        raise ValidationError("Il faut garder au moins un super admin actif.")


@transaction.atomic
def add_member(staff, data: dict) -> User:
    _staff(staff, "admin")
    email = data["email"].lower()
    if User.objects.filter(email=email).exists():
        raise ValidationError("Un compte existe déjà avec cet email.")
    member = User(
        email=email,
        first_name=data["first_name"],
        last_name=data.get("last_name", ""),
        is_staff=True,
        staff_role=data["role"],
    )
    member.set_password(data["password"])
    member.save()
    log(staff, A.TEAM_ADD, "staff", member.pk, member, member.get_staff_role_display())
    return member


@transaction.atomic
def set_member_role(staff, member: User, role: str) -> User:
    _staff(staff, "admin")
    if member.pk == staff.pk:
        raise ValidationError("Vous ne pouvez pas changer votre propre rôle.")
    if member.is_superuser:
        raise ValidationError("Le rôle d'un superutilisateur Django se gère dans l'admin.")
    if member.console_role == role:
        raise ValidationError("Ce membre a déjà ce rôle.")
    if role != User.StaffRole.SUPER:
        _keep_a_super(member)
    member.staff_role = role
    member.save(update_fields=["staff_role"])
    log(staff, A.TEAM_ROLE, "staff", member.pk, member, member.get_staff_role_display())
    return member


@transaction.atomic
def set_member_active(staff, member: User, active: bool, note: str = "") -> User:
    _staff(staff, "admin")
    if member.is_superuser:
        raise ValidationError("L'accès d'un superutilisateur Django se gère dans l'admin.")
    if member.pk == staff.pk:
        raise ValidationError("Vous ne pouvez pas retirer votre propre accès.")
    if member.is_active == active:
        raise ValidationError("Rien à changer pour ce membre.")
    if not active:
        _keep_a_super(member)
    member.is_active = active
    member.save(update_fields=["is_active"])
    if not active:
        Token.objects.filter(user=member).delete()
    action = A.TEAM_REACTIVATE if active else A.TEAM_DEACTIVATE
    log(staff, action, "staff", member.pk, member, note.strip())
    return member


# --- Marketing : codes promo et campagnes ------------------------------------------------------


def _save_with_m2m(obj, data: dict, m2m: tuple[str, ...]):
    plain = {k: v for k, v in data.items() if k not in m2m}
    for key, value in plain.items():
        setattr(obj, key, value)
    obj.save()
    for key in m2m:
        if key in data:
            getattr(obj, key).set(data[key])
    return obj


def _m2m_changes(obj, data: dict, m2m: tuple[str, ...]) -> list[str]:
    changed = []
    for key in m2m:
        if key in data and set(getattr(obj, key).values_list("pk", flat=True)) != {
            x.pk for x in data[key]
        }:
            changed.append(str(obj._meta.get_field(key).verbose_name))
    return changed


@transaction.atomic
def save_coupon(staff, data: dict, coupon: Coupon | None = None) -> Coupon:
    _staff(staff, "marketing")
    m2m = ("trades", "zones")
    if coupon is None:
        if Coupon.objects.filter(code=data["code"]).exists():
            raise ValidationError({"code": "Ce code existe déjà."})
        coupon, details, action = Coupon(), "", A.COUPON_CREATE
    else:
        plain = {k: v for k, v in data.items() if k not in m2m}
        details = ", ".join(
            filter(None, [_changes(coupon, plain), *_m2m_changes(coupon, data, m2m)])
        )
        action = A.COUPON_UPDATE
        if not details:
            raise ValidationError("Aucune modification.")
    coupon = _save_with_m2m(coupon, data, m2m)
    log(staff, action, "coupon", coupon.pk, f"Code {coupon.code}", details)
    return coupon


@transaction.atomic
def save_campaign(staff, data: dict, campaign: Campaign | None = None) -> Campaign:
    _staff(staff, "marketing")
    if campaign is None:
        campaign, details, action = Campaign(), "", A.CAMPAIGN_CREATE
    else:
        details, action = _changes(campaign, data), A.CAMPAIGN_UPDATE
        if not details:
            raise ValidationError("Aucune modification.")
    for key, value in data.items():
        setattr(campaign, key, value)
    campaign.save()
    log(staff, action, "campaign", campaign.pk, campaign.title, details)
    return campaign


# --- Finance : commissions et règlements des pros ----------------------------------------------


@transaction.atomic
def update_commissions(staff, default: int, per_trade: dict[int, int | None]) -> None:
    """Taux par défaut et taux propres aux métiers (None = taux par défaut).

    Les missions déjà réservées gardent le taux figé à leur réservation.
    """
    _staff(staff, "finance")
    changes = []
    current = PlatformSettings.load()
    if current.default_commission_percent != default:
        changes.append(f"par défaut {current.default_commission_percent} → {default} %")
        current.default_commission_percent = default
        current.updated_by = staff
        current.save()
    for trade in Trade.objects.filter(pk__in=per_trade):
        rate = per_trade[trade.pk]
        if trade.commission_percent != rate:
            before = (
                "défaut" if trade.commission_percent is None else f"{trade.commission_percent} %"
            )
            after = "défaut" if rate is None else f"{rate} %"
            changes.append(f"{trade.name} {before} → {after}")
            trade.commission_percent = rate
            trade.save(update_fields=["commission_percent"])
    if not changes:
        raise ValidationError("Aucune modification.")
    log(staff, A.COMMISSION_UPDATE, "commission", 1, "Taux de commission", "; ".join(changes))


@transaction.atomic
def add_settlement(staff, pro: User, data: dict) -> ProSettlement:
    _staff(staff, "finance")
    if not pro.is_pro:
        raise ValidationError("Les règlements concernent les pros.")
    settlement = ProSettlement.objects.create(pro=pro, recorded_by=staff, **data)
    log(
        staff,
        A.SETTLEMENT_ADD,
        "pro",
        pro.pk,
        pro,
        f"{settlement.get_direction_display()} : {settlement.amount} F CFA "
        f"({settlement.get_method_display()})",
    )
    return settlement

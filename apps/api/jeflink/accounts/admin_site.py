"""Admin Django : second facteur TOTP et limite de débit (spec 001, S3 ; tâche 21).

L'admin est réservé à l'équipe technique (comptes ``is_staff``), en lecture seule, et servi
sur l'hôte interne en production (infra, tâche 4). En plus :

- **second facteur** : le formulaire de connexion exige un code TOTP. Le mécanisme est celui des
  Ops (``accounts.mfa``, déjà revu) : secret en MultiFernet, anti-rejeu, verrou à 10 échecs sur
  24 h glissantes. Choix d'un « équivalent » maison plutôt que ``django-otp`` : aucune
  dépendance de plus, un seul mécanisme TOTP à maintenir et à auditer ;
- **toute page de l'admin** exige que la session ait validé ce code (une connexion forcée ou une
  session ouverte ailleurs ne suffit pas) ;
- **limite de débit** sur la page de connexion, par IP et par identifiant, qui refuse si Redis
  ne répond pas.

L'enrôlement passe par la commande ``enroll_admin_totp`` (deux Admin, URI remise hors bande) ;
le premier code valide confirme l'appareil.
"""

import unicodedata
from datetime import timedelta

from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.db import transaction
from django.dispatch import receiver
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from jeflink.common.alerts import alert_once
from jeflink.common.client_ip import rate_limit_bucket
from jeflink.common.errors import DomainError
from jeflink.common.pii import phone_hmac
from jeflink.common.ratelimit import Limit, RateLimitUnavailable, consume
from jeflink.trust.models import AuditEvent
from jeflink.trust.services import audit

SESSION_KEY = "jf_admin_mfa"
LOGIN_PER_IP = Limit("admin:login_ip", 10, 600)
LOGIN_PER_USERNAME = Limit("admin:login_username", 10, 3600)
INVALID = "Identifiants ou code invalides."
# Un appareil émis mais jamais confirmé expire : relancer enroll_admin_totp (revue tâche 21, I3).
UNCONFIRMED_DEVICE_TTL = timedelta(hours=24)


def admin_identifier(raw: str) -> str:
    """Forme de l'identifiant que Django authentifie (NFKC), puis E.164 si c'est un numéro :
    les variantes Unicode d'un même numéro partagent le même compteur (revue tâche 21, I2)."""
    from .phone import normalize_phone

    ident = unicodedata.normalize("NFKC", (raw or "").strip())[:64]
    try:
        return normalize_phone(ident)
    except DomainError:
        return ident


class AdminTotpAuthenticationForm(AdminAuthenticationForm):
    """Téléphone, mot de passe et code TOTP. Toute erreur a le même message (pas d'oracle)."""

    error_messages = {"invalid_login": INVALID, "inactive": INVALID}

    otp_code = forms.RegexField(
        regex=r"^[0-9]{6}$",
        label="Code de l'application d'authentification",
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric"}),
        error_messages={"invalid": INVALID, "required": INVALID},
    )

    def clean(self):
        cleaned = super().clean()  # mot de passe, compte actif et is_staff
        user = self.get_user()
        code = cleaned.get("otp_code")
        if user is None or not code:
            raise forms.ValidationError(INVALID, code="invalid_login")
        try:
            device_public_id = verify_admin_code(user, code)
        except DomainError as exc:
            raise forms.ValidationError(INVALID, code="invalid_login") from exc
        # Le drapeau n'est posé qu'après la connexion, avec rotation de la clé (M1).
        self.request._jf_admin_mfa = {
            "uid": str(user.public_id),
            "device": str(device_public_id),
            "at": int(timezone.now().timestamp()),
        }
        return cleaned


@receiver(user_logged_in)
def _mark_admin_mfa(sender, request, user, **kwargs) -> None:
    flag = getattr(request, "_jf_admin_mfa", None) if request is not None else None
    if flag and flag["uid"] == str(user.public_id):
        request.session[SESSION_KEY] = flag
        request.session.cycle_key()


@receiver(user_login_failed)
def _audit_admin_login_failed(sender, credentials, request=None, **kwargs) -> None:
    """Mot de passe faux sur l'admin : tracé, identifiant pseudonymisé seulement (M4)."""
    if request is None or not request.path.startswith("/admin/"):
        return
    audit(
        action="accounts.admin.login_failed",
        actor_kind=AuditEvent.ActorKind.SYSTEM,
        metadata={"username_hmac": phone_hmac(admin_identifier(credentials.get("username", "")))},
    )


def verify_admin_code(user, code: str):
    """Code TOTP de l'admin, dans une transaction qui compte l'échec (même logique que l'Ops).

    Renvoie le ``public_id`` de l'appareil, auquel la session est liée. Un appareil non
    confirmé compte aussi ses échecs et expire au bout de 24 h. L'échec est validé en base
    puis audité hors transaction : il survit à l'erreur levée.
    """
    from .mfa import Stage, _accept_code, _count_failure, _lock_device, _lock_user, _raise

    with transaction.atomic():
        now = timezone.now()
        user = _lock_user(user.pk)
        device = _lock_device(user)
        if device is None or device.locked_at is not None:
            raise DomainError("mfa_locked", status=403)
        if device.confirmed_at is None and now - device.created_at > UNCONFIRMED_DEVICE_TTL:
            raise DomainError("mfa_enrollment_expired", status=403)
        if _accept_code(device, code, now):
            fields = ["last_used_step", "updated_at"]
            if device.confirmed_at is None:
                device.confirmed_at = now  # premier code : enrôlement confirmé
                fields.append("confirmed_at")
                audit(
                    action="accounts.admin.totp_confirmed",
                    actor=user,
                    actor_kind=AuditEvent.ActorKind.USER,
                    target=user,
                    metadata={},
                )
            device.save(update_fields=fields)
            audit(
                action="accounts.admin.logged_in",
                actor=user,
                actor_kind=AuditEvent.ActorKind.USER,
                target=user,
                metadata={},
            )
            return device.public_id
        failure = _count_failure(
            user=user,
            stage=Stage.ADMIN,
            now=now,
            challenge=None,
            device=device,
            count_unconfirmed=True,
        )
    _raise(failure)


def admin_mfa_valid(request: HttpRequest) -> bool:
    """La session a validé le second facteur, avec l'appareil actuel, non verrouillé, depuis
    moins de ``ADMIN_MFA_MAX_AGE`` : perte d'appareil, verrou ou réenrôlement la ferment (I1)."""
    from .models import TotpDevice

    flag = request.session.get(SESSION_KEY)
    if not isinstance(flag, dict) or flag.get("uid") != str(request.user.public_id):
        return False
    age = timezone.now().timestamp() - int(flag.get("at", 0))
    if age < 0 or age > settings.ADMIN_MFA_MAX_AGE:
        return False
    return TotpDevice.objects.filter(
        user=request.user,
        public_id=flag.get("device"),
        confirmed_at__isnull=False,
        locked_at__isnull=True,
    ).exists()


class JeflinkAdminSite(admin.AdminSite):
    site_header = "Jeflink · administration technique"
    site_title = "Jeflink admin"
    index_title = "Lecture seule, sauf la saisie du catalogue et des zones"
    login_form = AdminTotpAuthenticationForm

    def has_permission(self, request: HttpRequest) -> bool:
        return super().has_permission(request) and admin_mfa_valid(request)

    def login(self, request: HttpRequest, extra_context=None):
        if request.method == "POST":
            refused = _throttle_login(request)
            if refused is not None:
                return refused
        return super().login(request, extra_context)


def _throttle_login(request: HttpRequest) -> HttpResponse | None:
    """Limite par IP et par identifiant normalisé ; refus si Redis ne répond pas (jamais ouvert).

    Risques acceptés sur l'hôte interne (revue tâche 21) : la limite par identifiant peut être
    épuisée par un tiers du réseau interne (M5) ; un mot de passe juste se reconnaît au temps de
    réponse, sans ouvrir l'accès (M3).
    """
    bucket = rate_limit_bucket(getattr(request, "client_ip", "") or "")
    username = admin_identifier(request.POST.get("username") or "")
    checks = [(LOGIN_PER_IP, bucket)]
    if username:
        checks.append((LOGIN_PER_USERNAME, username))
    try:
        outcome = consume(checks)
    except RateLimitUnavailable:
        return HttpResponse("Service indisponible.", status=503, content_type="text/plain")
    if outcome.allowed:
        return None
    alert_once(f"admin_login_throttled:{bucket}", 3600, "admin_login_throttled")
    response = HttpResponse(
        "Trop de tentatives. Réessayez plus tard.", status=429, content_type="text/plain"
    )
    response["Retry-After"] = str(outcome.retry_after)
    return response

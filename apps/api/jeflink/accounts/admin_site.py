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
STEP_UP_KEY = "jf_admin_step_up"
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


def verify_admin_code(user, code: str, *, audit_action: str = "accounts.admin.logged_in"):
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
                action=audit_action,
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


# --- Second facteur redemandé pour l'argent (spec 005) -----------------------------------------


def verify_admin_step_up(request: HttpRequest, code: str) -> None:
    """Code TOTP frais : ouvre, pour cette session, une fenêtre de ``ADMIN_STEP_UP_TTL`` pendant
    laquelle l'opérateur enchaîne les actions d'argent. Même mécanisme que la connexion
    (anti-rejeu, verrou), audité ``accounts.admin.step_up``. La fenêtre ne se prolonge pas à
    l'usage."""
    if not admin_mfa_valid(request):
        raise DomainError("mfa_required", status=403)
    device_public_id = verify_admin_code(request.user, code, audit_action="accounts.admin.step_up")
    request.session[STEP_UP_KEY] = {
        "uid": str(request.user.public_id),
        "device": str(device_public_id),
        "at": int(timezone.now().timestamp()),
    }


def admin_step_up_valid(request: HttpRequest) -> bool:
    session = getattr(request, "session", None)
    if session is None or not getattr(request, "user", None):
        return False  # sans session, jamais de fenêtre ouverte (échec fermé, sans 500)
    flag = session.get(STEP_UP_KEY)
    if not isinstance(flag, dict) or flag.get("uid") != str(request.user.public_id):
        return False
    age = timezone.now().timestamp() - int(flag.get("at", 0))
    mfa = session.get(SESSION_KEY) or {}
    return (
        0 <= age <= settings.ADMIN_STEP_UP_TTL
        and flag.get("device") == mfa.get("device")
        and admin_mfa_valid(request)
    )


class StepUpForm(forms.Form):
    """Base des formulaires d'argent de l'admin : exige un code TOTP quand la fenêtre de
    ``ADMIN_STEP_UP_TTL`` est fermée. La requête est passée à la construction (``request=``) ou
    portée par la classe (``step_up_request``, formulaires des ``ModelAdmin``)."""

    otp_code = forms.CharField(
        label="Code de l'application d'authentification (redemandé pour toute action d'argent)",
        required=False,
        max_length=6,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric"}),
    )
    step_up_request: HttpRequest | None = None

    def __init__(self, *args, request: HttpRequest | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        if request is not None:
            self.step_up_request = request
        if self.step_up_request is not None and admin_step_up_valid(self.step_up_request):
            self.fields["otp_code"].widget = forms.HiddenInput()

    def clean(self):
        cleaned = super().clean()
        request = self.step_up_request
        if request is None:
            raise forms.ValidationError("Second facteur indisponible.")
        if admin_step_up_valid(request):
            return cleaned
        if getattr(request, "session", None) is None:
            raise forms.ValidationError("Second facteur indisponible.")
        code = (cleaned.get("otp_code") or "").strip()
        try:
            if len(code) != 6 or not code.isdigit():
                raise DomainError("mfa_code_invalid")
            verify_admin_step_up(request, code)
        except DomainError as exc:
            raise forms.ValidationError("Code invalide ou expiré.", code="step_up") from exc
        return cleaned


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

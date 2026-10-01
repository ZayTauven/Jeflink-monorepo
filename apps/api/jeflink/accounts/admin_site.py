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

from django import forms
from django.contrib import admin
from django.contrib.admin.forms import AdminAuthenticationForm
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from jeflink.common.client_ip import rate_limit_bucket
from jeflink.common.errors import DomainError
from jeflink.common.ratelimit import Limit, RateLimitUnavailable, consume
from jeflink.trust.models import AuditEvent
from jeflink.trust.services import audit

SESSION_KEY = "jf_admin_mfa"
LOGIN_PER_IP = Limit("admin:login_ip", 10, 600)
LOGIN_PER_USERNAME = Limit("admin:login_username", 10, 3600)
INVALID = "Identifiants ou code invalides."


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
            verify_admin_code(user, code)
        except DomainError as exc:
            raise forms.ValidationError(INVALID, code="invalid_login") from exc
        self.request.session[SESSION_KEY] = str(user.public_id)
        return cleaned


def verify_admin_code(user, code: str) -> None:
    """Code TOTP de l'admin, dans une transaction qui compte l'échec (même logique que l'Ops).

    L'échec est validé en base puis audité hors transaction : il survit à l'erreur levée.
    """
    from .mfa import Stage, _accept_code, _count_failure, _lock_device, _lock_user, _raise

    with transaction.atomic():
        now = timezone.now()
        user = _lock_user(user.pk)
        device = _lock_device(user)
        if device is None or device.locked_at is not None:
            raise DomainError("mfa_locked", status=403)
        if _accept_code(device, code, now):
            fields = ["last_used_step", "updated_at"]
            if device.confirmed_at is None:
                device.confirmed_at = now  # premier code : enrôlement confirmé
                fields.append("confirmed_at")
            device.save(update_fields=fields)
            audit(
                action="accounts.admin.logged_in",
                actor=user,
                actor_kind=AuditEvent.ActorKind.OPS,
                target=user,
                metadata={},
            )
            return
        failure = _count_failure(
            user=user, stage=Stage.ADMIN, now=now, challenge=None, device=device
        )
    _raise(failure)


class JeflinkAdminSite(admin.AdminSite):
    site_header = "Jeflink · administration technique"
    site_title = "Jeflink admin"
    index_title = "Lecture seule"
    login_form = AdminTotpAuthenticationForm

    def has_permission(self, request: HttpRequest) -> bool:
        return super().has_permission(request) and request.session.get(SESSION_KEY) == str(
            request.user.public_id
        )

    def login(self, request: HttpRequest, extra_context=None):
        if request.method == "POST":
            refused = _throttle_login(request)
            if refused is not None:
                return refused
        return super().login(request, extra_context)


def _throttle_login(request: HttpRequest) -> HttpResponse | None:
    """Limite par IP et par identifiant saisi ; refus si Redis ne répond pas (jamais ouvert)."""
    bucket = rate_limit_bucket(getattr(request, "client_ip", "") or "")
    username = (request.POST.get("username") or "").strip()[:64]
    checks = [(LOGIN_PER_IP, bucket)]
    if username:
        checks.append((LOGIN_PER_USERNAME, username))
    try:
        outcome = consume(checks)
    except RateLimitUnavailable:
        return HttpResponse("Service indisponible.", status=503, content_type="text/plain")
    if outcome.allowed:
        return None
    response = HttpResponse(
        "Trop de tentatives. Réessayez plus tard.", status=429, content_type="text/plain"
    )
    response["Retry-After"] = str(outcome.retry_after)
    return response

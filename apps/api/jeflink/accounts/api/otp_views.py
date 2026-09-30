"""Endpoints de connexion par code SMS : config, request, resend, verify (spec 001).

Vues minces : désérialisation, contexte de la requête (app, langue, appareil), service.
"""

import phonenumbers
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from jeflink.accounts.client_challenge import client_challenge_required
from jeflink.accounts.otp import CODE_LENGTH, VerifyResult, request_otp, resend_otp, verify_otp
from jeflink.accounts.selectors import account_profile
from jeflink.common.client_ip import is_trusted_bff_request
from jeflink.common.errors import DomainError

from .serializers import (
    AuthConfigSerializer,
    OtpChallengeResponseSerializer,
    OtpRequestSerializer,
    OtpResendSerializer,
    OtpVerifyResponseSerializer,
    OtpVerifySerializer,
)

APP_HEADER = "X-Jeflink-App"
INSTALL_HEADER = "X-Install-Id"
REGION_LABELS = {"SN": _("Sénégal")}

IDEMPOTENCY_PARAMETER = OpenApiParameter(
    "Idempotency-Key", str, OpenApiParameter.HEADER, required=True,
    description="Une clé par saisie du numéro (16 à 64 caractères) : même clé, même réponse.",
)  # fmt: skip


def resolve_app(request: Request, body_app: str | None) -> str:
    """``web``/``console`` : imposés par le BFF de confiance ; sinon ``client``/``pro`` (S10)."""
    if is_trusted_bff_request(request._request):
        app = request.headers.get(APP_HEADER, "")
        if app not in {"web", "console"}:
            raise DomainError("app_invalid")
        return app
    if body_app in {"client", "pro"}:
        return body_app
    raise DomainError("app_invalid")


def request_language(request: Request) -> str:
    return "wo" if request.headers.get("Accept-Language", "").lower().startswith("wo") else "fr"


class AuthConfigView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    rate_limit_scope = "auth_config"

    @extend_schema(tags=["auth"], operation_id="auth_config", responses=AuthConfigSerializer)
    def get(self, request: Request) -> Response:
        regions = [
            {
                "region": region,
                "dial_code": f"+{phonenumbers.country_code_for_region(region)}",
                "label": str(REGION_LABELS.get(region, region)),
            }
            for region in settings.OTP_ALLOWED_REGIONS
        ]
        data = {
            "regions": regions,
            "code_length": CODE_LENGTH,
            "client_challenge_required": client_challenge_required(),
            "terms_version": settings.TERMS_VERSION,
        }
        return Response(AuthConfigSerializer(data).data)


class OtpRequestView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    rate_limit_scope = "otp_request"

    @extend_schema(
        tags=["auth"],
        operation_id="auth_otp_request",
        parameters=[IDEMPOTENCY_PARAMETER],
        request=OtpRequestSerializer,
        responses={
            202: OtpChallengeResponseSerializer,
            400: OpenApiResponse(
                description="phone_invalid, phone_not_mobile, phone_region_not_supported"
            ),
            429: OpenApiResponse(description="otp_rate_limited (+ retry_after)"),
            503: OpenApiResponse(description="otp_temporarily_unavailable"),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = OtpRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        body = request_otp(
            raw_phone=data["phone"],
            app=resolve_app(request, data.get("app")),
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            install_id=request.headers.get(INSTALL_HEADER, ""),
            language=request_language(request),
            client_challenge_token=data["client_challenge_token"],
        )
        return Response(body, status=status.HTTP_202_ACCEPTED)


class OtpResendView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    rate_limit_scope = "otp_request"

    @extend_schema(
        tags=["auth"],
        operation_id="auth_otp_resend",
        request=OtpResendSerializer,
        responses={202: OtpChallengeResponseSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = OtpResendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        body = resend_otp(**serializer.validated_data)
        return Response(body, status=status.HTTP_202_ACCEPTED)


def _verify_body(result: VerifyResult) -> dict:
    # Numéro peut-être recyclé : rien de l'ancien titulaire (nom, rôles, langue) (I2).
    profile = account_profile(result.user, restricted=result.restricted)
    return {
        "status": "authenticated",
        "user": profile,
        "is_new_user": result.is_new_user,
        "restricted": result.restricted,
        "restriction_kind": profile["restriction_kind"],
        "other_sessions": [
            {
                "public_id": s.public_id,
                "app": s.app,
                "device_label": s.device_label,
                "last_seen_at": s.last_seen_at,
            }
            for s in result.other_sessions
        ],
        "pending_invitations": [],  # tâche 12
        "tokens": {
            "access": result.tokens.access,
            "refresh": result.tokens.refresh,
            "access_expires_at": result.tokens.access_expires_at,
        },
    }


class OtpVerifyView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    rate_limit_scope = "otp_verify"

    @extend_schema(
        tags=["auth"],
        operation_id="auth_otp_verify",
        request=OtpVerifySerializer,
        responses={
            200: OtpVerifyResponseSerializer,
            400: OpenApiResponse(
                description=(
                    "otp_invalid (+ attempts_remaining), otp_expired, "
                    "otp_challenge_invalid, terms_not_accepted"
                )
            ),
            403: OpenApiResponse(description="account_disabled, account_not_allowed"),
            409: OpenApiResponse(description="otp_already_used"),
            429: OpenApiResponse(description="otp_locked"),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = OtpVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        device = data["device"]
        install_id = device["install_id"] or request.headers.get(INSTALL_HEADER, "")
        result = verify_otp(
            challenge_id=data["challenge_id"],
            challenge_secret=data["challenge_secret"],
            code=data["code"],
            terms_version=data["terms_version"],
            app=resolve_app(request, data.get("app")),
            platform=device["platform"],
            device_label=device["label"],
            install_id=install_id,
        )
        return Response(OtpVerifyResponseSerializer(_verify_body(result)).data)

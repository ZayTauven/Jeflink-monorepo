"""Second facteur TOTP des Ops (spec 001, S1, S25) : setup, confirm, verify, step-up.

``setup``, ``confirm`` et ``verify`` n'ont pas de session : ils prennent le ``mfa_token`` remis
par ``otp/verify`` (cookie ``__Host-jf_mfa`` côté BFF). ``step-up`` exige une session console
ops. Vues minces : désérialisation puis service.
"""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from jeflink.accounts.mfa import MfaResult, confirm_totp, setup_totp, step_up, verify_totp
from jeflink.accounts.otp import VerifyResult
from jeflink.accounts.permissions import IsClient, token_claims
from jeflink.accounts.selectors import active_sessions_for

from .otp_views import verify_body
from .serializers import (
    AccessTokenSerializer,
    OtpVerifyResponseSerializer,
    StepUpRequestSerializer,
    TotpCodeRequestSerializer,
    TotpSetupRequestSerializer,
    TotpSetupResponseSerializer,
)

MFA_ERRORS = {
    400: OpenApiResponse(description="mfa_invalid (+ attempts_remaining)"),
    401: OpenApiResponse(description="mfa_token_invalid"),
    403: OpenApiResponse(description="mfa_locked, mfa_enrollment_not_authorized"),
}


def _authenticated(result: MfaResult) -> Response:
    others = list(active_sessions_for(result.user).exclude(pk=result.tokens.session.pk)[:10])
    body = verify_body(
        VerifyResult(
            user=result.user,
            tokens=result.tokens,
            is_new_user=False,
            restricted=False,
            other_sessions=others,
        )
    )
    return Response(OtpVerifyResponseSerializer(body).data)


class _MfaView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    rate_limit_scope = "mfa"


class TotpSetupView(_MfaView):
    @extend_schema(
        tags=["auth"],
        operation_id="auth_mfa_totp_setup",
        request=TotpSetupRequestSerializer,
        responses={200: TotpSetupResponseSerializer, **MFA_ERRORS},
    )
    def post(self, request: Request) -> Response:
        serializer = TotpSetupRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        body = setup_totp(**serializer.validated_data)
        return Response(TotpSetupResponseSerializer(body).data)


class TotpConfirmView(_MfaView):
    @extend_schema(
        tags=["auth"],
        operation_id="auth_mfa_totp_confirm",
        request=TotpCodeRequestSerializer,
        responses={200: OtpVerifyResponseSerializer, **MFA_ERRORS},
    )
    def post(self, request: Request) -> Response:
        serializer = TotpCodeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return _authenticated(confirm_totp(**serializer.validated_data))


class TotpVerifyView(_MfaView):
    @extend_schema(
        tags=["auth"],
        operation_id="auth_mfa_totp_verify",
        request=TotpCodeRequestSerializer,
        responses={200: OtpVerifyResponseSerializer, **MFA_ERRORS},
    )
    def post(self, request: Request) -> Response:
        serializer = TotpCodeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return _authenticated(verify_totp(**serializer.validated_data))


class TotpStepUpView(APIView):
    permission_classes = [IsClient]

    @extend_schema(
        tags=["auth"],
        operation_id="auth_mfa_totp_step_up",
        request=StepUpRequestSerializer,
        responses={
            200: AccessTokenSerializer,
            400: OpenApiResponse(description="mfa_invalid"),
            403: OpenApiResponse(description="ops_forbidden, mfa_locked"),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = StepUpRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        access, expires = step_up(
            user=request.user,
            session_public_id=token_claims(request)["sid"],
            code=serializer.validated_data["code"],
        )
        return Response(
            AccessTokenSerializer({"access": access, "access_expires_at": expires}).data
        )

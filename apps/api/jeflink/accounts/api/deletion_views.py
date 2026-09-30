"""Suppression du compte (exigée par les stores) et « Repartir de zéro » (compte dormant)."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from jeflink.accounts.deletion import delete_account, fresh_start, request_deletion_otp
from jeflink.accounts.otp import VerifyResult
from jeflink.accounts.permissions import AllowRestrictedSession, IsClient, token_claims

from .otp_views import IDEMPOTENCY_PARAMETER, INSTALL_HEADER, verify_body
from .serializers import (
    DeletionConfirmSerializer,
    OtpChallengeResponseSerializer,
    OtpVerifyResponseSerializer,
)

BLOCKED = OpenApiResponse(description="account_deletion_blocked (+ reasons)")


class DeletionOtpView(APIView):
    permission_classes = [IsClient]

    @extend_schema(
        tags=["me"],
        operation_id="me_deletion_otp",
        parameters=[IDEMPOTENCY_PARAMETER],
        request=None,
        responses={
            202: OtpChallengeResponseSerializer,
            409: BLOCKED,
            429: OpenApiResponse(description="otp_rate_limited (+ retry_after)"),
        },
    )
    def post(self, request: Request) -> Response:
        body = request_deletion_otp(
            user=request.user,
            app=token_claims(request)["app"],
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            install_id=request.headers.get(INSTALL_HEADER, ""),
        )
        return Response(body, status=status.HTTP_202_ACCEPTED)


class DeletionView(APIView):
    permission_classes = [IsClient]

    @extend_schema(
        tags=["me"],
        operation_id="me_deletion",
        request=DeletionConfirmSerializer,
        responses={
            204: None,
            400: OpenApiResponse(description="otp_invalid, otp_expired, otp_challenge_invalid"),
            409: BLOCKED,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = DeletionConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        delete_account(user=request.user, **serializer.validated_data)
        return Response(status=status.HTTP_204_NO_CONTENT)


class FreshStartView(APIView):
    """Session restreinte (compte dormant, client) : « Repartir de zéro »."""

    permission_classes = [AllowRestrictedSession]

    @extend_schema(
        tags=["me"],
        operation_id="me_fresh_start",
        request=None,
        responses={
            200: OtpVerifyResponseSerializer,
            403: OpenApiResponse(description="fresh_start_not_allowed, reauth_required"),
            409: BLOCKED,
        },
    )
    def post(self, request: Request) -> Response:
        claims = token_claims(request)
        tokens = fresh_start(
            user=request.user,
            session_public_id=claims["sid"],
            auth_time=claims.get("auth_time"),
        )
        user = tokens.session.user
        body = verify_body(
            VerifyResult(user=user, tokens=tokens, is_new_user=True, restricted=False)
        )
        return Response(OtpVerifyResponseSerializer(body).data)

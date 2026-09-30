"""Vues de sessions et de profil. Permissions + désérialisation + service, rien d'autre."""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from jeflink.accounts.models import DeviceSession, User
from jeflink.accounts.permissions import AllowRestrictedSession, IsClient, token_claims
from jeflink.accounts.selectors import account_profile, active_sessions_for
from jeflink.accounts.services import update_profile
from jeflink.accounts.sessions import (
    TokenPair,
    refresh_session,
    revoke_other_sessions,
    revoke_session,
)

from .serializers import (
    DeviceSessionSerializer,
    MeSerializer,
    MeUpdateSerializer,
    RefreshRequestSerializer,
    TokenPairSerializer,
)


def _token_response(pair: TokenPair) -> Response:
    return Response(
        TokenPairSerializer(
            {
                "access": pair.access,
                "refresh": pair.refresh,
                "access_expires_at": pair.access_expires_at,
            }
        ).data
    )


class TokenRefreshView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    rate_limit_scope = "token_refresh"

    @extend_schema(
        tags=["auth"],
        operation_id="auth_token_refresh",
        request=RefreshRequestSerializer,
        responses={
            200: TokenPairSerializer,
            401: OpenApiResponse(description="refresh_invalid, session_revoked"),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = RefreshRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return _token_response(refresh_session(serializer.validated_data["refresh"]))


class LogoutView(APIView):
    # Une session restreinte doit toujours pouvoir se déconnecter.
    permission_classes = [AllowRestrictedSession]

    @extend_schema(tags=["auth"], operation_id="auth_logout", request=None, responses={204: None})
    def post(self, request: Request) -> Response:
        session = DeviceSession.objects.filter(
            public_id=token_claims(request)["sid"], user=request.user
        ).first()
        if session is not None:
            revoke_session(session, reason=DeviceSession.RevokedReason.LOGOUT)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """Profil du compte. Une session restreinte lit un profil minimal mais ne modifie rien."""

    def get_permissions(self):
        if self.request.method == "GET":
            # Profil minimal : l'app sait quel écran de compte dormant afficher (I2).
            return [AllowRestrictedSession()]
        return [IsClient()]

    @staticmethod
    def _body(request: Request, user: User) -> dict:
        restricted = bool(token_claims(request).get("restricted", False))
        return MeSerializer(account_profile(user, restricted=restricted)).data

    @extend_schema(tags=["me"], operation_id="me_retrieve", responses=MeSerializer)
    def get(self, request: Request) -> Response:
        return Response(self._body(request, request.user))

    @extend_schema(
        tags=["me"],
        operation_id="me_update",
        request=MeUpdateSerializer,
        responses={
            200: MeSerializer,
            400: OpenApiResponse(
                description="display_name_length, display_name_invalid, display_name_reserved"
            ),
            403: OpenApiResponse(description="session_restricted"),
        },
    )
    def patch(self, request: Request) -> Response:
        serializer = MeUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = update_profile(user=request.user, **serializer.validated_data)
        return Response(self._body(request, user))


class MySessionsView(generics.ListAPIView):
    permission_classes = [IsClient]
    serializer_class = DeviceSessionSerializer

    def get_queryset(self):
        return active_sessions_for(self.request.user)

    def get_serializer_context(self) -> dict:
        return {
            **super().get_serializer_context(),
            "current_sid": token_claims(self.request)["sid"],
        }

    @extend_schema(tags=["me"], operation_id="me_sessions_list")
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)


class MySessionDetailView(APIView):
    permission_classes = [IsClient]

    @extend_schema(tags=["me"], operation_id="me_sessions_revoke", responses={204: None})
    def delete(self, request: Request, public_id) -> Response:
        # Filtré par l'utilisateur : la session d'un autre renvoie 404, jamais 403 (S5).
        session = get_object_or_404(active_sessions_for(request.user), public_id=public_id)
        revoke_session(session, reason=DeviceSession.RevokedReason.USER_REVOKED)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RevokeOtherSessionsView(APIView):
    permission_classes = [IsClient]

    @extend_schema(
        tags=["me"], operation_id="me_sessions_revoke_others", request=None, responses={204: None}
    )
    def post(self, request: Request) -> Response:
        revoke_other_sessions(
            user=request.user,
            current_sid=token_claims(request)["sid"],
            reason=DeviceSession.RevokedReason.USER_REVOKED,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

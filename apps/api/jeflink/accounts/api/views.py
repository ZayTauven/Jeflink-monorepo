"""Vues de sessions, de profil et d'invitations : permissions, désérialisation, service."""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from jeflink.accounts.models import DeviceSession, User
from jeflink.accounts.permissions import AllowRestrictedSession, IsClient, token_claims
from jeflink.accounts.selectors import (
    account_profile,
    active_sessions_for,
    pending_invitations_for,
)
from jeflink.accounts.services import accept_invitation, decline_invitation, update_profile
from jeflink.accounts.sessions import (
    TokenPair,
    refresh_session,
    revoke_by_refresh,
    revoke_other_sessions,
    revoke_session,
)

from .serializers import (
    AcceptInvitationSerializer,
    DeviceSessionSerializer,
    InvitationSerializer,
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


class TokenRevokeView(APIView):
    """Déconnexion par le refresh, sans accès valide (BFF web, apps hors ligne longtemps)."""

    permission_classes = [AllowAny]
    authentication_classes = []
    rate_limit_scope = "token_revoke"  # distincte : marteler revoke n'épuise pas le refresh

    @extend_schema(
        tags=["auth"],
        operation_id="auth_token_revoke",
        request=RefreshRequestSerializer,
        responses={204: None},
    )
    def post(self, request: Request) -> Response:
        serializer = RefreshRequestSerializer(data=request.data)
        if serializer.is_valid():
            revoke_by_refresh(serializer.validated_data["refresh"])
        # Toujours 204 : un jeton inconnu, déjà révoqué ou invalide ne se distingue pas.
        return Response(status=status.HTTP_204_NO_CONTENT)


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


class MyInvitationsView(generics.ListAPIView):
    """Invitations en attente pour le numéro du compte (S19)."""

    permission_classes = [IsClient]
    serializer_class = InvitationSerializer

    def get_queryset(self):
        return pending_invitations_for(self.request.user)

    @extend_schema(tags=["me"], operation_id="me_invitations_list")
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)


class AcceptInvitationView(APIView):
    permission_classes = [IsClient]

    @extend_schema(
        tags=["me"],
        operation_id="me_invitations_accept",
        request=AcceptInvitationSerializer,
        responses={
            204: OpenApiResponse(description="Acceptée (rejouer une acceptation faite : 204)"),
            400: OpenApiResponse(description="display_name_length, display_name_reserved…"),
            403: OpenApiResponse(description="profile_incomplete, role_not_allowed"),
            404: OpenApiResponse(description="not_found (autre numéro, close ou expirée)"),
            503: OpenApiResponse(description="invitation_unavailable"),
        },
    )
    def post(self, request: Request, public_id) -> Response:
        serializer = AcceptInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        accept_invitation(
            user=request.user,
            invitation_public_id=public_id,
            display_name=serializer.validated_data["display_name"],
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class DeclineInvitationView(APIView):
    permission_classes = [IsClient]

    @extend_schema(
        tags=["me"],
        operation_id="me_invitations_decline",
        request=None,
        responses={204: None, 404: OpenApiResponse(description="not_found")},
    )
    def post(self, request: Request, public_id) -> Response:
        decline_invitation(user=request.user, invitation_public_id=public_id)
        return Response(status=status.HTTP_204_NO_CONTENT)

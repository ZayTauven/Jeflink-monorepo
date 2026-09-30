"""Endpoints Ops sur les comptes (tag ``ops-accounts``, spec 001 ; tâche 15).

Lecture : ``ops.accounts.view``. Actions : ``ops.accounts.manage`` avec un TOTP de moins de
5 min (step-up, S25). Aucune donnée personnelle dans les URL (S14) : la recherche est en POST.
"""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from jeflink.accounts import ops
from jeflink.accounts.permissions import HasOpsPerm
from jeflink.accounts.selectors import active_roles, active_sessions_for
from jeflink.common.pii import mask_phone

from .serializers import (
    OpsAccountDetailSerializer,
    OpsSearchResultSerializer,
    OpsSearchSerializer,
    RevealedPhoneSerializer,
    ops_action_serializer,
)

CanView = HasOpsPerm("ops.accounts.view", step_up=False)
CanManage = HasOpsPerm("ops.accounts.manage", step_up=True)

COMMON_ERRORS = {
    400: OpenApiResponse(description="reason_invalid, note_invalid"),
    403: OpenApiResponse(description="ops_forbidden, ops_step_up_required, ops_target_forbidden"),
    404: OpenApiResponse(description="not_found"),
}


def _summary(user) -> dict:
    return {
        "public_id": user.public_id,
        "phone_masked": mask_phone(user.phone) if user.phone else "",
        "display_name": user.display_name,
        "profile_status": user.profile_status,
        "is_active": user.is_active,
        "roles": sorted(active_roles(user)),
    }


class OpsAccountSearchView(APIView):
    permission_classes = [CanView]

    @extend_schema(
        tags=["ops-accounts"],
        operation_id="ops_accounts_search",
        request=OpsSearchSerializer,
        responses={
            200: OpsSearchResultSerializer,
            400: OpenApiResponse(description="phone_invalid"),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = OpsSearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = ops.search_account(actor=request.user, raw_phone=serializer.validated_data["phone"])
        results = [_summary(user)] if user is not None else []
        return Response(OpsSearchResultSerializer({"results": results}).data)


class OpsAccountDetailView(APIView):
    permission_classes = [CanView]

    @extend_schema(
        tags=["ops-accounts"],
        operation_id="ops_accounts_retrieve",
        responses={200: OpsAccountDetailSerializer, **COMMON_ERRORS},
    )
    def get(self, request: Request, public_id) -> Response:
        user = ops.account_for_ops(actor=request.user, public_id=public_id)
        body = {
            **_summary(user),
            "preferred_language": user.preferred_language,
            "deactivation_reason": user.deactivation_reason,
            "deleted": user.is_deleted,
            "dormant_restricted": user.dormant_restricted_since is not None,
            "otp_blocked_until": ops.otp_block_until(user),
            "sessions": list(active_sessions_for(user)[:20]),
            "created_at": user.created_at,
            "phone_verified_at": user.phone_verified_at,
            "phone_changed_at": user.phone_changed_at,
        }
        return Response(OpsAccountDetailSerializer(body).data)


def _action_view(action: str, service, *, permission, operation_id: str, response=None):
    request_serializer = ops_action_serializer(action)
    success = {200: response} if response is not None else {204: None}

    class _View(APIView):
        permission_classes = [permission]

        @extend_schema(
            tags=["ops-accounts"],
            operation_id=operation_id,
            request=request_serializer,
            responses={**success, **COMMON_ERRORS},
        )
        def post(self, request: Request, public_id) -> Response:
            serializer = request_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            result = service(actor=request.user, public_id=public_id, **serializer.validated_data)
            if response is None:
                return Response(status=status.HTTP_204_NO_CONTENT)
            return Response(response({"phone": result}).data)

    _View.__name__ = f"Ops{''.join(p.capitalize() for p in action.split('_'))}View"
    return _View


OpsRevealPhoneView = _action_view(
    "reveal_phone",
    ops.reveal_phone,
    permission=CanView,
    operation_id="ops_accounts_reveal_phone",
    response=RevealedPhoneSerializer,
)
OpsRevokeSessionsView = _action_view(
    "revoke_sessions",
    ops.ops_revoke_sessions,
    permission=CanManage,
    operation_id="ops_accounts_revoke_sessions",
)
OpsUnblockOtpView = _action_view(
    "unblock_otp",
    ops.ops_unblock_otp,
    permission=CanManage,
    operation_id="ops_accounts_unblock_otp",
)
OpsDeactivateView = _action_view(
    "deactivate", ops.ops_deactivate, permission=CanManage, operation_id="ops_accounts_deactivate"
)
OpsReactivateView = _action_view(
    "reactivate", ops.ops_reactivate, permission=CanManage, operation_id="ops_accounts_reactivate"
)
OpsClearDormantView = _action_view(
    "clear_dormant",
    ops.ops_clear_dormant,
    permission=CanManage,
    operation_id="ops_accounts_clear_dormant",
)

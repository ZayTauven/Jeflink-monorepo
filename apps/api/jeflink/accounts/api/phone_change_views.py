"""Changement de numéro (S2) : actions Ops et confirmation par l'utilisateur."""

from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from jeflink.accounts import phone_change
from jeflink.accounts.models import PhoneChangeRequest
from jeflink.accounts.permissions import HasOpsPerm

from .otp_views import INSTALL_HEADER, resolve_app, verify_body
from .serializers import (
    OtpVerifyResponseSerializer,
    PhoneChangeApproveSerializer,
    PhoneChangeConfirmSerializer,
    PhoneChangeCreateSerializer,
    PhoneChangeRejectSerializer,
    PhoneChangeRequestSerializer,
)

CanChangePhone = HasOpsPerm("ops.accounts.change_phone", step_up=True)
CanListPhoneChanges = HasOpsPerm("ops.accounts.change_phone", step_up=False)

OPS_ERRORS = {
    403: OpenApiResponse(
        description=(
            "ops_forbidden, ops_step_up_required, ops_target_forbidden, "
            "ops_second_operator_required"
        )
    ),
    404: OpenApiResponse(description="not_found"),
    409: OpenApiResponse(description="phone_change_closed"),
    429: OpenApiResponse(description="otp_rate_limited, phone_change_codes_exhausted"),
}


class PhoneChangeCreateView(APIView):
    permission_classes = [CanChangePhone]

    @extend_schema(
        tags=["ops-accounts"],
        operation_id="ops_accounts_phone_change",
        request=PhoneChangeCreateSerializer,
        responses={
            201: PhoneChangeRequestSerializer,
            400: OpenApiResponse(
                description="phone_invalid, phone_unchanged, reason_invalid, note_invalid"
            ),
            **OPS_ERRORS,
            409: OpenApiResponse(
                description="phone_in_use, phone_change_in_progress, account_disabled"
            ),
        },
    )
    def post(self, request: Request, public_id) -> Response:
        serializer = PhoneChangeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        change = phone_change.request_phone_change(
            actor=request.user, public_id=public_id, **serializer.validated_data
        )
        return Response(PhoneChangeRequestSerializer(change).data, status=status.HTTP_201_CREATED)


class PhoneChangeListView(generics.ListAPIView):
    """Demandes ouvertes, pour que le second Ops trouve celles à approuver."""

    permission_classes = [CanListPhoneChanges]
    serializer_class = PhoneChangeRequestSerializer

    def get_queryset(self):
        return PhoneChangeRequest.objects.filter(
            status__in=PhoneChangeRequest.OPEN, expires_at__gt=timezone.now()
        ).select_related("user", "requested_by")

    @extend_schema(tags=["ops-accounts"], operation_id="ops_phone_changes_list")
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)


class PhoneChangeApproveView(APIView):
    permission_classes = [CanChangePhone]

    @extend_schema(
        tags=["ops-accounts"],
        operation_id="ops_phone_changes_approve",
        request=PhoneChangeApproveSerializer,
        responses={
            204: None,
            400: OpenApiResponse(description="phone_change_mismatch"),
            **OPS_ERRORS,
        },
    )
    def post(self, request: Request, public_id) -> Response:
        serializer = PhoneChangeApproveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone_change.approve_phone_change(
            actor=request.user, request_public_id=public_id, **serializer.validated_data
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class PhoneChangeRejectView(APIView):
    permission_classes = [CanChangePhone]

    @extend_schema(
        tags=["ops-accounts"],
        operation_id="ops_phone_changes_reject",
        request=PhoneChangeRejectSerializer,
        responses={204: None, **OPS_ERRORS},
    )
    def post(self, request: Request, public_id) -> Response:
        serializer = PhoneChangeRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone_change.reject_phone_change(
            actor=request.user, request_public_id=public_id, **serializer.validated_data
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class PhoneChangeResendView(APIView):
    permission_classes = [CanChangePhone]

    @extend_schema(
        tags=["ops-accounts"],
        operation_id="ops_phone_changes_resend_code",
        request=None,
        responses={200: PhoneChangeRequestSerializer, **OPS_ERRORS},
    )
    def post(self, request: Request, public_id) -> Response:
        # Statut renvoyé : « pending_approval » si le compte est devenu pro (aucun code parti).
        change = phone_change.resend_phone_change_code(
            actor=request.user, request_public_id=public_id
        )
        return Response(PhoneChangeRequestSerializer(change).data)


class PhoneChangeConfirmView(APIView):
    """« J'ai changé de numéro » : l'utilisateur saisit le code reçu sur le nouveau numéro."""

    permission_classes = [AllowAny]
    authentication_classes = []
    rate_limit_scope = "phone_change_confirm"

    @extend_schema(
        tags=["auth"],
        operation_id="auth_phone_change_confirm",
        request=PhoneChangeConfirmSerializer,
        responses={
            200: OtpVerifyResponseSerializer,
            400: OpenApiResponse(description="otp_invalid, terms_not_accepted, phone_invalid"),
            403: OpenApiResponse(description="account_disabled"),
            409: OpenApiResponse(description="otp_already_used, phone_in_use"),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = PhoneChangeConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        device = data["device"]
        result = phone_change.confirm_phone_change(
            new_phone=data["phone"],
            code=data["code"],
            terms_version=data["terms_version"],
            app=resolve_app(request, data.get("app")),
            platform=device["platform"],
            device_label=device["label"],
            install_id=device["install_id"] or request.headers.get(INSTALL_HEADER, ""),
        )
        return Response(OtpVerifyResponseSerializer(verify_body(result)).data)

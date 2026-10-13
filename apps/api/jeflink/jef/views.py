from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import services
from .models import JefSession


class StartSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=2000)
    trade = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")


class BriefSerializer(serializers.Serializer):
    answers = serializers.DictField(
        child=serializers.CharField(max_length=200, allow_blank=True), required=False, default=dict
    )


def payload(session: JefSession) -> dict:
    trade = session.trade
    return {
        "id": session.pk,
        "mode": session.mode,
        "trade": {"slug": trade.slug, "name": trade.name} if trade else None,
        "questions": [
            {"id": q["id"], "question": q["question"], "choices": q["choices"]}
            for q in session.questions
        ],
        "safety": services.safety(session),
        "answers": session.answers,
        "brief": session.brief,
    }


@extend_schema(request=StartSerializer, responses=OpenApiTypes.OBJECT)
@api_view(["POST"])
def start(request):
    """Le client décrit son souci : Jef propose un métier et pose jusqu'à trois questions."""
    data = StartSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    session = services.start(
        request.user, data.validated_data["text"], data.validated_data["trade"]
    )
    return Response(payload(session), status=status.HTTP_201_CREATED)


@extend_schema(request=BriefSerializer, responses=OpenApiTypes.OBJECT)
@api_view(["POST"])
def brief(request, pk: int):
    """Le client a répondu : Jef rédige la demande et la fiche du pro."""
    data = BriefSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    session = get_object_or_404(JefSession, pk=pk, client=request.user)
    session = services.write_brief(request.user, session, data.validated_data["answers"])
    return Response(payload(session))

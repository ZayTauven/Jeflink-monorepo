from django.http import FileResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from jeflink.console.permissions import can
from jeflink.media import delete_document, delete_image, private_storage, save_document, save_image

from .models import ProDocument, ProProfile, SavedAddress
from .serializers import (
    AddressSerializer,
    ContactSerializer,
    DocumentSerializer,
    LoginSerializer,
    MeSerializer,
    ProfileSerializer,
    RegisterSerializer,
)

AuthResponse = inline_serializer(
    "AuthResponse", {"token": serializers.CharField(), "user": MeSerializer()}
)


def _auth_payload(user):
    token, _ = Token.objects.get_or_create(user=user)
    return {"token": token.key, "user": MeSerializer(user).data}


@extend_schema(request=RegisterSerializer, responses={201: AuthResponse})
@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    return Response(_auth_payload(user), status=status.HTTP_201_CREATED)


@extend_schema(request=LoginSerializer, responses={200: AuthResponse})
@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    serializer = LoginSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    return Response(_auth_payload(serializer.validated_data["user"]))


@extend_schema(request=None, responses={204: None})
@api_view(["POST"])
def logout(request):
    Token.objects.filter(user=request.user).delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(methods=["GET"], responses=MeSerializer)
@extend_schema(methods=["PUT"], request=ProfileSerializer, responses=MeSerializer)
@api_view(["GET", "PUT"])
def me(request):
    """Mon compte. PUT : mon profil (formulaire complet, voir ProfileSerializer)."""
    if request.method == "PUT":
        data = ProfileSerializer(request.user, data=request.data)
        data.is_valid(raise_exception=True)
        data.save()
    return Response(MeSerializer(request.user).data)


@extend_schema(methods=["GET"], responses=AddressSerializer(many=True))
@extend_schema(methods=["POST"], request=AddressSerializer, responses={201: AddressSerializer})
@api_view(["GET", "POST"])
def my_addresses(request):
    """Mes adresses enregistrées (5 au plus), reprises dans le formulaire de demande."""
    if request.method == "GET":
        return Response(AddressSerializer(request.user.addresses.all(), many=True).data)
    if request.user.addresses.count() >= SavedAddress.MAX:
        raise serializers.ValidationError(
            f"{SavedAddress.MAX} adresses au plus : supprimez-en une d'abord."
        )
    data = AddressSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    address = data.save(user=request.user)
    return Response(AddressSerializer(address).data, status=status.HTTP_201_CREATED)


@extend_schema(methods=["PUT"], request=AddressSerializer, responses=AddressSerializer)
@extend_schema(methods=["DELETE"], request=None, responses={204: None})
@api_view(["PUT", "DELETE"])
def my_address(request, pk: int):
    address = get_object_or_404(request.user.addresses, pk=pk)  # les miennes seulement
    if request.method == "DELETE":
        address.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    data = AddressSerializer(address, data=request.data)
    data.is_valid(raise_exception=True)
    return Response(AddressSerializer(data.save()).data)


@extend_schema(
    methods=["POST"],
    request={
        "multipart/form-data": inline_serializer("PhotoUpload", {"photo": serializers.ImageField()})
    },
    responses=MeSerializer,
)
@extend_schema(methods=["DELETE"], request=None, responses=MeSerializer)
@api_view(["POST", "DELETE"])
@parser_classes([MultiPartParser])
def my_photo(request):
    """Ma photo de profil : POST (champ « photo ») la remplace, DELETE la retire.

    Pour un pro, c'est aussi la photo de son profil public.
    """
    user = request.user
    profile = getattr(user, "pro_profile", None)
    old = {user.photo, profile.photo if profile else ""}
    url = (
        ""
        if request.method == "DELETE"
        else save_image(request.FILES.get("photo"), "profils", max_side=1000)
    )
    user.photo = url
    user.save(update_fields=["photo"])
    if profile:
        profile.photo = url
        profile.save(update_fields=["photo"])
    for previous in old - {url}:
        delete_image(previous, "profils")
    return Response(MeSerializer(user).data)


@extend_schema(request=ContactSerializer, responses={201: None})
@api_view(["POST"])
@permission_classes([AllowAny])
def contact(request):
    serializer = ContactSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(status=status.HTTP_201_CREATED)


# --- Documents du pro (privés) -----------------------------------------------------------------


def _my_profile(request) -> ProProfile:
    profile = getattr(request.user, "pro_profile", None)
    if profile is None:
        raise PermissionDenied("Réservé aux comptes pro.")
    return profile


@extend_schema(methods=["GET"], responses=DocumentSerializer(many=True))
@extend_schema(
    methods=["POST"],
    request={
        "multipart/form-data": inline_serializer(
            "DocumentUpload",
            {
                "kind": serializers.ChoiceField(ProDocument.Kind.choices),
                "file": serializers.FileField(),
            },
        )
    },
    responses={201: DocumentSerializer},
)
@api_view(["GET", "POST"])
@parser_classes([MultiPartParser])
def my_documents(request):
    """Mes justificatifs (pro) : pièce d'identité, attestations. Examinés par l'équipe."""
    profile = _my_profile(request)
    if request.method == "GET":
        return Response(DocumentSerializer(profile.documents.all(), many=True).data)
    kind = request.data.get("kind")
    if kind not in ProDocument.Kind.values:
        raise serializers.ValidationError({"kind": "Choisissez le type de document."})
    if profile.documents.count() >= ProDocument.MAX:
        raise serializers.ValidationError(
            f"{ProDocument.MAX} documents au plus : supprimez-en un refusé d'abord."
        )
    path, content_type = save_document(request.FILES.get("file"))
    document = ProDocument.objects.create(
        profile=profile, kind=kind, file=path, content_type=content_type
    )
    return Response(DocumentSerializer(document).data, status=status.HTTP_201_CREATED)


@extend_schema(request=None, responses={204: None})
@api_view(["DELETE"])
def my_document(request, pk: int):
    """Retirer un de mes documents, tant qu'il n'est pas accepté (il fonde la vérification)."""
    document = get_object_or_404(_my_profile(request).documents, pk=pk)
    if document.status == ProDocument.Status.ACCEPTED:
        raise serializers.ValidationError("Un document accepté reste : écrivez au support.")
    delete_document(document.file)
    document.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(responses={(200, "application/octet-stream"): OpenApiTypes.BINARY})
@api_view(["GET"])
def document_file(request, pk: int):
    """Fichier d'un document : son pro, ou l'équipe Opérations. Jamais mis en cache ; un PDF
    est toujours téléchargé (jamais affiché dans une page du site)."""
    document = get_object_or_404(ProDocument.objects.select_related("profile"), pk=pk)
    user = request.user
    if document.profile.user_id != user.pk and not can(user, "operations"):
        raise NotFound()  # rien ne dit qu'il existe
    try:
        handle = private_storage().open(document.file, "rb")
    except OSError as exc:
        raise NotFound("Fichier introuvable.") from exc
    pdf = document.content_type == "application/pdf"
    response = FileResponse(
        handle,
        content_type=document.content_type,
        as_attachment=pdf,
        filename=f"jeflink-document-{document.pk}.{'pdf' if pdf else 'webp'}",
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = (
        "default-src 'none'; img-src 'self'; sandbox; frame-ancestors 'none'"
    )
    response["Cross-Origin-Resource-Policy"] = "same-origin"
    response["Referrer-Policy"] = "no-referrer"
    return response

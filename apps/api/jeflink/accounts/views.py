from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from jeflink.media import delete_image, save_image

from .models import SavedAddress
from .serializers import (
    AddressSerializer,
    ContactSerializer,
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

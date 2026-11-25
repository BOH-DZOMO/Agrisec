import uuid

from django.contrib.auth import authenticate
from django.db import transaction
from django.urls import reverse
from drf_spectacular.utils import OpenApiResponse
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema_view
from drf_spectacular.utils import inline_serializer
from rest_framework import generics
from rest_framework import serializers
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import action
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.mixins import UpdateModelMixin
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet

from agrisec.users.models import User

from .serializers import UserLoginSerializer
from .serializers import UserSerializer
from .serializers import UserSignupSerializer


@extend_schema_view(
    retrieve=extend_schema(tags=["Users"], summary="Get user profile by ID"),
    update=extend_schema(tags=["Users"], summary="Replace user profile"),
    partial_update=extend_schema(tags=["Users"], summary="Partially update user profile"),
)
class UserViewSet(RetrieveModelMixin, UpdateModelMixin, GenericViewSet):
    serializer_class = UserSerializer
    queryset = User.objects.all()
    lookup_field = "pk"

    def get_queryset(self, *args, **kwargs):
        if getattr(self, "swagger_fake_view", False):
            return User.objects.none()
        assert isinstance(self.request.user.id, uuid.UUID)
        return self.queryset.filter(id=self.request.user.id)

    @extend_schema(
        tags=["Users"],
        summary="Get current authenticated user",
        responses={200: UserSerializer},
    )
    @action(detail=False, methods=["get"])
    def me(self, request):
        serializer = UserSerializer(request.user, context={"request": request})
        return Response(status=status.HTTP_200_OK, data=serializer.data)


class CustomAuthToken(ObtainAuthToken):
    serializer_class = UserLoginSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        tags=["Auth"],
        summary="Obtain an authentication token",
        description="Authenticate with email and password to receive a fresh DRF auth token.",
        request=UserLoginSerializer,
        responses={
            200: inline_serializer(
                name="AuthTokenResponse",
                fields={
                    "token": serializers.CharField(),
                    "url": serializers.CharField(),
                },
            ),
            401: OpenApiResponse(description="Invalid email or password."),
        },
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request=request,
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response(
                {"detail": "Unable to log in with the provided credentials."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        with transaction.atomic():
            Token.objects.filter(user=user).delete()
            token = Token.objects.create(user=user)
        return Response(
            {
                "token": token.key,
                "url": reverse("api:user-detail", kwargs={"pk": user.pk}),
            },
        )


class SignupView(generics.CreateAPIView):
    serializer_class = UserSignupSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        tags=["Auth"],
        summary="Register a new user account",
        description="Creates a new user account and immediately issues an authentication token.",
        request=UserSignupSerializer,
        responses={
            201: inline_serializer(
                name="UserSignupResponse",
                fields={
                    "message": serializers.CharField(),
                    "token": serializers.CharField(),
                    "url": serializers.CharField(),
                },
            ),
            400: OpenApiResponse(description="Validation error (e.g. mismatched or weak passwords)."),
        },
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {
                "message": "User registered successfully.",
                "token": token.key,
                "url": serializer.data["url"],
            },
            status=status.HTTP_201_CREATED,
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Auth"],
        summary="Revoke current authentication token",
        description="Deletes the active user's auth token to log out.",
        request=None,
        responses={
            200: inline_serializer(
                name="LogoutResponse",
                fields={"message": serializers.CharField()},
            ),
        },
    )
    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response({"message": "Logged out successfully."})
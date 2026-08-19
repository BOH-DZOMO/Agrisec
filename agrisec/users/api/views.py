from rest_framework import status
import uuid
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.mixins import UpdateModelMixin
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework.views import APIView
from agrisec.users.models import User
from rest_framework import generics
from django.contrib.auth import authenticate
from django.urls import reverse
from django.db import transaction


from .serializers import UserSerializer, UserSignupSerializer, UserLoginSerializer

from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authtoken.models import Token
from rest_framework import status

from rest_framework.authtoken.views import ObtainAuthToken





class UserViewSet(RetrieveModelMixin, UpdateModelMixin, GenericViewSet):
    serializer_class = UserSerializer
    queryset = User.objects.all()
    lookup_field = "pk"

    def get_queryset(self, *args, **kwargs):
        assert isinstance(self.request.user.id, uuid.UUID)
        return self.queryset.filter(id=self.request.user.id)

    @action(detail=False)
    def me(self, request):
        serializer = UserSerializer(request.user, context={"request": request})
        return Response(status=status.HTTP_200_OK, data=serializer.data)


class CustomAuthToken(ObtainAuthToken):
    serializer_class = UserLoginSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request=request,
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response({
                "detail": "Unable to log in with the provided credentials."
                },status=status.HTTP_401_UNAUTHORIZED)

        with transaction.atomic():
            Token.objects.filter(user=user).delete()
            token = Token.objects.create(user=user)
        return Response({
            'token': token.key,
            "url": reverse("api:user-detail", kwargs={"pk": user.pk})
        })

        
class SignupView(generics.CreateAPIView):
    serializer_class = UserSignupSerializer
    permission_classes = [AllowAny] # Anyone is allowed to sign up!

    def create(self, request, *args, **kwargs):
        # 1. Run validation via the serializer
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # 2. Save the user to the database (triggers our create method above)
        user = serializer.save()
        
        # 3. Optional: Automatically log them in by generating an Auth Token immediately
        token, created = Token.objects.get_or_create(user=user)
        
        # 4. Return custom registration feedback
        return Response({
            "message": "User registered successfully.",
            "token": token.key,
            "url": serializer.data["url"] # Password is automatically hidden here!
        }, status=status.HTTP_201_CREATED)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response({"message": "Logged out successfully."})
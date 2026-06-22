from django.contrib.auth import login, logout
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import CommuteWindow, ContentSource, DownloadItem, Subscription, UserPreference
from core.permissions import IsAdminOrReadOnly, IsOwner
from core.serializers import (
    CommuteWindowSerializer,
    ContentSourceSerializer,
    DownloadItemSerializer,
    LoginSerializer,
    RegisterSerializer,
    SubscriptionSerializer,
    UserPreferenceSerializer,
    UserSerializer,
)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        login(request, user)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        login(request, user)
        return Response(UserSerializer(user).data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class UserPreferenceViewSet(viewsets.ModelViewSet):
    serializer_class = UserPreferenceSerializer
    permission_classes = [IsAuthenticated, IsOwner]
    http_method_names = ["get", "put", "patch", "head", "options"]

    def get_queryset(self):
        return UserPreference.objects.filter(user=self.request.user)

    def get_user_preference(self):
        preference, _ = UserPreference.objects.get_or_create(user=self.request.user)
        return preference

    @action(detail=False, methods=["get", "put", "patch"], url_path="me")
    def me(self, request):
        preference = self.get_user_preference()

        if request.method == "GET":
            serializer = self.get_serializer(preference)
            return Response(serializer.data)

        serializer = self.get_serializer(
            preference,
            data=request.data,
            partial=request.method == "PATCH",
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ContentSourceViewSet(viewsets.ModelViewSet):
    serializer_class = ContentSourceSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        queryset = ContentSource.objects.all()
        if not self.request.user.is_staff:
            queryset = queryset.filter(is_active=True)
        return queryset


class SubscriptionViewSet(viewsets.ModelViewSet):
    serializer_class = SubscriptionSerializer
    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self):
        return (
            Subscription.objects.filter(user=self.request.user)
            .select_related("source", "user")
            .order_by("priority", "source__name")
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class DownloadItemViewSet(viewsets.ModelViewSet):
    serializer_class = DownloadItemSerializer
    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self):
        return (
            DownloadItem.objects.filter(user=self.request.user)
            .select_related("source", "user")
            .order_by("-available_from", "-created_at")
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class CommuteWindowViewSet(viewsets.ModelViewSet):
    serializer_class = CommuteWindowSerializer
    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self):
        return CommuteWindow.objects.filter(user=self.request.user).order_by(
            "start_time",
            "label",
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

from django.contrib.auth import login, logout
from django.conf import settings
from django.core.cache import cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from redis import RedisError
from redis import from_url as redis_from_url
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.ingestion.adapters import (
    SUPPORTED_SOURCE_TYPES,
    SourceIngestionError,
    fetch_source_items,
    supports_source_discovery,
)
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
from core.tasks import discover_source_items, prepare_download_item


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


class RedisHealthView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        redis_url = getattr(settings, "REDIS_URL", None)
        if not redis_url:
            return Response(
                {
                    "redis": "unavailable",
                    "error": "REDIS_URL is not configured.",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            client = redis_from_url(
                redis_url,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            ping_result = client.ping()
        except (RedisError, ValueError) as exc:
            return Response(
                {
                    "redis": "unavailable",
                    "error": str(exc),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "redis": "connected",
                "ping": bool(ping_result),
            }
        )


class CacheTestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        cache_key = f"cache-test:{request.user.pk}"
        cache_value = "hello from redis"

        try:
            cache.set(cache_key, cache_value, timeout=60)
            returned_value = cache.get(cache_key)
        except Exception as exc:
            return Response(
                {
                    "cache": "unavailable",
                    "error": str(exc),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if returned_value != cache_value:
            return Response(
                {
                    "cache": "unavailable",
                    "error": "Cache read did not match the written value.",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "cache": "working",
                "value": returned_value,
            }
        )


class SourcePreviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, source_id):
        try:
            source = ContentSource.objects.get(pk=source_id, is_active=True)
        except ContentSource.DoesNotExist:
            return Response(
                {"detail": "Content source was not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if source.policy != ContentSource.POLICY_CACHE_ALLOWED:
            return Response(
                {"detail": "Only cache-allowed sources can be previewed for discovery."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            items = fetch_source_items(source, limit=5)
        except SourceIngestionError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "source": ContentSourceSerializer(source).data,
                "count": len(items),
                "items": items,
            }
        )


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

    @action(detail=False, methods=["get"], url_path="cache-allowed")
    def cache_allowed(self, request):
        queryset = self.get_queryset().filter(policy=ContentSource.POLICY_CACHE_ALLOWED)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["post"],
        url_path="discover",
        permission_classes=[IsAuthenticated],
    )
    def discover(self, request, pk=None):
        source = self.get_object()

        if source.policy != ContentSource.POLICY_CACHE_ALLOWED:
            return Response(
                {"detail": "Only cache-allowed sources can run discovery."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not supports_source_discovery(source):
            return Response(
                {
                    "detail": (
                        f"Discovery is currently available for {SUPPORTED_SOURCE_TYPES} only."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            async_result = discover_source_items.delay(source.pk, request.user.pk)
        except Exception as exc:
            return Response(
                {
                    "detail": "Could not enqueue the source discovery task.",
                    "error": str(exc),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "detail": "Source discovery task queued.",
                "task_id": async_result.id,
                "source": self.get_serializer(source).data,
            },
            status=status.HTTP_202_ACCEPTED,
        )


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

    @action(detail=True, methods=["post"], url_path="prepare")
    def prepare(self, request, pk=None):
        download_item = self.get_object()

        if download_item.status == DownloadItem.STATUS_READY:
            return Response(
                {
                    "detail": "Download item is already ready.",
                    "download": self.get_serializer(download_item).data,
                }
            )

        if download_item.status == DownloadItem.STATUS_DOWNLOADING:
            return Response(
                {
                    "detail": "Download item is already being prepared.",
                    "download": self.get_serializer(download_item).data,
                },
                status=status.HTTP_202_ACCEPTED,
            )

        if download_item.source.policy != ContentSource.POLICY_CACHE_ALLOWED:
            return Response(
                {"detail": "This source is metadata-only and cannot be cached."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not download_item.media_url:
            return Response(
                {"detail": "This item does not have a downloadable media URL."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            async_result = prepare_download_item.delay(download_item.pk)
        except Exception as exc:
            return Response(
                {
                    "detail": "Could not enqueue the offline preparation task.",
                    "error": str(exc),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        download_item.refresh_from_db()
        return Response(
            {
                "detail": "Offline preparation task queued.",
                "task_id": async_result.id,
                "download": self.get_serializer(download_item).data,
            },
            status=status.HTTP_202_ACCEPTED,
        )


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

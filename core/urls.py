from django.urls import include, path
from rest_framework.routers import DefaultRouter

from core.views import (
    CommuteWindowViewSet,
    ContentSourceViewSet,
    DownloadItemViewSet,
    LoginView,
    LogoutView,
    MeView,
    CacheTestView,
    RegisterView,
    RedisHealthView,
    SourcePreviewView,
    SubscriptionViewSet,
    UserPreferenceViewSet,
)


router = DefaultRouter()
router.register("preferences", UserPreferenceViewSet, basename="preference")
router.register("commute", CommuteWindowViewSet, basename="commute")
router.register("commute-windows", CommuteWindowViewSet, basename="commute-window")
router.register("sources", ContentSourceViewSet, basename="source")
router.register("subscriptions", SubscriptionViewSet, basename="subscription")
router.register("downloads", DownloadItemViewSet, basename="download")

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("system/redis-health/", RedisHealthView.as_view(), name="redis-health"),
    path("system/cache-test/", CacheTestView.as_view(), name="cache-test"),
    path(
        "system/source-preview/<int:source_id>/",
        SourcePreviewView.as_view(),
        name="source-preview",
    ),
    path("", include(router.urls)),
]

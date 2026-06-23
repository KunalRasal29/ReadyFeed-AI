from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import CommuteWindow, ContentSource, DownloadItem, Subscription
from core.tasks import debug_task


User = get_user_model()


class ApiRoutePermissionTests(TestCase):
    def setUp(self):
        self.source = ContentSource.objects.create(
            name="Daily World News",
            type=ContentSource.TYPE_NEWS,
            feed_url="https://example.com/feeds/world-news.xml",
            policy=ContentSource.POLICY_METADATA_ONLY,
        )
        self.user = User.objects.create_user(
            username="route_user",
            password="test-password-123",
        )
        self.other_user = User.objects.create_user(
            username="other_user",
            password="test-password-123",
        )

    def test_unauthenticated_route_access(self):
        client = APIClient()

        self.assertEqual(client.get("/api/sources/").status_code, 200)
        self.assertEqual(
            client.post(
                "/api/auth/register/",
                {
                    "username": "new_user",
                    "password": "test-password-123",
                },
                format="json",
            ).status_code,
            201,
        )
        self.assertEqual(
            client.post(
                "/api/auth/login/",
                {
                    "username": "route_user",
                    "password": "test-password-123",
                },
                format="json",
            ).status_code,
            200,
        )

        client.logout()
        protected_routes = [
            ("get", "/api/auth/me/"),
            ("post", "/api/auth/logout/"),
            ("get", "/api/subscriptions/"),
            ("get", "/api/preferences/"),
            ("get", "/api/downloads/"),
            ("get", "/api/commute/"),
            ("get", "/api/system/redis-health/"),
            ("post", "/api/system/cache-test/"),
        ]
        for method, path in protected_routes:
            response = getattr(client, method)(path)
            self.assertEqual(response.status_code, 403, path)

    def test_authenticated_users_only_see_their_own_data(self):
        Subscription.objects.create(user=self.user, source=self.source)
        other_subscription = Subscription.objects.create(
            user=self.other_user,
            source=ContentSource.objects.create(
                name="Other Podcast",
                type=ContentSource.TYPE_PODCAST,
                feed_url="https://example.com/feeds/other-podcast.xml",
                policy=ContentSource.POLICY_METADATA_ONLY,
            ),
        )
        DownloadItem.objects.create(
            user=self.user,
            source=self.source,
            title="Mine",
            original_url="https://example.com/mine",
        )
        DownloadItem.objects.create(
            user=self.other_user,
            source=other_subscription.source,
            title="Other",
            original_url="https://example.com/other",
        )
        CommuteWindow.objects.create(
            user=self.user,
            label="Morning",
            start_time="08:00",
            end_time="09:00",
            days_of_week=["mon", "tue"],
        )
        CommuteWindow.objects.create(
            user=self.other_user,
            label="Evening",
            start_time="18:00",
            end_time="19:00",
            days_of_week=["wed"],
        )

        client = APIClient()
        client.login(username="route_user", password="test-password-123")

        preferences = client.get("/api/preferences/").json()
        subscriptions = client.get("/api/subscriptions/").json()
        downloads = client.get("/api/downloads/").json()
        commute = client.get("/api/commute/").json()

        self.assertEqual(len(preferences), 1)
        self.assertEqual(preferences[0]["user"], self.user.id)
        self.assertEqual(len(subscriptions), 1)
        self.assertEqual(subscriptions[0]["user"], self.user.id)
        self.assertEqual(len(downloads), 1)
        self.assertEqual(downloads[0]["title"], "Mine")
        self.assertEqual(len(commute), 1)
        self.assertEqual(commute[0]["label"], "Morning")

    def test_cors_headers_allow_vite_origin(self):
        response = APIClient().get(
            "/api/sources/",
            HTTP_ORIGIN="http://localhost:5173",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["access-control-allow-origin"],
            "http://localhost:5173",
        )
        self.assertEqual(response["access-control-allow-credentials"], "true")

    @override_settings(REDIS_URL=None)
    def test_redis_health_reports_unavailable_without_url(self):
        client = APIClient()
        client.login(username="route_user", password="test-password-123")

        response = client.get("/api/system/redis-health/")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["redis"], "unavailable")

    @override_settings(
        REDIS_URL=None,
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "test-cache",
            }
        },
    )
    def test_cache_test_endpoint_works_with_fallback_cache(self):
        client = APIClient()
        client.login(username="route_user", password="test-password-123")

        response = client.post("/api/system/cache-test/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "cache": "working",
                "value": "hello from redis",
            },
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_debug_task_runs_in_eager_mode(self):
        result = debug_task.delay("READYFEED Celery works")

        self.assertEqual(result.get(timeout=5), "READYFEED Celery works")

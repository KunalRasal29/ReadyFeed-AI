from pathlib import Path
import tempfile
from io import StringIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.models import CommuteWindow, ContentSource, DownloadItem, Subscription
from core.tasks import debug_task, prepare_download_item


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

    def test_cache_allowed_sources_endpoint_is_public_and_filtered(self):
        cache_source = ContentSource.objects.create(
            name="Open Image Source",
            type=ContentSource.TYPE_IMAGE,
            feed_url="https://example.com/open-images.json",
            policy=ContentSource.POLICY_CACHE_ALLOWED,
            license_name="Creative Commons Zero (CC0)",
            license_url="https://creativecommons.org/publicdomain/zero/1.0/",
        )
        ContentSource.objects.create(
            name="Inactive Open Image Source",
            type=ContentSource.TYPE_IMAGE,
            feed_url="https://example.com/inactive-open-images.json",
            policy=ContentSource.POLICY_CACHE_ALLOWED,
            is_active=False,
        )

        response = APIClient().get("/api/sources/cache-allowed/")

        self.assertEqual(response.status_code, 200)
        names = {source["name"] for source in response.json()}
        self.assertIn(cache_source.name, names)
        self.assertNotIn("Daily World News", names)
        self.assertNotIn("Inactive Open Image Source", names)

    def test_seed_defaults_creates_at_least_50_cache_allowed_sources(self):
        call_command("seed_defaults", stdout=StringIO())

        cache_allowed_count = ContentSource.objects.filter(
            policy=ContentSource.POLICY_CACHE_ALLOWED,
            is_active=True,
        ).count()

        self.assertGreaterEqual(cache_allowed_count, 50)
        self.assertFalse(
            ContentSource.objects.filter(
                name="Daily Meme Digest",
                policy=ContentSource.POLICY_CACHE_ALLOWED,
                is_active=True,
            ).exists()
        )

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

    def test_prepare_download_task_creates_offline_file(self):
        download_item = DownloadItem.objects.create(
            user=self.user,
            source=self.source,
            title="Offline News Brief",
            description="A short summary for the train.",
            original_url="https://example.com/news/offline-brief",
        )

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(
                CELERY_TASK_ALWAYS_EAGER=True,
                MEDIA_ROOT=Path(media_root),
            ):
                result = prepare_download_item.delay(download_item.id)

                self.assertEqual(result.get(timeout=5)["status"], DownloadItem.STATUS_READY)

                download_item.refresh_from_db()
                prepared_path = Path(download_item.local_file_path)
                if not prepared_path.is_absolute():
                    prepared_path = settings.BASE_DIR / prepared_path

                self.assertTrue(prepared_path.exists())

        self.assertEqual(download_item.status, DownloadItem.STATUS_READY)
        self.assertGreater(download_item.file_size_bytes, 0)
        self.assertEqual(download_item.error_message, "")

    def test_prepare_download_endpoint_queues_user_item(self):
        download_item = DownloadItem.objects.create(
            user=self.user,
            source=self.source,
            title="Endpoint Prepared Item",
            original_url="https://example.com/news/endpoint-prepared",
        )

        client = APIClient()
        client.login(username="route_user", password="test-password-123")

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(
                CELERY_TASK_ALWAYS_EAGER=True,
                MEDIA_ROOT=Path(media_root),
            ):
                response = client.post(f"/api/downloads/{download_item.id}/prepare/")

                self.assertEqual(response.status_code, 202)
                self.assertEqual(response.json()["detail"], "Offline preparation task queued.")

        download_item.refresh_from_db()
        self.assertEqual(download_item.status, DownloadItem.STATUS_READY)

    def test_prepare_download_endpoint_cannot_access_another_users_item(self):
        other_download = DownloadItem.objects.create(
            user=self.other_user,
            source=self.source,
            title="Other User Item",
            original_url="https://example.com/news/other",
        )

        client = APIClient()
        client.login(username="route_user", password="test-password-123")

        response = client.post(f"/api/downloads/{other_download.id}/prepare/")

        self.assertEqual(response.status_code, 404)

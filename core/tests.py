from pathlib import Path
import tempfile
from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.ingestion.adapters import fetch_source_items
from core.models import CommuteWindow, ContentSource, DownloadItem, Subscription
from core.tasks import debug_task, discover_source_items, prepare_download_item


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
            ("get", f"/api/system/source-preview/{self.source.id}/"),
            ("post", f"/api/sources/{self.source.id}/discover/"),
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

    def test_source_preview_returns_wikimedia_items_without_saving(self):
        source = ContentSource.objects.create(
            name="Wikimedia Commons Memes - Test",
            type=ContentSource.TYPE_MEME,
            feed_url="https://commons.wikimedia.org/w/api.php?action=query&gsrsearch=cat",
            policy=ContentSource.POLICY_CACHE_ALLOWED,
            license_name="Wikimedia Commons free licenses / public domain",
            license_url="https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia",
            attribution_required=True,
        )
        client = APIClient()
        client.login(username="route_user", password="test-password-123")
        fake_items = [
            {
                "title": "Funny cat.jpg",
                "description": "Discovered from Wikimedia Commons.",
                "original_url": "https://commons.wikimedia.org/wiki/File:Funny_cat.jpg",
                "media_url": "https://upload.wikimedia.org/funny-cat.jpg",
                "license_name": "CC BY-SA 4.0",
                "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
                "author": "Example author",
                "mime_type": "image/jpeg",
            }
        ]

        with patch("core.views.fetch_source_items", return_value=fake_items):
            response = client.get(f"/api/system/source-preview/{source.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["title"], "Funny cat.jpg")
        self.assertFalse(
            DownloadItem.objects.filter(
                user=self.user,
                source=source,
                original_url=fake_items[0]["original_url"],
            ).exists()
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_discover_source_task_creates_queued_download_items(self):
        source = ContentSource.objects.create(
            name="Wikimedia Commons Memes - Test",
            type=ContentSource.TYPE_MEME,
            feed_url="https://commons.wikimedia.org/w/api.php?action=query&gsrsearch=cat",
            policy=ContentSource.POLICY_CACHE_ALLOWED,
        )
        fake_items = [
            {
                "title": "Funny cat.jpg",
                "description": "Discovered from Wikimedia Commons.",
                "original_url": "https://commons.wikimedia.org/wiki/File:Funny_cat.jpg",
                "media_url": "https://upload.wikimedia.org/funny-cat.jpg",
            }
        ]

        with patch("core.tasks.fetch_source_items", return_value=fake_items):
            result = discover_source_items.delay(source.id, self.user.id)

        self.assertEqual(result.get(timeout=5)["created_count"], 1)
        download_item = DownloadItem.objects.get(
            user=self.user,
            source=source,
            original_url=fake_items[0]["original_url"],
        )
        self.assertEqual(download_item.status, DownloadItem.STATUS_QUEUED)
        self.assertEqual(download_item.media_url, fake_items[0]["media_url"])
        self.assertIsNone(download_item.file_size_bytes)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_discover_endpoint_queues_task_for_wikimedia_source(self):
        source = ContentSource.objects.create(
            name="Wikimedia Commons Memes - Test",
            type=ContentSource.TYPE_MEME,
            feed_url="https://commons.wikimedia.org/w/api.php?action=query&gsrsearch=cat",
            policy=ContentSource.POLICY_CACHE_ALLOWED,
        )
        client = APIClient()
        client.login(username="route_user", password="test-password-123")
        fake_items = [
            {
                "title": "Funny cat.jpg",
                "description": "Discovered from Wikimedia Commons.",
                "original_url": "https://commons.wikimedia.org/wiki/File:Funny_cat.jpg",
                "media_url": "https://upload.wikimedia.org/funny-cat.jpg",
            }
        ]

        with patch("core.tasks.fetch_source_items", return_value=fake_items):
            response = client.post(f"/api/sources/{source.id}/discover/")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["detail"], "Source discovery task queued.")
        self.assertTrue(
            DownloadItem.objects.filter(
                user=self.user,
                source=source,
                original_url=fake_items[0]["original_url"],
                status=DownloadItem.STATUS_QUEUED,
            ).exists()
        )

    def test_discover_endpoint_rejects_metadata_only_source(self):
        client = APIClient()
        client.login(username="route_user", password="test-password-123")

        response = client.post(f"/api/sources/{self.source.id}/discover/")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"],
            "Only cache-allowed sources can run discovery.",
        )

    def test_nasa_adapter_normalizes_search_results(self):
        source = ContentSource.objects.create(
            name="NASA Images - Mars Test",
            type=ContentSource.TYPE_IMAGE,
            feed_url="https://images-api.nasa.gov/search?q=mars&media_type=image",
            policy=ContentSource.POLICY_CACHE_ALLOWED,
            license_name="NASA Media Usage Guidelines",
            license_url="https://www.nasa.gov/nasa-brand-center/images-and-media/",
            attribution_required=True,
        )
        nasa_response = {
            "collection": {
                "items": [
                    {
                        "data": [
                            {
                                "center": "JPL",
                                "date_created": "2021-02-18T00:00:00Z",
                                "description": "Mars rover image.",
                                "keywords": ["Mars", "Rover"],
                                "media_type": "image",
                                "nasa_id": "PIA24421",
                                "photographer": "NASA/JPL-Caltech",
                                "title": "Mars Perseverance Rover",
                            }
                        ],
                        "links": [
                            {
                                "href": "https://images-assets.nasa.gov/image/PIA24421/PIA24421~thumb.jpg",
                                "rel": "preview",
                                "render": "image",
                            }
                        ],
                    }
                ]
            }
        }

        with patch("core.ingestion.nasa._fetch_json", return_value=nasa_response):
            items = fetch_source_items(source, limit=5)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Mars Perseverance Rover")
        self.assertEqual(
            items[0]["original_url"],
            "https://images.nasa.gov/details/PIA24421",
        )
        self.assertEqual(
            items[0]["media_url"],
            "https://images-assets.nasa.gov/image/PIA24421/PIA24421~thumb.jpg",
        )
        self.assertEqual(items[0]["license_name"], "NASA Media Usage Guidelines")
        self.assertIn("NASA ID: PIA24421", items[0]["description"])

    def test_gutendex_adapter_normalizes_public_domain_books(self):
        source = ContentSource.objects.create(
            name="Gutendex Public Domain Books - Adventure Test",
            type=ContentSource.TYPE_BOOK,
            feed_url="https://gutendex.com/books/?copyright=false&languages=en&topic=adventure",
            policy=ContentSource.POLICY_CACHE_ALLOWED,
            license_name="Project Gutenberg License / Public domain in the USA",
            license_url="https://www.gutenberg.org/policy/license.html",
            attribution_required=True,
        )
        gutendex_response = {
            "count": 1,
            "next": None,
            "previous": None,
            "results": [
                {
                    "id": 1342,
                    "title": "Pride and Prejudice",
                    "subjects": ["Courtship -- Fiction"],
                    "authors": [{"name": "Austen, Jane", "birth_year": 1775, "death_year": 1817}],
                    "summaries": ["A classic novel."],
                    "bookshelves": ["Best Books Ever Listings"],
                    "languages": ["en"],
                    "copyright": False,
                    "media_type": "Text",
                    "formats": {
                        "text/html": "https://www.gutenberg.org/ebooks/1342.html.images",
                        "application/epub+zip": "https://www.gutenberg.org/ebooks/1342.epub3.images",
                    },
                    "download_count": 100000,
                }
            ],
        }

        with patch("core.ingestion.gutendex._fetch_json", return_value=gutendex_response):
            items = fetch_source_items(source, limit=5)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Pride and Prejudice")
        self.assertEqual(
            items[0]["original_url"],
            "https://www.gutenberg.org/ebooks/1342",
        )
        self.assertEqual(
            items[0]["media_url"],
            "https://www.gutenberg.org/ebooks/1342.html.images",
        )
        self.assertEqual(items[0]["author"], "Austen, Jane")
        self.assertIn("Project Gutenberg ID: 1342", items[0]["description"])

    def test_met_adapter_normalizes_public_domain_objects(self):
        source = ContentSource.objects.create(
            name="The Met Open Access - Flowers Test",
            type=ContentSource.TYPE_IMAGE,
            feed_url="https://collectionapi.metmuseum.org/public/collection/v1/search?hasImages=true&q=flowers",
            policy=ContentSource.POLICY_CACHE_ALLOWED,
            license_name="Creative Commons Zero (CC0)",
            license_url="https://www.metmuseum.org/hubs/open-access",
        )
        search_response = {
            "total": 1,
            "objectIDs": [436535],
        }
        object_response = {
            "objectID": 436535,
            "isPublicDomain": True,
            "primaryImage": "https://images.metmuseum.org/CRDImages/ep/original/DT1567.jpg",
            "primaryImageSmall": "https://images.metmuseum.org/CRDImages/ep/web-large/DT1567.jpg",
            "department": "European Paintings",
            "objectName": "Painting",
            "title": "Roses",
            "artistDisplayName": "Vincent van Gogh",
            "objectDate": "1890",
            "medium": "Oil on canvas",
            "dimensions": "10 x 13 in.",
            "creditLine": "The Met Collection",
            "objectURL": "https://www.metmuseum.org/art/collection/search/436535",
            "tags": [{"term": "Flowers"}],
        }

        with patch(
            "core.ingestion.met._fetch_json",
            side_effect=[search_response, object_response],
        ):
            items = fetch_source_items(source, limit=5)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Roses")
        self.assertEqual(
            items[0]["original_url"],
            "https://www.metmuseum.org/art/collection/search/436535",
        )
        self.assertEqual(
            items[0]["media_url"],
            "https://images.metmuseum.org/CRDImages/ep/web-large/DT1567.jpg",
        )
        self.assertEqual(items[0]["license_name"], "Creative Commons Zero (CC0)")
        self.assertIn("The Met object ID: 436535", items[0]["description"])

    def test_artic_adapter_normalizes_public_domain_artworks(self):
        source = ContentSource.objects.create(
            name="Art Institute Chicago Public Domain - Cats Test",
            type=ContentSource.TYPE_IMAGE,
            feed_url=(
                "https://api.artic.edu/api/v1/artworks/search?"
                "q=cats&query%5Bterm%5D%5Bis_public_domain%5D=true"
            ),
            policy=ContentSource.POLICY_CACHE_ALLOWED,
            license_name="Creative Commons Zero (CC0)",
            license_url="https://api.artic.edu/docs/",
        )
        artic_response = {
            "data": [
                {
                    "id": 27992,
                    "title": "A Sunday on La Grande Jatte",
                    "artist_display": "Georges Seurat\nFrench, 1859-1891",
                    "date_display": "1884",
                    "medium_display": "Oil on canvas",
                    "place_of_origin": "France",
                    "image_id": "2d484387-2509-5e8e-2c43-22f9981972eb",
                    "is_public_domain": True,
                    "credit_line": "Helen Birch Bartlett Memorial Collection",
                    "classification_title": "painting",
                    "subject_titles": ["parks", "leisure"],
                    "thumbnail": {"alt_text": "People in a park."},
                }
            ],
            "config": {"iiif_url": "https://www.artic.edu/iiif/2"},
        }

        with patch("core.ingestion.artic._fetch_json", return_value=artic_response):
            items = fetch_source_items(source, limit=5)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "A Sunday on La Grande Jatte")
        self.assertEqual(items[0]["original_url"], "https://www.artic.edu/artworks/27992")
        self.assertEqual(
            items[0]["media_url"],
            (
                "https://www.artic.edu/iiif/2/"
                "2d484387-2509-5e8e-2c43-22f9981972eb/full/843,/0/default.jpg"
            ),
        )
        self.assertEqual(items[0]["license_name"], "Creative Commons Zero (CC0)")
        self.assertIn("ArtIC artwork ID: 27992", items[0]["description"])

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_discover_endpoint_queues_task_for_nasa_source(self):
        source = ContentSource.objects.create(
            name="NASA Images - Mars Test",
            type=ContentSource.TYPE_IMAGE,
            feed_url="https://images-api.nasa.gov/search?q=mars&media_type=image",
            policy=ContentSource.POLICY_CACHE_ALLOWED,
            license_name="NASA Media Usage Guidelines",
        )
        client = APIClient()
        client.login(username="route_user", password="test-password-123")
        fake_items = [
            {
                "title": "Mars Perseverance Rover",
                "description": "Discovered from NASA Images and Video Library.",
                "original_url": "https://images.nasa.gov/details/PIA24421",
                "media_url": "https://images-assets.nasa.gov/image/PIA24421/PIA24421~thumb.jpg",
            }
        ]

        with patch("core.tasks.fetch_source_items", return_value=fake_items):
            response = client.post(f"/api/sources/{source.id}/discover/")

        self.assertEqual(response.status_code, 202)
        self.assertTrue(
            DownloadItem.objects.filter(
                user=self.user,
                source=source,
                original_url=fake_items[0]["original_url"],
                status=DownloadItem.STATUS_QUEUED,
            ).exists()
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_discover_endpoint_queues_task_for_gutendex_source(self):
        source = ContentSource.objects.create(
            name="Gutendex Public Domain Books - Adventure Test",
            type=ContentSource.TYPE_BOOK,
            feed_url="https://gutendex.com/books/?copyright=false&languages=en&topic=adventure",
            policy=ContentSource.POLICY_CACHE_ALLOWED,
            license_name="Project Gutenberg License / Public domain in the USA",
        )
        client = APIClient()
        client.login(username="route_user", password="test-password-123")
        fake_items = [
            {
                "title": "Pride and Prejudice",
                "description": "Discovered from Gutendex / Project Gutenberg.",
                "original_url": "https://www.gutenberg.org/ebooks/1342",
                "media_url": "https://www.gutenberg.org/ebooks/1342.html.images",
            }
        ]

        with patch("core.tasks.fetch_source_items", return_value=fake_items):
            response = client.post(f"/api/sources/{source.id}/discover/")

        self.assertEqual(response.status_code, 202)
        self.assertTrue(
            DownloadItem.objects.filter(
                user=self.user,
                source=source,
                original_url=fake_items[0]["original_url"],
                status=DownloadItem.STATUS_QUEUED,
            ).exists()
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_discover_endpoint_queues_task_for_met_source(self):
        source = ContentSource.objects.create(
            name="The Met Open Access - Flowers Test",
            type=ContentSource.TYPE_IMAGE,
            feed_url="https://collectionapi.metmuseum.org/public/collection/v1/search?hasImages=true&q=flowers",
            policy=ContentSource.POLICY_CACHE_ALLOWED,
            license_name="Creative Commons Zero (CC0)",
        )
        client = APIClient()
        client.login(username="route_user", password="test-password-123")
        fake_items = [
            {
                "title": "Roses",
                "description": "Discovered from The Met Open Access Collection API.",
                "original_url": "https://www.metmuseum.org/art/collection/search/436535",
                "media_url": "https://images.metmuseum.org/CRDImages/ep/web-large/DT1567.jpg",
            }
        ]

        with patch("core.tasks.fetch_source_items", return_value=fake_items):
            response = client.post(f"/api/sources/{source.id}/discover/")

        self.assertEqual(response.status_code, 202)
        self.assertTrue(
            DownloadItem.objects.filter(
                user=self.user,
                source=source,
                original_url=fake_items[0]["original_url"],
                status=DownloadItem.STATUS_QUEUED,
            ).exists()
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_discover_endpoint_queues_task_for_artic_source(self):
        source = ContentSource.objects.create(
            name="Art Institute Chicago Public Domain - Cats Test",
            type=ContentSource.TYPE_IMAGE,
            feed_url=(
                "https://api.artic.edu/api/v1/artworks/search?"
                "q=cats&query%5Bterm%5D%5Bis_public_domain%5D=true"
            ),
            policy=ContentSource.POLICY_CACHE_ALLOWED,
            license_name="Creative Commons Zero (CC0)",
        )
        client = APIClient()
        client.login(username="route_user", password="test-password-123")
        fake_items = [
            {
                "title": "A Sunday on La Grande Jatte",
                "description": "Discovered from the Art Institute of Chicago API.",
                "original_url": "https://www.artic.edu/artworks/27992",
                "media_url": (
                    "https://www.artic.edu/iiif/2/"
                    "2d484387-2509-5e8e-2c43-22f9981972eb/full/843,/0/default.jpg"
                ),
            }
        ]

        with patch("core.tasks.fetch_source_items", return_value=fake_items):
            response = client.post(f"/api/sources/{source.id}/discover/")

        self.assertEqual(response.status_code, 202)
        self.assertTrue(
            DownloadItem.objects.filter(
                user=self.user,
                source=source,
                original_url=fake_items[0]["original_url"],
                status=DownloadItem.STATUS_QUEUED,
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

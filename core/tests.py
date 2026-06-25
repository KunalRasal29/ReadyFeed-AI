from datetime import datetime, time, timedelta
from pathlib import Path
import tempfile
from io import BytesIO, StringIO
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.ingestion.adapters import fetch_source_items
from core.models import CommuteWindow, ContentSource, DownloadItem, Subscription
from core.tasks import (
    OfflineDownloadError,
    debug_task,
    discover_source_items,
    prepare_download_item,
    queue_commute_preparation,
)


User = get_user_model()


class FakeDownloadHeaders(dict):
    def get_content_type(self):
        return self.get("Content-Type", "application/octet-stream").split(";")[0]


class FakeDownloadResponse:
    def __init__(self, body, headers=None):
        self.stream = BytesIO(body)
        self.headers = FakeDownloadHeaders(headers or {})

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, size=-1):
        return self.stream.read(size)


class FakeS3Client:
    def __init__(self):
        self.uploads = []
        self.presigned_calls = []

    def upload_file(self, Filename, Bucket, Key, ExtraArgs=None):
        self.uploads.append(
            {
                "bucket": Bucket,
                "key": Key,
                "extra_args": ExtraArgs or {},
                "body": Path(Filename).read_bytes(),
            }
        )

    def generate_presigned_url(self, ClientMethod, Params, ExpiresIn):
        self.presigned_calls.append(
            {
                "client_method": ClientMethod,
                "params": Params,
                "expires_in": ExpiresIn,
            }
        )
        return f"https://signed.example.test/{Params['Key']}?expires={ExpiresIn}"


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

    def test_loc_adapter_normalizes_free_to_use_items(self):
        source = ContentSource.objects.create(
            name="Library of Congress Free to Use - Cats Test",
            type=ContentSource.TYPE_IMAGE,
            feed_url="https://www.loc.gov/free-to-use/cats/?fo=json",
            policy=ContentSource.POLICY_CACHE_ALLOWED,
            license_name="Library of Congress Free to Use and Reuse",
            license_url="https://www.loc.gov/free-to-use/",
        )
        loc_response = {
            "results": [
                {
                    "title": "Cat portrait",
                    "date": "1900",
                    "description": ["A cat portrait."],
                    "rights": "No known restrictions on publication.",
                    "subject": ["cats"],
                    "creator": ["Library of Congress"],
                    "image_url": [
                        "https://www.loc.gov/static/images/fallback.jpg",
                        (
                            "https://www.loc.gov/pictures/item/12345/"
                            "resource/cph.3g12345/preview.jpg"
                        ),
                    ],
                    "url": "https://www.loc.gov/item/12345/",
                }
            ]
        }

        with patch("core.ingestion.loc._fetch_json", return_value=loc_response):
            items = fetch_source_items(source, limit=5)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Cat portrait")
        self.assertEqual(items[0]["original_url"], "https://www.loc.gov/item/12345/")
        self.assertEqual(
            items[0]["media_url"],
            "https://www.loc.gov/pictures/item/12345/resource/cph.3g12345/preview.jpg",
        )
        self.assertEqual(
            items[0]["license_name"],
            "Library of Congress Free to Use and Reuse",
        )
        self.assertEqual(items[0]["author"], "Library of Congress")
        self.assertIn(
            "Discovered from a Library of Congress Free to Use and Reuse collection.",
            items[0]["description"],
        )
        self.assertIn("No known restrictions on publication.", items[0]["description"])

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

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_discover_endpoint_queues_task_for_loc_source(self):
        source = ContentSource.objects.create(
            name="Library of Congress Free to Use - Cats Test",
            type=ContentSource.TYPE_IMAGE,
            feed_url="https://www.loc.gov/free-to-use/cats/?fo=json",
            policy=ContentSource.POLICY_CACHE_ALLOWED,
            license_name="Library of Congress Free to Use and Reuse",
        )
        client = APIClient()
        client.login(username="route_user", password="test-password-123")
        fake_items = [
            {
                "title": "Cat portrait",
                "description": "Discovered from a Library of Congress Free to Use and Reuse collection.",
                "original_url": "https://www.loc.gov/item/12345/",
                "media_url": (
                    "https://www.loc.gov/pictures/item/12345/"
                    "resource/cph.3g12345/preview.jpg"
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

    @override_settings(
        CELERY_TASK_ALWAYS_EAGER=True,
        TIME_ZONE="UTC",
        COMMUTE_PREP_LOOKAHEAD_HOURS=4,
        COMMUTE_PREP_SCAN_INTERVAL_MINUTES=15,
    )
    def test_queue_commute_preparation_enqueues_downloads_four_hours_before_commute(self):
        fixed_now = timezone.make_aware(datetime(2026, 6, 25, 8, 0, 0))
        cache_source = ContentSource.objects.create(
            name="Open Image Downloads",
            type=ContentSource.TYPE_IMAGE,
            feed_url="https://example.com/open-images.json",
            policy=ContentSource.POLICY_CACHE_ALLOWED,
        )
        ready_download = DownloadItem.objects.create(
            user=self.user,
            source=cache_source,
            title="Already Ready",
            original_url="https://example.com/images/ready",
            media_url="https://example.com/images/ready.jpg",
            status=DownloadItem.STATUS_READY,
        )
        queued_downloads = [
            DownloadItem.objects.create(
                user=self.user,
                source=cache_source,
                title=f"Queued Image {index}",
                original_url=f"https://example.com/images/queued-{index}",
                media_url=f"https://example.com/images/queued-{index}.jpg",
            )
            for index in range(2)
        ]
        DownloadItem.objects.create(
            user=self.other_user,
            source=cache_source,
            title="Other User Queued Image",
            original_url="https://example.com/images/other-user",
            media_url="https://example.com/images/other-user.jpg",
        )
        CommuteWindow.objects.create(
            user=self.user,
            label="Lunch Commute",
            start_time=time(12, 5),
            end_time=time(12, 45),
            days_of_week=["thu"],
        )

        with patch("core.tasks.timezone.now", return_value=fixed_now), patch(
            "core.tasks.prepare_download_item.delay",
        ) as prepare_delay:
            result = queue_commute_preparation.apply().get(timeout=5)

        self.assertEqual(result["matched_windows_count"], 1)
        self.assertEqual(result["queued_count"], 2)
        self.assertEqual(
            set(result["queued_download_ids"]),
            {download.id for download in queued_downloads},
        )
        self.assertEqual(prepare_delay.call_count, 2)
        self.assertNotIn(ready_download.id, result["queued_download_ids"])

    @override_settings(
        CELERY_TASK_ALWAYS_EAGER=True,
        TIME_ZONE="UTC",
        COMMUTE_PREP_LOOKAHEAD_HOURS=4,
        COMMUTE_PREP_SCAN_INTERVAL_MINUTES=15,
    )
    def test_queue_commute_preparation_ignores_commutes_outside_scan_window(self):
        fixed_now = timezone.make_aware(datetime(2026, 6, 25, 8, 0, 0))
        cache_source = ContentSource.objects.create(
            name="Open Image Downloads",
            type=ContentSource.TYPE_IMAGE,
            feed_url="https://example.com/open-images.json",
            policy=ContentSource.POLICY_CACHE_ALLOWED,
        )
        DownloadItem.objects.create(
            user=self.user,
            source=cache_source,
            title="Queued Image",
            original_url="https://example.com/images/queued",
            media_url="https://example.com/images/queued.jpg",
        )
        CommuteWindow.objects.create(
            user=self.user,
            label="Soon Commute",
            start_time=time(11, 55),
            end_time=time(12, 30),
            days_of_week=["thu"],
        )

        with patch("core.tasks.timezone.now", return_value=fixed_now), patch(
            "core.tasks.prepare_download_item.delay",
        ) as prepare_delay:
            result = queue_commute_preparation.apply().get(timeout=5)

        self.assertEqual(result["matched_windows_count"], 0)
        self.assertEqual(result["queued_count"], 0)
        prepare_delay.assert_not_called()

    @override_settings(
        CELERY_TASK_ALWAYS_EAGER=True,
        TIME_ZONE="UTC",
        COMMUTE_PREP_LOOKAHEAD_HOURS=4,
        COMMUTE_PREP_SCAN_INTERVAL_MINUTES=15,
    )
    def test_queue_commute_preparation_respects_commute_days(self):
        fixed_now = timezone.make_aware(datetime(2026, 6, 25, 8, 0, 0))
        cache_source = ContentSource.objects.create(
            name="Open Image Downloads",
            type=ContentSource.TYPE_IMAGE,
            feed_url="https://example.com/open-images.json",
            policy=ContentSource.POLICY_CACHE_ALLOWED,
        )
        DownloadItem.objects.create(
            user=self.user,
            source=cache_source,
            title="Queued Image",
            original_url="https://example.com/images/queued",
            media_url="https://example.com/images/queued.jpg",
        )
        CommuteWindow.objects.create(
            user=self.user,
            label="Friday Commute",
            start_time=time(12, 5),
            end_time=time(12, 45),
            days_of_week=["fri"],
        )

        with patch("core.tasks.timezone.now", return_value=fixed_now), patch(
            "core.tasks.prepare_download_item.delay",
        ) as prepare_delay:
            result = queue_commute_preparation.apply().get(timeout=5)

        self.assertEqual(result["matched_windows_count"], 0)
        self.assertEqual(result["queued_count"], 0)
        prepare_delay.assert_not_called()

    @override_settings(OFFLINE_FILE_STORAGE=DownloadItem.STORAGE_LOCAL)
    def test_prepare_download_task_creates_offline_file(self):
        cache_source = ContentSource.objects.create(
            name="Open Image Downloads",
            type=ContentSource.TYPE_IMAGE,
            feed_url="https://example.com/open-images.json",
            policy=ContentSource.POLICY_CACHE_ALLOWED,
        )
        download_item = DownloadItem.objects.create(
            user=self.user,
            source=cache_source,
            title="Offline Cat Image",
            description="A downloadable image for the train.",
            original_url="https://example.com/images/offline-cat",
            media_url="https://example.com/images/offline-cat.jpg",
        )
        media_body = b"real offline image bytes"

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(
                CELERY_TASK_ALWAYS_EAGER=True,
                MEDIA_ROOT=Path(media_root),
            ):
                with patch(
                    "core.tasks.urlopen",
                    return_value=FakeDownloadResponse(
                        media_body,
                        {
                            "Content-Type": "image/jpeg",
                            "Content-Length": str(len(media_body)),
                        },
                    ),
                ):
                    result = prepare_download_item.delay(download_item.id)

                self.assertEqual(result.get(timeout=5)["status"], DownloadItem.STATUS_READY)

                download_item.refresh_from_db()
                prepared_path = Path(settings.MEDIA_ROOT) / download_item.local_file_path

                self.assertTrue(prepared_path.exists())
                self.assertEqual(prepared_path.read_bytes(), media_body)

        self.assertEqual(download_item.status, DownloadItem.STATUS_READY)
        self.assertEqual(download_item.file_size_bytes, len(media_body))
        self.assertEqual(download_item.error_message, "")
        self.assertEqual(download_item.storage_backend, DownloadItem.STORAGE_LOCAL)
        self.assertEqual(download_item.storage_key, "")
        self.assertTrue(download_item.local_file_path.endswith(".jpg"))

    def test_prepare_download_task_uploads_offline_file_to_s3(self):
        cache_source = ContentSource.objects.create(
            name="Open Image Downloads",
            type=ContentSource.TYPE_IMAGE,
            feed_url="https://example.com/open-images.json",
            policy=ContentSource.POLICY_CACHE_ALLOWED,
        )
        download_item = DownloadItem.objects.create(
            user=self.user,
            source=cache_source,
            title="Offline S3 Image",
            description="A downloadable image for S3.",
            original_url="https://example.com/images/offline-s3",
            media_url="https://example.com/images/offline-s3.png",
        )
        media_body = b"real s3 image bytes"
        fake_s3 = FakeS3Client()

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(
                CELERY_TASK_ALWAYS_EAGER=True,
                MEDIA_ROOT=Path(media_root),
                OFFLINE_FILE_STORAGE=DownloadItem.STORAGE_S3,
                AWS_STORAGE_BUCKET_NAME="readyfeed-test-bucket",
                AWS_S3_REGION_NAME="ap-south-1",
            ):
                with patch(
                    "core.tasks.urlopen",
                    return_value=FakeDownloadResponse(
                        media_body,
                        {
                            "Content-Type": "image/png",
                            "Content-Length": str(len(media_body)),
                        },
                    ),
                ), patch("core.offline_storage._s3_client", return_value=fake_s3):
                    result = prepare_download_item.delay(download_item.id)

                self.assertEqual(result.get(timeout=5)["status"], DownloadItem.STATUS_READY)

        download_item.refresh_from_db()
        self.assertEqual(download_item.status, DownloadItem.STATUS_READY)
        self.assertEqual(download_item.storage_backend, DownloadItem.STORAGE_S3)
        self.assertEqual(download_item.local_file_path, "")
        self.assertTrue(download_item.storage_key.startswith("offline_items/"))
        self.assertTrue(download_item.storage_key.endswith(".png"))
        self.assertEqual(download_item.file_size_bytes, len(media_body))
        self.assertEqual(fake_s3.uploads[0]["bucket"], "readyfeed-test-bucket")
        self.assertEqual(fake_s3.uploads[0]["key"], download_item.storage_key)
        self.assertEqual(fake_s3.uploads[0]["body"], media_body)
        self.assertEqual(
            fake_s3.uploads[0]["extra_args"]["ContentType"],
            "image/png",
        )

    def test_download_serializer_returns_s3_presigned_url(self):
        cache_source = ContentSource.objects.create(
            name="Open Image Downloads",
            type=ContentSource.TYPE_IMAGE,
            feed_url="https://example.com/open-images.json",
            policy=ContentSource.POLICY_CACHE_ALLOWED,
        )
        DownloadItem.objects.create(
            user=self.user,
            source=cache_source,
            title="Ready S3 Item",
            original_url="https://example.com/images/ready-s3",
            media_url="https://example.com/images/ready-s3.jpg",
            status=DownloadItem.STATUS_READY,
            storage_backend=DownloadItem.STORAGE_S3,
            storage_key="offline_items/1/download-1-ready-s3.jpg",
            file_size_bytes=128,
        )
        fake_s3 = FakeS3Client()
        client = APIClient()
        client.login(username="route_user", password="test-password-123")

        with override_settings(
            AWS_STORAGE_BUCKET_NAME="readyfeed-test-bucket",
            AWS_S3_PRESIGNED_EXPIRES=600,
        ):
            with patch("core.offline_storage._s3_client", return_value=fake_s3):
                response = client.get("/api/downloads/")

        self.assertEqual(response.status_code, 200)
        download = response.json()[0]
        self.assertEqual(download["storage_backend"], DownloadItem.STORAGE_S3)
        self.assertEqual(download["storage_key"], "offline_items/1/download-1-ready-s3.jpg")
        self.assertEqual(
            download["offline_file_url"],
            "https://signed.example.test/offline_items/1/download-1-ready-s3.jpg?expires=600",
        )
        self.assertEqual(download["local_file_url"], download["offline_file_url"])
        self.assertEqual(
            fake_s3.presigned_calls[0]["params"],
            {
                "Bucket": "readyfeed-test-bucket",
                "Key": "offline_items/1/download-1-ready-s3.jpg",
            },
        )

    @override_settings(OFFLINE_FILE_STORAGE=DownloadItem.STORAGE_LOCAL)
    def test_prepare_download_task_fails_when_storage_limit_is_exceeded(self):
        self.user.preference.max_storage_mb = 0
        self.user.preference.save(update_fields=["max_storage_mb", "updated_at"])
        cache_source = ContentSource.objects.create(
            name="Open Image Downloads",
            type=ContentSource.TYPE_IMAGE,
            feed_url="https://example.com/open-images.json",
            policy=ContentSource.POLICY_CACHE_ALLOWED,
        )
        download_item = DownloadItem.objects.create(
            user=self.user,
            source=cache_source,
            title="Large Offline Image",
            original_url="https://example.com/images/large-image",
            media_url="https://example.com/images/large-image.jpg",
        )
        media_body = b"too large for zero storage"

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(
                CELERY_TASK_ALWAYS_EAGER=True,
                MEDIA_ROOT=Path(media_root),
            ):
                with patch(
                    "core.tasks.urlopen",
                    return_value=FakeDownloadResponse(
                        media_body,
                        {
                            "Content-Type": "image/jpeg",
                            "Content-Length": str(len(media_body)),
                        },
                    ),
                ):
                    result = prepare_download_item.delay(download_item.id)
                    with self.assertRaises(OfflineDownloadError):
                        result.get(timeout=5)

        download_item.refresh_from_db()
        self.assertEqual(download_item.status, DownloadItem.STATUS_FAILED)
        self.assertIn("storage preference", download_item.error_message)
        self.assertEqual(download_item.local_file_path, "")
        self.assertIsNone(download_item.file_size_bytes)

    @override_settings(OFFLINE_FILE_STORAGE=DownloadItem.STORAGE_LOCAL)
    def test_prepare_download_endpoint_queues_user_item(self):
        cache_source = ContentSource.objects.create(
            name="Open Image Downloads",
            type=ContentSource.TYPE_IMAGE,
            feed_url="https://example.com/open-images.json",
            policy=ContentSource.POLICY_CACHE_ALLOWED,
        )
        download_item = DownloadItem.objects.create(
            user=self.user,
            source=cache_source,
            title="Endpoint Prepared Item",
            original_url="https://example.com/images/endpoint-prepared",
            media_url="https://example.com/images/endpoint-prepared.png",
        )
        media_body = b"endpoint image bytes"

        client = APIClient()
        client.login(username="route_user", password="test-password-123")

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(
                CELERY_TASK_ALWAYS_EAGER=True,
                MEDIA_ROOT=Path(media_root),
            ):
                with patch(
                    "core.tasks.urlopen",
                    return_value=FakeDownloadResponse(
                        media_body,
                        {
                            "Content-Type": "image/png",
                            "Content-Length": str(len(media_body)),
                        },
                    ),
                ):
                    response = client.post(f"/api/downloads/{download_item.id}/prepare/")

                self.assertEqual(response.status_code, 202)
                self.assertEqual(response.json()["detail"], "Offline preparation task queued.")
                self.assertTrue(response.json()["download"]["local_file_url"])

        download_item.refresh_from_db()
        self.assertEqual(download_item.status, DownloadItem.STATUS_READY)
        self.assertEqual(download_item.file_size_bytes, len(media_body))
        self.assertEqual(download_item.storage_backend, DownloadItem.STORAGE_LOCAL)
        self.assertEqual(download_item.storage_key, "")

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

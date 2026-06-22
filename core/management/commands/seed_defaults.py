from django.core.management.base import BaseCommand

from core.models import ContentSource


DEFAULT_SOURCES = [
    {
        "name": "Morning Tech Podcast",
        "type": ContentSource.TYPE_PODCAST,
        "feed_url": "https://example.com/feeds/morning-tech.xml",
        "policy": ContentSource.POLICY_METADATA_ONLY,
    },
    {
        "name": "Python Bytes",
        "type": ContentSource.TYPE_PODCAST,
        "feed_url": "https://pythonbytes.fm/episodes/rss",
        "policy": ContentSource.POLICY_METADATA_ONLY,
    },
    {
        "name": "Daily World News",
        "type": ContentSource.TYPE_NEWS,
        "feed_url": "https://example.com/feeds/world-news.xml",
        "policy": ContentSource.POLICY_METADATA_ONLY,
    },
    {
        "name": "Hacker News",
        "type": ContentSource.TYPE_NEWS,
        "feed_url": "https://news.ycombinator.com/rss",
        "policy": ContentSource.POLICY_METADATA_ONLY,
    },
    {
        "name": "XKCD",
        "type": ContentSource.TYPE_MEME,
        "feed_url": "https://xkcd.com/rss.xml",
        "policy": ContentSource.POLICY_CACHE_ALLOWED,
    },
    {
        "name": "Daily Meme Digest",
        "type": ContentSource.TYPE_MEME,
        "feed_url": "https://example.com/feeds/memes.xml",
        "policy": ContentSource.POLICY_CACHE_ALLOWED,
    },
]

LEGACY_SAMPLE_SOURCE_NAMES = [
    "Django Weblog",
    "TED Talks",
]


class Command(BaseCommand):
    help = "Create default content sources for local development."

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0

        for source_data in DEFAULT_SOURCES:
            _, created = ContentSource.objects.update_or_create(
                name=source_data["name"],
                defaults={**source_data, "is_active": True},
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        deactivated_count = ContentSource.objects.filter(
            name__in=LEGACY_SAMPLE_SOURCE_NAMES,
        ).update(is_active=False)

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded content sources: "
                f"{created_count} created, {updated_count} updated, "
                f"{deactivated_count} legacy samples deactivated."
            )
        )

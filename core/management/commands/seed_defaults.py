from django.core.management.base import BaseCommand

from core.models import ContentSource


NASA_LICENSE = {
    "license_name": "NASA Media Usage Guidelines",
    "license_url": "https://www.nasa.gov/nasa-brand-center/images-and-media/",
    "attribution_required": True,
    "usage_notes": (
        "Cache NASA-created media only; do not imply NASA endorsement; avoid NASA "
        "logos, identifiers, or employee likenesses in promotional use."
    ),
}

CC0_LICENSE = {
    "license_name": "Creative Commons Zero (CC0)",
    "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
    "attribution_required": False,
    "usage_notes": "Cache only records/images explicitly marked public domain or CC0.",
}

MET_LICENSE = {
    **CC0_LICENSE,
    "license_url": "https://www.metmuseum.org/hubs/open-access",
    "usage_notes": (
        "Search returns object IDs; cache only object details where isPublicDomain "
        "is true and primaryImage is present."
    ),
}

ARTIC_LICENSE = {
    **CC0_LICENSE,
    "license_url": "https://api.artic.edu/docs/",
    "usage_notes": (
        "Endpoint filters public-domain artworks; download IIIF images one at a "
        "time and throttle requests."
    ),
}

LOC_LICENSE = {
    "license_name": "Library of Congress Free to Use and Reuse",
    "license_url": "https://www.loc.gov/free-to-use/",
    "attribution_required": False,
    "usage_notes": (
        "These curated sets are rights-free; keep any item-level rights text returned "
        "by the Library of Congress API."
    ),
}

GUTENBERG_LICENSE = {
    "license_name": "Project Gutenberg License / Public domain in the USA",
    "license_url": "https://www.gutenberg.org/policy/license.html",
    "attribution_required": True,
    "usage_notes": (
        "Gutendex exposes Project Gutenberg metadata; cache books with copyright=false "
        "and preserve Project Gutenberg license/trademark requirements when redistributing."
    ),
}

WIKIMEDIA_COMMONS_LICENSE = {
    "license_name": "Wikimedia Commons free licenses / public domain",
    "license_url": "https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia",
    "attribution_required": True,
    "usage_notes": (
        "Cache only files hosted on Wikimedia Commons. Store each file's author, "
        "source URL, and exact license from imageinfo/extmetadata before reuse."
    ),
}


def metadata_source(name, source_type, feed_url, usage_notes=""):
    return {
        "name": name,
        "type": source_type,
        "feed_url": feed_url,
        "policy": ContentSource.POLICY_METADATA_ONLY,
        "license_name": "",
        "license_url": "",
        "attribution_required": False,
        "usage_notes": usage_notes,
    }


def cache_source(name, source_type, feed_url, license_data):
    return {
        "name": name,
        "type": source_type,
        "feed_url": feed_url,
        "policy": ContentSource.POLICY_CACHE_ALLOWED,
        **license_data,
    }


NASA_TOPICS = [
    ("Mars", "mars"),
    ("Earth", "earth"),
    ("Moon", "moon"),
    ("Apollo", "apollo"),
    ("Artemis", "artemis"),
    ("Hubble", "hubble"),
    ("James Webb", "james%20webb"),
    ("Spacewalk", "spacewalk"),
    ("Jupiter", "jupiter"),
    ("Saturn", "saturn"),
]

MET_TOPICS = [
    ("Flowers", "flowers"),
    ("Egypt", "egypt"),
    ("Cats", "cats"),
    ("Birds", "birds"),
    ("Landscape", "landscape"),
    ("Portraits", "portraits"),
    ("Sculpture", "sculpture"),
    ("Japan", "japan"),
    ("Music", "music"),
    ("Textiles", "textiles"),
]

ARTIC_TOPICS = [
    ("Cats", "cats"),
    ("Landscapes", "landscape"),
    ("Architecture", "architecture"),
    ("Flowers", "flowers"),
    ("Photography", "photography"),
    ("Birds", "birds"),
    ("Posters", "posters"),
    ("Sculpture", "sculpture"),
    ("Textiles", "textiles"),
    ("Japan", "japan"),
]

LOC_SETS = [
    ("Cats", "cats"),
    ("Birds", "birds"),
    ("Classic Children's Books", "classic-childrens-books"),
    ("Public Domain Films", "public-domain-films-from-the-national-film-registry"),
    ("Travel Posters", "travel-posters"),
]

GUTENDEX_TOPICS = [
    ("Science", "science"),
    ("Children", "children"),
    ("Adventure", "adventure"),
    ("History", "history"),
    ("Philosophy", "philosophy"),
]

WIKIMEDIA_MEME_TOPICS = [
    ("Internet Memes", "internet%20meme"),
    ("Reaction Images", "reaction%20image"),
    ("Image Macros", "image%20macro"),
    ("Lolcats", "lolcat"),
    ("Doge", "doge%20meme"),
    ("Rage Comics", "rage%20comic"),
    ("Funny Cats", "funny%20cat"),
    ("Funny Dogs", "funny%20dog"),
    ("Humor Signs", "humor%20sign"),
    ("Cartoons", "cartoon%20humor"),
]


DEFAULT_SOURCES = [
    metadata_source(
        "Morning Tech Podcast",
        ContentSource.TYPE_PODCAST,
        "https://example.com/feeds/morning-tech.xml",
        "Placeholder source; keep metadata-only until a real feed license is reviewed.",
    ),
    metadata_source(
        "Python Bytes",
        ContentSource.TYPE_PODCAST,
        "https://pythonbytes.fm/episodes/rss",
        "Podcast RSS metadata only; do not cache episode audio without reviewing show terms.",
    ),
    metadata_source(
        "Daily World News",
        ContentSource.TYPE_NEWS,
        "https://example.com/feeds/world-news.xml",
        "Placeholder source; keep metadata-only.",
    ),
    metadata_source(
        "Hacker News",
        ContentSource.TYPE_NEWS,
        "https://news.ycombinator.com/rss",
        "Metadata/link feed only; linked article rights vary by publisher.",
    ),
    metadata_source(
        "XKCD",
        ContentSource.TYPE_MEME,
        "https://xkcd.com/rss.xml",
        "XKCD uses a non-commercial license, so keep it metadata-only by default.",
    ),
]

DEFAULT_SOURCES += [
    cache_source(
        f"NASA Images - {label}",
        ContentSource.TYPE_IMAGE,
        f"https://images-api.nasa.gov/search?q={query}&media_type=image",
        NASA_LICENSE,
    )
    for label, query in NASA_TOPICS
]

DEFAULT_SOURCES += [
    cache_source(
        f"The Met Open Access - {label}",
        ContentSource.TYPE_IMAGE,
        f"https://collectionapi.metmuseum.org/public/collection/v1/search?hasImages=true&q={query}",
        MET_LICENSE,
    )
    for label, query in MET_TOPICS
]

DEFAULT_SOURCES += [
    cache_source(
        f"Art Institute Chicago Public Domain - {label}",
        ContentSource.TYPE_IMAGE,
        "https://api.artic.edu/api/v1/artworks/search?"
        f"q={query}&query%5Bterm%5D%5Bis_public_domain%5D=true"
        "&fields=id,title,image_id,artist_display,is_public_domain",
        ARTIC_LICENSE,
    )
    for label, query in ARTIC_TOPICS
]

DEFAULT_SOURCES += [
    cache_source(
        f"Library of Congress Free to Use - {label}",
        ContentSource.TYPE_IMAGE,
        f"https://www.loc.gov/free-to-use/{slug}/?fo=json",
        LOC_LICENSE,
    )
    for label, slug in LOC_SETS
]

DEFAULT_SOURCES += [
    cache_source(
        f"Gutendex Public Domain Books - {label}",
        ContentSource.TYPE_BOOK,
        f"https://gutendex.com/books/?copyright=false&languages=en&topic={topic}",
        GUTENBERG_LICENSE,
    )
    for label, topic in GUTENDEX_TOPICS
]

DEFAULT_SOURCES += [
    cache_source(
        f"Wikimedia Commons Memes - {label}",
        ContentSource.TYPE_MEME,
        "https://commons.wikimedia.org/w/api.php?action=query&format=json"
        "&generator=search&gsrnamespace=6"
        f"&gsrsearch={query}"
        "&prop=imageinfo&iiprop=url%7Cextmetadata&iiurlwidth=800",
        WIKIMEDIA_COMMONS_LICENSE,
    )
    for label, query in WIKIMEDIA_MEME_TOPICS
]

LEGACY_SAMPLE_SOURCE_NAMES = [
    "Daily Meme Digest",
    "Django Weblog",
    "TED Talks",
    "Cleveland Museum CC0 - Landscape",
    "Cleveland Museum CC0 - Portrait",
    "Cleveland Museum CC0 - Japanese Art",
    "Cleveland Museum CC0 - Textiles",
    "Cleveland Museum CC0 - Sculpture",
    "Cleveland Museum CC0 - Ceramics",
    "Cleveland Museum CC0 - Animals",
    "Cleveland Museum CC0 - Architecture",
    "Cleveland Museum CC0 - Mythology",
    "Cleveland Museum CC0 - Music",
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

        cache_allowed_count = ContentSource.objects.filter(
            policy=ContentSource.POLICY_CACHE_ALLOWED,
            is_active=True,
        ).count()

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded content sources: "
                f"{created_count} created, {updated_count} updated, "
                f"{deactivated_count} legacy samples deactivated, "
                f"{cache_allowed_count} active cache-allowed sources available."
            )
        )

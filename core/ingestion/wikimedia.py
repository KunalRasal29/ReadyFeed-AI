import json
import re
from html import unescape
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen


COMMONS_API_HOST = "commons.wikimedia.org"
COMMONS_API_PATH = "/w/api.php"
USER_AGENT = "READYFEED-AI/0.1 local-development"


class WikimediaIngestionError(Exception):
    pass


def is_wikimedia_commons_source(source):
    parsed = urlparse(source.feed_url)
    return parsed.netloc == COMMONS_API_HOST and parsed.path == COMMONS_API_PATH


def fetch_wikimedia_source_items(source, limit=10, timeout=8):
    if not is_wikimedia_commons_source(source):
        raise WikimediaIngestionError(
            "Discovery is currently available for Wikimedia Commons sources only."
        )

    data = _fetch_json(_with_query_overrides(source.feed_url, limit), timeout=timeout)
    pages = data.get("query", {}).get("pages", {})
    items = []

    for page in pages.values():
        item = _page_to_item(page, source)
        if item:
            items.append(item)

    items.sort(key=lambda item: item["title"].lower())
    return items[:limit]


def _with_query_overrides(url, limit):
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(
        {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrnamespace": "6",
            "gsrlimit": str(limit),
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|mime|size",
            "iiurlwidth": "800",
        }
    )
    return urlunparse(parsed._replace(query=urlencode(query)))


def _fetch_json(url, timeout):
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return json.loads(response.read().decode(charset))
    except Exception as exc:
        raise WikimediaIngestionError(f"Could not fetch Wikimedia Commons data: {exc}") from exc


def _page_to_item(page, source):
    image_info = (page.get("imageinfo") or [{}])[0]
    media_url = image_info.get("thumburl") or image_info.get("url", "")
    original_url = image_info.get("descriptionurl") or _commons_file_url(page.get("title", ""))
    metadata = image_info.get("extmetadata") or {}
    license_name = _metadata_value(metadata, "LicenseShortName")
    usage_terms = _metadata_value(metadata, "UsageTerms")
    license_url = _metadata_value(metadata, "LicenseUrl")
    author = _metadata_value(metadata, "Artist") or image_info.get("user", "")
    credit = _metadata_value(metadata, "Credit")
    title = _clean_title(page.get("title", "Untitled Wikimedia file"))
    mime_type = image_info.get("mime", "")

    if not media_url or not _is_cache_compatible_license(license_name, usage_terms):
        return None

    return {
        "title": title,
        "description": _description_for_item(
            source=source,
            author=author,
            license_name=license_name or usage_terms or source.license_name,
            license_url=license_url or source.license_url,
            original_url=original_url,
            credit=credit,
            mime_type=mime_type,
        ),
        "original_url": original_url,
        "media_url": media_url,
        "license_name": license_name or usage_terms or source.license_name,
        "license_url": license_url or source.license_url,
        "author": author,
        "mime_type": mime_type,
        "file_size_bytes": image_info.get("size"),
    }


def _metadata_value(metadata, key):
    value = metadata.get(key, {}).get("value", "")
    return _strip_html(value)


def _strip_html(value):
    text = re.sub(r"<[^>]*>", "", str(value or ""))
    return " ".join(unescape(text).split())


def _clean_title(title):
    cleaned = title.replace("File:", "", 1).replace("_", " ").strip()
    return cleaned[:255] or "Untitled Wikimedia file"


def _commons_file_url(title):
    filename = title.replace(" ", "_")
    return f"https://commons.wikimedia.org/wiki/{filename}"


def _is_cache_compatible_license(license_name, usage_terms):
    license_text = f"{license_name} {usage_terms}".lower()
    blocked_terms = ["noncommercial", "non-commercial", "no derivatives", "fair use"]
    allowed_terms = [
        "public domain",
        "cc0",
        "cc by",
        "cc-by",
        "creative commons",
        "gfdl",
        "gnu free documentation",
    ]

    if any(term in license_text for term in blocked_terms):
        return False
    return any(term in license_text for term in allowed_terms)


def _description_for_item(
    source,
    author,
    license_name,
    license_url,
    original_url,
    credit,
    mime_type,
):
    lines = [
        "Discovered from Wikimedia Commons.",
        f"Source: {source.name}",
        f"Author: {author or 'Unknown'}",
        f"License: {license_name or 'Unknown'}",
    ]

    if license_url:
        lines.append(f"License URL: {license_url}")
    if credit:
        lines.append(f"Credit: {credit}")
    if mime_type:
        lines.append(f"Media type: {mime_type}")

    lines.extend(
        [
            f"Original page: {original_url}",
            "Item-level license metadata was captured during discovery; verify attribution before reuse.",
        ]
    )
    return "\n".join(lines)

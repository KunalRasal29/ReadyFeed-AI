import json
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen


ARTIC_API_HOST = "api.artic.edu"
ARTIC_SEARCH_PATH = "/api/v1/artworks/search"
USER_AGENT = "READYFEED-AI/0.1 local-development"
AIC_USER_AGENT = "READYFEED-AI local-development"


class ArticIngestionError(Exception):
    pass


def is_artic_source(source):
    parsed = urlparse(source.feed_url)
    return parsed.netloc == ARTIC_API_HOST and parsed.path == ARTIC_SEARCH_PATH


def fetch_artic_source_items(source, limit=10, timeout=8):
    if not is_artic_source(source):
        raise ArticIngestionError(
            "Discovery is currently available for Art Institute Chicago search sources only."
        )

    data = _fetch_json(_with_query_overrides(source.feed_url, limit), timeout=timeout)
    results = data.get("data", [])
    iiif_url = data.get("config", {}).get("iiif_url") or "https://www.artic.edu/iiif/2"
    items = []

    for artwork in results:
        item = _artwork_to_item(artwork, source, iiif_url)
        if item:
            items.append(item)

    return items[:limit]


def _with_query_overrides(url, limit):
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(
        {
            "query[term][is_public_domain]": "true",
            "limit": str(limit),
            "fields": ",".join(
                [
                    "id",
                    "title",
                    "artist_display",
                    "date_display",
                    "medium_display",
                    "place_of_origin",
                    "image_id",
                    "is_public_domain",
                    "credit_line",
                    "classification_title",
                    "subject_titles",
                    "thumbnail",
                ]
            ),
        }
    )
    return urlunparse(parsed._replace(query=urlencode(query)))


def _fetch_json(url, timeout):
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "AIC-User-Agent": AIC_USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return json.loads(response.read().decode(charset))
    except Exception as exc:
        raise ArticIngestionError(
            f"Could not fetch Art Institute Chicago data: {exc}"
        ) from exc


def _artwork_to_item(artwork, source, iiif_url):
    if artwork.get("is_public_domain") is not True:
        return None

    image_id = artwork.get("image_id")
    artwork_id = artwork.get("id")
    if not image_id or not artwork_id:
        return None

    title = _clean_text(artwork.get("title", f"ArtIC artwork {artwork_id}"))[:255]
    original_url = f"https://www.artic.edu/artworks/{artwork_id}"
    media_url = f"{iiif_url.rstrip('/')}/{image_id}/full/843,/0/default.jpg"
    author = _clean_text(artwork.get("artist_display", "Unknown"))

    return {
        "title": title,
        "description": _description_for_item(
            source=source,
            artwork=artwork,
            author=author,
            original_url=original_url,
        ),
        "original_url": original_url,
        "media_url": media_url,
        "license_name": source.license_name,
        "license_url": source.license_url,
        "author": author,
        "mime_type": "image/jpeg",
    }


def _clean_text(value):
    return " ".join(str(value or "").split())


def _description_for_item(source, artwork, author, original_url):
    lines = [
        "Discovered from the Art Institute of Chicago API.",
        f"Source: {source.name}",
        f"ArtIC artwork ID: {artwork.get('id', 'Unknown')}",
        f"Artist: {author or 'Unknown'}",
        f"License policy: {source.license_name or 'Creative Commons Zero (CC0)'}",
    ]

    for label, key in [
        ("Date", "date_display"),
        ("Medium", "medium_display"),
        ("Origin", "place_of_origin"),
        ("Classification", "classification_title"),
        ("Credit line", "credit_line"),
    ]:
        value = _clean_text(artwork.get(key, ""))
        if value:
            lines.append(f"{label}: {value}")

    subjects = artwork.get("subject_titles") or []
    if subjects:
        lines.append(f"Subjects: {', '.join(subjects[:8])}")

    thumbnail = artwork.get("thumbnail") or {}
    if thumbnail.get("alt_text"):
        lines.extend(["", _clean_text(thumbnail["alt_text"])])

    lines.extend(
        [
            "",
            f"Original page: {original_url}",
            (
                "The Art Institute of Chicago API marked this artwork as public domain; "
                "download images one at a time and prefer the 843px IIIF size."
            ),
        ]
    )
    return "\n".join(lines)

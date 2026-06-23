import json
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen


MET_API_HOST = "collectionapi.metmuseum.org"
MET_SEARCH_PATH = "/public/collection/v1/search"
MET_OBJECT_PATH = "/public/collection/v1/objects"
USER_AGENT = "READYFEED-AI/0.1 local-development"


class MetIngestionError(Exception):
    pass


def is_met_source(source):
    parsed = urlparse(source.feed_url)
    return parsed.netloc == MET_API_HOST and parsed.path == MET_SEARCH_PATH


def fetch_met_source_items(source, limit=10, timeout=8):
    if not is_met_source(source):
        raise MetIngestionError(
            "Discovery is currently available for The Met Open Access search sources only."
        )

    data = _fetch_json(_with_query_overrides(source.feed_url), timeout=timeout)
    object_ids = data.get("objectIDs") or []
    items = []

    for object_id in object_ids[: limit * 5]:
        detail_url = f"https://{MET_API_HOST}{MET_OBJECT_PATH}/{object_id}"
        item = _object_to_item(_fetch_json(detail_url, timeout=timeout), source)
        if item:
            items.append(item)
        if len(items) >= limit:
            break

    return items


def _with_query_overrides(url):
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["hasImages"] = "true"
    return urlunparse(parsed._replace(query=urlencode(query)))


def _fetch_json(url, timeout):
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return json.loads(response.read().decode(charset))
    except Exception as exc:
        raise MetIngestionError(f"Could not fetch The Met data: {exc}") from exc


def _object_to_item(obj, source):
    if not obj.get("isPublicDomain"):
        return None

    media_url = obj.get("primaryImageSmall") or obj.get("primaryImage")
    object_id = obj.get("objectID")
    if not media_url or not object_id:
        return None

    title = _clean_text(obj.get("title", f"The Met object {object_id}"))[:255]
    original_url = obj.get("objectURL") or (
        f"https://www.metmuseum.org/art/collection/search/{object_id}"
    )
    author = _clean_text(
        obj.get("artistDisplayName")
        or obj.get("culture")
        or obj.get("department")
        or "The Metropolitan Museum of Art"
    )

    return {
        "title": title,
        "description": _description_for_item(
            source=source,
            obj=obj,
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


def _description_for_item(source, obj, author, original_url):
    lines = [
        "Discovered from The Met Open Access Collection API.",
        f"Source: {source.name}",
        f"The Met object ID: {obj.get('objectID', 'Unknown')}",
        f"Artist/culture: {author or 'Unknown'}",
        f"License policy: {source.license_name or 'Creative Commons Zero (CC0)'}",
    ]

    for label, key in [
        ("Department", "department"),
        ("Object type", "objectName"),
        ("Date", "objectDate"),
        ("Medium", "medium"),
        ("Dimensions", "dimensions"),
        ("Credit line", "creditLine"),
    ]:
        value = _clean_text(obj.get(key, ""))
        if value:
            lines.append(f"{label}: {value}")

    tags = [tag.get("term", "") for tag in obj.get("tags") or [] if tag.get("term")]
    if tags:
        lines.append(f"Tags: {', '.join(tags[:8])}")

    lines.extend(
        [
            "",
            f"Original page: {original_url}",
            (
                "The Met object metadata marked this work as public domain and "
                "provided an Open Access image URL."
            ),
        ]
    )
    return "\n".join(lines)

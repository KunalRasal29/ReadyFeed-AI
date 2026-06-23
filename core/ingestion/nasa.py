import json
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen


NASA_API_HOST = "images-api.nasa.gov"
NASA_SEARCH_PATH = "/search"
USER_AGENT = "READYFEED-AI/0.1 local-development"


class NASAIngestionError(Exception):
    pass


def is_nasa_images_source(source):
    parsed = urlparse(source.feed_url)
    return parsed.netloc == NASA_API_HOST and parsed.path == NASA_SEARCH_PATH


def fetch_nasa_source_items(source, limit=10, timeout=8):
    if not is_nasa_images_source(source):
        raise NASAIngestionError(
            "Discovery is currently available for NASA Images search sources only."
        )

    data = _fetch_json(_with_query_overrides(source.feed_url, limit), timeout=timeout)
    results = data.get("collection", {}).get("items", [])
    items = []

    for result in results:
        item = _result_to_item(result, source)
        if item:
            items.append(item)

    return items[:limit]


def _with_query_overrides(url, limit):
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(
        {
            "media_type": "image",
            "page_size": str(limit),
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
        raise NASAIngestionError(f"Could not fetch NASA Images data: {exc}") from exc


def _result_to_item(result, source):
    metadata = (result.get("data") or [{}])[0]
    media_type = metadata.get("media_type", "")
    nasa_id = metadata.get("nasa_id", "")
    media_url = _preview_image_url(result)

    if media_type != "image" or not nasa_id or not media_url:
        return None

    title = _clean_text(metadata.get("title", "Untitled NASA image"))[:255]
    original_url = f"https://images.nasa.gov/details/{quote(nasa_id)}"
    author = _clean_text(
        metadata.get("photographer")
        or metadata.get("secondary_creator")
        or metadata.get("center")
        or "NASA"
    )

    return {
        "title": title,
        "description": _description_for_item(
            source=source,
            metadata=metadata,
            author=author,
            original_url=original_url,
        ),
        "original_url": original_url,
        "media_url": media_url,
        "license_name": source.license_name,
        "license_url": source.license_url,
        "author": author,
        "mime_type": "image",
    }


def _preview_image_url(result):
    for link in result.get("links") or []:
        if link.get("render") == "image" and link.get("href"):
            return link["href"]
    return ""


def _clean_text(value):
    return " ".join(str(value or "").split())


def _description_for_item(source, metadata, author, original_url):
    lines = [
        "Discovered from NASA Images and Video Library.",
        f"Source: {source.name}",
        f"NASA ID: {metadata.get('nasa_id', 'Unknown')}",
        f"Author/center: {author or 'NASA'}",
        f"License policy: {source.license_name or 'NASA Media Usage Guidelines'}",
    ]

    if metadata.get("date_created"):
        lines.append(f"Date created: {metadata['date_created']}")
    if metadata.get("center"):
        lines.append(f"NASA center: {metadata['center']}")
    if metadata.get("keywords"):
        lines.append(f"Keywords: {', '.join(metadata['keywords'][:8])}")
    if metadata.get("description"):
        lines.extend(["", _clean_text(metadata["description"])])

    lines.extend(
        [
            "",
            f"Original page: {original_url}",
            (
                "Cache only NASA-created media and follow NASA media usage rules; "
                "do not imply NASA endorsement."
            ),
        ]
    )
    return "\n".join(lines)

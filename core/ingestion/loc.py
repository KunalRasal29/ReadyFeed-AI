import json
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen


LOC_HOST = "www.loc.gov"
FREE_TO_USE_PREFIX = "/free-to-use/"
USER_AGENT = "READYFEED-AI/0.1 local-development"


class LOCIngestionError(Exception):
    pass


def is_loc_source(source):
    parsed = urlparse(source.feed_url)
    return parsed.netloc == LOC_HOST and parsed.path.startswith(FREE_TO_USE_PREFIX)


def fetch_loc_source_items(source, limit=10, timeout=8):
    if not is_loc_source(source):
        raise LOCIngestionError(
            "Discovery is currently available for Library of Congress Free to Use sources only."
        )

    data = _fetch_json(_with_json_format(source.feed_url), timeout=timeout)
    candidates = _candidate_items(data)
    items = []

    for candidate in candidates:
        item = _candidate_to_item(candidate, source)
        if item:
            items.append(item)
        if len(items) >= limit:
            break

    return items


def _with_json_format(url):
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["fo"] = "json"
    return urlunparse(parsed._replace(query=urlencode(query)))


def _fetch_json(url, timeout):
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return json.loads(response.read().decode(charset))
    except Exception as exc:
        raise LOCIngestionError(f"Could not fetch Library of Congress data: {exc}") from exc


def _candidate_items(data):
    for key_path in [
        ("results",),
        ("content", "results"),
        ("content", "items"),
        ("content", "item", "resources"),
        ("item", "resources"),
    ]:
        value = _get_nested(data, key_path)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    return _collect_candidate_dicts(data)


def _get_nested(value, key_path):
    current = value
    for key in key_path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _collect_candidate_dicts(value):
    candidates = []
    if isinstance(value, dict):
        if _has_required_item_shape(value):
            candidates.append(value)
        for child in value.values():
            candidates.extend(_collect_candidate_dicts(child))
    elif isinstance(value, list):
        for child in value:
            candidates.extend(_collect_candidate_dicts(child))
    return candidates


def _has_required_item_shape(value):
    return bool(
        value.get("title")
        and _first_url(value.get("image_url") or value.get("image") or value.get("images"))
        and _item_url(value)
    )


def _candidate_to_item(candidate, source):
    title = _clean_text(candidate.get("title") or candidate.get("name"))[:255]
    media_url = _first_url(
        candidate.get("image_url")
        or candidate.get("image")
        or candidate.get("images")
        or candidate.get("thumbnail")
    )
    original_url = _item_url(candidate)

    if not title or not media_url or not original_url:
        return None

    return {
        "title": title,
        "description": _description_for_item(
            source=source,
            candidate=candidate,
            original_url=original_url,
        ),
        "original_url": original_url,
        "media_url": media_url,
        "license_name": source.license_name,
        "license_url": source.license_url,
        "author": _creator(candidate),
        "mime_type": "image",
    }


def _first_url(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        for item in reversed(value):
            url = _first_url(item)
            if url:
                return url
    if isinstance(value, dict):
        for key in ["url", "href", "src", "full", "large", "medium", "small"]:
            url = _first_url(value.get(key))
            if url:
                return url
    return ""


def _item_url(candidate):
    for key in ["url", "link", "href", "id"]:
        value = candidate.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value

    item = candidate.get("item")
    if isinstance(item, dict):
        return _item_url(item)

    return ""


def _creator(candidate):
    for key in ["creator", "contributor", "contributors", "author"]:
        value = candidate.get(key)
        if isinstance(value, str):
            return _clean_text(value)
        if isinstance(value, list):
            names = [_clean_text(item) for item in value if _clean_text(item)]
            if names:
                return ", ".join(names[:3])
    return "Library of Congress"


def _clean_text(value):
    if isinstance(value, list):
        return " ".join(_clean_text(item) for item in value if _clean_text(item))
    if isinstance(value, dict):
        return _clean_text(value.get("title") or value.get("name") or value.get("label"))
    return " ".join(str(value or "").split())


def _description_for_item(source, candidate, original_url):
    lines = [
        "Discovered from a Library of Congress Free to Use and Reuse collection.",
        f"Source: {source.name}",
        f"Creator: {_creator(candidate)}",
        f"License policy: {source.license_name or 'Library of Congress Free to Use and Reuse'}",
    ]

    for label, key in [
        ("Date", "date"),
        ("Description", "description"),
        ("Rights", "rights"),
        ("Rights advisory", "rights_advisory"),
        ("Subjects", "subject"),
        ("Location", "location"),
        ("Medium", "medium"),
    ]:
        value = _clean_text(candidate.get(key))
        if value:
            lines.append(f"{label}: {value}")

    lines.extend(
        [
            "",
            f"Original page: {original_url}",
            (
                "This source is from a Library of Congress Free to Use set; "
                "preserve any item-level rights text returned by the LOC API."
            ),
        ]
    )
    return "\n".join(lines)

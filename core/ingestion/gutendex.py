import json
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen


GUTENDEX_API_HOST = "gutendex.com"
GUTENDEX_BOOKS_PATH = "/books/"
USER_AGENT = "READYFEED-AI/0.1 local-development"


class GutendexIngestionError(Exception):
    pass


def is_gutendex_source(source):
    parsed = urlparse(source.feed_url)
    return parsed.netloc == GUTENDEX_API_HOST and parsed.path == GUTENDEX_BOOKS_PATH


def fetch_gutendex_source_items(source, limit=10, timeout=8):
    if not is_gutendex_source(source):
        raise GutendexIngestionError(
            "Discovery is currently available for Gutendex / Project Gutenberg sources only."
        )

    data = _fetch_json(_with_query_overrides(source.feed_url), timeout=timeout)
    books = data.get("results", [])
    items = []

    for book in books:
        item = _book_to_item(book, source)
        if item:
            items.append(item)

    return items[:limit]


def _with_query_overrides(url):
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["copyright"] = "false"
    return urlunparse(parsed._replace(query=urlencode(query)))


def _fetch_json(url, timeout):
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return json.loads(response.read().decode(charset))
    except Exception as exc:
        raise GutendexIngestionError(f"Could not fetch Gutendex data: {exc}") from exc


def _book_to_item(book, source):
    if book.get("copyright") is not False:
        return None

    media_url, mime_type = _preferred_format(book.get("formats") or {})
    book_id = book.get("id")
    title = _clean_text(book.get("title", "Untitled Project Gutenberg book"))[:255]

    if not book_id or not media_url:
        return None

    original_url = f"https://www.gutenberg.org/ebooks/{book_id}"
    authors = _person_names(book.get("authors") or [])

    return {
        "title": title,
        "description": _description_for_item(
            source=source,
            book=book,
            authors=authors,
            original_url=original_url,
            mime_type=mime_type,
        ),
        "original_url": original_url,
        "media_url": media_url,
        "license_name": source.license_name,
        "license_url": source.license_url,
        "author": ", ".join(authors) or "Unknown",
        "mime_type": mime_type,
    }


def _preferred_format(formats):
    preferred_mime_prefixes = [
        "text/html",
        "text/plain",
        "application/epub+zip",
    ]

    for prefix in preferred_mime_prefixes:
        for mime_type, url in formats.items():
            if mime_type.startswith(prefix) and _is_downloadable_url(url):
                return url, mime_type

    return "", ""


def _is_downloadable_url(url):
    return bool(url) and not str(url).endswith(".zip")


def _person_names(people):
    names = []
    for person in people:
        name = _clean_text(person.get("name", ""))
        if name:
            names.append(name)
    return names


def _clean_text(value):
    return " ".join(str(value or "").split())


def _description_for_item(source, book, authors, original_url, mime_type):
    lines = [
        "Discovered from Gutendex / Project Gutenberg.",
        f"Source: {source.name}",
        f"Project Gutenberg ID: {book.get('id', 'Unknown')}",
        f"Author: {', '.join(authors) or 'Unknown'}",
        f"License policy: {source.license_name or 'Project Gutenberg License / Public domain in the USA'}",
        f"Download format: {mime_type or 'Unknown'}",
    ]

    if book.get("languages"):
        lines.append(f"Languages: {', '.join(book['languages'])}")
    if book.get("subjects"):
        lines.append(f"Subjects: {', '.join(book['subjects'][:8])}")
    if book.get("bookshelves"):
        lines.append(f"Bookshelves: {', '.join(book['bookshelves'][:6])}")
    if book.get("summaries"):
        lines.extend(["", _clean_text(book["summaries"][0])])

    lines.extend(
        [
            "",
            f"Original page: {original_url}",
            (
                "Gutendex returned copyright=false; preserve Project Gutenberg "
                "license and trademark requirements when redistributing."
            ),
        ]
    )
    return "\n".join(lines)

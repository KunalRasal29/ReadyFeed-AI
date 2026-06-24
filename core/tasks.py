import mimetypes
import re
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.ingestion.adapters import fetch_source_items
from core.models import ContentSource, DownloadItem


DOWNLOAD_CHUNK_SIZE = 1024 * 64
DOWNLOAD_TIMEOUT_SECONDS = 30
USER_AGENT = "READYFEED-AI/0.1 local-development"


class OfflineDownloadError(Exception):
    pass


@shared_task
def debug_task(message="hello from celery"):
    return message


@shared_task(bind=True)
def discover_source_items(self, source_id, user_id, limit=10):
    source = ContentSource.objects.get(pk=source_id)
    user = get_user_model().objects.get(pk=user_id)
    discovered_items = fetch_source_items(source, limit=limit)
    created_count = 0
    skipped_count = 0
    download_ids = []

    for item in discovered_items:
        download_item, created = DownloadItem.objects.get_or_create(
            user=user,
            source=source,
            original_url=item["original_url"],
            defaults={
                "title": item["title"][:255],
                "description": item["description"],
                "media_url": item["media_url"],
                "status": DownloadItem.STATUS_QUEUED,
                "available_from": timezone.now(),
            },
        )

        if created:
            created_count += 1
            download_ids.append(download_item.id)
        else:
            skipped_count += 1

    return {
        "task_id": self.request.id,
        "source_id": source_id,
        "user_id": user_id,
        "fetched_count": len(discovered_items),
        "created_count": created_count,
        "skipped_count": skipped_count,
        "download_ids": download_ids,
    }


@shared_task(bind=True)
def prepare_download_item(self, download_item_id):
    """Download the item's cache-allowed media file for offline use."""
    try:
        with transaction.atomic():
            download_item = (
                DownloadItem.objects.select_for_update()
                .select_related("source", "user")
                .get(pk=download_item_id)
            )

            if download_item.status == DownloadItem.STATUS_READY:
                return {
                    "download_item_id": download_item.id,
                    "status": download_item.status,
                    "message": "Download item is already ready.",
                }

            if download_item.status == DownloadItem.STATUS_DOWNLOADING:
                return {
                    "download_item_id": download_item.id,
                    "status": download_item.status,
                    "message": "Download item is already being prepared.",
                }

            download_item.status = DownloadItem.STATUS_DOWNLOADING
            download_item.error_message = ""
            download_item.save(update_fields=["status", "error_message", "updated_at"])

        stored_path, file_size_bytes = _download_media_file(download_item)

        DownloadItem.objects.filter(pk=download_item_id).update(
            status=DownloadItem.STATUS_READY,
            local_file_path=stored_path,
            file_size_bytes=file_size_bytes,
            error_message="",
            updated_at=timezone.now(),
        )

        return {
            "download_item_id": download_item_id,
            "status": DownloadItem.STATUS_READY,
            "local_file_path": stored_path,
            "file_size_bytes": file_size_bytes,
        }
    except DownloadItem.DoesNotExist:
        return {
            "download_item_id": download_item_id,
            "status": "missing",
            "message": "Download item does not exist.",
        }
    except Exception as exc:
        DownloadItem.objects.filter(pk=download_item_id).update(
            status=DownloadItem.STATUS_FAILED,
            error_message=str(exc),
            updated_at=timezone.now(),
        )
        raise


def _download_media_file(download_item):
    _validate_downloadable(download_item)

    request = Request(download_item.media_url, headers={"User-Agent": USER_AGENT})
    output_dir = Path(settings.MEDIA_ROOT) / "offline_items" / str(download_item.user_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    used_storage_bytes = _used_storage_bytes(
        user_id=download_item.user_id,
        exclude_download_item_id=download_item.id,
    )
    max_storage_bytes = _max_storage_bytes(download_item)
    output_path = None
    partial_path = None

    try:
        with urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            content_type = _response_content_type(response)
            content_length = _response_content_length(response)

            if content_length and used_storage_bytes + content_length > max_storage_bytes:
                raise OfflineDownloadError(
                    "Downloading this item would exceed your storage preference."
                )

            output_path = _output_path_for_download(
                output_dir=output_dir,
                download_item=download_item,
                content_type=content_type,
            )
            partial_path = output_path.with_name(f"{output_path.name}.part")
            bytes_written = 0

            with partial_path.open("wb") as output_file:
                while True:
                    chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                    if not chunk:
                        break

                    bytes_written += len(chunk)
                    if used_storage_bytes + bytes_written > max_storage_bytes:
                        raise OfflineDownloadError(
                            "Downloading this item would exceed your storage preference."
                        )
                    output_file.write(chunk)

            if bytes_written <= 0:
                raise OfflineDownloadError("The remote media file was empty.")

            partial_path.replace(output_path)

        return _stored_media_path(output_path), output_path.stat().st_size
    except OfflineDownloadError:
        _remove_partial_file(partial_path)
        raise
    except Exception as exc:
        _remove_partial_file(partial_path)
        raise OfflineDownloadError(f"Could not download media file: {exc}") from exc


def _validate_downloadable(download_item):
    if download_item.source.policy != ContentSource.POLICY_CACHE_ALLOWED:
        raise OfflineDownloadError("This source is metadata-only and cannot be cached.")

    if not download_item.media_url:
        raise OfflineDownloadError("This item does not have a downloadable media URL.")

    parsed_url = urlparse(download_item.media_url)
    if parsed_url.scheme not in {"http", "https"}:
        raise OfflineDownloadError("Only HTTP and HTTPS media URLs can be downloaded.")


def _used_storage_bytes(user_id, exclude_download_item_id):
    return (
        DownloadItem.objects.filter(
            user_id=user_id,
            status=DownloadItem.STATUS_READY,
        )
        .exclude(pk=exclude_download_item_id)
        .aggregate(total=Sum("file_size_bytes"))
        .get("total")
        or 0
    )


def _max_storage_bytes(download_item):
    preference = getattr(download_item.user, "preference", None)
    max_storage_mb = getattr(preference, "max_storage_mb", 500) or 0
    return max_storage_mb * 1024 * 1024


def _response_content_type(response):
    get_content_type = getattr(response.headers, "get_content_type", None)
    if callable(get_content_type):
        return get_content_type()
    return response.headers.get("Content-Type", "application/octet-stream").split(";")[0]


def _response_content_length(response):
    raw_value = response.headers.get("Content-Length")
    if not raw_value:
        return None

    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def _output_path_for_download(output_dir, download_item, content_type):
    slug = _slugify(download_item.title)
    extension = _extension_for_download(download_item.media_url, content_type)
    return output_dir / f"download-{download_item.id}-{slug}{extension}"


def _slugify(value):
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value or "").strip("-").lower()
    return slug[:60] or "item"


def _extension_for_download(media_url, content_type):
    guessed = ""
    if content_type and content_type != "application/octet-stream":
        guessed = mimetypes.guess_extension(content_type) or ""

    if guessed == ".jpe":
        return ".jpg"
    if guessed:
        return guessed

    suffix = Path(unquote(urlparse(media_url).path)).suffix.lower()
    if suffix and re.match(r"^\.[a-z0-9]{1,10}$", suffix):
        return suffix

    return ".bin"


def _stored_media_path(output_path):
    try:
        return str(output_path.relative_to(settings.MEDIA_ROOT))
    except ValueError:
        return str(output_path)


def _remove_partial_file(path):
    if not path:
        return

    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass

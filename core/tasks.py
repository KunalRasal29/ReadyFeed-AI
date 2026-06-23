from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.models import ContentSource, DownloadItem


@shared_task
def debug_task(message="hello from celery"):
    return message


@shared_task(bind=True)
def prepare_download_item(self, download_item_id):
    """Prepare a DownloadItem for offline use without fetching remote media yet."""
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

        output_dir = Path(settings.MEDIA_ROOT) / "offline_items" / str(download_item.user_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"download-{download_item.id}.txt"

        prepared_at = timezone.now()
        media_note = "No media URL was provided."
        if download_item.media_url and download_item.source.policy == ContentSource.POLICY_CACHE_ALLOWED:
            media_note = "Media URL recorded for a future cache/download pipeline."
        elif download_item.media_url:
            media_note = "Media URL recorded as metadata only because this source does not allow caching."

        content = "\n".join(
            [
                "READYFEED AI Offline Content Package",
                f"Prepared at: {prepared_at.isoformat()}",
                f"Task id: {self.request.id or 'eager'}",
                "",
                f"Title: {download_item.title}",
                f"Source: {download_item.source.name}",
                f"Source type: {download_item.source.type}",
                f"Source policy: {download_item.source.policy}",
                f"Original URL: {download_item.original_url}",
                f"Media URL: {download_item.media_url or 'None'}",
                "",
                "Description:",
                download_item.description or "No description provided.",
                "",
                "Offline preparation note:",
                media_note,
                "",
            ]
        )
        output_path.write_text(content, encoding="utf-8")
        file_size_bytes = output_path.stat().st_size

        try:
            stored_path = str(output_path.relative_to(settings.BASE_DIR))
        except ValueError:
            stored_path = str(output_path)

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

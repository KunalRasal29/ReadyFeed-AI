from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from django.conf import settings

from core.models import DownloadItem


class OfflineStorageError(Exception):
    pass


@dataclass(frozen=True)
class StoredOfflineFile:
    storage_backend: str
    file_size_bytes: int
    local_file_path: str = ""
    storage_key: str = ""


def configured_storage_backend():
    backend = getattr(settings, "OFFLINE_FILE_STORAGE", DownloadItem.STORAGE_LOCAL)
    backend = (backend or DownloadItem.STORAGE_LOCAL).lower()

    if backend not in {DownloadItem.STORAGE_LOCAL, DownloadItem.STORAGE_S3}:
        raise OfflineStorageError(
            "OFFLINE_FILE_STORAGE must be either 'local' or 's3'."
        )

    return backend


def store_offline_file(file_path, download_item, content_type="application/octet-stream"):
    backend = configured_storage_backend()
    file_path = Path(file_path)
    file_size_bytes = file_path.stat().st_size

    if backend == DownloadItem.STORAGE_S3:
        storage_key = _s3_key_for_download(download_item, file_path.name)
        _upload_file_to_s3(file_path, storage_key, content_type)
        return StoredOfflineFile(
            storage_backend=DownloadItem.STORAGE_S3,
            storage_key=storage_key,
            file_size_bytes=file_size_bytes,
        )

    return StoredOfflineFile(
        storage_backend=DownloadItem.STORAGE_LOCAL,
        local_file_path=_local_media_path(file_path),
        file_size_bytes=file_size_bytes,
    )


def offline_file_url(download_item, request=None):
    if download_item.storage_backend == DownloadItem.STORAGE_S3:
        if not download_item.storage_key:
            return ""
        return _generate_s3_presigned_url(download_item.storage_key)

    if not download_item.local_file_path:
        return ""

    media_path = download_item.local_file_path.replace("\\", "/").lstrip("/")
    media_prefix = settings.MEDIA_URL.strip("/")
    if media_prefix and media_path.startswith(f"{media_prefix}/"):
        media_path = media_path[len(media_prefix) + 1 :]

    url = f"{settings.MEDIA_URL.rstrip('/')}/{quote(media_path, safe='/')}"
    if request:
        return request.build_absolute_uri(url)
    return url


def _local_media_path(file_path):
    try:
        return str(file_path.relative_to(settings.MEDIA_ROOT))
    except ValueError:
        return str(file_path)


def _s3_key_for_download(download_item, filename):
    safe_filename = quote(filename, safe="._-")
    return f"offline_items/{download_item.user_id}/{safe_filename}"


def _upload_file_to_s3(file_path, storage_key, content_type):
    bucket = _s3_bucket_name()
    extra_args = {
        "ContentType": content_type or "application/octet-stream",
        "Metadata": {
            "app": "readyfeed-ai",
            "purpose": "offline-download",
        },
    }

    try:
        _s3_client().upload_file(
            str(file_path),
            bucket,
            storage_key,
            ExtraArgs=extra_args,
        )
    except Exception as exc:
        raise OfflineStorageError(f"Could not upload offline file to S3: {exc}") from exc


def _generate_s3_presigned_url(storage_key):
    bucket = _s3_bucket_name()

    try:
        return _s3_client().generate_presigned_url(
            "get_object",
            Params={
                "Bucket": bucket,
                "Key": storage_key,
            },
            ExpiresIn=getattr(settings, "AWS_S3_PRESIGNED_EXPIRES", 3600),
        )
    except Exception as exc:
        raise OfflineStorageError(f"Could not create S3 presigned URL: {exc}") from exc


def _s3_bucket_name():
    bucket = getattr(settings, "AWS_STORAGE_BUCKET_NAME", "")
    if not bucket:
        raise OfflineStorageError("AWS_STORAGE_BUCKET_NAME is required for S3 storage.")
    return bucket


def _s3_client():
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise OfflineStorageError(
            "boto3 is required for S3 storage. Run pip install -r requirements.txt."
        ) from exc

    client_kwargs = {
        "service_name": "s3",
        "region_name": getattr(settings, "AWS_S3_REGION_NAME", "us-east-1"),
        "config": Config(
            signature_version="s3v4",
            s3={
                "addressing_style": getattr(
                    settings,
                    "AWS_S3_ADDRESSING_STYLE",
                    "virtual",
                )
            },
        ),
    }

    endpoint_url = getattr(settings, "AWS_S3_ENDPOINT_URL", "")
    if endpoint_url:
        client_kwargs["endpoint_url"] = endpoint_url

    return boto3.client(**client_kwargs)

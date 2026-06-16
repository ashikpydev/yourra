"""
Object storage helpers.

- In LOCAL_MODE: files are stored on local disk under LOCAL_STORAGE_DIR,
  keyed exactly like R2 keys (uploads/{user_id}/{job_id}/{filename}).
- In production: Cloudflare R2 (S3-compatible) via boto3.
"""
import os
import shutil

from backend.config import settings

# ----------------------------------------------------------------------------
# Local disk implementation (LOCAL_MODE)
# ----------------------------------------------------------------------------

def _local_path(key: str) -> str:
    return os.path.join(settings.LOCAL_STORAGE_DIR, key.replace("/", os.sep))


def _local_upload(fileobj, key: str) -> str:
    dest = _local_path(key)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        shutil.copyfileobj(fileobj, f)
    return key


def _local_download(key: str, local_path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
    shutil.copyfile(_local_path(key), local_path)


# ----------------------------------------------------------------------------
# Cloudflare R2 implementation (production)
# ----------------------------------------------------------------------------

def _client():
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


# ----------------------------------------------------------------------------
# Public API (same signatures in both modes)
# ----------------------------------------------------------------------------

def upload_fileobj(fileobj, key: str, content_type: str | None = None) -> str:
    """Stream-upload a file-like object. Returns the storage key."""
    if settings.LOCAL_MODE:
        return _local_upload(fileobj, key)
    extra_args = {}
    if content_type:
        extra_args["ContentType"] = content_type
    _client().upload_fileobj(fileobj, settings.R2_BUCKET_NAME, key, ExtraArgs=extra_args)
    return key


def download_to_path(key: str, local_path: str) -> None:
    """Download an object to a local file path."""
    if settings.LOCAL_MODE:
        return _local_download(key, local_path)
    _client().download_file(settings.R2_BUCKET_NAME, key, local_path)


def delete_object(key: str) -> None:
    if settings.LOCAL_MODE:
        try:
            os.remove(_local_path(key))
        except FileNotFoundError:
            pass
        return
    _client().delete_object(Bucket=settings.R2_BUCKET_NAME, Key=key)


def object_exists(key: str) -> bool:
    if settings.LOCAL_MODE:
        return os.path.exists(_local_path(key))
    try:
        _client().head_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
        return True
    except Exception:
        return False


def local_full_path(key: str) -> str:
    """Absolute disk path for a key (LOCAL_MODE only) — used to stream audio."""
    return _local_path(key)


def presigned_get_url(key: str, expires: int = 3600) -> str:
    """A short-lived signed URL to GET an R2 object directly (supports range/seek)."""
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.R2_BUCKET_NAME, "Key": key},
        ExpiresIn=expires,
    )

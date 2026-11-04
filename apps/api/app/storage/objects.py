"""Object storage (S3-compatible: MinIO locally, Scaleway / OVHcloud in production, EU only).

Files are never served by the API: clients get short-lived signed URLs.
"""

from functools import lru_cache
from typing import BinaryIO, Protocol

import boto3
from botocore.client import Config

from app.core.config import get_settings


class ObjectStorage(Protocol):
    def put(self, key: str, fileobj: BinaryIO, content_type: str) -> None: ...
    def delete(self, key: str) -> None: ...
    def signed_download_url(self, key: str, filename: str, ttl_seconds: int) -> str: ...


def _ascii_fallback(filename: str) -> str:
    return filename.encode("ascii", "replace").decode().replace("?", "_").replace('"', "_")


class S3Storage:
    def __init__(self, client: object | None = None, bucket: str | None = None) -> None:
        s = get_settings()
        self._bucket = bucket or s.s3_bucket
        self._s3 = client or boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint,
            aws_access_key_id=s.s3_access_key or None,
            aws_secret_access_key=s.s3_secret_key or None,
            region_name=s.s3_region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def put(self, key: str, fileobj: BinaryIO, content_type: str) -> None:
        self._s3.upload_fileobj(  # type: ignore[attr-defined]
            fileobj,
            self._bucket,
            key,
            ExtraArgs=(
                {"ContentType": content_type, "ServerSideEncryption": "AES256"}
                if get_settings().environment == "production"
                else {"ContentType": content_type}
            ),
        )

    def delete(self, key: str) -> None:
        self._s3.delete_object(Bucket=self._bucket, Key=key)  # type: ignore[attr-defined]

    def signed_download_url(self, key: str, filename: str, ttl_seconds: int) -> str:
        from urllib.parse import quote

        disposition = f"attachment; filename=\"{_ascii_fallback(filename)}\"; filename*=UTF-8''{quote(filename)}"
        return str(
            self._s3.generate_presigned_url(  # type: ignore[attr-defined]
                "get_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": key,
                    "ResponseContentDisposition": disposition,
                },
                ExpiresIn=ttl_seconds,
            )
        )


@lru_cache
def get_storage() -> ObjectStorage:
    return S3Storage()

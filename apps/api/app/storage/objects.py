import io

"""Object storage (S3-compatible: MinIO locally, Scaleway / OVHcloud in production, EU only).

Files are never served by the API: clients get short-lived signed URLs.
"""

import tempfile
from functools import lru_cache
from typing import TYPE_CHECKING, Any, BinaryIO, Protocol
from urllib.parse import quote

import boto3
from botocore.client import Config

from app.core.config import get_settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


class ObjectStorage(Protocol):
    def put(self, key: str, fileobj: BinaryIO, content_type: str) -> None: ...
    def get(self, key: str) -> BinaryIO: ...
    def delete(self, key: str) -> None: ...
    def signed_download_url(self, key: str, filename: str, ttl_seconds: int) -> str: ...


def _ascii_fallback(filename: str) -> str:
    return filename.encode("ascii", "replace").decode().replace("?", "_").replace('"', "_")


class _NonClosing(io.RawIOBase):
    """Read-through wrapper whose ``close`` leaves the wrapped file open."""

    def __init__(self, inner: BinaryIO) -> None:
        self._inner = inner

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        return self._inner.read(size)

    def readinto(self, buffer: Any) -> int:
        data = self._inner.read(len(buffer))
        buffer[: len(data)] = data
        return len(data)

    def seekable(self) -> bool:
        return True

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        return self._inner.seek(offset, whence)

    def tell(self) -> int:
        return self._inner.tell()


class S3Storage:
    def __init__(self, client: "S3Client | None" = None, bucket: str | None = None) -> None:
        s = get_settings()
        self._bucket = bucket or s.s3_bucket
        self._s3: S3Client = client or boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint,
            aws_access_key_id=s.s3_access_key or None,
            aws_secret_access_key=s.s3_secret_key or None,
            region_name=s.s3_region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def put(self, key: str, fileobj: BinaryIO, content_type: str) -> None:
        """Upload ``fileobj`` from its start. The caller's file stays open and is rewound
        (boto3 would otherwise close it, and the DCE pipeline reads it again afterwards)."""
        fileobj.seek(0)
        self._s3.upload_fileobj(
            _NonClosing(fileobj),  # type: ignore[arg-type]
            self._bucket,
            key,
            ExtraArgs=(
                {"ContentType": content_type, "ServerSideEncryption": "AES256"}
                if get_settings().environment == "production"
                else {"ContentType": content_type}
            ),
        )
        fileobj.seek(0)

    def get(self, key: str) -> BinaryIO:
        """Download to a spooled temp file (RAM up to 16 MB, then disk), cursor at 0."""
        buf = tempfile.SpooledTemporaryFile(max_size=16 * 1024 * 1024)  # noqa: SIM115
        self._s3.download_fileobj(self._bucket, key, buf)
        buf.seek(0)
        return buf  # type: ignore[return-value]

    def delete(self, key: str) -> None:
        self._s3.delete_object(Bucket=self._bucket, Key=key)

    def signed_download_url(self, key: str, filename: str, ttl_seconds: int) -> str:
        disposition = (
            f'attachment; filename="{_ascii_fallback(filename)}"; '
            f"filename*=UTF-8''{quote(filename)}"
        )
        return self._s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key, "ResponseContentDisposition": disposition},
            ExpiresIn=ttl_seconds,
        )


@lru_cache
def get_storage() -> ObjectStorage:
    return S3Storage()

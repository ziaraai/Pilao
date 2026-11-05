"""Object storage, behind one interface (ADR-033).

* ``S3Storage``: any S3-compatible service (MinIO locally, Scaleway / OVHcloud, EU only);
  clients download through short-lived presigned URLs.
* ``DiskStorage``: the server's own disk, for a single-server deployment (the pilot).
  Clients download through short-lived URLs signed by the API (HMAC, like S3's), served
  by ``GET /files/download``: no session needed, nothing to guess, nothing to replay late.
"""

import base64
import hashlib
import hmac
import io
import os
import re
import tempfile
import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO, Protocol
from urllib.parse import quote, urlencode

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


_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_KEY = re.compile(rf"^{_UUID}/{_UUID}$")  # "<organization>/<file>", as files.py builds them


class InvalidLink(Exception):
    """A download link that was altered, or has expired."""


class DiskStorage:
    def __init__(self, root: Path, secret: str, public_api_url: str) -> None:
        self._root, self._secret = root, secret.encode()
        self._base = public_api_url.rstrip("/")

    def _path(self, key: str) -> Path:
        if not _KEY.fullmatch(key):  # never a path built from anything else (no "..")
            raise ValueError(f"invalid storage key: {key!r}")
        return self._root / key

    def put(self, key: str, fileobj: BinaryIO, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.part")
        fileobj.seek(0)
        try:
            with tmp.open("wb") as out:
                while chunk := fileobj.read(1024 * 1024):
                    out.write(chunk)
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp, path)  # a reader never sees half a file
        finally:
            tmp.unlink(missing_ok=True)
        fileobj.seek(0)

    def get(self, key: str) -> BinaryIO:
        return self._path(key).open("rb")

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def _signature(self, key: str, expires: int, filename: str) -> str:
        mac = hmac.new(self._secret, f"{key}\n{expires}\n{filename}".encode(), hashlib.sha256)
        return base64.urlsafe_b64encode(mac.digest()).decode().rstrip("=")

    def signed_download_url(self, key: str, filename: str, ttl_seconds: int) -> str:
        self._path(key)
        expires = int(time.time()) + ttl_seconds
        query = urlencode(
            {"k": key, "e": expires, "n": filename, "s": self._signature(key, expires, filename)}
        )
        return f"{self._base}/files/download?{query}"

    def open_signed(self, key: str, expires: int, filename: str, signature: str) -> Path:
        """The file a link points to, if the link is intact and still valid."""
        if not _KEY.fullmatch(key) or not hmac.compare_digest(
            signature, self._signature(key, expires, filename)
        ):
            raise InvalidLink("altered")
        if expires < time.time():
            raise InvalidLink("expired")
        path = self._path(key)
        if not path.is_file():
            raise FileNotFoundError(key)
        return path


@lru_cache
def get_storage() -> ObjectStorage:
    s = get_settings()
    if s.storage_backend == "disk":
        return DiskStorage(Path(s.storage_dir), s.app_secret_key, s.api_public_url)
    return S3Storage()

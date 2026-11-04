import io
from collections.abc import Iterator

import boto3
import pytest
import requests
from botocore.client import Config
from botocore.exceptions import ClientError
from moto import mock_aws

from app.storage.objects import S3Storage

BUCKET = "pilao-test"


@pytest.fixture
def s3() -> Iterator[S3Storage]:
    with mock_aws():
        client = boto3.client(
            "s3",
            region_name="us-east-1",
            aws_access_key_id="k",
            aws_secret_access_key="s",
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),  # as in prod
        )
        client.create_bucket(Bucket=BUCKET)
        storage = S3Storage(client=client, bucket=BUCKET)
        storage.raw = client  # type: ignore[attr-defined]
        yield storage


def test_put_then_signed_url_downloads_with_attachment_header(s3: S3Storage) -> None:
    s3.put("org/abc", io.BytesIO(b"hello"), "application/pdf")
    url = s3.signed_download_url("org/abc", "Mémoire final.pdf", 300)
    assert "X-Amz-Expires=300" in url and "X-Amz-Signature=" in url
    res = requests.get(url, timeout=5)
    assert res.status_code == 200 and res.content == b"hello"
    disposition = res.headers["content-disposition"]
    assert (
        disposition.startswith("attachment;")
        and "filename*=UTF-8''M%C3%A9moire%20final.pdf" in disposition
    )


def test_signed_url_expires_when_asked(s3: S3Storage) -> None:
    short = s3.signed_download_url("org/a", "a.pdf", 5)
    longer = s3.signed_download_url("org/a", "a.pdf", 3600)
    assert "X-Amz-Expires=5" in short and "X-Amz-Expires=3600" in longer


def test_delete(s3: S3Storage) -> None:
    s3.put("org/x", io.BytesIO(b"x"), "application/pdf")
    s3.raw.head_object(Bucket=BUCKET, Key="org/x")  # type: ignore[attr-defined]
    s3.delete("org/x")
    with pytest.raises(ClientError) as err:
        s3.raw.head_object(Bucket=BUCKET, Key="org/x")  # type: ignore[attr-defined]
    assert err.value.response["Error"]["Code"] == "404"


def test_put_leaves_the_callers_file_open_and_rewound(s3: S3Storage) -> None:
    data = io.BytesIO(b"%PDF-1.4 contenu du DCE")
    data.read(3)  # cursor anywhere: the whole file is uploaded anyway
    s3.put("org/keep", data, "application/pdf")
    assert not data.closed and data.tell() == 0
    assert data.read() == b"%PDF-1.4 contenu du DCE"  # still readable (text extraction)
    stored = s3.raw.get_object(Bucket=BUCKET, Key="org/keep")["Body"].read()  # type: ignore[attr-defined]
    assert stored == b"%PDF-1.4 contenu du DCE"

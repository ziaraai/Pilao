"""Files on the server's own disk, downloaded through links signed by the API (ADR-033)."""

import io
import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.storage.objects import DiskStorage, InvalidLink, get_storage

SECRET = "s" * 40
Factory = Callable[[], TestClient]


def key() -> str:
    return f"{uuid.uuid4()}/{uuid.uuid4()}"


@pytest.fixture
def disk(tmp_path: Path) -> DiskStorage:
    return DiskStorage(tmp_path / "files", SECRET, "https://app.pilao.pro/api/")


def test_files_are_written_whole_and_only_where_keys_say(disk: DiskStorage, tmp_path: Path) -> None:
    k = key()
    data = io.BytesIO(b"%PDF-1.7 " + b"x" * 3_000_000)
    disk.put(k, data, "application/pdf")
    assert data.tell() == 0  # rewound for the next reader, as S3Storage does
    with disk.get(k) as fh:
        assert fh.read() == data.getvalue()
    files = [p for p in (tmp_path / "files").rglob("*") if p.is_file()]
    assert [p.relative_to(tmp_path / "files").as_posix() for p in files] == [k]  # no .part left
    for bad in ("../../etc/passwd", "org/file", f"{uuid.uuid4()}/../x", f"{uuid.uuid4()}"):
        with pytest.raises(ValueError):
            disk.put(bad, io.BytesIO(b"x"), "text/plain")
    disk.delete(k)
    disk.delete(k)  # already gone: nothing to do, as on S3
    assert not (tmp_path / "files" / k).exists()


def test_a_link_works_once_signed_and_not_once_altered(disk: DiskStorage) -> None:
    k = key()
    disk.put(k, io.BytesIO(b"contenu"), "application/pdf")
    url = disk.signed_download_url(k, "Mémoire technique.pdf", 300)
    assert url.startswith("https://app.pilao.pro/api/files/download?")
    q = {name: values[0] for name, values in parse_qs(urlsplit(url).query).items()}
    assert disk.open_signed(q["k"], int(q["e"]), q["n"], q["s"]).read_bytes() == b"contenu"
    for altered in (
        {**q, "n": "autre.pdf"},  # another name
        {**q, "e": str(int(q["e"]) + 3600)},  # a longer life
        {**q, "k": key()},  # another file
        {**q, "s": q["s"][:-1] + ("A" if q["s"][-1] != "A" else "B")},
    ):
        with pytest.raises(InvalidLink):
            disk.open_signed(altered["k"], int(altered["e"]), altered["n"], altered["s"])
    other = DiskStorage(Path("/nowhere"), "t" * 40, "https://app.pilao.pro/api")
    with pytest.raises(InvalidLink):  # signed with another server's secret
        other.open_signed(q["k"], int(q["e"]), q["n"], q["s"])
    expired = disk.signed_download_url(k, "a.pdf", -1)
    qe = {name: values[0] for name, values in parse_qs(urlsplit(expired).query).items()}
    with pytest.raises(InvalidLink):
        disk.open_signed(qe["k"], int(qe["e"]), qe["n"], qe["s"])


@pytest.fixture
def disk_client(make_client: Factory, disk: DiskStorage) -> Iterator[TestClient]:
    from app.main import app

    client = make_client()  # installs the test overrides, storage included
    app.dependency_overrides[get_storage] = lambda: disk
    yield client


def test_the_api_serves_a_signed_link_without_a_session(
    disk_client: TestClient, disk: DiskStorage
) -> None:
    k = key()
    disk.put(k, io.BytesIO(b"%PDF-1.7 dossier"), "application/pdf")
    url = disk.signed_download_url(k, "Mémoire — Lyon.pdf", 300)
    path = url.removeprefix("https://app.pilao.pro/api")
    res = disk_client.get(path)  # no cookie: the signature is the authorization
    assert res.status_code == 200 and res.content == b"%PDF-1.7 dossier"
    assert res.headers["content-type"] == "application/pdf"
    assert res.headers["content-disposition"].startswith("attachment;")
    assert (
        "filename*=utf-8''M%C3%A9moire%20%E2%80%94%20Lyon.pdf" in res.headers["content-disposition"]
    )
    assert res.headers["cache-control"] == "private, no-store"

    tampered = path.replace("Lyon", "Paris")
    assert disk_client.get(tampered).status_code == 410
    disk.delete(k)
    assert disk_client.get(path).status_code == 404
    expired = disk.signed_download_url(k, "a.pdf", -10).removeprefix("https://app.pilao.pro/api")
    assert disk_client.get(expired).json()["error"]["code"] == "link_invalid"


def test_s3_deployments_have_no_such_route(make_client: Factory) -> None:
    q = f"k={key()}&e={int(time.time()) + 60}&n=a.pdf&s=x"
    assert make_client().get(f"/files/download?{q}").status_code == 404


def test_production_on_disk_needs_a_public_api_url_and_a_real_secret() -> None:
    base = {
        "_env_file": None,
        "environment": "production",
        "app_base_url": "https://app.pilao.pro",
        "database_url": "postgresql+psycopg://pilao:secret@postgres:5432/pilao",
        "clamav_host": "clamav",
        "embedding_model": "openrouter/mistralai/mistral-embed-2312",
        "storage_backend": "disk",
    }
    weak = Settings(**base, api_public_url="http://app.pilao.pro/api")  # type: ignore[arg-type]
    assert weak.production_problems() == [
        "API_PUBLIC_URL doit être en https:// (liens de téléchargement).",
        "APP_SECRET_KEY doit faire au moins 32 caractères aléatoires.",
    ]  # and no S3 settings asked for
    good = Settings(  # type: ignore[arg-type]
        **base, api_public_url="https://app.pilao.pro/api", app_secret_key=SECRET
    )
    assert good.production_problems() == []

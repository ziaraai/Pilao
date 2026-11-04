import io
import zipfile

import pytest

from app.documents.archive import ArchiveError, ArchiveLimits, clean_path, expand


def make_zip(entries: dict[str, bytes], method: int = zipfile.ZIP_DEFLATED) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", method) as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return out.getvalue()


def collect(data: bytes, name: str = "DCE.zip", limits: ArchiveLimits | None = None):  # type: ignore[no-untyped-def]
    members, skipped = expand(io.BytesIO(data), name, limits)
    out = {m.path: m.data.read() for m in members}
    return out, skipped


PDF = b"%PDF-1.4 contenu"


def test_flat_and_nested_archives() -> None:
    inner = make_zip({"Annexes/plan.pdf": PDF})
    files, skipped = collect(
        make_zip({"RC.pdf": PDF, "Pieces/CCTP.pdf": PDF, "annexes.zip": inner})
    )
    assert files == {
        "DCE.zip/RC.pdf": PDF,
        "DCE.zip/Pieces/CCTP.pdf": PDF,
        "DCE.zip/annexes.zip/Annexes/plan.pdf": PDF,
    }
    assert skipped == []


def test_office_files_are_not_mistaken_for_nested_archives() -> None:
    docx = make_zip({"word/document.xml": b"<w/>"})
    files, _ = collect(make_zip({"AE.docx": docx}))
    assert files == {"DCE.zip/AE.docx": docx}


def test_junk_directories_and_files_are_ignored() -> None:
    files, skipped = collect(
        make_zip(
            {
                "__MACOSX/._RC.pdf": b"x",
                "RC.pdf": PDF,
                ".DS_Store": b"x",
                "Thumbs.db": b"x",
                "Pieces/~$CCTP.docx": b"x",
                "Pieces/": b"",
            }
        )
    )
    assert list(files) == ["DCE.zip/RC.pdf"] and skipped == []


def test_path_traversal_names_are_neutralized() -> None:
    files, _ = collect(
        make_zip({"../../etc/passwd.pdf": PDF, "/abs/RC.pdf": PDF, "a\\b\\c.pdf": PDF})
    )
    assert set(files) == {"DCE.zip/etc/passwd.pdf", "DCE.zip/abs/RC.pdf", "DCE.zip/a/b/c.pdf"}
    assert clean_path("../..//./x") == "x"


def test_french_names_from_windows_tools_are_recovered() -> None:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        info = zipfile.ZipInfo("x")
        # Simulate a Windows archiver: cp850 bytes, no UTF-8 flag.
        info.filename = "Règlement_de_consultation.pdf".encode("cp850").decode("cp437")
        info.flag_bits &= ~0x800
        zf.writestr(info, PDF)
    files, _ = collect(out.getvalue())
    assert list(files) == ["DCE.zip/Règlement_de_consultation.pdf"]


def test_zip_bomb_by_ratio_is_refused() -> None:
    bomb = make_zip({"bomb.pdf": b"%PDF" + b"\0" * (40 * 1024 * 1024)})
    assert len(bomb) < 200_000  # tiny on the wire
    with pytest.raises(ArchiveError, match="compression anormal"):
        collect(bomb)


def test_size_count_and_depth_limits() -> None:
    small = ArchiveLimits(max_members=3, max_total_bytes=40, max_member_bytes=30, max_depth=2)
    with pytest.raises(ArchiveError, match="trop volumineux"):
        collect(make_zip({"big.pdf": PDF * 3}), limits=small)
    with pytest.raises(ArchiveError, match="décompressée"):
        collect(make_zip({"a.pdf": PDF, "b.pdf": PDF, "c.pdf": PDF}), limits=small)
    with pytest.raises(ArchiveError, match="Trop de fichiers"):
        collect(make_zip({f"{i}.pdf": b"%PDF" for i in range(4)}), limits=small)
    deep = make_zip({"l3.pdf": PDF})
    for level in range(3):
        deep = make_zip({f"niveau{level}.zip": deep})
    files, skipped = collect(deep, limits=ArchiveLimits(max_depth=2))
    assert files == {} and skipped and "trop profonde" in skipped[0].reason


def test_encrypted_member_is_skipped_with_reason() -> None:
    data = bytearray(make_zip({"secret.pdf": PDF, "RC.pdf": PDF}, method=zipfile.ZIP_STORED))
    # Flip the "encrypted" bit of the first entry in both headers.
    local = data.find(b"PK\x03\x04")
    central = data.find(b"PK\x01\x02")
    data[local + 6] |= 0x1
    data[central + 8] |= 0x1
    files, skipped = collect(bytes(data))
    assert list(files) == ["DCE.zip/RC.pdf"]
    assert skipped[0].path == "DCE.zip/secret.pdf" and "mot de passe" in skipped[0].reason


def test_unreadable_archive() -> None:
    with pytest.raises(ArchiveError, match="illisible"):
        collect(b"PK\x03\x04 not a zip")

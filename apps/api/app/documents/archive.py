"""Safe expansion of DCE archives (ZIP, nested ZIPs included) — US-3.1 CA1.

Nothing is written to disk under a name taken from the archive: each member is copied into
an anonymous spooled temp file. Hard limits protect against zip bombs and abuse:

* sizes are counted on the bytes really decompressed (headers can lie);
* a member whose compression ratio is absurd is refused;
* member count, total size and nesting depth are capped;
* encrypted members are skipped with an explanation, junk files (``__MACOSX``...) ignored.
"""

import io
import tempfile
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import BinaryIO

from app.domain.filetypes import ZIP, detect

CHUNK = 1024 * 1024
JUNK_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}
JUNK_DIRS = ("__macosx/",)


class ArchiveError(Exception):
    """The whole archive is refused (French message, shown to the user)."""


@dataclass(frozen=True)
class ArchiveLimits:
    max_members: int = 2000
    max_total_bytes: int = 1024**3
    max_member_bytes: int = 250 * 1024**2
    max_depth: int = 3
    max_ratio: int = 200  # uncompressed / compressed, checked once a member exceeds 10 MB


@dataclass
class Member:
    path: str  # display path inside the archive(s), e.g. "DCE.zip/Pieces/CCTP.pdf"
    data: BinaryIO  # cursor at 0; caller closes
    size: int


@dataclass(frozen=True)
class Skipped:
    path: str
    reason: str


@dataclass
class _Budget:
    limits: ArchiveLimits
    members: int = 0
    total: int = 0
    skipped: list[Skipped] = field(default_factory=list)


def decode_name(info: zipfile.ZipInfo) -> str:
    """Archive names without the UTF-8 flag are cp437 for Python; French Windows tools write
    cp850 (or UTF-8 without the flag). Recover the real name instead of « Ã©tude.pdf »."""
    if info.flag_bits & 0x800:
        return info.filename
    raw = info.filename.encode("cp437", errors="replace")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp850", errors="replace")


def clean_path(name: str) -> str:
    """Display-safe relative path: no absolute part, no '..', forward slashes only."""
    parts = [p for p in name.replace("\\", "/").split("/") if p not in ("", ".", "..")]
    return "/".join(parts)


def _is_junk(path: str) -> bool:
    lowered = path.lower()
    base = lowered.rsplit("/", 1)[-1]
    return (
        any(lowered.startswith(d) or f"/{d}" in lowered for d in JUNK_DIRS)
        or base in JUNK_NAMES
        or base.startswith(("._", "~$"))  # AppleDouble and Office lock files
    )


def _copy_member(
    zf: zipfile.ZipFile, info: zipfile.ZipInfo, budget: _Budget, path: str
) -> BinaryIO:
    limits = budget.limits
    out = tempfile.SpooledTemporaryFile(max_size=8 * CHUNK)  # noqa: SIM115 - caller closes
    written = 0
    try:
        with zf.open(info) as src:
            while chunk := src.read(CHUNK):
                written += len(chunk)
                budget.total += len(chunk)
                if written > limits.max_member_bytes:
                    raise ArchiveError(f"« {path} » est trop volumineux une fois décompressé.")
                if budget.total > limits.max_total_bytes:
                    raise ArchiveError("Archive trop volumineuse une fois décompressée.")
                if written > 10 * CHUNK and written > limits.max_ratio * max(info.compress_size, 1):
                    raise ArchiveError(
                        f"« {path} » a un taux de compression anormal (archive piégée ?)."
                    )
                out.write(chunk)
    except BaseException:
        out.close()
        raise
    out.seek(0)
    return out  # type: ignore[return-value]


def _walk(fileobj: BinaryIO, prefix: str, depth: int, budget: _Budget) -> Iterator[Member]:
    try:
        zf = zipfile.ZipFile(fileobj)
    except (zipfile.BadZipFile, OSError, ValueError) as exc:
        raise ArchiveError(f"Archive illisible : « {prefix or 'ZIP'} ».") from exc
    with zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            path = clean_path(f"{prefix}/{decode_name(info)}" if prefix else decode_name(info))
            if not path or _is_junk(path):
                continue
            budget.members += 1
            if budget.members > budget.limits.max_members:
                raise ArchiveError(
                    f"Trop de fichiers dans l'archive ({budget.limits.max_members} max)."
                )
            if info.flag_bits & 0x1:
                budget.skipped.append(Skipped(path, "protégé par mot de passe"))
                continue
            try:
                data = _copy_member(zf, info, budget, path)
            except (zipfile.BadZipFile, OSError, EOFError, ValueError, NotImplementedError):
                budget.skipped.append(Skipped(path, "fichier corrompu dans l'archive"))
                continue
            kind = detect(data)
            if kind is ZIP:
                if depth + 1 > budget.limits.max_depth:
                    data.close()
                    budget.skipped.append(Skipped(path, "archive imbriquée trop profonde"))
                    continue
                try:
                    yield from _walk(data, path, depth + 1, budget)
                finally:
                    data.close()
                continue
            size = data.seek(0, io.SEEK_END)
            data.seek(0)
            yield Member(path, data, size)


def expand(
    fileobj: BinaryIO, name: str, limits: ArchiveLimits | None = None
) -> tuple[Iterator[Member], list[Skipped]]:
    """Members of a ZIP (recursively). ``skipped`` fills up while the iterator is consumed.

    Raises :class:`ArchiveError` (possibly mid-iteration) when a hard limit is hit.
    """
    budget = _Budget(limits or ArchiveLimits())
    fileobj.seek(0)
    return _walk(fileobj, clean_path(name), 1, budget), budget.skipped

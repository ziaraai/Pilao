"""The complete bid folder as a ZIP (US-4.6 CA3)."""

import io
import re
import unicodedata
import zipfile
from collections.abc import Sequence

_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def safe_name(name: str) -> str:
    """A file name every system accepts (no separators, no control characters)."""
    name = "".join(c for c in unicodedata.normalize("NFC", name) if unicodedata.category(c) != "Cf")
    return _UNSAFE.sub("_", name).strip(" .")[:150] or "document"


def build_zip(entries: Sequence[tuple[str, bytes]]) -> bytes:
    """``entries`` are (folder/name, content); duplicate names get a number."""
    out = io.BytesIO()
    seen: set[str] = set()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, content in entries:
            folder, _, name = path.rpartition("/")
            stem, dot, ext = safe_name(name).rpartition(".")
            stem, ext = (stem, f".{ext}") if dot else (ext, "")
            candidate, n = f"{stem}{ext}", 1
            while f"{folder}/{candidate}" in seen:
                n += 1
                candidate = f"{stem} ({n}){ext}"
            full = f"{folder}/{candidate}" if folder else candidate
            seen.add(f"{folder}/{candidate}")
            archive.writestr(full, content)
    return out.getvalue()

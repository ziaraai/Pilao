"""Antivirus scanning through a ClamAV daemon (clamd INSTREAM protocol, no extra dependency)."""

import socket
import struct
from functools import lru_cache
from typing import BinaryIO, Protocol

from app.core.config import get_settings

CHUNK = 64 * 1024


class ScannerUnavailable(Exception):
    """The scanner could not be reached or answered garbage: fail closed."""


class ScanTooLarge(Exception):
    """clamd refused the stream for its size (StreamMaxLength, 100 MB by default)."""


class VirusScanner(Protocol):
    def scan(self, fileobj: BinaryIO) -> str | None:
        """Return the signature name if infected, None if clean."""


class NullScanner:
    """Local development only: scans nothing."""

    def scan(self, fileobj: BinaryIO) -> str | None:
        return None


class ClamAvScanner:
    def __init__(self, host: str, port: int, timeout: float = 30.0) -> None:
        self._addr, self._timeout = (host, port), timeout

    def scan(self, fileobj: BinaryIO) -> str | None:
        fileobj.seek(0)
        try:
            with socket.create_connection(self._addr, timeout=self._timeout) as sock:
                sock.sendall(b"zINSTREAM\0")
                while chunk := fileobj.read(CHUNK):
                    sock.sendall(struct.pack(">I", len(chunk)) + chunk)
                sock.sendall(struct.pack(">I", 0))
                reply = b""
                while not reply.endswith(b"\0") and (part := sock.recv(4096)):
                    reply += part
        except OSError as exc:
            raise ScannerUnavailable(str(exc)) from exc
        finally:
            fileobj.seek(0)
        text = reply.rstrip(b"\0\n").decode(errors="replace")
        if text.endswith("OK"):
            return None
        if "size limit exceeded" in text.lower():
            raise ScanTooLarge(text)
        if text.endswith("FOUND"):
            return text.removeprefix("stream:").removesuffix("FOUND").strip()
        raise ScannerUnavailable(f"unexpected clamd reply: {text!r}")


@lru_cache
def get_scanner() -> VirusScanner:
    s = get_settings()
    if s.clamav_host:
        return ClamAvScanner(s.clamav_host, s.clamav_port)
    if s.environment == "production":
        raise ScannerUnavailable("CLAMAV_HOST must be set in production")
    return NullScanner()

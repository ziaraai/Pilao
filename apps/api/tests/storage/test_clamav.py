import io
import socket
import struct
import threading

import pytest

from app.storage.antivirus import ClamAvScanner, ScannerUnavailable, ScanTooLarge


def serve(reply: bytes | None) -> tuple[ClamAvScanner, list[bytes]]:
    """Minimal clamd INSTREAM server on a random port. ``reply=None`` closes without answering."""
    received: list[bytes] = []
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)

    def run() -> None:
        conn, _ = srv.accept()
        with conn:
            buf = b""
            while not buf.startswith(b"zINSTREAM\0"):
                buf += conn.recv(4096)
            data = buf[len(b"zINSTREAM\0") :]
            payload = b""
            while True:
                while len(data) < 4:
                    data += conn.recv(65536)
                (size,) = struct.unpack(">I", data[:4])
                data = data[4:]
                if size == 0:
                    break
                while len(data) < size:
                    data += conn.recv(65536)
                payload += data[:size]
                data = data[size:]
            received.append(payload)
            if reply is not None:
                conn.sendall(reply)
        srv.close()

    threading.Thread(target=run, daemon=True).start()
    return ClamAvScanner("127.0.0.1", srv.getsockname()[1], timeout=5), received


def test_clean_file() -> None:
    scanner, received = serve(b"stream: OK\0")
    data = b"x" * 200_000  # several protocol chunks
    f = io.BytesIO(data)
    assert scanner.scan(f) is None
    assert received == [data] and f.tell() == 0  # whole file streamed, cursor rewound


def test_infected_file_returns_signature() -> None:
    scanner, _ = serve(b"stream: Eicar-Test-Signature FOUND\0")
    assert scanner.scan(io.BytesIO(b"virus")) == "Eicar-Test-Signature"


def test_scanner_errors_are_unavailable_not_clean() -> None:
    scanner, _ = serve(b"UNKNOWN COMMAND\0")
    with pytest.raises(ScannerUnavailable):
        scanner.scan(io.BytesIO(b"data"))
    silent, _ = serve(None)
    with pytest.raises(ScannerUnavailable):
        silent.scan(io.BytesIO(b"data"))


def test_unreachable_daemon_fails_closed() -> None:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    with pytest.raises(ScannerUnavailable):
        ClamAvScanner("127.0.0.1", port, timeout=1).scan(io.BytesIO(b"data"))


def test_production_without_clamav_refuses_to_start_scanner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import get_settings
    from app.storage.antivirus import NullScanner, get_scanner

    get_scanner.cache_clear()
    monkeypatch.setattr(get_settings(), "environment", "production")
    monkeypatch.setattr(get_settings(), "clamav_host", None)
    with pytest.raises(ScannerUnavailable):
        get_scanner()
    monkeypatch.setattr(get_settings(), "environment", "local")
    get_scanner.cache_clear()
    assert isinstance(get_scanner(), NullScanner)
    get_scanner.cache_clear()


def test_size_limit_is_reported_as_too_large_not_as_an_outage() -> None:
    scanner, _ = serve(b"INSTREAM size limit exceeded. ERROR\0")
    with pytest.raises(ScanTooLarge):
        scanner.scan(io.BytesIO(b"data"))

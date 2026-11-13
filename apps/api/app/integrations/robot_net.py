"""Where the DCE robot may go: public addresses only (spec « Récupération des DCE », § 5).

A user can paste a link: without this filter the server's browser could be sent to the
internal network (cloud metadata, database, admin consoles). HTTP and private addresses are
only allowed with ``DCE_ROBOT_ALLOW_PRIVATE_HOSTS`` (tests and the local journey).
"""

import ipaddress
import socket
from urllib.parse import urlsplit


def is_public_address(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    # is_global also refuses the shared address space (100.64.0.0/10, some clouds' metadata)
    return addr.is_global and not addr.is_multicast


def _literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def addresses_of(host: str) -> list[str] | None:
    """The addresses of ``host``, or ``None`` when it does not resolve."""
    try:
        infos = socket.getaddrinfo(host, None)
    except (OSError, UnicodeError):
        return None
    return [str(info[4][0]) for info in infos]


def url_allowed(url: str, allow_private: bool, resolve: bool = True) -> bool:
    """HTTPS to a public address. ``resolve=False``: no network, only the scheme, ``localhost``
    and an address written in digits are checked (the service, before queueing)."""
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
    except ValueError:
        return False
    if parts.scheme not in ("http", "https") or not host:
        return False
    if allow_private:
        return True
    if parts.scheme != "https" or host == "localhost" or host.endswith(".localhost"):
        return False
    if _literal(host):
        return is_public_address(host)
    if not resolve:
        return True
    addresses = addresses_of(host)
    return bool(addresses) and all(is_public_address(a) for a in (addresses or []))

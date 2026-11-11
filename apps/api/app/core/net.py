"""The client's address, as the API sees it (behind nginx: run uvicorn with --proxy-headers)."""

import ipaddress

from fastapi import Request


def client_ip(request: Request) -> str | None:
    """Client IP if it is a valid address."""
    host = request.client.host if request.client else None
    try:
        return str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        return None

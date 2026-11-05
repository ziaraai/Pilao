"""Application logs on standard output (containers, systemd): ``LOG_LEVEL`` sets the level."""

import logging
import os


def configure_logging() -> None:
    """Idempotent: uvicorn and RQ configure their own loggers, ``pilao.*`` uses the root one."""
    root = logging.getLogger()
    if any(getattr(h, "_pilao", False) for h in root.handlers):
        return
    handler = logging.StreamHandler()
    handler._pilao = True  # type: ignore[attr-defined]
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(handler)
    logging.getLogger("pilao").setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())

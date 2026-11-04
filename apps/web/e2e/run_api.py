"""API with INFO logs (the console mailer writes verification links there)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "api"))
import logging, uvicorn
logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
uvicorn.run("app.main:app", host="127.0.0.1", port=8000, log_level="info")

"""The production image must carry every file the application reads at run time."""

from pathlib import Path

from app.core.config import get_settings
from app.services.dce_analysis import SCHEMA_PATH

ROOT = Path(__file__).resolve().parents[3]
DOCKERFILE = (ROOT / "apps/api/Dockerfile").read_text(encoding="utf-8")


def test_runtime_files_are_copied_into_the_image() -> None:
    prompts = Path(get_settings().prompts_dir)
    for folder in (prompts, SCHEMA_PATH.parent):  # read relative to PROMPTS_DIR in the image
        relative = folder.relative_to(ROOT)
        assert f"COPY {relative} ./{relative}" in DOCKERFILE, f"{relative} missing from the image"


def test_no_download_at_start() -> None:
    assert "LITELLM_LOCAL_MODEL_COST_MAP=True" in DOCKERFILE

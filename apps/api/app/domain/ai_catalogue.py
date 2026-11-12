"""Which catalogue models a task may use, and their price in euros (lot 5, spec §2)."""

from app.ai.openrouter import CatalogueModel

NEEDS_IMAGES = {"compliance_reading"}  # the reading of attestations sends page images


def usable(m: CatalogueModel, needs_images: bool) -> bool:
    """JSON answers, a known price, no « :free » offer (it keeps the texts sent: contrary to
    the privacy policy), no « ~ » alias (the model behind it would change without notice)."""
    if m.id.endswith(":free") or m.id.startswith("~"):
        return False
    if not m.json_output or m.prompt_usd < 0 or m.completion_usd < 0:
        return False
    return m.reads_images or not needs_images


def eur_per_million(usd_per_token: float, rate: float) -> float:
    return round(usd_per_token * 1_000_000 * rate, 4)

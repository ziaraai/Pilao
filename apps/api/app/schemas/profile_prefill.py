"""Pre-filling the profile: what the model answers, and what the API exchanges."""

from pydantic import BaseModel, ConfigDict, Field


class ExtractedItem(BaseModel):
    """Lenient on purpose: every value is checked afterwards (app/domain/profile_prefill.py)."""

    model_config = ConfigDict(extra="ignore")
    excerpt: str


class ExtractedHumanResource(ExtractedItem):
    qualification: str | None = None
    count: int | None = None
    description: str | None = None


class ExtractedEquipment(ExtractedItem):
    name: str | None = None
    category: str | None = None
    quantity: int | None = None


class ExtractedCertification(ExtractedItem):
    name: str | None = None
    number: str | None = None
    valid_until: str | None = None


class ExtractedReference(ExtractedItem):
    client_name: str | None = None
    client_type: str | None = None
    title: str | None = None
    location: str | None = None
    department: str | None = None
    amount_eur: float | None = None
    year: int | None = None
    duration_months: int | None = None
    description: str | None = None


class ProfileExtraction(BaseModel):
    """Answer of prompts/extraction_profil.md."""

    model_config = ConfigDict(extra="ignore")
    human_resources: list[ExtractedHumanResource] = Field(default_factory=list)
    equipment: list[ExtractedEquipment] = Field(default_factory=list)
    certifications: list[ExtractedCertification] = Field(default_factory=list)
    references: list[ExtractedReference] = Field(default_factory=list)

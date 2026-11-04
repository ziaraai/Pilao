import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import (
    AuditLog,
    Certification,
    CompanyProfile,
    CompanyReference,
    Equipment,
    File,
    HumanResource,
    Organization,
)
from app.domain import completeness
from app.domain.trades import defaults_for
from app.schemas.profile import ProfileIn

# Single place that must be extended when a business table joins the completeness score.
_COUNTED = {
    "human_resources": HumanResource,
    "equipment": Equipment,
    "certifications": Certification,
    "references": CompanyReference,
}


def get_or_create_profile(db: Session, org: Organization) -> CompanyProfile:
    profile = db.scalar(select(CompanyProfile))  # tenant-filtered
    if profile is None:
        # The first screens load several profile endpoints in parallel: a plain INSERT would
        # make all but one of them fail on uq_company_profiles_org_id.
        db.execute(
            pg_insert(CompanyProfile)
            .values(org_id=org.id)
            .on_conflict_do_nothing(index_elements=[CompanyProfile.org_id])
        )
        profile = db.scalars(select(CompanyProfile)).one()
    return profile


def audit(
    db: Session,
    user_id: uuid.UUID,
    action: str,
    entity: str,
    entity_id: uuid.UUID | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id, action=action, entity=entity, entity_id=entity_id, meta=meta or {}
        )
    )


def compute_completeness(
    db: Session, org: Organization, profile: CompanyProfile
) -> completeness.Completeness:
    counts = {k: db.scalar(select(func.count()).select_from(m)) or 0 for k, m in _COUNTED.items()}
    revenues = (profile.revenue_y1_cents, profile.revenue_y2_cents, profile.revenue_y3_cents)
    return completeness.compute(
        completeness.Facts(
            has_address=bool(org.address_line and org.postal_code and org.city),
            has_naf=bool(org.naf_code),
            trades=len(profile.trades),
            cpv_or_keywords=len(profile.cpv_codes) + len(profile.keywords_include),
            departments=len(profile.departments),
            revenue_years=sum(r is not None for r in revenues),
            human_resources=counts["human_resources"],
            equipment=counts["equipment"],
            certifications=counts["certifications"],
            references=counts["references"],
        )
    )


def refresh_completeness(db: Session, org: Organization) -> completeness.Completeness:
    profile = get_or_create_profile(db, org)  # its SELECT autoflushes pending writes
    result = compute_completeness(db, org, profile)
    profile.completeness_pct = result.pct
    return result


def update_profile(
    db: Session, org: Organization, user_id: uuid.UUID, data: ProfileIn
) -> tuple[CompanyProfile, completeness.Completeness]:
    profile = get_or_create_profile(db, org)
    values = data.model_dump(exclude={"apply_trade_defaults"})
    if data.apply_trade_defaults and data.trades:
        cpv, keywords = defaults_for(data.trades)
        values["cpv_codes"] = list(dict.fromkeys([*values["cpv_codes"], *cpv]))
        # An explicitly excluded keyword wins over a trade default (ADR-010: never both).
        excluded = {k.lower() for k in values["keywords_exclude"]}
        keywords = [k for k in keywords if k.lower() not in excluded]
        values["keywords_include"] = list(dict.fromkeys([*values["keywords_include"], *keywords]))
    for key, value in values.items():
        setattr(profile, key, value)
    audit(db, user_id, "update", "company_profile", profile.id)
    result = refresh_completeness(db, org)
    # US-1.2 CA4: a settings change must re-score open tenders. The scoring job arrives with
    # phase 3 (P3-03); enqueue it from here when it exists.
    db.commit()
    return profile, result


def ensure_files_belong_to_org(db: Session, *file_ids: uuid.UUID | None) -> None:
    """Reject references to files of another organization (the scoped session hides them)."""
    for file_id in file_ids:
        if file_id is not None and db.get(File, file_id) is None:
            raise ApiError(422, "unknown_file", "Fichier introuvable.")

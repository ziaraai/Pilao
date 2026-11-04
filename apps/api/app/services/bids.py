import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog, Bid, DceFile, DceVersion, File, User
from app.schemas.bids import BidIn, BidPatch
from app.services import files as files_svc
from app.storage.objects import ObjectStorage


def create_bid(db: Session, user: User, data: BidIn) -> Bid:
    bid = Bid(**data.model_dump(), owner_user_id=user.id, status="to_review")
    db.add(bid)
    db.flush()
    db.add(AuditLog(user_id=user.id, action="create", entity="bid", entity_id=bid.id))
    db.commit()
    return bid


def update_bid(db: Session, user: User, bid: Bid, data: BidPatch) -> Bid:
    changes: dict[str, Any] = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        if value is None and key in ("title", "status"):
            continue  # mandatory fields cannot be cleared
        setattr(bid, key, value)
    db.add(
        AuditLog(
            user_id=user.id,
            action="update",
            entity="bid",
            entity_id=bid.id,
            meta={"fields": sorted(changes)},
        )
    )
    db.commit()
    return bid


def delete_bid(db: Session, user: User, bid: Bid, storage: ObjectStorage) -> None:
    """Delete the bid, its DCE versions, every extracted and deposited file, and S3 objects."""
    versions = db.scalars(select(DceVersion).where(DceVersion.bid_id == bid.id)).all()
    file_ids: set[uuid.UUID] = {fid for v in versions for fid in v.source_file_ids}
    file_ids |= set(
        db.scalars(
            select(DceFile.file_id).where(DceFile.dce_version_id.in_([v.id for v in versions]))
        )
    )
    db.add(AuditLog(user_id=user.id, action="delete", entity="bid", entity_id=bid.id))
    db.delete(bid)  # cascades to dce_versions and dce_files
    db.commit()
    for file_id in file_ids:
        record = db.get(File, file_id)
        if record is not None:
            files_svc.delete_file(db, user, record, storage)

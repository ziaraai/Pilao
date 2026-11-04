import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, UploadFile
from sqlalchemy import select

from app.core.deps import CurrentAuth, ScopedDb
from app.core.errors import ApiError
from app.db.models import Bid, DceAnalysis, DceFile, DcePage, DceVersion, Requirement
from app.routers.files import Storage, _scanner
from app.schemas.bids import (
    AnalysisOut,
    BidIn,
    BidOut,
    BidPatch,
    BidStatus,
    DceFileOut,
    DceKindIn,
    DcePageOut,
    DceVersionOut,
    RequirementOut,
    SourceOut,
)
from app.services import bids as svc
from app.services import dce as dce_svc
from app.services import dce_analysis as analysis_svc
from app.storage.antivirus import VirusScanner
from app.workers.queue import JobQueue, get_job_queue

router = APIRouter(tags=["bids"])
Queue = Annotated[JobQueue, Depends(get_job_queue)]


def _bid(db: ScopedDb, bid_id: uuid.UUID) -> Bid:
    bid = db.get(Bid, bid_id)
    if bid is None:
        raise ApiError(404, "not_found", "Dossier introuvable.")
    return bid


def _version_out(db: ScopedDb, version: DceVersion) -> DceVersionOut:
    files = db.scalars(
        select(DceFile).where(DceFile.dce_version_id == version.id).order_by(DceFile.path)
    )
    out = DceVersionOut.model_validate(version)
    return out.model_copy(update={"files": [DceFileOut.model_validate(f) for f in files]})


@router.post("/bids", status_code=201)
def create_bid(data: BidIn, ctx: CurrentAuth, db: ScopedDb) -> BidOut:
    return BidOut.model_validate(svc.create_bid(db, ctx.user, data))


@router.get("/bids")
def list_bids(db: ScopedDb, status: Annotated[BidStatus | None, Query()] = None) -> list[BidOut]:
    stmt = select(Bid).order_by(Bid.deadline_at.asc().nulls_last(), Bid.created_at.desc())
    if status is not None:
        stmt = stmt.where(Bid.status == status)
    return [BidOut.model_validate(b) for b in db.scalars(stmt)]


@router.get("/bids/{bid_id}")
def get_bid(bid_id: uuid.UUID, db: ScopedDb) -> BidOut:
    return BidOut.model_validate(_bid(db, bid_id))


@router.patch("/bids/{bid_id}")
def patch_bid(bid_id: uuid.UUID, data: BidPatch, ctx: CurrentAuth, db: ScopedDb) -> BidOut:
    return BidOut.model_validate(svc.update_bid(db, ctx.user, _bid(db, bid_id), data))


@router.delete("/bids/{bid_id}", status_code=204)
def delete_bid(bid_id: uuid.UUID, ctx: CurrentAuth, db: ScopedDb, storage: Storage) -> Response:
    svc.delete_bid(db, ctx.user, _bid(db, bid_id), storage)
    return Response(status_code=204)


@router.post("/bids/{bid_id}/dce", status_code=202)
def deposit_dce(
    bid_id: uuid.UUID,
    files: list[UploadFile],
    ctx: CurrentAuth,
    db: ScopedDb,
    storage: Storage,
    scanner: Annotated[VirusScanner, Depends(_scanner)],
    queue: Queue,
) -> DceVersionOut:
    """Deposit the DCE (ZIP and/or documents). Each deposit is a new version, processed in the
    background: poll ``GET /bids/{id}/dce`` for its status and its files."""
    version = dce_svc.create_version(
        db,
        ctx.org,
        ctx.user,
        _bid(db, bid_id),
        [(f.file, f.filename) for f in files],
        storage,
        scanner,
        queue,
    )
    return _version_out(db, version)


@router.get("/bids/{bid_id}/dce")
def list_versions(bid_id: uuid.UUID, db: ScopedDb) -> list[DceVersionOut]:
    bid = _bid(db, bid_id)
    versions = db.scalars(
        select(DceVersion).where(DceVersion.bid_id == bid.id).order_by(DceVersion.version.desc())
    )
    return [_version_out(db, v) for v in versions]


@router.get("/bids/{bid_id}/dce/{version}")
def get_version(bid_id: uuid.UUID, version: int, db: ScopedDb) -> DceVersionOut:
    bid = _bid(db, bid_id)
    row = db.scalar(
        select(DceVersion).where(DceVersion.bid_id == bid.id, DceVersion.version == version)
    )
    if row is None:
        raise ApiError(404, "not_found", "Version introuvable.")
    return _version_out(db, row)


@router.patch("/dce-files/{file_id}")
def set_kind(file_id: uuid.UUID, data: DceKindIn, db: ScopedDb) -> DceFileOut:
    """The user corrects the automatic typing (US-3.1 CA2)."""
    row = db.get(DceFile, file_id)
    if row is None:
        raise ApiError(404, "not_found", "Fichier introuvable.")
    row.detected_kind, row.kind_source, row.kind_confirmed = data.kind, "user", True
    db.commit()
    return DceFileOut.model_validate(row)


@router.get("/dce-files/{file_id}/pages")
def get_pages(
    file_id: uuid.UUID,
    db: ScopedDb,
    first: Annotated[int, Query(alias="from", ge=1)] = 1,
    count: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[DcePageOut]:
    """Page texts of a DCE piece, used to show the source of an extracted fact."""
    row = db.get(DceFile, file_id)
    if row is None:
        raise ApiError(404, "not_found", "Fichier introuvable.")
    pages = db.scalars(
        select(DcePage)
        .where(DcePage.dce_file_id == row.id, DcePage.page >= first)
        .order_by(DcePage.page)
        .limit(count)
    )
    return [DcePageOut.model_validate(p) for p in pages]


@router.post("/bids/{bid_id}/analysis", status_code=202)
def run_analysis(bid_id: uuid.UUID, db: ScopedDb, queue: Queue) -> AnalysisOut:
    """Re-run the AI analysis on the latest ready DCE version."""
    return _analysis_out(db, analysis_svc.rerun(db, _bid(db, bid_id), queue))


@router.get("/bids/{bid_id}/analysis")
def get_analysis(bid_id: uuid.UUID, db: ScopedDb) -> AnalysisOut:
    """Latest analysis sheet. Every item carries its source: file, page, dce_file_id."""
    bid = _bid(db, bid_id)
    analysis = db.scalars(
        select(DceAnalysis)
        .where(DceAnalysis.bid_id == bid.id)
        .order_by(DceAnalysis.created_at.desc())
    ).first()
    if analysis is None:
        raise ApiError(404, "not_found", "Aucune analyse pour ce dossier.")
    return _analysis_out(db, analysis)


def _analysis_out(db: ScopedDb, analysis: DceAnalysis) -> AnalysisOut:
    version = db.get_one(DceVersion, analysis.dce_version_id)
    files = {
        f.id: f.path
        for f in db.scalars(select(DceFile).where(DceFile.dce_version_id == version.id))
    }
    requirements = [
        RequirementOut(
            id=r.id,
            ref=r.ref,
            text=r.text,
            category=r.category,
            importance=r.importance,
            source=(
                SourceOut(file=files[r.source_file_id], page=r.page, dce_file_id=r.source_file_id)
                if r.source_file_id in files
                else None
            ),
        )
        for r in db.scalars(
            select(Requirement)
            .where(Requirement.dce_analysis_id == analysis.id)
            .order_by(Requirement.position)
        )
    ]
    return AnalysisOut(
        id=analysis.id,
        status=analysis.status,
        error=analysis.error,
        dce_version=version.version,
        data=analysis.data,
        requirements=requirements,
        warnings=analysis.warnings,
        model=analysis.model,
        prompt_version=analysis.prompt_version,
        created_at=analysis.created_at,
    )

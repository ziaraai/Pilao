"""AI reading of attestations (prompts/lecture_attestation.md), text or vision."""

import base64
import io
from dataclasses import dataclass
from typing import Any, BinaryIO, Protocol

import pdfplumber
from sqlalchemy.orm import Session

from app.ai import llm
from app.ai.prompts import load_prompt
from app.db.models import Organization
from app.domain.filetypes import JPEG, PDF, PNG
from app.schemas.vault import ReadingOut

MAX_TEXT_CHARS = 12_000
MAX_VISION_PAGES = 2
MIN_TEXT_CHARS = 60  # below this a PDF is treated as a scan and sent to the vision model


@dataclass(frozen=True)
class ReadingResult:
    data: ReadingOut
    raw: dict[str, Any]
    model: str
    prompt_version: str | None


class DocumentReader(Protocol):
    def read(
        self, db: Session, org: Organization, fileobj: BinaryIO, mime: str
    ) -> ReadingResult: ...


def _pdf_text_or_images(fileobj: BinaryIO) -> tuple[str, list[bytes]]:
    """First pages' text; if the PDF has no text layer, PNG renderings of its first pages."""
    fileobj.seek(0)
    with pdfplumber.open(io.BytesIO(fileobj.read())) as pdf:
        pages = pdf.pages[: MAX_VISION_PAGES + 1]
        text = "\n\n".join((p.extract_text() or "") for p in pages).strip()
        if len(text) >= MIN_TEXT_CHARS:
            return text[:MAX_TEXT_CHARS], []
        images = []
        for page in pdf.pages[:MAX_VISION_PAGES]:
            buf = io.BytesIO()
            page.to_image(resolution=150).original.save(buf, format="PNG")
            images.append(buf.getvalue())
        return "", images


def _data_uri(content: bytes, mime: str) -> dict[str, Any]:
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime};base64,{base64.b64encode(content).decode()}"},
    }


class LLMDocumentReader:
    task = "compliance_reading"

    def read(self, db: Session, org: Organization, fileobj: BinaryIO, mime: str) -> ReadingResult:
        prompt = load_prompt("lecture_attestation")
        images: list[dict[str, Any]] = []
        if mime == PDF.mime:
            text, rendered = _pdf_text_or_images(fileobj)
            images = [_data_uri(b, PNG.mime) for b in rendered]
        elif mime in (PNG.mime, JPEG.mime):
            fileobj.seek(0)
            text, images = "", [_data_uri(fileobj.read(), mime)]
        else:
            raise llm.LlmError("Format non pris en charge pour la lecture automatique.")
        content = text or "(le document est fourni sous forme d'image, voir pièce jointe)"
        system, user = prompt.render(
            org_name=org.name, org_siren=org.siren, document_content=content
        )
        user_message: dict[str, Any] = {"role": "user", "content": user}
        if images:
            user_message["content"] = [{"type": "text", "text": user}, *images]
        result = llm.complete(
            db,
            org_id=org.id,
            task=self.task,
            messages=[{"role": "system", "content": system}, user_message],
            response_model=ReadingOut,
            prompt_version=prompt.version,
        )
        return ReadingResult(result.data, result.raw, result.model, prompt.version)


def get_document_reader() -> DocumentReader:
    return LLMDocumentReader()

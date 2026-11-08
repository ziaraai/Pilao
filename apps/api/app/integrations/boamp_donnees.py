"""What Pilao takes from « donnees », the whole BOAMP notice (JSON in a string).

Two shapes are met (docs/07 §1):
* European notices (``famille`` JOUE): ``{"EFORMS": {"ContractNotice": …}}``, the eForms UBL
  tree, also used by TED. Read by its exact paths: description and estimated amount of the
  procedure (``cac:ProcurementProject``), lots (``cac:ProcurementProjectLot``), link to the
  tender documents (``cac:CallForTendersDocumentReference`` → ``cbc:URI``), else the buyer
  profile (``cbc:BuyerProfileURI``).
* national notices (FNSimple and others): not seen yet in full, read by field names: the
  longest « description » / « objet » text, the first « montant » / « valeur » amount,
  the first link whose name speaks of documents or consultation, else of the buyer profile.

Nothing here raises: an odd notice gives empty details, never a failed import.
"""

import html
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

URL = re.compile(r"^https?://\S+$", re.IGNORECASE)


@dataclass(frozen=True)
class Lot:
    number: str | None
    title: str
    amount_eur: float | None = None


@dataclass(frozen=True)
class Details:
    description: str | None = None
    amount_eur: float | None = None
    documents_url: str | None = None
    lots: list[Lot] = field(default_factory=list)


def parse(raw: Any) -> Details:
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return Details()
    if not isinstance(data, dict):
        return Details()
    eforms = data.get("EFORMS")
    if isinstance(eforms, dict):
        root = next((v for v in eforms.values() if isinstance(v, dict)), None)
        if root is not None:
            return _eforms(root)
    return _by_names(data)


# ---------- eForms ------------------------------------------------------------------------


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _get(node: Any, *path: str) -> Any:
    for key in path:
        if isinstance(node, list):  # several: the first one
            node = node[0] if node else None
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _text(value: Any) -> str | None:
    """« abc », {"#text": "abc", "@languageID": "FRA"}, or a list of these: French first."""
    items = _list(value)
    texts = [
        (i.get("@languageID"), i.get("#text")) if isinstance(i, dict) else (None, i) for i in items
    ]
    texts = [(lang, str(t).strip()) for lang, t in texts if t is not None and str(t).strip()]
    for lang, text in texts:
        if lang in (None, "FRA"):
            return text
    return texts[0][1] if texts else None


def _amount(value: Any) -> float | None:
    raw = _text(value)
    if raw is None:
        return None
    cleaned = re.sub(r"[\s  €]", "", raw).replace(",", ".")
    try:
        amount = float(cleaned)
    except ValueError:
        return None
    return amount if amount > 0 else None


def _url(value: Any) -> str | None:
    raw = _text(value)
    return _link(raw) if raw else None


def _link(raw: str) -> str | None:
    """A web link as written in the notice, « &amp; » decoded (seen on the server)."""
    url = html.unescape(raw).strip()
    return url if URL.match(url) else None


def _eforms(root: dict[str, Any]) -> Details:
    project = root.get("cac:ProcurementProject")
    lots = []
    documents = None
    for item in _list(root.get("cac:ProcurementProjectLot")):
        lot_project = _get(item, "cac:ProcurementProject")
        title = _text(_get(lot_project, "cbc:Name"))
        if title:
            lots.append(
                Lot(
                    number=_text(_get(item, "cbc:ID")),
                    title=title[:1000],
                    amount_eur=_amount(
                        _get(
                            lot_project,
                            "cac:RequestedTenderTotal",
                            "cbc:EstimatedOverallContractAmount",
                        )
                    ),
                )
            )
        for ref in _list(_get(item, "cac:TenderingTerms", "cac:CallForTendersDocumentReference")):
            documents = documents or _url(
                _get(ref, "cac:Attachment", "cac:ExternalReference", "cbc:URI")
            )
    profile = None
    for party in _list(root.get("cac:ContractingParty")):
        profile = profile or _url(_get(party, "cbc:BuyerProfileURI"))
    amount = _amount(
        _get(project, "cac:RequestedTenderTotal", "cbc:EstimatedOverallContractAmount")
    )
    if amount is None and lots and all(lot.amount_eur is not None for lot in lots):
        amount = sum(lot.amount_eur or 0 for lot in lots)
    return Details(
        description=_text(_get(project, "cbc:Description")),
        amount_eur=amount,
        documents_url=documents or profile,
        lots=lots if len(lots) > 1 else [],
    )


# ---------- other shapes, by field names -----------------------------------------------


def _leaves(node: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], Any]]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _leaves(value, (*path, str(key)))
    elif isinstance(node, list):
        for value in node:
            yield from _leaves(value, path)
    else:
        yield path, node


def _by_names(data: dict[str, Any]) -> Details:
    description, amount, documents, profile = None, None, None, None
    for path, value in _leaves(data):
        if value is None:
            continue
        names = "/".join(path).lower()
        last = path[-1].lower() if path else ""
        text = str(value).strip()
        if URL.match(text):
            if documents is None and re.search(r"doc|consult|dce", last):
                documents = _link(text)
            elif profile is None and re.search(r"profil|acheteur|buyer", last):
                profile = _link(text)
            continue
        if re.search(r"description|objet", last) and len(text) > len(description or ""):
            description = text
        elif (
            amount is None
            and re.search(r"montant|valeur|estim", names)
            and not re.search(r"duree|delai|pourcent|taux", names)
        ):
            amount = _amount(text)
    return Details(
        description=description[:20_000] if description else None,
        amount_eur=amount,
        documents_url=documents or profile,
    )

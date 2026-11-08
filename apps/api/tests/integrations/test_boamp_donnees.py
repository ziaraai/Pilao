"""« donnees » of a BOAMP notice (P3-01). The eForms record below follows the UBL tree seen
on the server (``EFORMS`` → ``ContractNotice`` → ``ext:UBLExtensions``, ``@languageID`` /
``#text`` values) with the eForms paths of the procedure, the lots and the documents; the
national record is hand-written: its real shape is checked with ``--essai``."""

import json

from app.integrations.boamp_donnees import parse

EFORMS = {
    "EFORMS": {
        "ContractNotice": {
            "ext:UBLExtensions": {"ext:UBLExtension": {}},
            "cac:ContractingParty": {
                "cbc:BuyerProfileURI": "https://www.marches-publics.info/acheteur/42"
            },
            "cac:ProcurementProject": {
                "cbc:Name": {"@languageID": "FRA", "#text": "Nettoyage des locaux"},
                "cbc:Description": [
                    {"@languageID": "ENG", "#text": "Cleaning of the offices"},
                    {"@languageID": "FRA", "#text": "Nettoyage quotidien des bureaux et vitrerie"},
                ],
                "cac:RequestedTenderTotal": {
                    "cbc:EstimatedOverallContractAmount": {"@currencyID": "EUR", "#text": "1200000"}
                },
            },
            "cac:ProcurementProjectLot": [
                {
                    "cbc:ID": {"@schemeName": "Lot", "#text": "LOT-0001"},
                    "cac:TenderingTerms": {
                        "cac:CallForTendersDocumentReference": {
                            "cac:Attachment": {
                                "cac:ExternalReference": {
                                    "cbc:URI": "https://www.marches-publics.info/dce/1877603"
                                }
                            }
                        }
                    },
                    "cac:ProcurementProject": {
                        "cbc:Name": {"@languageID": "FRA", "#text": "Siège social"},
                        "cac:RequestedTenderTotal": {
                            "cbc:EstimatedOverallContractAmount": {"#text": "800000"}
                        },
                    },
                },
                {
                    "cbc:ID": {"@schemeName": "Lot", "#text": "LOT-0002"},
                    "cac:ProcurementProject": {
                        "cbc:Name": {"@languageID": "FRA", "#text": "Agences"},
                        "cac:RequestedTenderTotal": {
                            "cbc:EstimatedOverallContractAmount": {"#text": "400000"}
                        },
                    },
                },
            ],
        }
    }
}


def test_an_eforms_notice() -> None:
    d = parse(json.dumps(EFORMS))
    assert d.description == "Nettoyage quotidien des bureaux et vitrerie"  # French first
    assert d.amount_eur == 1_200_000
    assert d.documents_url == "https://www.marches-publics.info/dce/1877603"
    assert [(lot.number, lot.title, lot.amount_eur) for lot in d.lots] == [
        ("LOT-0001", "Siège social", 800_000),
        ("LOT-0002", "Agences", 400_000),
    ]


def test_eforms_fallbacks() -> None:
    notice = json.loads(json.dumps(EFORMS))
    root = notice["EFORMS"]["ContractNotice"]
    del root["cac:ProcurementProject"]["cac:RequestedTenderTotal"]  # sum of the lots
    del root["cac:ProcurementProjectLot"][0]["cac:TenderingTerms"]  # the buyer profile
    d = parse(json.dumps(notice))
    assert d.amount_eur == 1_200_000
    assert d.documents_url == "https://www.marches-publics.info/acheteur/42"
    root["cac:ProcurementProjectLot"] = root["cac:ProcurementProjectLot"][0]  # one lot: none
    assert parse(json.dumps(notice)).lots == []


def test_a_national_notice_by_field_names() -> None:
    d = parse(
        json.dumps(
            {
                "FNSimple": {
                    "initial": {
                        "communication": {
                            "urlProfilAcheteur": "https://www.achatpublic.com/acheteur",
                            "urlDocConsul": "https://www.achatpublic.com/dce/123",
                        },
                        "description": {
                            "objet": "Entretien des locaux de la mairie",
                            "descriptionDetaillee": "Nettoyage quotidien de la mairie et des écoles",
                            "valeurEstimee": {"valeur": "45 000,00", "devise": "EUR"},
                            "dureeMois": "36",
                        },
                    }
                }
            }
        )
    )
    assert d.description == "Nettoyage quotidien de la mairie et des écoles"  # the longest
    assert d.amount_eur == 45_000
    assert d.documents_url == "https://www.achatpublic.com/dce/123"


def test_odd_donnees_give_nothing() -> None:
    for raw in (None, "", "pas du json", "[1, 2]", json.dumps({"EFORMS": {"X": "y"}})):
        d = parse(raw)
        assert (d.description, d.amount_eur, d.documents_url, d.lots) == (None, None, None, [])

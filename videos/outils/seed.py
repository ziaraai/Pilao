"""Seed the fictitious company « Propreté Démo » through the API (local demo stack, real AI).

Usage: python seed.py <docs_dir> <state.json> <api_log> phase1|phase2|phase3
"""

import json
import re
import subprocess
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx

DOCS, STATE, LOG, PHASE = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
EMAIL, PW = "karim@proprete-demo.fr", "correct-horse-battery"
state = json.loads(STATE.read_text()) if STATE.exists() else {}
c = httpx.Client(base_url="http://localhost:8000", timeout=180, headers={"Origin": "http://localhost:3000"})


def save() -> None:
    STATE.write_text(json.dumps(state, indent=2))


def ok(res: httpx.Response, *codes: int) -> dict:
    if res.status_code not in (codes or (200, 201, 202, 204)):
        raise SystemExit(f"{res.request.method} {res.request.url} → {res.status_code} {res.text[:400]}")
    return res.json() if res.content else {}


def wait(what: str, check, timeout: int = 900, every: float = 4) -> object:
    start = time.time()
    while time.time() - start < timeout:
        value = check()
        if value:
            print(f"  {what}: ok ({int(time.time() - start)} s)")
            return value
        time.sleep(every)
    raise SystemExit(f"timeout: {what}")


def luhn_siret(prefix: str) -> str:
    for d in range(10):
        s = prefix + str(d)
        total = 0
        for i, ch in enumerate(reversed(s)):
            n = int(ch) * (2 if i % 2 else 1)
            total += n - 9 if n > 9 else n
        if total % 10 == 0:
            return s
    raise ValueError


def login() -> None:
    ok(c.post("/auth/login", json={"email": EMAIL, "password": PW}))


def phase1() -> None:
    siret = luhn_siret("9123456740001")
    if c.post("/auth/login", json={"email": EMAIL, "password": PW}).status_code == 200:
        return phase1_profile()
    ok(
        c.post(
            "/auth/register",
            json={
                "email": EMAIL,
                "password": PW,
                "full_name": "Karim Benali",
                "siret": siret,
                "org_name": "Propreté Démo",
                "accept_terms": True,
            },
        )
    )
    token = re.findall(r"verifier-email\?token=(\S+)", LOG.read_text())[-1]
    ok(c.post("/auth/verify-email", json={"token": token}))
    login()
    phase1_profile()


def phase1_profile() -> None:
    ok(
        c.put(
            "/profile/company",
            json={
                "name": "Propreté Démo",
                "legal_form": "SAS",
                "address_line": "12 rue des Artisans",
                "postal_code": "69007",
                "city": "Lyon",
                "phone": "04 78 00 00 00",
                "contact_email": "contact@proprete-demo.fr",
                "signatory_name": "Karim Benali",
                "signatory_role": "Gérant",
            },
        )
    )
    ok(
        c.put(
            "/profile",
            json={
                "trades": ["nettoyage_locaux", "vitrerie", "remise_en_etat"],
                "departments": ["69", "01", "38", "42"],
                "min_amount_cents": 2_000_000,
                "max_amount_cents": 60_000_000,
                "revenue_y1_cents": 186_000_000,
                "revenue_y2_cents": 171_500_000,
                "revenue_y3_cents": 158_200_000,
                "min_score_alert": 60,
                "apply_trade_defaults": True,
            },
        )
    )
    for ref in (
        {
            "client_name": "Commune de Saint-Aubin-du-Lac",
            "client_type": "public",
            "title": "Nettoyage des écoles et de la mairie",
            "location": "Saint-Aubin-du-Lac",
            "department": "69",
            "amount_cents": 9_500_000,
            "year": 2023,
            "duration_months": 36,
        },
        {
            "client_name": "Habitat Val-de-Saône",
            "client_type": "public",
            "title": "Entretien des parties communes de 420 logements",
            "location": "Villefranche",
            "department": "69",
            "amount_cents": 12_800_000,
            "year": 2022,
            "duration_months": 48,
        },
    ):
        ok(c.post("/profile/references", json=ref))
    with (DOCS / "Memoire_CCI_2024.docx").open("rb") as f:
        doc = ok(
            c.post(
                "/knowledge",
                data={"kind": "past_memoir", "title": "Mémoire CCI 2024"},
                files={"file": ("Memoire_CCI_2024.docx", f, "application/octet-stream")},
            )
        )
    state["knowledge_id"] = doc["id"]
    vault = {}
    for name, kind in (("Attestation_URSSAF.pdf", "urssaf_vigilance"), ("Kbis_Proprete_Demo.pdf", "kbis")):
        with (DOCS / name).open("rb") as f:
            vault[kind] = ok(
                c.post("/vault", data={"kind": kind}, files={"file": (name, f, "application/pdf")})
            )["id"]
    state["vault"] = vault
    save()
    print("phase1 ok")


def load_tenders() -> None:
    now = datetime.now(UTC)
    deadline = (date.today() + timedelta(days=21)).isoformat() + "T10:00:00+00:00"

    def notice(i: int, title: str, buyer: str, cpv: str, dep: str, amount: float, days: int, desc: str) -> dict:
        return {
            "source": "boamp" if i % 3 else "ted",
            "source_id": f"DEMO-PILAO-{i}",
            "title": title,
            "description": desc,
            "buyer_name": buyer,
            "procedure": "Procédure adaptée",
            "contract_nature": "services",
            "cpv_codes": [cpv],
            "departments": [dep],
            "estimated_amount_eur": amount,
            "published_at": (now - timedelta(days=1)).isoformat(),
            "deadline_at": deadline
            if i == 1
            else (date.today() + timedelta(days=days)).isoformat() + "T10:00:00+00:00",
            "notice_url": f"https://www.boamp.fr/avis/detail/DEMO-{i}",
        }

    notices = [
        notice(1, "Nettoyage et entretien des bâtiments communaux", "Ville de Belmont-sur-Rhône", "90911200", "69", 180000, 21,
               "Nettoyage quotidien de l'hôtel de ville, de la médiathèque et de deux groupes scolaires (6 630 m²), vitrerie trimestrielle et remise en état estivale des écoles. Marché d'un an reconductible trois fois."),
        notice(2, "Entretien ménager des locaux du centre aquatique intercommunal", "Communauté de communes Val-de-Saône", "90911200", "01", 95000, 28,
               "Entretien quotidien des vestiaires, sanitaires et halls du centre aquatique, désinfection des plages, sept jours sur sept."),
        notice(3, "Nettoyage des vitres des bâtiments du syndicat", "Syndicat intercommunal des Trois Rivières", "90911300", "42", 38000, 33,
               "Nettoyage semestriel des vitreries intérieures et extérieures de cinq bâtiments administratifs, travaux en hauteur."),
        notice(4, "Remise en état de logements après travaux", "Office public de l'habitat Rhône-Sud", "90911200", "69", 64000, 19,
               "Nettoyage de fin de chantier et remise en état de 120 logements réhabilités : sols, menuiseries, vitrages, sanitaires."),
        notice(5, "Prestations de nettoyage des locaux administratifs et techniques", "Centre hospitalier de Belmont", "90919200", "69", 240000, 40,
               "Nettoyage des bureaux, salles de réunion et locaux techniques (hors zones de soins) d'un centre hospitalier."),
        notice(6, "Travaux de réfection de voirie", "Ville de Belmont-sur-Rhône", "45233140", "69", 400000, 25,
               "Reprise de chaussée et de trottoirs."),
    ]
    path = DOCS / "annonces.json"
    path.write_text(json.dumps(notices, ensure_ascii=False))
    out = subprocess.run(
        ["uv", "run", "python", "-m", "app.cli", "load-tenders", str(path)],
        cwd=str(Path(__file__).resolve().parents[2] / "apps" / "api"),
        capture_output=True,
        text=True,
    )
    print(out.stdout[-400:], out.stderr[-400:])


def phase2() -> None:
    login()
    load_tenders()
    wait("knowledge indexed", lambda: c.get(f"/knowledge/{state['knowledge_id']}").json()["status"] == "ready")
    # vault: wait for the AI reading, then confirm the dates (the Kbis is too old: expired)
    today = date.today()
    for kind, doc_id in state["vault"].items():
        wait(f"vault {kind} read", lambda d=doc_id: c.get(f"/vault/{d}").json().get("reading_status") in ("done", "error", "ready", "unavailable"), 300)
        issued = today - timedelta(days=40 if kind == "urssaf_vigilance" else 100)
        until = issued + timedelta(days=180 if kind == "urssaf_vigilance" else 90)
        ok(
            c.put(
                f"/vault/{doc_id}/confirm",
                json={
                    "kind": kind,
                    "issuer": "URSSAF Rhône-Alpes" if kind == "urssaf_vigilance" else "Greffe du tribunal de commerce de Lyon",
                    "siren_on_document": "912345674",
                    "issued_at": issued.isoformat(),
                    "valid_until": until.isoformat(),
                },
            )
        )
    # profile pre-fill from the old memoir (real AI)
    ok(c.post("/profile/suggestions/read"))
    body = wait(
        "profile pre-fill",
        lambda: (lambda b: b if b["job"] and b["job"]["status"] in ("done", "error") else None)(
            c.get("/profile/suggestions").json()
        ),
    )
    print("  suggestions:", [(i["kind"], i["data"], i["missing"]) for i in body["items"]], body["job"])
    state["suggestions"] = body["items"]
    save()
    # notices scored, then follow the Belmont one
    tenders = wait(
        "notices scored",
        lambda: (lambda t: t if t["items"] and all(i["score"] is not None for i in t["items"]) else None)(
            c.get("/tenders", params={"status": "new"}).json()
        ),
        600,
    )
    print("  scores:", [(t["title"][:40], t["score"]) for t in tenders["items"]])
    belmont = next(t for t in tenders["items"] if "bâtiments communaux" in t["title"])
    aqua = next(t for t in tenders["items"] if "aquatique" in t["title"])
    state["bid"] = ok(c.post(f"/tenders/{belmont['tender_id']}/track"))["id"]
    state["bid_aqua"] = ok(c.post(f"/tenders/{aqua['tender_id']}/track"))["id"]
    with (DOCS / "DCE_Belmont_nettoyage.zip").open("rb") as f:
        ok(c.post(f"/bids/{state['bid']}/dce", files=[("files", ("DCE_Belmont_nettoyage.zip", f, "application/zip"))]))
    save()
    wait(
        "DCE analysed",
        lambda: c.get(f"/bids/{state['bid']}/analysis").json().get("status") in ("ready", "error")
        if c.get(f"/bids/{state['bid']}/analysis").status_code == 200
        else None,
        900,
        8,
    )
    a = c.get(f"/bids/{state['bid']}/analysis").json()
    print("  analysis:", a["status"], a.get("error"))
    print("phase2 ok")


def phase3() -> None:
    login()
    # accept the pre-fill proposals (completed where needed) so the memoir knows the means
    body = c.get("/profile/suggestions").json()
    items = []
    for s in body["items"]:
        data = dict(s["data"])
        if s["kind"] == "human_resource" and data.get("count") is None:
            data["count"] = 1
        if s["kind"] == "reference":
            data.setdefault("client_type", None)
            data["client_type"] = data["client_type"] or ("public" if "Département" in (data.get("client_name") or "") else "private")
            data["title"] = data.get("title") or "Prestations de nettoyage"
        items.append({"id": s["id"], "data": data})
    if items:
        print("  accept:", ok(c.post("/profile/suggestions/accept", json={"items": items})))
    memoir = ok(c.post(f"/bids/{state['bid']}/memoir"))
    state["memoir"] = memoir["id"]
    save()
    ok(c.post(f"/memoirs/{state['memoir']}/generate"))
    wait(
        "memoir drafted",
        lambda: (lambda m: all(s["status"] in ("ready", "error") for s in m["sections"]) and m["sections"])(
            c.get(f"/memoirs/{state['memoir']}").json()
        ),
        1200,
        8,
    )
    m = c.get(f"/memoirs/{state['memoir']}").json()
    print("  sections:", [(s["title"], s["status"]) for s in m["sections"]])
    for kind in ("dc1", "dc2"):
        ok(c.post(f"/bids/{state['bid']}/documents/{kind}"))
    # an earlier offer, won, for « Vos résultats »
    won = ok(c.post("/bids", json={"title": "Nettoyage des écoles et de la mairie", "buyer_name": "Commune de Saint-Aubin-du-Lac"}))
    ok(c.patch(f"/bids/{won['id']}", json={"status": "submitted", "submitted_amount_cents": 9_480_000}))
    ok(c.patch(f"/bids/{won['id']}", json={"status": "won", "result_rank": 1, "minutes_with_pilao": 150, "minutes_usual": 600}))
    save()
    print("phase3 ok")


{"phase1": phase1, "phase2": phase2, "phase3": phase3}[PHASE]()

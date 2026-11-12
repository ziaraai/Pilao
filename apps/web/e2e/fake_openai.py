"""Minimal OpenAI-compatible server: DCE analysis, chapters, conformity, notice scores."""
import json, re, sys
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

DEADLINE = (datetime.now(UTC) + timedelta(days=30)).replace(microsecond=0).isoformat()
RC, CCTP = "DCE/RC.pdf", "DCE/CCTP.pdf"
ANSWER = {
    "key_info": {
        "buyer_name": {"value": "Ville de Lyon", "source": {"file": RC, "page": 1}},
        "title": {"value": "Nettoyage des bureaux de la mairie", "source": {"file": RC, "page": 1}},
        "submission_deadline": {"value": DEADLINE, "source": {"file": RC, "page": 1}},
        "estimated_amount_eur_ht": {"value": 120000, "source": {"file": RC, "page": 1}},
        "lots": [],
    },
    "site_visit": {"mandatory": False, "dates": [], "source": {"file": RC, "page": 1}},
    "award_criteria": [
        {"name": "Valeur technique", "weight_pct": 60, "source": {"file": RC, "page": 2}},
        {"name": "Prix", "weight_pct": 40, "source": {"file": RC, "page": 2}},
    ],
    "memoir_requirements": {"imposed_outline": ["1. Moyens", "2. Méthodologie"], "max_pages": 10, "source": {"file": RC, "page": 2}},
    "required_documents": [
        {"name": "Attestation de vigilance URSSAF", "phase": "candidature", "source": {"file": RC, "page": 2}},
        {"name": "Extrait Kbis", "phase": "candidature", "source": {"file": RC, "page": 2}},
    ],
    "requirements": [
        {"ref": "CCTP-1", "text": "Nettoyage quotidien des bureaux avant 8h", "category": "schedule", "importance": "mandatory", "source": {"file": CCTP, "page": 1}},
        {"ref": "CCTP-2", "text": "Vitrerie intérieure une fois par trimestre", "category": "frequency", "importance": "mandatory", "source": {"file": CCTP, "page": 2}},
        {"ref": "CCTP-3", "text": "Produits écolabellisés", "category": "product", "importance": "expected", "source": {"file": CCTP, "page": 2}},
    ],
    "watch_points": [{"text": "Pénalités de retard prévues au CCAP", "severity": "warning", "source": {"file": RC, "page": 1}}],
}


def chapter(prompt):
    """A careful writer: answers its requirements, never invents a number (CCTP-3 needs asking)."""
    title = re.search(r"Chapitre à rédiger : \*\*(.+?)\*\*", prompt).group(1)
    asked = "Consigne de l'entreprise" in prompt
    refs = [r for r in re.findall(r"^- \[(CCTP-\d+)\]", prompt, re.M) if r != "CCTP-3" or asked]
    excerpts = re.findall(r'<excerpt id="([^"]+)"', prompt)
    lines = [f"## {title}", "", "Notre organisation pour ce marché :", ""]
    lines += [f"- Exigence {r} : nous la traitons dans ce chapitre." for r in refs]
    lines += ["", "| Zone | Fréquence |", "|---|---|", "| Bureaux | **quotidienne** |", "",
              "Nous nous engageons à intervenir sous 2 heures.", "",
              "Équipe dédiée : [À COMPLÉTER : nombre d'agents affectés au site]."]
    return {"markdown": "\n".join(lines), "covered_requirements": refs,
            "sources": [{"excerpt_id": e, "used_for": "matériel"} for e in excerpts[:1]],
            "to_complete": ["nombre d'agents affectés au site"], "commitments": []}


def matrix(prompt):
    sections = re.findall(r'<section id="([^"]+)" title="[^"]*">\n(.*?)\n</section>', prompt, re.S)
    items = []
    for ref in re.findall(r"^- \[(CCTP-\d+)\]", prompt, re.M):
        quote = f"Exigence {ref} : nous la traitons dans ce chapitre."
        home = next((sid for sid, text in sections if quote in text), None)
        items.append({"requirement_ref": ref, "status": "covered" if home else "missing",
                      "section_id": home, "excerpt": quote if home else None,
                      "comment": None if home else "Le mémoire n'en parle pas."})
    return {"items": items}


def profile(prompt):
    # US-1.6: lines written in the e2e memoir (fixtures.py); the staff line already in the
    # profile must not be proposed again.
    return {"equipment": [{"name": "Autolaveuse Tennant T5", "category": "Autolaveuses",
                           "quantity": 3, "excerpt": "3 autolaveuses Tennant T5"}],
            "human_resources": [
                {"qualification": "Chef d'équipe", "count": None, "excerpt": "2 chefs d'equipe"},
                {"qualification": "Agent de service", "count": None, "excerpt": "agents de service"}]}


def score(prompt):
    core = "médiathèque" in prompt
    return {"score": 82 if core else 64,
            "explanation": "Cœur de métier dans votre département." if core
            else "Prestation voisine de votre activité.", "relevant_lots": []}


MODEL = {"pricing": {"prompt": "0.0000001", "completion": "0.0000005"}, "context_length": 128000,
         "architecture": {"input_modalities": ["text"]}, "supported_parameters": ["response_format"]}
CATALOGUE = [  # lot 5: OpenRouter's catalogue, as the administration reads it
    {**MODEL, "id": "fake-extraction", "name": "Fake Extraction"},
    {**MODEL, "id": "fake-generation", "name": "Fake Generation"},
    {**MODEL, "id": "fake-scoring", "name": "Fake Scoring"},
    {**MODEL, "id": "fake-scoring-2", "name": "Fake Scoring 2"},
    {**MODEL, "id": "fake-free:free", "name": "Fake Free"},
]


class H(BaseHTTPRequestHandler):
    def _json(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(data))); self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # lot 5: OpenRouter's catalogue, key check and credit
        good = self.headers.get("authorization", "").startswith("Bearer sk-or-v1-e2e")
        if self.path.endswith("/models"):
            return self._json(200, {"data": CATALOGUE})
        if self.path.endswith("/key"):
            return self._json(200 if good else 401, {"data": {"usage": 0.1}} if good else {"error": "no"})
        if self.path.endswith("/credits"):
            return self._json(200, {"data": {"total_credits": 5, "total_usage": 1.32}})
        return self._json(404, {})

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
        prompt = request["messages"][1]["content"] if len(request.get("messages", [])) > 1 else ""
        system = request["messages"][0]["content"] if request.get("messages") else ""
        answer = ({"ok": True} if '{"ok": true}' in system  # lot 5: a model's trial
                  else profile(prompt) if "<profile_document" in prompt
                  else chapter(prompt) if "Chapitre à rédiger" in prompt
                  else matrix(prompt) if "<memoir>" in prompt
                  else score(prompt) if "<tender>" in prompt else ANSWER)
        body = {"id": "x", "object": "chat.completion", "created": 0, "model": "fake",
                "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(answer)}}],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500}}
        data = json.dumps(body).encode()
        self.send_response(200); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(data))); self.end_headers()
        self.wfile.write(data)
    def log_message(self, *a): pass

HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()

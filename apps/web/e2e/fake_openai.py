"""Minimal OpenAI-compatible server: answers the DCE analysis with sourced data."""
import json, sys
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

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("content-length", 0)))
        body = {"id": "x", "object": "chat.completion", "created": 0, "model": "fake",
                "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(ANSWER)}}],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500}}
        data = json.dumps(body).encode()
        self.send_response(200); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(data))); self.end_headers()
        self.wfile.write(data)
    def log_message(self, *a): pass

HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()

---
id: lecture_attestation
version: 0.1.0
task: compliance_document_reading
input: image(s) ou texte d'un document administratif
---

# Système

Tu lis un document administratif français déposé par une entreprise et tu en extrais les informations utiles pour un dossier de marché public. Tu n'inventes rien : si une information n'est pas lisible, mets `null`.

Types possibles : `kbis`, `rne_certificate`, `urssaf_vigilance`, `tax_compliance`, `cibtp_certificate`, `insurance_rc_pro`, `insurance_decennale`, `qualification`, `other`.

Règles de validité :
- `urssaf_vigilance` : valable 6 mois à partir de la date de délivrance si aucune date de fin n'est écrite.
- `kbis` : souvent exigé de moins de 3 mois ; mettre `valid_until` = date de délivrance + 3 mois et `validity_rule` = "kbis_3_months".
- Autres : date de fin écrite sur le document.

Réponds uniquement en JSON.

# Utilisateur

Entreprise attendue : {{org_name}} — SIREN {{org_siren}}

Document :
{{document_content}}

Réponds :
```json
{
  "kind": "urssaf_vigilance",
  "issuer": "URSSAF …",
  "holder_name": "…",
  "siren_on_document": "123456789",
  "issued_at": "2026-10-15",
  "valid_until": "2027-04-15",
  "validity_rule": "written | urssaf_6_months | kbis_3_months",
  "verification_code": "… ou null",
  "confidence": 0.0
}
```

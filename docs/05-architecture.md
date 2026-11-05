# 05 — Architecture

## Vue d'ensemble

```
            ┌────────────────────┐
            │  apps/web (Next.js) │  interface FR, éditeur de mémoire
            └─────────┬──────────┘
                      │ HTTPS (JSON, auth par session/JWT)
            ┌─────────▼──────────┐
            │  apps/api (FastAPI) │  logique métier, multi-tenant
            └──┬──────┬───────┬──┘
               │      │       │ enqueue
     ┌─────────▼┐ ┌───▼────┐ ┌▼──────────────────┐
     │PostgreSQL│ │ S3 (UE)│ │ Redis + worker(s)  │
     │+pgvector │ │fichiers│ │ import AO, analyse │
     └──────────┘ └────────┘ │ DCE, génération    │
                             └──┬──────────┬──────┘
                                │          │
                     ┌──────────▼──┐  ┌────▼─────────────┐
                     │ API externes │  │ app/ai/llm.py     │
                     │ BOAMP, TED,  │  │ (LiteLLM →        │
                     │ SIRENE       │  │  OpenRouter / UE) │
                     └─────────────┘  └──────────────────┘
```

## Arborescence proposée (monorepo)

```
pilao/
├── CLAUDE.md
├── docs/ prompts/ schemas/ data/          # cette base de connaissance
├── apps/
│   ├── web/                               # Next.js
│   │   ├── app/(auth)/ app/(app)/
│   │   │   ├── dashboard/  tenders/  bids/[id]/  profile/  vault/  settings/
│   │   ├── components/  lib/api.ts  lib/i18n/fr.ts
│   └── api/                               # FastAPI + worker
│       ├── app/
│       │   ├── main.py
│       │   ├── core/        config.py, security.py, tenancy.py, logging.py
│       │   ├── db/          base.py, session.py, models/*.py
│       │   ├── schemas/     pydantic (miroir de /schemas/*.json)
│       │   ├── routers/     auth, orgs, profile, tenders, bids, dce, memoirs, vault, exports
│       │   ├── services/    logique métier par module
│       │   ├── integrations/ boamp.py, ted.py, recherche_entreprises.py
│       │   ├── documents/   extract.py (pdf/docx/xlsx), ocr.py, classify.py, chunk.py
│       │   ├── ai/          llm.py, embeddings.py, prompts.py (charge /prompts), costs.py
│       │   ├── exports/     docx_builder.py, pdf.py, dc_forms.py
│       │   └── workers/     jobs.py, schedules.py
│       ├── alembic/
│       └── tests/           unit/, api/, ai/ (cas de test des prompts), fixtures/
├── infra/
│   ├── docker-compose.yml               # postgres(pgvector), redis, minio
│   └── deploy/                          # à définir (Scaleway / OVHcloud)
└── samples/                             # DCE réels — NON VERSIONNÉ (.gitignore)
```

## Tâches de fond (worker)

| Job | Déclencheur | Description |
|---|---|---|
| `import_boamp` | Planifié, 2×/jour minimum | Récupère les nouvelles annonces, upsert `tenders` |
| `import_ted` | Planifié, 1×/jour | Idem, filtré sur la France |
| `match_tenders(org_id?)` | Après import, ou changement de profil | Pré-filtre + score IA → `tender_matches` |
| `index_knowledge_document(doc_id)` | Dépôt d'un document | Extraction, découpage, embeddings |
| `process_dce(bid_id, version)` | Dépôt d'un DCE | Décompression, typage, extraction, OCR |
| `analyze_dce(bid_id)` | Après `process_dce` | Fiche d'analyse + exigences |
| `generate_memoir(bid_id)` | Action utilisateur | Plan → chapitres → matrice |
| `read_compliance_document(doc_id)` | Dépôt d'une attestation | Lecture IA des dates |
| `send_daily_digest` | Planifié, 7 h (Paris) | E-mail des nouvelles annonces |
| `check_expirations` | Planifié, 1×/jour | Alertes J-30 / J-7 |

Chaque job est **idempotent** et met à jour un statut visible (`pending`, `running`, `done`, `error` + message).

## Variables d'environnement

```dotenv
DATABASE_URL=postgresql+psycopg://pilao:pilao@localhost:5432/pilao
REDIS_URL=redis://localhost:6379/0
S3_ENDPOINT=http://localhost:9000
S3_BUCKET=pilao-local
S3_ACCESS_KEY=...
S3_SECRET_KEY=...
S3_REGION=fr-par
APP_SECRET_KEY=...
APP_BASE_URL=http://localhost:3000
# IA
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=...
LLM_MODEL_EXTRACTION=...        # à fixer après la phase 0
LLM_MODEL_GENERATION=...
LLM_MODEL_SCORING=...
LLM_MODEL_VISION=...
EMBEDDING_MODEL=...
AI_MONTHLY_BUDGET_EUR_PER_ORG=50   # garde-fou
# Intégrations
BOAMP_BASE_URL=https://boamp-datadila.opendatasoft.com/api/explore/v2.1
TED_BASE_URL=https://api.ted.europa.eu/v3
RECHERCHE_ENTREPRISES_BASE_URL=https://recherche-entreprises.api.gouv.fr
# Export PDF (worker) : LibreOffice headless
SOFFICE_PATH=soffice
PDF_TIMEOUT_SECONDS=180
# E-mail (plus tard)
SMTP_URL=...
```

## Principes

- **Multi-tenant par ligne** : `org_id` partout + dépendance FastAPI `get_current_org()` qui injecte le filtre. Tests automatiques qui vérifient qu'un utilisateur de l'org A ne voit rien de l'org B.
- **Couche IA unique** : `app/ai/llm.py` expose `complete(task, messages, schema=None)` ; le modèle est choisi par tâche via la config. Journalisation des coûts dans `ai_calls`.
- **Prompts en fichiers** : chargés depuis `/prompts` avec un numéro de version dans l'en-tête ; la version est enregistrée avec chaque résultat.
- **Fichiers** : jamais servis directement ; URL signées à durée courte.

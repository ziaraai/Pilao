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
│   │   ├── app/(auth)/ app/(app)/ app/(admin)/   # (admin) : l'administration de la plateforme (ADR-040)
│   │   │   ├── dashboard/  tenders/  bids/[id]/  profile/  vault/  settings/
│   │   ├── components/ (admin/ : coquille et blocs de l'administration ; module-gate.tsx)  lib/api.ts  lib/admin.ts  lib/modules.ts
│   └── api/                               # FastAPI + worker
│       ├── app/
│       │   ├── main.py
│       │   ├── modules.py   registre des modules (veille, reponse) — ADR-041
│       │   ├── core/        config.py, security.py, tenancy.py, logging.py, crypto.py, admin_deps.py
│       │   ├── db/          base.py, session.py, models/*.py
│       │   ├── schemas/     pydantic (miroir de /schemas/*.json)
│       │   ├── routers/     auth, orgs, profile, tenders, bids, dce, memoirs, vault, exports ; admin/ (auth, supervision)
│       │   ├── services/    logique métier par module ; admin/ (access, auth, audit, supervision)
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
| `fetch_dce(fetch_id)` | « Récupérer le DCE », ou une mise à jour trouvée | Robot Playwright (Chromium sans écran, `app/integrations/atexo.py`) sur PLACE et Atexo : ZIP déposé comme un dépôt (ADR-045) ; une tâche à la fois par site (verrou Redis), 600 s au plus |
| `watch_dces` | Planifié, 05:40 UTC (06:40 Paris en hiver) | Relit la page des consultations récupérées par le robot : nouvelle version, date limite, 3 échecs → surveillance interrompue |
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
USD_EUR_RATE=0.86                  # prix des fournisseurs en dollars → coûts et budget en euros
LLM_REASONING_TOKENS=8000          # marge pour le raisonnement caché des modèles, en plus de la réponse
LLM_DENY_DATA_COLLECTION=true      # OpenRouter : écarte les fournisseurs qui conservent les requêtes
LLM_ZERO_DATA_RETENTION=false      # true : uniquement les fournisseurs qui ne gardent rien (plus strict)
LOGIN_ATTEMPTS_RETENTION_DAYS=30   # puis effacées (tâche horaire)
INVITATION_TTL_HOURS=168           # lien d'invitation d'un collaborateur (7 jours)
MAX_USERS_PER_ORG=25               # garde-fou en attendant les formules
FEEDBACK_EMAIL=equipe@…            # chaque avis « Votre avis » y est transmis aussitôt
SMTP_HOST=… SMTP_PORT=587 SMTP_USER=… SMTP_PASSWORD=… SMTP_FROM=…  # envoi des e-mails (ADR-032)
SMTP_VERIFY_TLS=true               # false seulement pour la messagerie du serveur lui-même
STORAGE_BACKEND=s3                 # ou disk : fichiers sur le disque d'un seul serveur (ADR-033)
STORAGE_DIR=/data/files            # avec disk
API_PUBLIC_URL=https://…/api       # avec disk : base des liens de téléchargement signés
EMBEDDING_PRICE_USD_PER_MILLION=0.1  # quand le fournisseur ne renvoie pas le coût
# Intégrations
TED_API_URL=https://api.ted.europa.eu
TED_IMPORT_ENABLED=true
BOAMP_API_URL=https://boamp-datadila.opendatasoft.com/api/explore/v2.1
BOAMP_IMPORT_ENABLED=false
TENDER_IMPORT_BACKFILL_DAYS=14
RECHERCHE_ENTREPRISES_BASE_URL=https://recherche-entreprises.api.gouv.fr
# Export PDF (worker) : LibreOffice headless
SOFFICE_PATH=soffice
PDF_TIMEOUT_SECONDS=180
# E-mail (plus tard)
SMTP_URL=...
# Robot de récupération des DCE (ADR-045) ; l'admin peut le couper (dce_robot.enabled)
DCE_ROBOT_ENABLED=true
DCE_ROBOT_ALLOW_PRIVATE_HOSTS=false   # vrai seulement pour les tests et le parcours local
DCE_ROBOT_BROWSER_PATH=               # vide : le Chromium installé par Playwright (/opt/pw-browsers dans l'image)
```

## Principes

- **Multi-tenant par ligne** : `org_id` partout + dépendance FastAPI `get_current_org()` qui injecte le filtre. Tests automatiques qui vérifient qu'un utilisateur de l'org A ne voit rien de l'org B.
- **Modules** (ADR-041, lot 3) : `app/modules.py` déclare chaque module (clé, nom, contenu, entrées de menu) ; `organizations.modules` liste ceux d'une entreprise. La dépendance `require_module(clé)` (`core/deps.py`), posée sur le routeur entier d'un module, refuse ses routes (403 `module_disabled`) après la connexion et la suspension ; le travail de fond d'un module saute les entreprises qui ne l'ont pas. Côté web, `lib/modules.ts` filtre le menu et `ModuleGate` remplace les pages d'un module absent par une carte. Ajouter un module = son code + une entrée de `MODULES`.
- **Crédits** (ADR-043, lot 4) : chaque module déclare ses actions payantes dans `app/modules.py` (`PaidAction`) ; `app/services/credits.py` est le seul endroit qui écrit le journal des crédits (`credit_entries`) : prise au lancement d'une action (`lock_org` : `FOR NO KEY UPDATE` sur la ligne de l'entreprise, pris au début de l'action), remboursement automatique quand son travail finit en erreur (`set_job_status`), recharges, crédits offerts. Les travaux laissés pour morts sont fermés (donc remboursés) par `app/services/stale_works.py`, planifié toutes les 15 minutes dans `app/workers/cron.py`. Le solde est calculé (`app/domain/credits.py` : mois de Paris, crédits du mois puis supplémentaires), jamais stocké. Aucun montant en euros ne sort vers l'espace client.
- **Réglages de la plateforme** (ADR-044, lot 5) : `app/platform_settings.py` déclare les réglages modifiables depuis l'admin (modèle de chaque tâche, clé OpenRouter, imports, budget d'IA, adresses) avec leur valeur du serveur (`Settings`) ; `app/core/runtime.py` donne la valeur en usage (celle de `platform_settings`, sinon celle du serveur) à partir d'un instantané relu au plus toutes les 30 secondes par processus. Le code ne lit plus ces réglages dans `get_settings()` : `llm.model_for`, la clé passée à LiteLLM (`api_key`), le budget, les adresses et `tender_import.readers` passent par `runtime`. `app/ai/openrouter.py` est le seul client HTTP d'OpenRouter hors LiteLLM (catalogue, clé, crédit).
- **Couche IA unique** : `app/ai/llm.py` expose `complete(task, messages, schema=None)` ; le modèle est choisi par tâche via la config. Journalisation des coûts dans `ai_calls`.
- **Prompts en fichiers** : chargés depuis `/prompts` avec un numéro de version dans l'en-tête ; la version est enregistrée avec chaque résultat.
- **Fichiers** : jamais servis directement ; URL signées à durée courte.

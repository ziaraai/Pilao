# 06 — Modèle de données (PostgreSQL)

Conventions : `id uuid pk default gen_random_uuid()`, `created_at` / `updated_at timestamptz`, montants en **centimes** (`bigint`), toutes les tables métier ont `org_id uuid not null references organizations(id)` (sauf tables globales signalées).

## Comptes

```sql
organizations (
  id, siren char(9) not null, siret char(14) unique not null,
  name text not null, legal_form text, naf_code text,
  address_line text, postal_code text, city text, department char(3),
  headcount_range text, logo_file_id uuid null,
  brand_color text null,                       -- couleur des titres des documents Word
  phone text, contact_email text,              -- pré-remplissage DC1/DC2 (saisis une fois)
  signatory_name text, signatory_role text,    -- personne habilitée à engager l'entreprise
  suspended_at timestamptz null,               -- suspendue par l'administration (lot 2)
  suspension_reason text null,                 -- raison saisie par Pilao, jamais montrée au client
  modules text[] not null default '{veille,reponse}',  -- modules actifs (lot 3, ADR-041 ; clés de app/modules.py)
  plan_id uuid not null -> plans,              -- sa formule (lot 4) ; à la création : la formule par défaut
  welcome_credits_at timestamptz null,         -- crédits offerts déjà donnés (jamais deux fois)
  created_at, updated_at
)

users (
  id, org_id, email citext unique not null, full_name text,
  role text check (role in ('org_admin','org_member')) not null,
  password_hash text, email_verified_at timestamptz, last_login_at timestamptz
)

-- Administration de la plateforme (ADR-040) : tables globales, jamais filtrées par org_id
platform_admins (
  id, email citext unique, full_name text, password_hash text,
  totp_secret_enc text,              -- secret de l'application d'authentification, chiffré (core/crypto.py)
  totp_confirmed_at timestamptz,     -- vide tant que l'activation n'est pas finie
  totp_last_step bigint,             -- dernier pas de temps accepté : un code ne sert qu'une fois
  recovery_codes jsonb default '[]', -- empreintes SHA-256 des codes de secours restants
  setup_token_hash char(64) unique, setup_expires_at timestamptz,   -- lien d'activation, 30 min
  last_login_at timestamptz, disabled_at timestamptz
)
platform_admin_sessions ( id, admin_id -> platform_admins cascade, token_hash char(64) unique,
                          expires_at, revoked_at, user_agent, ip inet )         -- 12 h
platform_audit_logs ( id, admin_id -> platform_admins set null, admin_email text, action text,
                      org_id uuid null,  -- sans clé étrangère : la ligne survit à l'entreprise
                      at timestamptz, ip inet, meta jsonb )                      -- 12 mois

-- Formules et crédits (lot 4, ADR-043)
platform_settings ( key text pk, value jsonb null, secret text null, secret_last4 text null,
                    updated_at, updated_by -> platform_admins set null )
  -- lot 5 (ADR-044) : une ligne par réglage changé dans l'admin ; pas de ligne = valeur du
  -- serveur. La clé OpenRouter : `secret` chiffré (Fernet, clé dérivée d'APP_SECRET_KEY).

plans ( id, name text (unique, sans la casse), description text, modules text[],
        monthly_credits int, welcome_credits int, price_note text,   -- price_note : pour l'exploitant seul
        is_default bool (une seule à vrai), archived_at timestamptz null, created_at, updated_at )
credit_prices ( action text pk, credits int, updated_at )   -- sans ligne : le prix de départ du registre
credit_entries ( id, org_id, at, kind text check in ('charge','refund','grant','welcome'), action text null,
                 monthly int, extra int,       -- négatifs pour une prise : où elle a été prise
                 month date null,              -- 1er jour du mois de Paris de la prise
                 bid_id -> bids set null, user_id -> users set null, platform_admin_id -> platform_admins set null,
                 reason text null, ref_id uuid null,             -- le travail payé (analyse, mémoire, chapitre…)
                 refund_of uuid unique -> credit_entries )        -- un remboursement, une seule fois
```

## Profil

```sql
company_profiles (                      -- 1 ligne par org
  org_id pk, trades text[],             -- ex. {'nettoyage_locaux','vitrerie'}
  cpv_codes text[], keywords_include text[], keywords_exclude text[],
  departments text[], max_distance_km int null,
  min_amount_cents bigint null, max_amount_cents bigint null,
  revenue_y1_cents bigint, revenue_y2_cents bigint, revenue_y3_cents bigint,
  min_score_alert int default 60, completeness_pct int default 0
)

human_resources ( id, org_id, qualification text, count int, description text )
equipment       ( id, org_id, name text, category text, quantity int, spec_file_id uuid null )
certifications  ( id, org_id, name text, number text, valid_until date, file_id uuid null )

company_references (                    -- "references" est un mot réservé SQL
  id, org_id, client_name text, client_type text check (client_type in ('public','private')),
  title text, location text, department char(3), amount_cents bigint,
  year int, duration_months int, description text, cpv_codes text[],
  photo_file_ids uuid[], embedding vector(?)  -- dimension selon le modèle choisi
)

profile_suggestions (                   -- US-1.6 : lignes proposées depuis les documents
  id, org_id, kind text check (kind in ('human_resource','equipment','certification','reference')),
  data jsonb,                           -- les champs, au format de la saisie du profil
  missing text[],                       -- champs obligatoires encore vides
  document_id uuid references knowledge_documents on delete cascade,
  page smallint null, heading text null, excerpt text,  -- la source : phrase recopiée
  key text,                             -- clé normalisée (doublons)
  status text check (status in ('pending','accepted','dismissed'))
)
-- index (org_id, status) ; la lecture est suivie par jobs (kind = 'profile_prefill', ref_id = org_id)
```

## Base documentaire (RAG)

```sql
knowledge_documents (
  id, org_id, file_id, kind text check (kind in
    ('memoir_template','past_memoir','qse_policy','technical_sheet','other')),
  title text, status text, error text null
)

document_chunks (
  id, org_id, source_type text check (source_type in ('knowledge','dce')),
  source_id uuid,                       -- knowledge_documents.id ou dce_files.id
  page_from int, page_to int, heading text null,
  content text not null, tokens int,
  embedding vector(?), metadata jsonb
)
-- index : ivfflat ou hnsw sur embedding, + index (org_id, source_type)
```

## Annonces (tables globales, sans org_id)

```sql
tenders (
  id, source text check (source in ('boamp','ted')), source_id text,
  unique (source, source_id),
  notice_type text,                     -- contract_notice | correction | award | other
  title text, description text, buyer_name text, buyer_siret text null,
  procedure text, contract_nature text, -- services / travaux / fournitures
  cpv_codes text[], departments text[], nuts_codes text[],
  estimated_amount_cents bigint null, published_at timestamptz,
  deadline_at timestamptz null, notice_url text, documents_url text null,
  lots jsonb, raw jsonb not null,
  duplicate_of uuid null references tenders(id),  -- même marché reçu de l'autre source
  corrections jsonb                       -- rectificatifs reçus : [{source_id, received_at, changes}]
)                                         -- index GIN sur cpv_codes et departments

tender_matches (                          -- seules les annonces qui passent le pré-filtre
  id, org_id, tender_id, unique (org_id, tender_id),
  reasons jsonb,                          -- pourquoi elle correspond (CPV, mot-clé, département)
  score smallint null check (0..100), explanation text, relevant_lots jsonb, score_error text,
  status text check (status in ('new','tracked','dismissed')) default 'new',
  dismiss_reason text null, bid_id uuid null, model text, prompt_version text,
  scored_at timestamptz, digested_at timestamptz  -- vue par l'e-mail quotidien
)

notifications (                           -- ce qui a déjà été envoyé (aucun e-mail en double)
  id, org_id, kind text,                  -- digest | vault_expiry | correction
  key text, unique (org_id, kind, key),   -- « 2026-11-05 », « <document>:<fin>:30 »…
  recipients smallint, created_at
)
```

## Dossiers de réponse

```sql
bids (
  id, org_id, tender_id uuid null,      -- null si DCE déposé hors veille
  title text, buyer_name text, deadline_at timestamptz,
  status text check (status in ('to_review','in_progress','submitted','won','lost','dropped')),
  lot_label text null, submitted_amount_cents bigint null,
  result_rank int null, result_notes text null, owner_user_id uuid
)

dce_versions ( id, org_id, bid_id, version int, uploaded_by uuid, status text, diff_summary text null )

dce_files (
  id, org_id, dce_version_id, file_id,
  detected_kind text,                   -- rc, ccap, cctp, ae, bpu, dpgf, dqe, annex, other
  kind_confirmed bool default false,
  page_count int, ocr_used bool, text_status text
)

dce_analyses (
  id, org_id, bid_id, dce_version_id, data jsonb not null,   -- schemas/dce_analysis.schema.json
  go_no_go_score int, model text, prompt_version text, created_at
)

requirements (
  id, org_id, bid_id, dce_analysis_id,
  ref text,                             -- ex. "CCTP-12"
  text text, category text,             -- frequency, surface, product, schedule, staff, quality, safety, environment, other
  source_file_id uuid, page int, importance text   -- mandatory / expected / nice_to_have
)
```

## Mémoire et documents générés

```sql
memoirs (
  id, org_id, bid_id, version int, status text,  -- draft, generating, ready, exported
  outline jsonb, outline_source text check (outline_source in ('rc_imposed','org_template','sector_default')),
  estimated_pages numeric, max_pages int null
)

memoir_sections (
  id, org_id, memoir_id, position int, title text,
  content_md text, criterion_ref text null,     -- sous-critère de notation couvert
  sources jsonb,                                -- [{chunk_id, reference_id, ...}]
  flags jsonb,                                  -- [{type:'to_complete'|'number'|'name'|'commitment'|'length', text, term}]
  generated_by_model text, prompt_version text, edited_by_user bool default false,
  revision int default 0                        -- version courante ; une modification part de celle-ci
)

memoir_section_revisions (                      -- US-4.4 CA4 : tout texte qu'a eu un chapitre
  id, org_id, section_id, revision int, unique (section_id, revision),
  origin text check (origin in ('generated','edited','restored')),
  content_md text, flags jsonb, sources jsonb, covered_refs text[],
  instruction text null, model text null, prompt_version text null, created_by uuid null, created_at
)

conformity_items (
  id, org_id, memoir_id, requirement_id, section_id uuid null,
  status text check (status in ('covered','partial','missing')), excerpt text, comment text
)

generated_documents (
  id, org_id, bid_id, memoir_id uuid null,
  kind text,  -- dc1, dc2, staff_list, equipment_list, references_list, planning, memoir_docx, memoir_pdf, bundle_zip
  status text check (status in ('pending','ready','error')), error text,
  file_id uuid null, to_complete jsonb,  -- les [À COMPLÉTER] du document
  warnings jsonb,                        -- avertissements acceptés avant l'export (US-4.6 CA4)
  meta jsonb, created_by uuid, created_at  -- les 3 derniers de chaque type sont gardés par dossier
)
```

## Coffre-fort

```sql
compliance_documents (
  id, org_id, file_id,
  kind text,          -- kbis, rne_certificate, urssaf_vigilance, tax_compliance, cibtp_certificate, insurance_rc_pro, insurance_decennale, qualification, other
  issuer text, siren_on_document char(9) null,
  issued_at date null, valid_until date null,
  status text check (status in ('pending_review','valid','expiring','expired','mismatch')),
  extracted jsonb, confirmed_by uuid null, confirmed_at timestamptz null
)
```

## Transverses

```sql
files ( id, org_id, storage_key text, filename text, mime text, size_bytes bigint, sha256 char(64), uploaded_by uuid )

jobs ( id, org_id null, kind text, ref_id uuid, status text, progress int, error text, started_at, finished_at )

ai_calls (
  id, org_id null, bid_id null, task text, model text, prompt_version text,
  input_tokens int, output_tokens int, cost_eur numeric(10,5), latency_ms int,
  success bool, error text null, created_at
)

audit_logs ( id, org_id, user_id, action text, entity text, entity_id uuid, at timestamptz, meta jsonb )
  -- une action de Pilao depuis l'administration : user_id vide, meta = {"by": "pilao"} (lot 2)

auth_tokens ( id, org_id, user_id, kind text, token_hash char(64) unique, expires_at, used_at )
  -- kind : email_verify (48 h), invitation (7 jours), password_reset (1 heure, lot 2)

data_requests ( id, org_id, kind text, status text, due_at, requested_by -> users set null,
                platform_admin_id -> platform_admins set null,   -- suppression programmée par Pilao
                file_id, error )
```

## Points d'attention

- La dimension `vector(?)` dépend du modèle d'embeddings retenu en phase 0 : la fixer dans une migration dédiée.
- `tenders` est global (données publiques) ; `tender_matches` est par org.
- Suppression d'une org : cascade sur toutes les tables à `org_id` + suppression des fichiers S3 (job dédié).

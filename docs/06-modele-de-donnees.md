# 06 — Modèle de données (PostgreSQL)

Conventions : `id uuid pk default gen_random_uuid()`, `created_at` / `updated_at timestamptz`, montants en **centimes** (`bigint`), toutes les tables métier ont `org_id uuid not null references organizations(id)` (sauf tables globales signalées).

## Comptes

```sql
organizations (
  id, siren char(9) not null, siret char(14) unique not null,
  name text not null, legal_form text, naf_code text,
  address_line text, postal_code text, city text, department char(3),
  headcount_range text, logo_file_id uuid null,
  brand_color text null, created_at, updated_at
)

users (
  id, org_id, email citext unique not null, full_name text,
  role text check (role in ('org_admin','org_member')) not null,
  password_hash text, email_verified_at timestamptz, last_login_at timestamptz
)

platform_admins ( id, email citext unique )          -- global
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
  notice_type text,                     -- avis de marché, rectificatif, attribution
  title text, description text, buyer_name text, buyer_siret text null,
  procedure text, contract_nature text, -- services / travaux / fournitures
  cpv_codes text[], departments text[], nuts_codes text[],
  estimated_amount_cents bigint null, published_at timestamptz,
  deadline_at timestamptz null, notice_url text, documents_url text null,
  lots jsonb null, raw jsonb not null, embedding vector(?),
  duplicate_of uuid null references tenders(id)
)

tender_matches (
  org_id, tender_id, primary key (org_id, tender_id),
  prefilter_passed bool, score int, explanation text,
  status text check (status in ('new','tracked','dismissed')) default 'new',
  dismiss_reason text null, scored_at timestamptz, prompt_version text
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
  flags jsonb,                                  -- [{type:'to_complete'|'number'|'commitment', text}]
  generated_by_model text, prompt_version text, edited_by_user bool default false
)

conformity_items (
  id, org_id, memoir_id, requirement_id, section_id uuid null,
  status text check (status in ('covered','partial','missing')), excerpt text, comment text
)

generated_documents (
  id, org_id, bid_id, kind text,  -- dc1, dc2, dume_data, staff_list, equipment_list, references_list, planning, memoir_docx, memoir_pdf, bundle_zip
  file_id uuid, created_at
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
```

## Points d'attention

- La dimension `vector(?)` dépend du modèle d'embeddings retenu en phase 0 : la fixer dans une migration dédiée.
- `tenders` est global (données publiques) ; `tender_matches` est par org.
- Suppression d'une org : cascade sur toutes les tables à `org_id` + suppression des fichiers S3 (job dédié).

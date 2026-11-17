# Consultations — plan

**Spec :** `docs/superpowers/specs/2026-11-17-consultations-design.md` · exécution en ligne.

## T1 Données (migration 0033)
- `bids.kind` (`tender`|`consultation`, défaut `tender`), `bids.contact_name`, `bids.contact_email`.
- `price_services` (org_id, name, unit, price_cents ≥ 0, description, position).
- `price_sheets.excluded_sections` (JSONB liste de rubriques mises de côté).
- `quotes` (org_id, bid_id unique, year, seq, number, status drafting/ready/error, error,
  inclusions JSONB [{text, file, page}], validity_days 30, vat_bp 2000, file_id, docx_file_id),
  unique (org_id, year, seq).
- `BidIn`/`BidOut` : kind, contact_name, contact_email. Tests : création d'une consultation.

## T2 Ma liste de prix et rapprochement
- Pur (`domain/pricing.py`) : `normalize_unit`, `MatchIn`, `MatchOut`, `validate_matches(proposed,
  lines, services) -> dict[line_id, service_id]` (ids connus, même unité),
  `default_excluded(lines, matched) -> list[str]` (rubriques sans ligne rapprochée ; aucune si rien
  n'est rapproché), `compute(..., excluded=set())` : ligne d'une rubrique écartée → source
  `excluded`, ni prix, ni total, ni manquante ; `fill_writes` et `hours_summary` l'ignorent.
- Prompt `rapprochement_prestations` 0.1.0 (+ test). Lancé dans `run_read_prices` si la liste de
  prix n'est pas vide : entrées vides pré-remplies `{price_cents, service_id}` ; consultation →
  `excluded_sections = default_excluded(...)`.
- API : `GET/PUT /profile/services` (remplace la liste, 100 max, unités permises) ;
  `PUT /price-sheets/{id}` accepte `excluded_sections` ; `PriceLineOut.excluded`,
  `service_name` ; `PriceSheetOut.excluded_sections`, `options_total_cents` inchangé.

## T3 Devis
- Action payante `quote_draft` (1 crédit, remboursée en cas d'échec), tâche `quote_draft` →
  modèle de génération.
- Prompt `devis_prestations` 0.1.0 : extraits du CCTP (pages contenant les rubriques retenues,
  `[fichier p.N]`) → `{inclusions: [{text, file, page}]}` ; le serveur garde seulement les
  couples fichier/page fournis ; sans CCTP, pas d'appel.
- `exports/quote_docx.py` : `build_quote(data) -> bytes` (en-tête entreprise, client, numéro,
  date, validité, prestations comprises avec source, tableau, totaux HT/TVA/TTC, options à part,
  bon pour accord) ; PDF par le convertisseur existant.
- API : `POST /bids/{id}/quote` (202), `GET /bids/{id}/quote`, `PUT /bids/{id}/quote`
  (validity_days, vat_bp), `POST /bids/{id}/quote/download` (lien signé pdf|docx).

## T4 Écrans
- Nouveau dossier : choix « Appel d'offres » / « Consultation d'une entreprise (devis) » + client,
  contact. Liste : badge « Consultation ».
- Onglets d'une consultation : Aperçu · Documents · Prix · Devis.
- Profil : carte « Ma liste de prix ».
- Prix : case par rubrique « Chiffrée par nous / Mise de côté », mention « prix de votre liste ».
- Devis : réglages, bouton « Préparer le devis » (1 crédit), téléchargements.

## T5 Fin
- Parcours navigateur (consultation de bout en bout), ADR-052, US-4.10, docs 06/08/10, CLAUDE.md §6,
  suites complètes, captures, mise en ligne après « go ».

# 07 — Intégrations et API externes

Légende : **Vérifié** = confirmé sur la documentation officielle (novembre 2026). **À vérifier** = à confirmer par un appel réel ou la documentation avant de coder ; mettre ce fichier à jour ensuite.

## Synthèse

| API | Usage | Accès | Statut |
|---|---|---|---|
| BOAMP (DILA, Opendatasoft) | Annonces françaises | Gratuit, Licence Ouverte | Vérifié (existence, licence, fréquence) / champs à vérifier |
| TED (UE) | Annonces au-dessus des seuils européens | Gratuit, recherche sans clé | Vérifié (endpoint, accès) / syntaxe à vérifier |
| Recherche d'entreprises (data.gouv) | Profil à partir du SIRET | Ouvert, 7 appels/s | Vérifié (base URL, limite) / paramètres à vérifier |
| DECP (data.gouv) | Marchés attribués (V2) | Fichiers ouverts, quotidiens | Vérifié |
| APProch (data.gouv) | Achats prévus de l'État (V2) | Fichiers CSV/JSON ouverts | Vérifié |
| API Entreprise (État) | Attestations URSSAF, DGFiP… | **Réservée aux acteurs publics** — inutilisable par Pilao | Vérifié |
| Profils acheteurs (PLACE, Maximilien…) | Téléchargement des DCE | Pas d'API publique connue, souvent compte requis | V2, plateforme par plateforme |

---

## 1. BOAMP

- **Ce que c'est** : avis d'appel public à la concurrence et résultats de marchés, plus avis de PPP et de concessions.
- **Fréquence** : diffusion le jour de publication, 2 fois par jour, 7 jours sur 7 (selon la fiche data.gouv).
- **Accès** : dataset `boamp` sur `https://boamp-datadila.opendatasoft.com`. Licence Ouverte. Pas de clé mentionnée.
- **API** (standard Opendatasoft Explore v2.1) :
  - Schéma du dataset : `GET {BOAMP_BASE_URL}/catalog/datasets/boamp`
  - Enregistrements : `GET {BOAMP_BASE_URL}/catalog/datasets/boamp/records?where=...&order_by=...&limit=100&offset=0`
  - Export complet : `GET {BOAMP_BASE_URL}/catalog/datasets/boamp/exports/json?where=...`
- **Historique et schémas XML** : `https://echanges.dila.gouv.fr/OPENDATA/BOAMP/`
- **À vérifier en premier (ticket P1-INT-01)** :
  - [ ] liste exacte des champs (objet, acheteur, dates de parution et de limite, département, descripteurs/CPV, type d'avis, procédure, URL de l'avis, champ JSON détaillé) — appeler le schéma et enregistrer un exemple dans `apps/api/tests/fixtures/boamp_record.json` ;
  - [ ] syntaxe de filtre ODSQL pour « date de parution ≥ X » et « département IN (…) » ;
  - [ ] quotas d'appels Opendatasoft (anonyme vs avec clé) ;
  - [ ] où se trouve l'URL du DCE / profil acheteur dans l'enregistrement.
- **Stratégie d'import** : récupérer les avis publiés depuis le dernier import (curseur = date de parution), paginer, upsert sur `(source='boamp', source_id)`.

## 2. TED (Tenders Electronic Daily)

- **Endpoint** (vérifié) : `POST https://api.ted.europa.eu/v3/notices/search`
- **Accès** (vérifié) : la Search API ne nécessite pas d'authentification.
- **Pagination** (vérifié) : mode page (`page`, `limit`, max 250 par page, plafond 15 000 avis) ou mode itération (`paginationMode: "ITERATION"` + `iterationNextToken`, sans plafond ; jeton valable jusqu'à la prochaine publication + 24 h).
- **Réponse** : `notices`, `totalNoticeCount`, `iterationNextToken`. Champs au format eForms (BT-…).
- **Documentation** : `https://docs.ted.europa.eu/api/latest/index.html`, Swagger : `https://api.ted.europa.eu/swagger-ui/index.html`.
- **Exemple de corps — à vérifier dans le Swagger avant usage** :

```json
{
  "query": "place-of-performance IN (FRA) AND classification-cpv IN (90910000 90911200 90919200) AND publication-date >= 20261101",
  "fields": ["publication-number", "notice-title", "buyer-name", "classification-cpv",
             "deadline-receipt-tender-date-lot", "links"],
  "page": 1,
  "limit": 100,
  "paginationMode": "PAGE_NUMBER"
}
```

- **À vérifier (ticket P3-INT-02)** : noms exacts des champs et opérateurs, filtre par pays/NUTS, champ contenant l'URL des documents (des champs du type `document-restricted-url-lot` existent).

## 3. API Recherche d'entreprises

- **Base URL** (vérifié) : `https://recherche-entreprises.api.gouv.fr`
- **Accès** (vérifié) : ouvert, limite de **7 appels par seconde** (peut être abaissée en cas de surcharge).
- **Recherche** (à vérifier) : `GET /search?q={siren_ou_siret_ou_nom}&page=1&per_page=1`
- **Champs attendus** (à vérifier sur un appel réel) : `nom_complet`, `siren`, `siege.siret`, `siege.adresse`, `siege.code_postal`, `siege.libelle_commune`, `activite_principale`, `nature_juridique`, `tranche_effectif_salarie`, `dirigeants[]`.
- **Usage** : US-1.1 (pré-remplissage). Mettre en cache 24 h, gérer le 429 avec un délai.
- **Implémentation** : `apps/api/app/integrations/recherche_entreprises.py` (3 tentatives, attente exponentielle, `Retry-After` respecté, cache 24 h en mémoire). Endpoint public `GET /companies/lookup?siret=` (limité à 20 appels/min/IP) ; à l'inscription, l'identité de l'organisation est complétée côté serveur, sans jamais bloquer si l'API est en panne.
- **⚠ Non vérifié sur un appel réel** : le domaine était bloqué dans la session de développement. Le parseur est tolérant (tous les champs sont optionnels) et la fixture `tests/fixtures/recherche_entreprises_sample.json` est **écrite à la main** d'après la liste ci-dessus. À faire : appeler `GET /search?q=<siret>`, remplacer la fixture par la vraie réponse, corriger le parseur si besoin (noms de champs, `etat_administratif`, `departement`, code `tranche_effectif_salarie`).

## 4. DECP — Données essentielles de la commande publique (V2)

- Marchés attribués : acheteur, titulaire, montant, durée, date.
- Fichiers consolidés : `https://www.data.gouv.fr/datasets/5cd57bf68b4c4179299eb0e9`
- Mise à jour quotidienne. Usage V2 : analyse des concurrents, prix gagnants, marchés qui arrivent à échéance.

## 5. APProch — Projets d'achats publics (V2)

- Achats prévus par l'État avant publication de l'AO.
- `https://www.data.gouv.fr/datasets/projets-dachats-publics` (CSV et JSON, Licence Ouverte 2.0).

## 6. Attestations : ce qui n'est PAS possible

- **API Entreprise** : réservée aux acteurs publics ; les éditeurs privés ne peuvent l'utiliser que pour le compte d'un client public, et sans accès aux données. → **Pas d'utilisation par Pilao.**
- **URSSAF** : l'attestation de vigilance se télécharge depuis l'espace en ligne de l'entreprise ; elle est valable 6 mois et son authenticité peut être vérifiée sur urssaf.fr.
- **INPI** : attestation d'immatriculation au RNE gratuite sur `https://data.inpi.fr/`, avec SIRET permettant de vérifier l'authenticité.
- **Assurances** : pas d'API ; dépôt du PDF.
- Piste V2 : partenariat avec une plateforme de conformité fournisseurs (ex. Aprovall Portal, ex-e-attestations) — pas d'API publique documentée à ce jour.

## Règles techniques communes

- Client HTTP unique (`httpx`) avec timeouts, 3 tentatives avec attente exponentielle, journalisation des erreurs.
- Respecter les limites de débit ; pas de scraping des profils acheteurs en V1.
- Conserver la réponse brute (`tenders.raw`) pour pouvoir re-parser sans rappeler l'API.

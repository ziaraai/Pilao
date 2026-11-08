# 07 — Intégrations et API externes

Légende : **Vérifié** = confirmé sur la documentation officielle (novembre 2026). **À vérifier** = à confirmer par un appel réel ou la documentation avant de coder ; mettre ce fichier à jour ensuite.

## Synthèse

| API | Usage | Accès | Statut |
|---|---|---|---|
| BOAMP (DILA, Opendatasoft) | Annonces françaises | Gratuit, Licence Ouverte | Vérifié depuis le serveur (2026-11-08), importé toutes les 2 h |
| TED (UE) | Annonces au-dessus des seuils européens | Gratuit, recherche sans clé | Vérifié sur de vrais appels (2026-11-08), importé toutes les 2 h |
| Recherche d'entreprises (data.gouv) | Profil à partir du SIRET | Ouvert, 7 appels/s | Vérifié sur une vraie réponse (2026-11-08) |
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
  - Schéma du dataset : `GET {BOAMP_API_URL}/catalog/datasets/boamp`
  - Enregistrements : `GET {BOAMP_API_URL}/catalog/datasets/boamp/records?where=...&order_by=...&limit=100&offset=0`
  - Export complet : `GET {BOAMP_API_URL}/catalog/datasets/boamp/exports/json?where=...`
- **Historique et schémas XML** : `https://echanges.dila.gouv.fr/OPENDATA/BOAMP/`
- **Lecteur** : `apps/api/app/integrations/boamp.py` (un jour de parution après l'autre, pages de 100 : `/records` s'arrête à 10 000 ; conversion au format commun, tolérante). Import activé sur le serveur le 2026-11-08 (`BOAMP_IMPORT_ENABLED=true` dans `infra/server/app.env`), désactivé par défaut ailleurs.
- **Lu depuis le serveur le 2026-11-08** (`import-tenders --source boamp --essai`), l'hôte ne répondant pas depuis la session de développement. Champs réels du jeu de données : `idweb`, `id`, `contractfolderid`, `objet`, `filename`, `famille`, `famille_libelle`, `code_departement`, `code_departement_prestation`, `dateparution`, `datefindiffusion`, `datelimitereponse`, `nomacheteur`, `titulaire`, `perimetre`, `type_procedure`, `soustype_procedure`, `procedure_libelle`, `procedure_categorise`, `nature` (ex. `APPEL_OFFRE`), `sousnature`, `nature_libelle` (« Avis de marché »), `sousnature_libelle`, `nature_categorise` (`appeloffre/standard`), `nature_categorise_libelle`, `criteres`, `marche_public_simplifie`, `marche_public_simplifie_label`, `etat` (`INITIAL`), `descripteur_code`, `dc`, `descripteur_libelle` (thésaurus BOAMP, pas des CPV), `type_marche` (liste : `FOURNITURES`, `SERVICES`, `TRAVAUX`), `type_marche_facette`, `type_avis`, `annonce_lie`, `annonces_anterieures`, `source_schema`, `gestion`, `donnees`, `url_avis`.
  - `donnees` est l'avis complet en JSON ; pour un avis européen, au format eForms (`{"EFORMS": {"ContractNotice": …}}`). Les codes CPV y sont lus (`cbc:ItemClassificationCode`) : vérifié sur 3 avis réels (39000000, 50532400…).
  - Le lieu d'exécution est dans `code_departement_prestation`, le département de l'acheteur dans `code_departement`.
  - `datelimitereponse` est l'instant exact en temps universel (« 2026-11-30T11:00:00+00:00 » = « 12:00:00+01:00 » dans `donnees`) : gardé tel quel, affiché en heure de Paris. Vérifié sur 3 avis le 2026-11-08.
  - La Corse est écrite `20A` / `20B` (Pilao et les profils : `2A` / `2B`, converti) ; `code_departement_prestation` était vide sur les 3 avis vus.
- **Lecture en deux temps** (BOAMP publie plus de mille avis par jour, de 20 à 80 Ko chacun avec `donnees`) : pour chaque jour de parution, une liste légère (`select=idweb,datelimitereponse,nature,nature_libelle`), puis l'avis complet seulement pour ceux encore ouverts, pas encore en base et qui ne sont pas des attributions (`where=idweb = "…" OR …`, 40 par requête). Relire deux jours toutes les 2 heures ne retélécharge donc rien.
- **Reste à vérifier** : le format de `annonce_lie` sur un vrai rectificatif.
- **Vérification depuis le serveur** : `/opt/pilao/pilao.sh exec api python -m app.cli import-tenders --source boamp --essai` affiche la vraie liste des champs, les clés d'un vrai avis, le début de `donnees` et 3 avis tels que Pilao les lit, sans rien enregistrer. Corriger `boamp.py` d'après ce résultat, enregistrer un exemple dans `apps/api/tests/fixtures/boamp_record.json`, puis passer `BOAMP_IMPORT_ENABLED=true` dans `infra/server/app.env`.
- **Points ouverts** : quotas Opendatasoft (anonyme), lien du DCE / profil acheteur dans `donnees`, volume par jour (BOAMP ne se filtre pas par CPV côté serveur : tous les avis de la période sont lus, le pré-filtre de chaque entreprise trie).
- **Stratégie d'import** : celle de TED (ci-dessous) : depuis la dernière passe réussie moins un jour, upsert sur `(source='boamp', source_id=idweb)`.

## 2. TED (Tenders Electronic Daily)

- **Endpoint** (vérifié) : `POST https://api.ted.europa.eu/v3/notices/search`, sans clé.
- **Vérifié sur de vrais appels le 2026-11-08** (lecteur `apps/api/app/integrations/ted.py`, exemples réels dans `apps/api/tests/fixtures/ted_notices.json`) :
  - requête : `place-of-performance IN (FRA) AND classification-cpv IN (90910000 …) AND publication-date >= 20261101`. **La recherche par CPV est hiérarchique** : 90910000 ramène aussi 90911200, 90911300, etc. (même total que la liste détaillée) ;
  - un champ inconnu est refusé avec la liste complète des champs acceptés (1 830) ;
  - pagination : `paginationMode: "ITERATION"`, 250 avis par page au plus, `iterationNextToken` jusqu'à `null` ;
  - types d'avis : `cn-standard` (appel à concurrence), `can-standard` et `can-modif` (attribution) ; une procédure garde son `procedure-identifier` d'un avis à l'autre ; un avis de modification porte `change-notice-version-identifier` (= identifiant de l'avis d'origine + version) et `change-description`, et **répète l'avis entier** ;
  - champs utilisés : `title-proc`, `description-proc`, `buyer-name`, `buyer-identifier` (parfois un SIRET, parfois un numéro interne), `buyer-post-code`, `place-of-performance` (NUTS), `place-of-performance-post-code-lot` / `-proc`, `classification-cpv`, `contract-nature-main-proc`, `procedure-type`, `estimated-value-proc` / `-cur-proc` / `-lot`, `deadline-receipt-tender-date-lot` + `-time-lot`, `identifier-lot`, `title-lot`, `document-url-lot`, `links.html.FRA` ;
  - textes par langue (`{"fra": …}`, `{"mul": […]}`) ; dates avec un décalage parfois faux (« 2026-11-30+02:00 ») : une date limite française est lue en heure de Paris ; liens avec `&amp;`.
- **Correspondance** : une annonce Pilao par procédure (`source_id = procedure-identifier`) ; chaque avis de modification est un rectificatif sous son propre numéro de publication ; une attribution est gardée sous son numéro (V2) ; le département vient du code postal du lieu d'exécution, sinon de l'acheteur.
- **Mesure** (2026-11-08) : 14 jours d'avis France pour les CPV des métiers = 132 avis lus en 3 s.

## 3. API Recherche d'entreprises

- **Base URL** (vérifié) : `https://recherche-entreprises.api.gouv.fr`
- **Accès** (vérifié) : ouvert, limite de **7 appels par seconde** (peut être abaissée en cas de surcharge).
- **Recherche** (vérifiée le 2026-11-08) : `GET /search?q={siret}&page=1&per_page=1` → `results[0]` avec `siren`, `nom_complet` (avec le sigle : « ENG-PRO (E.P.) »), `nom_raison_sociale`, `nature_juridique`, `activite_principale`, `tranche_effectif_salarie`, `etat_administratif`, `dirigeants[]` (`nom`, `prenoms`, `qualite`, `type_dirigeant`), `siege` et `matching_etablissements[]` (`siret`, `adresse`, `numero_voie`, `indice_repetition`, `type_voie`, `libelle_voie`, `complement_adresse`, `code_postal`, `libelle_commune`, `departement` — absent pour les établissements secondaires).
- **Pièges vus sur la vraie réponse** : `adresse` contient déjà le code postal et la ville (la rue est reconstruite à partir de ses parties) ; un dirigeant peut figurer deux fois (« SAOUD » / « SAOUD (SAOUD) », prénoms avec ou sans trait d'union).
- **Usage** : US-1.1 (pré-remplissage). Mettre en cache 24 h, gérer le 429 avec un délai.
- **Implémentation** : `apps/api/app/integrations/recherche_entreprises.py` (3 tentatives, attente exponentielle, `Retry-After` respecté, cache 24 h en mémoire). Endpoint public `GET /companies/lookup?siret=` (limité à 20 appels/min/IP) ; à l'inscription, l'identité de l'organisation est complétée côté serveur, sans jamais bloquer si l'API est en panne. La fixture `tests/fixtures/recherche_entreprises_sample.json` garde la structure de la vraie réponse, avec des valeurs fictives.

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

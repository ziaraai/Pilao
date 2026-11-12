# Administration de la plateforme, lot 5 : réglages — conception

- **Date** : 2026-11-12
- **Statut** : à valider.
- **Stories** : US-6.15 (modèles d'IA par tâche), US-6.16 (clé OpenRouter), US-6.17 (imports
  d'annonces), US-6.18 (réglages généraux) ; ADR-044.
- **S'appuie sur** : ADR-040 (back-office, journal), lot 1 (`app/core/crypto.py`, chiffrement
  prévu pour les clés API), ADR-005 (un modèle par tâche, couche `app/ai/llm.py`), ADR-036
  (imports TED et BOAMP toutes les 2 h).

## 1. But

Permettre à l'exploitant de changer, depuis l'administration, ce qu'il change aujourd'hui dans le
fichier du serveur (`infra/server/app.env`) ou dans les secrets GitHub, puis par une remise en
ligne : le modèle d'IA de chaque tâche, la clé OpenRouter, les imports d'annonces et quelques
réglages simples. Un changement compte dans la minute, sans remise en ligne, et va au journal.

**Réussi quand** : Faycal ouvre « Réglages », voit ses 6 tâches d'IA avec leur modèle, leur prix
et leur coût sur 30 jours ; il choisit dans le catalogue OpenRouter un modèle moins cher pour la
note des annonces ; l'essai passe, c'est enregistré, et la note suivante utilise ce modèle
(visible dans « Coûts de l'IA ») ; il colle la clé de production et voit « •••• 9f2c, réglée ici »
et son crédit OpenRouter ; il coupe puis réactive BOAMP, clique « Importer maintenant » et voit le
passage dans « Technique » ; tout est au journal ; il n'a jamais touché au serveur.

Décisions prises en discussion :

1. **Quatre blocs** : modèles d'IA par tâche, clé OpenRouter, imports TED/BOAMP, réglages
   généraux (budget d'IA par entreprise et par mois, adresse de support, adresse des avis).
2. **Les modèles se choisissent dans le catalogue d'OpenRouter** (recherche, prix en euros,
   taille de texte), pas en tapant un nom ; un essai réel avant chaque enregistrement.
3. **Les réglages sont gardés dans la base** ; la valeur de l'admin passe avant celle du serveur ;
   sans valeur dans l'admin, celle du serveur s'applique ; « Revenir à la valeur du serveur »
   toujours possible. Écartés : modifier le fichier du serveur depuis l'admin (il faudrait piloter
   les conteneurs ; une erreur arrête le site) et garder les réglages dans Redis (ni durable, ni
   sauvegardé).
4. **Restent sur le serveur** : base, stockage, antivirus, envoi des e-mails (serveur et mot de
   passe), modèle d'indexation (en changer oblige à tout réindexer), taux dollar → euro. La clé
   GitHub reste la clé de secours.

## 2. Les notions

- **Réglage** : une valeur de la plateforme (pas d'une entreprise), connue par son nom
  (`model.tender_scoring`, `import.boamp_enabled`…). **Valeur effective** = celle de l'admin si
  elle existe, sinon celle du serveur.
- **Origine** : « réglé ici » (admin) ou « valeur du serveur ». La valeur du serveur est toujours
  affichée à côté.
- **Tâche d'IA** : les 6 tâches de `TASK_MODELS` (`app/ai/llm.py`) : lecture du DCE
  (`dce_extraction`), rédaction du mémoire (`memoir_generation`), régénération d'un chapitre
  (`memoir_regeneration`), pré-remplissage du profil (`profile_extraction`), note des annonces
  (`tender_scoring`), lecture des attestations (`compliance_reading`). La valeur du serveur d'une
  tâche est celle de son groupe actuel (`LLM_MODEL_EXTRACTION`, `_GENERATION`, `_SCORING`,
  `_VISION`).
- **Catalogue** : la liste publique des modèles d'OpenRouter (`GET /api/v1/models`, vérifiée le
  2026-11-12 : 432 modèles ; champs `id`, `name`, `pricing.prompt` et `pricing.completion` en
  dollars par jeton, `context_length`, `supported_parameters`, `architecture.input_modalities`).
- **Modèle utilisable** pour une tâche : `response_format` dans `supported_parameters` ; pas de
  variante `:free` (ces offres gardent les textes envoyés, contraire à la politique de
  confidentialité) ; pas d'alias `~…` (le modèle changerait sans prévenir) ; un prix connu (ni vide
  ni négatif) ; pour la lecture des attestations, `image` dans `input_modalities`.

## 3. Parcours

### 3.1 L'écran « Réglages » (`/admin/reglages`, 9e entrée du menu)

Quatre cartes.

**Modèles d'IA** — une ligne par tâche : libellé, modèle effectif (nom du catalogue et
identifiant), prix en euros par million de jetons (entrée / sortie), origine, coût réel et nombre
d'appels sur 30 jours (journal `ai_calls`).
- « Changer » ouvre le sélecteur : une recherche, la liste des modèles utilisables pour cette tâche
  (nom, identifiant, prix entrée / sortie en €, taille de texte), triée par nom. Choisir un modèle
  → « Essayer et enregistrer » → essai réel (§3.3) → enregistré, ou le message d'échec et rien de
  changé.
- « Revenir à la valeur du serveur » (grisé quand le serveur n'a pas de modèle pour cette tâche,
  ou quand la valeur est déjà celle du serveur).
- Un modèle effectif absent du catalogue : ligne en orange « Ce modèle n'est plus au catalogue
  d'OpenRouter. »
- En bas, en lecture seule : « Modèle d'indexation de la base documentaire : … (réglé sur le
  serveur : en changer oblige à réindexer tous les documents). »

**Clé OpenRouter** — « •••• 9f2c — réglée ici le 12/11/2026 » ou « •••• cc3a — clé du serveur »
(ou « Aucune clé ») ; le crédit du compte OpenRouter : « 3,68 $ restants sur 5,00 $ » (en dollars,
la monnaie du compte ; « Crédit indisponible » si OpenRouter ne répond pas).
- « Remplacer la clé » : un champ mot de passe, « Vérifier et enregistrer » → la clé est vérifiée
  auprès d'OpenRouter (§3.3) → enregistrée chiffrée ; refusée → rien de changé.
- « Revenir à la clé du serveur » (grisé quand il n'y a pas de clé réglée ici, ou pas de clé sur le
  serveur).
- Une clé réglée ici devenue illisible (la clé secrète du serveur a changé) : bandeau rouge « La
  clé enregistrée est illisible : la clé du serveur est utilisée. Remplacez-la. »

**Imports d'annonces** — pour TED et BOAMP : interrupteur « Actif » (origine affichée), dernier
passage (début, statut, annonces nouvelles et mises à jour, erreur éventuelle), « Importer
maintenant » (seulement si la source est active) → « Passage lancé : il apparaîtra dans
Technique. » Toutes les 2 h, le planificateur n'importe que les sources actives.

**Réglages généraux** — budget d'IA maximum par entreprise et par mois (en euros, entier de 1 à
10 000), adresse de support (« Contactez Pilao : … »), adresse qui reçoit les avis des testeurs ;
chacun avec sa valeur du serveur, « Enregistrer » et « Revenir à la valeur du serveur ». Une
adresse vide = « aucune ».

### 3.2 Ce que les réglages changent

| Réglage | Lu par |
|---|---|
| `model.<tâche>` (6) | `llm.model_for(task)` : chaque appel d'IA de la tâche |
| `openrouter_api_key` | chaque appel d'IA et d'indexation (`api_key` passé à LiteLLM) ; l'essai d'un modèle ; le crédit affiché |
| `import.ted_enabled`, `import.boamp_enabled` | le passage planifié (`tender_import.readers`) ; « Importer maintenant » |
| `ai_monthly_budget_eur_per_org` | `llm.ensure_budget` |
| `support_email` | « Contactez Pilao » partout (suspension, modules, crédits, `/auth/me`) |
| `feedback_email` | l'envoi des avis (`services/feedback.py`) |

Chaque processus (API, worker, planificateur) relit les réglages au plus toutes les 30 secondes ;
celui qui enregistre les relit aussitôt. Un changement compte donc partout en moins d'une minute.

### 3.3 Les vérifications

- **Essai d'un modèle** : un appel minuscule par la même route que les vrais appels (clé effective,
  `provider_routing` : aucun fournisseur qui garde les données), réponse JSON demandée (« Réponds
  uniquement par l'objet JSON {"ok": true}. »), réponse lue comme un objet JSON. Journalisé dans
  `ai_calls` (tâche `settings_check`, « Essai d'un modèle », sans entreprise : ligne
  « Plateforme »). Échec (erreur du fournisseur, réponse illisible, aucun fournisseur conforme) →
  422 avec la raison, rien d'enregistré.
- **Vérification d'une clé** : `GET /api/v1/key` avec la clé collée (vérifié le 2026-11-12 : 200
  avec `data.usage`, `data.limit`… ; 401 pour une clé refusée). 401 → « Clé refusée par
  OpenRouter. » ; OpenRouter injoignable → « OpenRouter ne répond pas : la clé n'est pas vérifiée,
  rien n'est changé. »
- **Crédit** : `GET /api/v1/credits` avec la clé effective (vérifié le 2026-11-12 : `data
  .total_credits`, `data.total_usage`, en dollars). Lu à l'ouverture de l'écran, jamais gardé.
- **Catalogue** : lu par l'API (pas par le navigateur) et gardé une heure ; injoignable → 503
  « Catalogue OpenRouter indisponible, réessayez dans un moment. » (les modèles en place
  continuent de tourner).
- L'adresse d'OpenRouter (`OPENROUTER_API_URL`, `https://openrouter.ai/api/v1`) et le préfixe
  LiteLLM des modèles du catalogue (`LLM_CATALOGUE_PREFIX`, `openrouter/`) sont des réglages du
  serveur : le parcours de test les pointe vers son faux serveur.

### 3.4 « À surveiller » (vue d'ensemble)

- Rouge : « La clé OpenRouter enregistrée est illisible » (lien vers Réglages).
- Orange : « {tâche} : modèle retiré du catalogue OpenRouter » — seulement si le catalogue est
  connu (en cache, ou lu en moins de 5 secondes) ; sinon rien.

### 3.5 Journal

| Action | Détail |
|---|---|
| `setting_changed` | réglage, libellé, avant → après (modèles, imports, réglages généraux) |
| `setting_reset` | réglage, libellé, avant → valeur du serveur |
| `api_key_replaced` | les 4 derniers caractères de la nouvelle clé (jamais la clé) |
| `api_key_reset` | — |
| `import_started` | source |

## 4. Données (migration 0027)

`platform_settings` — pas d'`org_id` (réglage de la plateforme, comme `plans`) :
`key text primary key`, `value jsonb null` (la valeur en clair), `secret text null` (chiffré par
`crypto.encrypt(..., "openrouter_api_key")`), `secret_last4 text null`, `updated_at timestamptz`,
`updated_by uuid null` (→ `platform_admins.id`, `on delete set null`). Une ligne par réglage
réglé ici ; « Revenir à la valeur du serveur » supprime la ligne. Rien n'est ajouté pour les
valeurs du serveur : elles restent dans `Settings`.

## 5. Construction

### 5.1 Registre et lecture

- `app/platform_settings.py` : le registre des réglages modifiables (nom, libellé français, type :
  modèle d'une tâche, booléen, entier borné, adresse e-mail, secret ; la valeur du serveur, lue
  dans `Settings`). Un réglage hors du registre est refusé (404).
- `app/core/runtime.py` : `effective(name)` = ligne de la base sinon valeur du serveur ; un
  instantané de toutes les lignes par processus, relu au plus toutes les 30 secondes,
  `invalidate()` après une écriture ; la clé déchiffrée à la lecture (illisible → `None` et un
  indicateur pour l'écran et « À surveiller »). Les appels qui n'ont pas de session (LiteLLM, le
  planificateur) passent par cet instantané.
- Branchements : `llm.model_for`, `llm._call_provider` et `embeddings` (`api_key`),
  `llm.ensure_budget`, les lecteurs de `support_email` et `feedback_email`, `tender_import
  .readers`. `get_settings()` reste la source des valeurs du serveur.

### 5.2 Services

- `app/services/admin/settings.py` : l'état de l'écran ; changer et remettre un réglage (journal) ;
  `catalogue(task)` (lecture, filtre §2, prix en € : dollars par jeton × 1 000 000 ×
  `USD_EUR_RATE`) ; `check_model(model)` (l'essai) ; `check_key(key)` et `credit()` ;
  `start_import(source)`.
- `app/ai/openrouter.py` : les trois lectures HTTP d'OpenRouter (`models`, `key`, `credits`), avec
  un délai court (10 s ; 5 s pour « À surveiller ») ; seul endroit qui parle à OpenRouter hors
  LiteLLM.
- « Importer maintenant » met en file un job `import_source_job(source)` (le même `run_import` que
  le passage planifié, depuis le dernier passage) ; refusé si la source est coupée, ou si un
  passage de cette source est en cours (`tender_imports.status = 'running'`, et le verrou
  `pg_try_advisory_lock` protège de toute façon).

### 5.3 API (super admin, session admin du lot 1)

| Méthode, chemin | Effet |
|---|---|
| `GET /admin/settings` | l'état des quatre cartes (jamais une clé, seulement ses 4 derniers caractères) |
| `GET /admin/settings/catalogue?task=` | les modèles utilisables pour la tâche |
| `PUT /admin/settings/models/{task}` `{model_id}` | essai puis enregistrement |
| `DELETE /admin/settings/models/{task}` | retour à la valeur du serveur |
| `PUT /admin/settings/api-key` `{key}` | vérification puis enregistrement chiffré |
| `DELETE /admin/settings/api-key` | retour à la clé du serveur |
| `PUT /admin/settings/imports/{source}` `{enabled}` | activer, couper |
| `POST /admin/settings/imports/{source}/run` | « Importer maintenant » (202) |
| `PUT /admin/settings/general/{name}` `{value}` | budget, support, avis |
| `DELETE /admin/settings/general/{name}` | retour à la valeur du serveur |

### 5.4 Front

- `app/(admin)/admin/(espace)/reglages/page.tsx` ; `components/admin/model-picker.tsx` (recherche,
  liste, essai) ; `components/admin/api-key-card.tsx` ; libellés du journal (`AUDIT_LABELS`) ;
  `ADMIN_NAV` « Réglages ».
- Les fonctions pures (prix en euros, filtre de recherche, libellé d'origine) dans
  `lib/settings.ts`, testées avec vitest.

## 6. Erreurs

| Cas | Réponse |
|---|---|
| Réglage, tâche ou source inconnus | 404 « Réglage inconnu. » / « Tâche inconnue. » / « Source inconnue. » |
| Modèle absent du catalogue ou inutilisable pour la tâche | 422 « Ce modèle ne convient pas à cette tâche. » |
| Essai du modèle raté | 422 « Le modèle n'a pas répondu correctement : {raison}. » |
| Catalogue injoignable | 503 « Catalogue OpenRouter indisponible, réessayez dans un moment. » |
| Clé refusée / OpenRouter injoignable / clé vide | 422 « Clé refusée par OpenRouter. » / 503 « OpenRouter ne répond pas : la clé n'est pas vérifiée, rien n'est changé. » / 422 |
| Retour à la valeur du serveur sans valeur sur le serveur | 409 « Le serveur n'a pas de valeur pour ce réglage. » (clé : « Le serveur n'a pas de clé : remplacez la clé plutôt que de la retirer. ») |
| Budget hors de 1 à 10 000, adresse mal formée | 422 |
| « Importer maintenant » sur une source coupée / déjà en cours / file en panne | 409 « Activez d'abord l'import {source}. » / 409 « Un passage est déjà en cours. » / 503 « File d'attente indisponible. » |
| Session d'entreprise sur `/admin/settings…` | 401, comme le reste de l'admin |

## 7. Tests

- **Lecture** (`tests/core/`) : la valeur de l'admin passe avant celle du serveur ; sans ligne, la
  valeur du serveur ; `invalidate()` relit aussitôt ; l'instantané est relu après 30 s ; une clé
  illisible donne `None` et l'indicateur.
- **Branchements** : un appel d'IA prend le modèle réglé pour sa tâche, et la clé réglée
  (`api_key` passé à LiteLLM, appel d'indexation compris) ; le budget réglé bloque ; l'adresse de
  support réglée apparaît dans « Contactez Pilao » et `/auth/me` ; l'adresse des avis réglée reçoit
  l'avis ; une source coupée ici n'est pas importée par le passage planifié.
- **Catalogue** (réponse d'OpenRouter simulée) : exclus `:free`, `~…`, sans `response_format`,
  sans prix, sans image pour la lecture des attestations ; prix convertis en euros ; cache d'une
  heure ; 503 si injoignable.
- **API** : essai réussi → enregistré et journalisé ; essai raté → rien d'enregistré ; modèle hors
  catalogue → 422 ; retour au serveur ; clé vérifiée → enregistrée chiffrée, la réponse ne contient
  jamais la clé, le journal seulement les 4 derniers caractères ; clé refusée → rien de changé ;
  retour à la clé du serveur (refusé sans clé du serveur) ; imports activer / couper / lancer et
  leurs refus ; réglages généraux et leurs bornes ; session d'entreprise refusée ; « À surveiller »
  (clé illisible, modèle retiré).
- **Front** (vitest) : prix en euros, recherche dans la liste, libellé d'origine.
- **Navigateur** (`journey.cjs`) : le faux serveur du parcours sert aussi le catalogue, la clé et le
  crédit ; l'admin change le modèle de la note des annonces (essai), remplace la clé, coupe puis
  réactive TED, lance « Importer maintenant », règle l'adresse de support et la voit côté client,
  lit le journal ; capture `admin-reglages.png`.

## 8. Documentation

- `docs/04` : US-6.15 à US-6.18 ; le module 6 (lot 5 fait).
- `docs/05` (réglages effectifs, `app/core/runtime.py`), `docs/06` (table), `docs/07` (OpenRouter :
  catalogue, clé et crédit vérifiés le 2026-11-12), `docs/09` (clé chiffrée en base, jamais
  renvoyée), `docs/10` (lot 5 fait), `docs/12` : ADR-044, `docs/14` (la clé GitHub devient la clé
  de secours ; les valeurs d'`app.env` restent les valeurs du serveur).
- `CLAUDE.md` §6.

## Hors périmètre du lot 5

Un modèle selon la formule ; d'autres fournisseurs qu'OpenRouter ou plusieurs clés ; le serveur
d'e-mails et son mot de passe ; le modèle d'indexation ; le taux dollar → euro ; l'historique des
valeurs (le journal suffit) ; un import « à blanc » depuis l'admin (la commande `import-tenders
--essai` reste) ; des réglages par entreprise.

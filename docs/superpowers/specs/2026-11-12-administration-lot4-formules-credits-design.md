# Administration de la plateforme, lot 4 : formules et crédits — conception

- **Date** : 2026-11-12
- **Statut** : validé et livré.
- **Stories** : US-6.11 (formules), US-6.12 (prix des actions), US-6.13 (formule et crédits d'une
  entreprise), US-6.14 (crédits côté client) ; ADR-043.
- **S'appuie sur** : lot 3 (`2026-11-11-administration-lot3-modules-design.md`, ADR-041), lot 2
  (ADR-042), ADR-040. Ne fixe aucun prix : la question Q3 reste ouverte, l'exploitant règle tout
  dans l'administration (`docs/01` : « ne pas coder de grille tarifaire avant décision »).

## 1. But

Donner à chaque entreprise une **formule** (des modules + des crédits) et faire payer en **crédits**
les actions qui coûtent de l'IA. L'exploitant crée ses formules, fixe le prix de chaque action en
crédits, attribue les formules et recharge les entreprises, à la main ; le paiement en ligne
(Stripe) viendra plus tard sur ce socle.

**Réussi quand** : Faycal crée « Essentiel » et « Pro », donne « Pro » à une entreprise ; elle voit
« 50 crédits restants », lance une analyse de DCE (« 2 crédits »), voit son solde baisser et la
ligne dans son historique ; à 0, le bouton est grisé avec « Contactez Pilao » ; Faycal ajoute 20
crédits, elle continue. Une nouvelle inscription reçoit « Découverte » et peut répondre à un appel
d'offres sans rien payer. Nulle part le client ne voit un euro.

Décisions prises en discussion :

1. **Un prix en crédits par action** (pas « 1 crédit = 1 dossier », pas « 1 crédit = une somme
   d'IA ») : chaque module déclare ses actions payantes ; l'exploitant fixe leur prix ; l'admin
   montre à côté le coût réel moyen d'IA, en euros, pour lui seul.
2. **Le client ne voit jamais d'euros** : son solde, le prix des actions et son historique, en
   crédits.
3. **Crédits du mois + crédits supplémentaires** : la formule donne des crédits chaque mois, remis
   au niveau de la formule le 1er (heure de Paris), le reste est perdu ; les crédits
   supplémentaires (recharges à la main, crédits offerts) n'expirent pas et ne sont pris qu'après
   ceux du mois.
4. **Sans assez de crédits, l'action est refusée, tout le reste marche** ; bandeau sous 20 % ;
   « À surveiller » côté admin.
5. **La formule décide des modules** ; les boutons du lot 3 restent pour les exceptions, marquées
   « hors formule ».
6. **Une formule par défaut** pour les nouvelles inscriptions ; au départ « Découverte »
   (gratuite : deux modules, 0 crédit par mois, **7 crédits offerts une seule fois** — une analyse
   et un mémoire) ; les entreprises existantes reçoivent « Pilote » (deux modules, 100 crédits par
   mois).
7. **Un journal des crédits** par entreprise ; le solde en est calculé (pas de compteur, pas de
   tâche de minuit).

## 2. Les notions

- **Formule** : nom, phrase vue par le client, modules compris, crédits par mois, crédits offerts
  (une seule fois, à la première attribution), prix pour l'exploitant (texte libre, jamais montré
  au client), « par défaut » (une seule formule), archivée ou non.
- **Crédits du mois** : allocation mensuelle de la formule actuelle moins ce qui a été pris sur le
  mois en cours (mois civil, heure de Paris), jamais sous 0.
- **Crédits supplémentaires** : tout ce qui a été ajouté (recharges, crédits offerts) moins ce qui
  y a été pris ; n'expirent pas.
- **Solde** = crédits du mois + crédits supplémentaires.
- **Actions payantes** (module « Réponse aux appels d'offres »), avec leur prix de départ :

| Clé | Nom | Prix de départ | Tâche d'IA (coût réel) |
|---|---|---|---|
| `dce_analysis` | Analyse du DCE | 2 | `dce_extraction` |
| `memoir_generation` | Rédaction du mémoire | 5 | `memoir_generation` |
| `chapter_regeneration` | Régénérer un chapitre | 1 | `memoir_regeneration` |
| `profile_prefill` | Pré-remplir le profil depuis vos documents | 1 | `profile_extraction` |

- **Gratuit** : la veille et les notes des annonces, la lecture des attestations, l'indexation des
  documents, le DC1/DC2, les exports, toute modification à la main. Un prix réglé à 0 rend une
  action gratuite.

## 3. Parcours

### 3.1 Administration

- **Écran « Formules »** (`/admin/formules`, 8ᵉ entrée du menu) :
  - la liste : nom, modules, crédits par mois, crédits offerts, ton prix, nombre d'entreprises,
    « Par défaut », « Archivée » ;
  - « Nouvelle formule » et « Modifier » : les champs du §2. Changer les modules ou les crédits par
    mois d'une formule s'applique tout de suite à ses entreprises ; la confirmation le dit : « Ces
    changements s'appliquent aux N entreprises qui ont cette formule. » Pour les modules, seuls ceux
    qui changent sont ajoutés ou retirés chez ces entreprises (leurs exceptions sont gardées) ;
  - « Formule par défaut » : la donne aux nouvelles inscriptions (retire le titre à l'ancienne) ;
  - « Archiver » : la formule n'est plus proposée, ses entreprises la gardent ; « Désarchiver ».
    La formule par défaut ne s'archive pas ;
  - aucune suppression.
- **Prix des actions** (même écran, deuxième carte) : pour chaque action payante, son module, son
  prix en crédits (modifiable, 0 à 1000) et, pour l'exploitant, sur les 30 derniers jours, combien
  de fois elle a été payée et son **coût réel moyen d'IA** en euros.
- **Fiche d'une entreprise**, carte **« Formule et crédits »** :
  - la formule, « Changer de formule » (liste des formules non archivées, confirmation) ;
  - « Crédits du mois : 42 sur 100 (renouvelés le 1er décembre) », « Crédits supplémentaires :
    12 » ;
  - « Ajouter des crédits » : nombre (1 à 100 000) et raison (obligatoire) ; ce sont des crédits
    supplémentaires ;
  - l'historique (50 derniers mouvements) : date, mouvement, action, dossier, auteur, crédits ;
  - la carte « Modules » (lot 3) marque « Hors formule » un module actif que la formule ne donne
    pas, ou un module de la formule désactivé.
- **Changer de formule** : les modules deviennent ceux de la nouvelle formule (les exceptions
  tombent) ; l'allocation du mois devient la sienne tout de suite (ce qui a déjà été pris ce mois-ci
  compte) ; les crédits supplémentaires restent ; ses crédits offerts ne sont donnés que si
  l'entreprise n'en a jamais reçu.
- **Créer une entreprise** (lot 2) : un champ « Formule », la formule par défaut présélectionnée.
- **Liste des entreprises** : colonnes « Formule » et « Crédits » (le solde).
- **Vue d'ensemble, « À surveiller »** : en orange, les entreprises à 0 crédit.
- **Journal** : `plan_created`, `plan_updated`, `plan_archived`, `plan_unarchived`,
  `plan_default_set`, `plan_changed` (l'entreprise, l'ancienne et la nouvelle formule),
  `credits_added` (l'entreprise, le nombre, la raison), `credit_price_changed` (l'action, l'ancien
  et le nouveau prix).

### 3.2 Espace client

- **Tableau de bord** : un compteur « 42 crédits restants » qui mène à l'onglet ci-dessous.
- **Profil, onglet « Formule et crédits »** (tous les utilisateurs) : la formule, sa phrase et ses
  modules ; « Crédits du mois : 42 sur 100, renouvelés le 1er décembre » (ou, sans crédits
  mensuels : « Crédits offerts et ajoutés : 7 ») ; « Crédits supplémentaires : 12 » ; le prix de
  chaque action ; l'historique (100 derniers mouvements : date, action, dossier, qui l'a lancée,
  crédits) ; « Pour changer de formule ou ajouter des crédits : contactez Pilao{ : SUPPORT_EMAIL}. »
- **Boutons payants** : le prix est affiché — « Lancer l'analyse · 2 crédits », « Rédiger le
  mémoire · 5 crédits », « Régénérer · 1 crédit », « Lire mes documents · 1 crédit ». Un prix à 0
  n'affiche rien.
- **Pas assez de crédits** : bouton grisé et, dessous, « Il faut 5 crédits, il vous en reste 3.
  Contactez Pilao{ : …}. » ; le serveur refuse aussi (§6).
- **Bandeau** sur toutes les pages : orange quand le solde est sous 20 % de la référence
  (l'allocation mensuelle, ou à défaut les crédits offerts de la formule) — « Il vous reste 8
  crédits. » ; rouge à 0 — « Vous n'avez plus de crédits : les actions payantes sont en pause.
  Contactez Pilao{ : …}. »
- **Analyse automatique du DCE** : si les crédits manquent au dépôt, le DCE est déposé et lu ;
  l'analyse attend avec « Analyse non lancée : crédits insuffisants. » et le bouton « Lancer
  l'analyse · 2 crédits ».
- **Remboursement** : une action qui échoue rend ses crédits ; la ligne « Remboursé : … n'a pas
  abouti » apparaît dans l'historique.

### 3.3 Règles de calcul

- **Prise** : au lancement de l'action, une fois toutes ses autres vérifications passées, dans la
  même transaction que la création du travail ; d'abord sur les crédits du mois, puis sur les
  supplémentaires. Le verrou de la ligne de l'entreprise empêche deux prises simultanées de
  dépasser le solde ; un double clic ne crée qu'une action (les règles « une seule à la fois »
  existantes s'appliquent avant la prise).
- **Mois** : mois civil, heure de Paris ; rien n'est écrit le 1er, le calcul repart de
  l'allocation.
- **Remboursement** : une seule fois par prise ; il rend ce qui avait été pris, là où ça avait été
  pris ; si le mois de la prise est terminé, la part du mois revient en crédits supplémentaires.
- **Quand rembourser** : le travail finit en erreur (IA indisponible, réponse invalide, panne,
  file d'attente injoignable, plafond mensuel d'IA atteint). Un mémoire dont certains chapitres
  sont en erreur n'est pas remboursé, mais **relancer un chapitre en erreur est gratuit**.
- **Garde-fous** : le plafond mensuel d'IA par entreprise (`AI_MONTHLY_BUDGET_EUR_PER_ORG`) reste ;
  une entreprise suspendue ou sans le module ne lance rien (lots 2 et 3).

## 4. Données (migration 0025)

- **`plans`** (table de la plateforme, sans `org_id`) : `id`, `name text unique` (insensible à la
  casse), `description text`, `modules text[]`, `monthly_credits int ≥ 0`, `welcome_credits int ≥ 0`,
  `price_note text` (pour l'exploitant), `is_default bool` (index unique partiel : une seule à
  vrai), `archived_at timestamptz null`, `created_at`, `updated_at`.
- **`credit_prices`** (plateforme) : `action text pk`, `credits int` (0 à 1000), `updated_at`. Une
  action sans ligne a le prix de départ du registre.
- **`organizations`** : `plan_id uuid not null references plans`, `welcome_credits_at timestamptz
  null` (crédits offerts déjà donnés).
- **`credit_entries`** (métier, `org_id`) : `id`, `org_id`, `at`, `kind` (`charge`, `refund`,
  `grant`, `welcome`), `action text null`, `monthly int`, `extra int` (négatifs pour une prise,
  positifs sinon), `month date` (1er jour du mois de Paris de la prise ; `null` hors prise),
  `bid_id uuid null`, `user_id uuid null`, `platform_admin_id uuid null`, `reason text null`,
  `ref_id uuid null` (l'analyse, le mémoire, le chapitre ou la lecture), `refund_of uuid null
  unique references credit_entries`. Index `(org_id, at desc)` et `(org_id, month)`.
- **Données de départ** : « Pilote » (deux modules, 100 par mois, 0 offert) donnée à toutes les
  entreprises existantes ; « Découverte » (deux modules, 0 par mois, 7 offerts, par défaut).

## 5. Construction

### 5.1 Registre et service

- `app/modules.py` : `PaidAction(key, name, default_credits, ai_task)` ; `Module.actions` ;
  `PAID_ACTIONS` (toutes, ordre du registre), `action_by_key`.
- `app/services/credits.py` (seul endroit qui écrit `credit_entries`) :
  - `balance(db, org) -> Balance` (`monthly_allowance`, `monthly_left`, `extra`, `total`,
    `reference`, `renews_on`) ;
  - `price(db, action) -> int` ;
  - `charge(db, org, action, *, user, bid_id, ref_id) -> CreditEntry | None` (rien si le prix est
    0 ; lève 402 `credits_exhausted`) ;
  - `refund(db, entry, reason)` (idempotent) et `refund_for(db, ref_id, reason)` ;
  - `grant(db, org, amount, reason, admin)`, `give_welcome(db, org)` ;
  - `history(db, org, limit)`.
- Branchements :
  - analyse du DCE : `dce_analysis.request_analysis` (dépôt automatique et relance) ; sans
    crédits au dépôt automatique, l'analyse est créée au statut `waiting_credits` sans être mise en
    file ; fin en erreur → `refund_for` ;
  - rédaction du mémoire : la route de génération ; fin en erreur du travail → remboursement ;
  - régénérer un chapitre : la route de régénération (gratuite si le chapitre est en erreur) ; les
    appels d'IA de la régénération prennent la tâche `memoir_regeneration` (coût séparé) ;
  - pré-remplissage du profil : `POST /profile/suggestions/read` ; fin en erreur → remboursement ;
  - formule : à l'inscription (formule par défaut + `give_welcome`), à la création par Pilao (formule
    choisie), au changement de formule.

### 5.2 API

| Méthode et route | Rôle |
|---|---|
| `GET /auth/me` | ajoute `credits: {total, reference, prices: {action: crédits}}` |
| `GET /credits` | la formule (nom, phrase, modules), le solde détaillé, les prix, l'historique (100) |
| `GET /admin/plans`, `POST /admin/plans`, `PUT /admin/plans/{id}` | formules ; `PUT` répond aussi `organizations_affected` |
| `POST /admin/plans/{id}/archive`, `POST /admin/plans/{id}/unarchive`, `PUT /admin/plans/{id}/default` | archivage, formule par défaut |
| `GET /admin/credit-prices`, `PUT /admin/credit-prices/{action}` | prix, utilisations et coût réel sur 30 jours |
| `PUT /admin/organizations/{id}/plan` | changer de formule (session limitée à l'entreprise) |
| `POST /admin/organizations/{id}/credits`, `GET /admin/organizations/{id}/credits` | recharger, solde et historique |
| `POST /admin/organizations` (lot 2) | accepte `plan_id` (sinon la formule par défaut) |

La liste et la fiche des entreprises ajoutent `plan` (id, nom), `credits_total`, et pour la fiche
`modules_off_plan`. Les réponses de l'espace client ne contiennent **aucun** montant en euros.

### 5.3 Front

- Client : `lib/credits.ts` (libellé d'un bouton avec son prix, bandeau : niveau et texte, pures et
  testées) ; compteur du tableau de bord ; bandeau dans la coquille ; onglet du Profil ; prix et
  refus sur les 4 boutons ; état « Analyse non lancée » ; après une action payante, `/auth/me` est
  relu (solde à jour).
- Admin : page `/admin/formules` (formules et prix des actions), carte
  `components/admin/org-plan.tsx`, champ « Formule » de la création, colonnes de la liste, ligne
  « À surveiller », libellés du journal, « Hors formule » sur la carte « Modules ».

## 6. Erreurs

| Cas | Réponse |
|---|---|
| Crédits insuffisants | 402 `credits_exhausted` « Il faut {n} crédits, il vous en reste {m}. Contactez Pilao{ : …}. » |
| Formule inconnue ; formule archivée donnée à une entreprise ou mise par défaut | 404 « Formule inconnue. » / 409 « Cette formule est archivée. » |
| Nom de formule déjà pris | 409 « Une formule porte déjà ce nom. » |
| Archiver la formule par défaut | 409 « Choisissez d'abord une autre formule par défaut. » |
| Module inconnu dans une formule | 422 |
| Action inconnue (prix) | 404 « Action inconnue. » |
| Recharge hors bornes, raison vide | 422 |

## 7. Tests

- **Calculs** (`tests/domain/`) : solde, ordre mois puis supplémentaires, changement de mois (heure
  de Paris), changement de formule en cours de mois, remboursement (même mois, mois passé),
  référence du bandeau.
- **Actions** (`tests/api/`) : pour chacune des 4 actions, prise au lancement, refus 402 avec le
  message, remboursement à l'échec (une seule fois), prix 0 = gratuit ; analyse automatique en
  attente sans crédits puis lancée à la main ; chapitre en erreur relancé gratuitement ; deux prises
  simultanées ne passent pas sous 0 ; plafond mensuel d'IA → remboursé.
- **Formules** : création, modification appliquée aux entreprises (exceptions gardées), une seule par
  défaut, archivage, crédits offerts donnés une seule fois (inscription, création par Pilao,
  changement de formule), journal, session d'entreprise refusée sur les routes `/admin`.
- **Cloisonnement** : une entreprise ne voit ni le solde ni l'historique d'une autre ; aucune
  réponse de l'espace client ne contient « € » ni un coût.
- **Front** (vitest) : libellés de prix, niveaux du bandeau.
- **Navigateur** (`journey.cjs`) : l'admin crée une formule et la donne à l'entreprise du parcours ;
  le client voit son solde, lance une action payante, le voit baisser ; à 0, bouton grisé et
  bandeau rouge ; l'admin recharge ; l'action repasse ; captures `admin-formules.png`,
  `credits.png`.

## 8. Documentation

- `docs/04` : US-6.11 à US-6.14 ; le module 6 mis à jour.
- `docs/05` (service des crédits, registre des actions), `docs/06` (tables), `docs/10` (lot 4
  fait), `docs/12` : ADR-043 (crédits par action, journal, euros jamais côté client), `docs/13` :
  Q3 (l'outil est prêt, les prix restent à décider), `docs/01` (la grille est réglée dans
  l'admin).
- `CLAUDE.md` §6.

## Hors périmètre du lot 4

Le paiement en ligne et les factures (Stripe) ; retirer des crédits ; des crédits par utilisateur ;
l'expiration des crédits supplémentaires ; des e-mails d'alerte au client (bandeau seulement) ; le
prorata au changement de formule ; une période d'essai limitée dans le temps ; des modules
nouveaux (devis, CRM).

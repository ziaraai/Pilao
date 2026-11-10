# Administration de la plateforme, lot 1 : compte super admin et supervision — conception

- **Date** : 2026-11-10
- **Statut** : validé et livré (lot 1).
- **Stories** : US-6.1 à US-6.3 (nouvelles, « Module 6 — Administration de la plateforme »). Le rôle
  `platform_admin` existe déjà dans `docs/04` et la table `platform_admins` en base (vide, sans
  écran).

## 0. Le back-office, en cinq lots

Le super admin est l'exploitant du SaaS : il gère les comptes, les modules, les formules, les
crédits, les clés API et les modèles d'IA. C'est trop pour un seul chantier ; chaque lot a sa
conception, son plan et sa mise en ligne.

| Lot | Contenu | Ce document |
|---|---|---|
| 1 | Espace d'administration, compte super admin séparé, supervision en lecture seule | oui |
| 2 | Gestion des comptes : créer, suspendre, réactiver, utilisateurs, invitations, suppression | non |
| 3 | Socle des modules : modules internes déclarés dans le code, activés par entreprise, menu adapté ; le produit actuel devient le module « Appels d'offres » | non |
| 4 | Formules et crédits : une formule = des modules + des crédits ; attribution à la main, Stripe plus tard | non |
| 5 | Réglages de la plateforme : modèle d'IA par tâche, clés API (chiffrées en base), imports | non |

Décisions prises en discussion, valables pour tous les lots :

- Le compte super admin est **séparé de tout compte d'entreprise** : ses propres comptes, ses
  propres sessions, sa propre page de connexion.
- Les modules (lot 3) sont des **modules internes activables**, pas des plugins installables.
- Le super admin **ne lit jamais le contenu** des mémoires, des DCE ni des documents déposés
  (`docs/04`, rôle `platform_admin`).

## 1. But

Donner à l'exploitant de Pilao un espace à lui, sûr, d'où il voit ce qui se passe sur la
plateforme sans pouvoir rien y modifier : qui est inscrit, qui s'en sert, ce que coûte l'IA,
ce qui est en panne, ce que disent les testeurs.

**Réussi quand** : Faycal crée son accès par une commande sur le serveur, se connecte sur
`app.pilao.pro/admin` avec son mot de passe et le code de son téléphone, et voit en une page les
entreprises du pilote, leur activité des 7 derniers jours, le coût de l'IA du mois, l'état des
imports TED / BOAMP et les tâches en erreur — sans passer par le terminal du serveur
(`feedback-report`, `psql`). Aucune session d'entreprise n'atteint ces écrans, et ces écrans ne
peuvent rien écrire chez un client.

## 2. Parcours

### 2.1 Créer son accès (une fois)

1. Dans le terminal de Plesk :
   `/opt/pilao/pilao.sh exec api python -m app.cli admin-access faycal@exemple.fr --name "Faycal"`.
   La commande crée le compte (ou réinitialise son accès s'il existe) et affiche un **lien
   d'activation** à usage unique, valable 30 minutes : `https://app.pilao.pro/admin/activation?jeton=…`.
2. Page d'activation, étape 1 : choisir un mot de passe (12 caractères au moins, saisi deux fois).
3. Étape 2 : un QR code (et la clé en texte, pour une saisie à la main) à scanner avec une
   application d'authentification ; saisir le code à 6 chiffres qu'elle affiche.
4. Étape 3 : **8 codes de secours** affichés une seule fois, avec « Copier » et la case
   « J'ai noté mes codes » ; puis l'administration s'ouvre, la session est déjà ouverte.

Aucun écran ne crée ni ne promeut un super admin : seul un accès au serveur le peut.

### 2.2 Se connecter

`/admin/connexion` : e-mail, mot de passe, code (les 6 chiffres de l'application, ou un code de
secours). Un seul bouton, une seule réponse en cas d'échec : « Identifiants ou code incorrects. »
Après 5 échecs en 15 minutes : « Trop de tentatives. Réessayez dans quelques minutes. »
La session dure 12 heures ; à son expiration, retour à la page de connexion puis à la page demandée.

### 2.3 Superviser

Barre de gauche bleu marine (pour ne jamais confondre avec l'espace d'une entreprise), mention
« Administration », cinq entrées ; en haut de chaque page, la pastille « Lecture seule ».

1. **Vue d'ensemble** (`/admin`) : six compteurs, « À surveiller », activité des 7 derniers
   jours par entreprise, imports des annonces, temps gagné par les testeurs.
2. **Entreprises** (`/admin/entreprises`) : la liste ; un clic ouvre la **fiche**
   (`/admin/entreprises/{id}`).
3. **Coûts de l'IA** (`/admin/couts-ia`) : un mois au choix, total, détail par entreprise, par
   tâche et par modèle.
4. **Technique** (`/admin/technique`) : historique des imports, tâches en erreur ou bloquées.
5. **Avis des testeurs** (`/admin/avis`) : les avis laissés dans l'application et le temps gagné.

### 2.4 Téléphone changé ou perdu

- Avec un code de secours : il remplace le code à 6 chiffres, une fois. La page d'accueil
  rappelle alors combien de codes il reste.
- Sans code de secours : relancer `admin-access` sur le serveur ; l'accès est réinitialisé
  (mot de passe, application, codes de secours, sessions) et un nouveau lien s'affiche.
- `admin-access EMAIL --disable` ferme un compte et ses sessions tout de suite.

## 3. Données (migration 0022)

Aucune table d'entreprise n'est modifiée. Ces trois tables sont **globales** (pas d'`org_id`).

**`platform_admins`** (existe : `id`, `email`, dates) — colonnes ajoutées :

| Colonne | Type | Rôle |
|---|---|---|
| `full_name` | text null | affiché dans la barre de gauche |
| `password_hash` | text null | Argon2, comme les comptes d'entreprise |
| `totp_secret_enc` | text null | secret de l'application d'authentification, **chiffré** (§5) |
| `totp_confirmed_at` | timestamptz null | vide tant que le premier code n'a pas été vérifié |
| `totp_last_step` | bigint null | dernier pas de temps accepté : un code ne sert qu'une fois |
| `recovery_codes` | jsonb, `[]` | empreintes SHA-256 des codes de secours restants |
| `setup_token_hash` | char(64) null, unique | empreinte du lien d'activation |
| `setup_expires_at` | timestamptz null | fin de validité du lien |
| `last_login_at` | timestamptz null | |
| `disabled_at` | timestamptz null | compte fermé |

**`platform_admin_sessions`** : `id`, `admin_id` (→ `platform_admins`, cascade), `token_hash`
char(64) unique, `expires_at`, `revoked_at`, `ip`, `user_agent`, `created_at`. Le calque de
`user_sessions`, sans `org_id`.

**`platform_audit_logs`** : `id`, `admin_id` (→ `platform_admins`, `set null`), `admin_email`
(gardé si le compte disparaît ; pour un échec, l'e-mail saisi), `action`, `org_id` uuid null
(sans clé étrangère : la ligne survit à la suppression de l'entreprise), `at`, `ip`, `meta` jsonb.
Index sur (`action`, `at`).

Actions du lot 1 : `access_reset` et `disabled` (commande), `setup_completed`, `login`,
`login_failed`, `recovery_code_used`, `logout`, `organization_viewed`.

Conservation : sessions effacées dès leur fin et journal effacé après 12 mois, par la purge
horaire existante (`services/retention.py`).

Le journal est écrit dès ce lot ; son écran de consultation arrive au lot 2, avec les premières
actions qui modifient quelque chose.

## 4. API

Toutes les routes sont sous `/admin` (en production : `app.pilao.pro/api/admin/…`), dans
`app/routers/admin/` ; la logique dans `app/services/admin/`.

| Méthode et route | Rôle |
|---|---|
| `POST /admin/auth/setup/lookup` | `{token}` → `{email}` ; 404 « Lien invalide ou expiré. » |
| `POST /admin/auth/setup/password` | `{token, password}` → enregistre le mot de passe, crée le secret ; `{secret, otpauth_uri, qr_svg}` |
| `POST /admin/auth/setup/confirm` | `{token, code}` → vérifie le code, active le compte, ouvre la session ; `{recovery_codes}` (seule fois) |
| `POST /admin/auth/login` | `{email, password, code}` → cookie de session ; `{email, full_name, recovery_codes_left, previous_login_at}` |
| `POST /admin/auth/logout` | révoque la session |
| `GET /admin/auth/me` | le super admin connecté, même forme que la réponse de connexion |
| `GET /admin/overview` | compteurs, alertes, activité 7 jours, derniers imports, temps gagné |
| `GET /admin/organizations` | la liste des entreprises |
| `GET /admin/organizations/{id}` | la fiche (écrit `organization_viewed` au journal) |
| `GET /admin/ai-costs?month=AAAA-MM` | coûts du mois (par défaut le mois en cours), 12 mois proposés |
| `GET /admin/system` | 20 derniers imports, 50 dernières tâches en erreur ou bloquées (30 jours) |
| `GET /admin/feedback?days=30` | avis (7, 30 ou 90 jours) et temps gagné |

Trois dépendances FastAPI, dans `app/core/admin_deps.py` :

- `CurrentAdmin` : lit **seulement** le cookie `pilao_admin_session`, cherche la session dans
  `platform_admin_sessions` (non révoquée, non expirée, compte non fermé), applique le même
  contrôle d'origine que l'espace client (`_csrf_check`). Sinon 401.
- `AdminDb` : session sans portée, en écriture, réservée à la connexion et au journal.
- `AdminReadDb` : session sans portée ouverte **en lecture seule côté PostgreSQL**
  (`SET TRANSACTION READ ONLY`). Toutes les routes de supervision lisent par elle : une écriture,
  même par erreur de code, est refusée par la base.

Aucune route `/admin` n'accepte le cookie `pilao_session`, et `get_auth_context` (espace client)
ne lit pas le cookie d'administration : deux noms de cookie, deux tables de sessions.

## 5. Sécurité de la connexion

- **Mot de passe** : 12 caractères au moins, Argon2 (`core/security.py`).
- **Code** : TOTP (RFC 6238 : SHA-1, 6 chiffres, pas de 30 s), fenêtre de ± 1 pas ; un pas déjà
  accepté est refusé (`totp_last_step`). Bibliothèque `pyotp`.
- **Secret chiffré** : Fernet (`cryptography`), clé dérivée de `APP_SECRET_KEY` par HKDF-SHA256
  (`info = "pilao/platform-admin/totp"`), dans `app/core/crypto.py`. Ce module servira aux clés
  API du lot 5. Changer `APP_SECRET_KEY` rend les secrets illisibles : relancer `admin-access`.
- **QR code** : dessiné par le serveur en SVG (`segno`) ; le secret n'est renvoyé que pendant
  l'activation, jamais ensuite.
- **Codes de secours** : 8 codes `xxxxx-xxxxx` tirés au hasard, stockés en empreintes, chacun
  utilisable une fois.
- **Lien d'activation** : jeton aléatoire, seule son empreinte est en base, 30 minutes, détruit
  à l'activation.
- **Blocage** : 5 échecs pour un même e-mail ou 30 pour une même adresse IP en 15 minutes → 429
  (la fenêtre et le seuil par adresse IP sont ceux des comptes d'entreprise). Un mot de passe juste
  avec un code faux compte comme un échec.
  Les échecs sont comptés dans `platform_audit_logs` (`login_failed`). Tentatives sur un même
  e-mail sérialisées (verrou consultatif), comme pour les comptes d'entreprise.
- **Pas d'indice** : même message et même travail (hachage compris) que l'e-mail existe ou non,
  que l'erreur soit le mot de passe ou le code.
- **Cookie** : `pilao_admin_session`, `HttpOnly`, `Secure`, `SameSite=Strict`, 12 heures, sans
  prolongation.
- **Limiteur** par adresse IP sur les routes `/admin/auth/*` (`core/ratelimit.py`).
- **Moteurs de recherche** : les pages `/admin` portent `robots: noindex, nofollow`.

Réglages (`core/config.py`) : `admin_session_cookie_name`, `admin_session_ttl_hours` (12),
`admin_setup_ttl_minutes` (30), `admin_login_max_failures` (5), `admin_audit_retention_days` (365).

## 6. Ce que montre la supervision

Jours et mois en heure de Paris. Montants en euros, deux décimales.

**Définitions**

- *Dernière activité* d'une entreprise : la plus récente entre la dernière connexion d'un de ses
  utilisateurs (`users.last_login_at`) et sa dernière action journalisée (`audit_log.at`).
- *Active sur 7 jours* : dernière activité depuis moins de 7 jours.
- *Dossiers en cours* : `bids.status` ∈ `to_review`, `in_progress`.
- *Mémoires rédigés* : `memoirs.status` ∈ `ready`, `exported`.
- *Coût de l'IA* : somme de `ai_calls.cost_eur` ; un appel sans entreprise (`org_id` vide) est
  rangé sous « Plateforme ».
- *Tâche en erreur* : `jobs.status = error`, datée de sa fin (`finished_at`, à défaut
  `updated_at`) ; *bloquée* : `running` depuis plus de 30 minutes (`started_at`) ou `pending`
  depuis plus de 30 minutes (`created_at`).

**Vue d'ensemble**

- Sous le titre : « Votre connexion précédente : hier à 17:42 » (l'avant-dernière entrée
  `login` du journal), pour repérer une connexion qui ne serait pas la vôtre.
- Compteurs : entreprises inscrites, actives sur 7 jours, dossiers en cours, mémoires rédigés,
  coût de l'IA du mois, tâches en erreur sur 24 heures.
- « À surveiller », le rouge d'abord, le plus récent en tête :
  - rouge — dernière passe d'un import (TED, BOAMP) en erreur, ou aucune passe réussie depuis
    6 heures, ou jamais (sources activées seulement) ;
  - rouge — chaque tâche en erreur sur 24 heures ou bloquée (10 lignes, puis « et n autres ») ;
  - rouge — sur 24 heures, plus de 20 % d'appels à l'IA en échec (10 appels au moins) ;
  - orange — entreprise inscrite depuis plus de 10 jours et sans activité depuis 10 jours.
  Rien à signaler : « Tout va bien. »
- Activité des 7 derniers jours, par entreprise : connexions (`audit_log`, action `login`),
  dossiers créés, mémoires créés, exports (`generated_documents` : Word, PDF, ZIP).
- Imports : dernière passe de chaque source (heure, lues, nouvelles, état).
- Temps gagné : par entreprise, sur les dossiers où les deux durées sont saisies (le calcul de
  `feedback-report`).

**Entreprises** — colonnes : nom, ville, inscrite le, utilisateurs, dernière activité, dossiers,
mémoires, profil complété (%), coût de l'IA du mois ; pastille « Suppression demandée » si une
demande d'effacement est en cours. Tri : dernière activité. 200 lignes au plus (pas de pagination
au lot 1).

**Fiche d'une entreprise**

- Identité : nom, SIRET, forme juridique, code NAF, ville et code postal, métiers, départements
  de veille, version des conditions acceptées.
- Compteurs : dossiers (par statut), mémoires rédigés, documents de la base documentaire,
  attestations (valides / expirées), profil complété, coût de l'IA du mois.
- Utilisateurs : nom, e-mail, rôle, e-mail vérifié, dernière connexion.
- Coût de l'IA : les 6 derniers mois, et le mois en cours par tâche.
- Tâches en erreur des 30 derniers jours : libellé, date, message.
- Avis laissés.

**Jamais affiché**, ni renvoyé par l'API : le texte d'un mémoire, d'un DCE ou d'un document, un
fichier, le titre d'un dossier, les lignes du profil (moyens, références, chiffre d'affaires).
Un message d'erreur de tâche est celui que l'utilisateur voit déjà ; il peut nommer un fichier,
jamais en citer le contenu.

**Coûts de l'IA** — pour le mois choisi : total ; par entreprise (appels, jetons lus et écrits,
coût) ; par tâche (appels, échecs, durée moyenne, coût) ; par modèle (appels, coût).
Libellés des tâches : `dce_extraction` « Analyse du DCE », `memoir_generation` « Rédaction du
mémoire », `tender_scoring` « Score des annonces », `profile_extraction` « Lecture des documents
du profil », `compliance_reading` « Lecture des attestations », `embedding` « Indexation ».

**Technique** — imports : source, début, durée, lues, nouvelles, mises à jour, corrigées,
écartées, état, erreur. Tâches : libellé en français (à défaut le code de la tâche), entreprise,
date, état (en erreur / bloquée), message.

**Avis des testeurs** — date, entreprise, utilisateur, type (Idée, Problème, Question), page,
message ; puis le temps gagné par entreprise.

## 7. Écrans (front)

- Groupe de routes `app/(admin)/admin/…` avec son `layout.tsx` et son `AdminShell`
  (`components/admin/`) : barre bleu marine `#011844`, entrée active en vert Pilao, nom du super
  admin et « Déconnexion » en bas. Sur téléphone, la barre se replie comme celle de l'espace client.
- Pages : `connexion`, `activation`, `page.tsx` (vue d'ensemble), `entreprises`,
  `entreprises/[id]`, `couts-ia`, `technique`, `avis`.
- Composants communs réutilisés (ADR-038) : `Card` à bandeau, compteurs, `tableHead` /
  `tableRow`, `PageTitle`. Couleurs : vert Pilao entreprises, bleu activité, ambre coûts,
  rouge erreurs, vert imports, violet avis.
- `lib/admin-auth.tsx` : le super admin connecté ; un 401 renvoie à
  `/admin/connexion?suite=…`. Types dans `lib/types.ts`.
- L'espace client ne contient **aucun lien** vers `/admin`.

## 8. Erreurs

| Cas | Réponse |
|---|---|
| Lien d'activation inconnu, expiré ou déjà utilisé | 404 « Lien invalide ou expiré. Relancez la commande sur le serveur. » |
| Mot de passe trop court, ou les deux saisies différentes | message sous le champ, rien n'est enregistré |
| Code d'activation faux | 400 « Code incorrect. Vérifiez l'heure de votre téléphone. » ; le lien reste valable |
| Connexion refusée (e-mail, mot de passe, code, compte fermé ou non activé) | 401 « Identifiants ou code incorrects. » |
| Trop d'échecs | 429 « Trop de tentatives. Réessayez dans quelques minutes. » |
| Session d'entreprise sur une route `/admin`, ou pas de session | 401 |
| Entreprise inconnue | 404 |
| Mois mal formé ou hors des 12 derniers | 422 |

## 9. Tests

- **Connexion** (`tests/api/test_admin_auth.py`) : activation complète ; lien expiré ou rejoué ;
  mot de passe court ; code faux, code rejoué (même pas de temps), code du pas voisin accepté ;
  code de secours utilisable une fois ; blocage après 5 échecs ; même réponse pour un e-mail
  inconnu ; compte fermé ; session expirée ou révoquée ; `admin-access` crée, réinitialise
  (sessions révoquées) et ferme un compte.
- **Cloisonnement** (`tests/api/test_admin_isolation.py`) : une session d'entreprise reçoit 401
  sur chaque route `/admin` ; une session de super admin reçoit 401 sur les routes d'entreprise ;
  une écriture par `AdminReadDb` échoue ; avec un texte témoin placé dans un mémoire, un DCE, un
  document, un titre de dossier et une ligne de profil, aucune réponse `/admin` ne le contient.
- **Supervision** (`tests/api/test_admin_supervision.py`) : avec deux entreprises, chaque
  compteur, chaque règle de « À surveiller » (déclenchée et non déclenchée), l'activité des
  7 jours, les coûts par mois, entreprise, tâche et modèle (appels sans entreprise sous
  « Plateforme »), la fiche et son entrée au journal, les imports, les tâches, les avis.
- **Domaine** (`tests/domain/test_totp.py`, `test_crypto.py`) : codes TOTP contre les vecteurs de
  la RFC, chiffrement aller-retour, clé différente → échec.
- **Rétention** : sessions finies et journal de plus de 12 mois effacés.
- **Navigateur** (`apps/web/e2e/journey.cjs`, étape nouvelle) : commande, activation avec un code
  calculé, déconnexion, connexion, visite des 5 écrans et d'une fiche, puis refus de `/admin`
  pour un compte d'entreprise.

## 10. Documentation

- `docs/04` : « Module 6 — Administration de la plateforme », US-6.1 (accès), US-6.2
  (supervision), US-6.3 (journal).
- `docs/05` (arborescence), `docs/06` (tables), `docs/09` (accès d'administration, journal,
  conservation), `docs/10` (les cinq lots), `docs/14` (créer son accès, réinitialiser).
- `docs/12` : ADR-040 (back-office en cinq lots ; compte séparé, TOTP, lecture seule par la
  base) et ADR-041 (modules internes activables, à concevoir au lot 3).
- `CLAUDE.md` : la commande `admin-access` ; `apps/web/e2e/README.md`.

## Hors périmètre du lot 1

Toute action qui modifie quelque chose (suspendre, créer, inviter, supprimer : lot 2) ; modules
(lot 3) ; formules et crédits (lot 4) ; réglages, clés API, modèles (lot 5) ; un écran pour gérer
les super admins ; l'accès de support au contenu d'un client ; les alertes par e-mail ; l'export
CSV (la commande `feedback-report --csv` reste) ; la pagination des listes.

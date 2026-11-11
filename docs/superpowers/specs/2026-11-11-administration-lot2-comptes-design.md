# Administration de la plateforme, lot 2 : gestion des comptes — conception

- **Date** : 2026-11-11
- **Statut** : validé et livré (lot 2).
- **Stories** : US-6.4 à US-6.8 (nouvelles), US-1.6 « Mot de passe oublié » (nouvelle, espace client).
- **S'appuie sur** : le lot 1 (`2026-11-10-administration-lot1-supervision-design.md`), ADR-040.

## 1. But

Le lot 1 permet de **voir** ; le lot 2 permet d'**agir sur les comptes** sans passer par le
serveur : ouvrir l'espace d'une entreprise, la suspendre et la réactiver, la supprimer, dépanner
ses utilisateurs, et relire ce qui a été fait. Les clients gagnent « Mot de passe oublié ? ».

**Réussi quand** : Faycal ouvre l'espace d'un nouveau client depuis `/admin` et le client reçoit
son lien ; il suspend un compte et ses utilisateurs sont dehors dans la seconde, avec un message
clair ; il réactive et tout revient ; il supprime un compte de test sur-le-champ et programme la
suppression d'un vrai client à 30 jours ; il renvoie un lien de mot de passe à un utilisateur
bloqué ; et le journal montre chacune de ces actions. À aucun moment il ne choisit un mot de passe
à la place de quelqu'un, ne se connecte en tant que lui, ni ne lit le contenu d'un client.

Décisions prises en discussion :

1. Deux façons d'ouvrir un compte : l'inscription libre (inchangée) **et** la création depuis
   l'administration.
2. Suspendre = **bloquer l'accès**, rien n'est effacé ; réactiver rend tout.
3. Supprimer = **immédiat** si personne de l'entreprise ne s'est jamais connecté ; sinon
   suspension et effacement **dans 30 jours**, annulable.
4. Utilisateurs : ajouter, renvoyer l'invitation ou l'e-mail de confirmation, envoyer un lien
   « nouveau mot de passe », changer le rôle, déconnecter partout, retirer. « Mot de passe
   oublié ? » en libre-service pour tous.
5. Les actions de l'administration **réutilisent les règles existantes** de l'espace client
   (`services/members.py`, `services/org_data.py`), « au nom de Pilao ».
6. Supprimer une entreprise et retirer un utilisateur demandent **à nouveau le code** de
   l'application d'authentification.

## 2. Parcours

### 2.1 Créer une entreprise

`/admin/entreprises` → bouton **« Créer une entreprise »** → `/admin/entreprises/nouvelle` :

1. SIRET (14 chiffres, clé de Luhn vérifiée comme à l'inscription). « Rechercher » interroge
   l'annuaire des entreprises (même route et même repli que l'inscription : annuaire injoignable →
   saisie à la main) et remplit le nom, la forme juridique, le code NAF, l'adresse.
2. Nom de l'entreprise (pré-rempli, modifiable).
3. Responsable : nom et e-mail.
4. « Créer et envoyer l'invitation ».

Le responsable est créé **administrateur, sans mot de passe** ; il reçoit :

> Objet : Pilao a ouvert l'espace de {entreprise}
>
> Bonjour {nom},
>
> L'équipe Pilao a ouvert l'espace de {entreprise} sur Pilao, la plateforme qui vous aide à
> répondre aux appels d'offres publics. Choisissez votre mot de passe pour y entrer (lien
> valable 7 jours) : {lien}

Le lien mène à la page d'invitation existante (`/invitation?token=…`) : nom, mot de passe
(12 caractères au moins), acceptation des conditions, puis l'espace s'ouvre. L'adresse est alors
confirmée (le lien l'a prouvée). Après la création, l'écran ouvre la fiche de l'entreprise.

Refus : SIRET déjà inscrit (« Ce SIRET a déjà un compte : {nom}. », avec le lien vers sa fiche),
e-mail déjà utilisé, SIRET invalide.

### 2.2 Suspendre, réactiver

Fiche d'une entreprise, en haut : **« Suspendre »** ouvre une fenêtre : raison (obligatoire,
500 caractères au plus, visible seulement dans l'administration), « Suspendre l'accès ».

Effet immédiat :

- toutes les sessions de l'entreprise sont révoquées ;
- connexion refusée avec : « L'accès de votre entreprise à Pilao est suspendu. Contactez Pilao :
  {SUPPORT_EMAIL}. » (sans adresse configurée : « … Contactez Pilao. ») ; le message n'est montré
  qu'après un mot de passe juste ;
- une page déjà ouverte reçoit le même refus à sa prochaine requête et renvoie à la connexion,
  qui affiche le message ;
- lien d'invitation, lien de confirmation d'e-mail et lien « nouveau mot de passe » de
  l'entreprise : refusés avec le même message ; aucun nouvel e-mail ne part pour elle ;
- la veille ne crée plus de correspondances ni de scores pour elle (pas de coût d'IA) ; pas
  d'alerte quotidienne, pas de rappel d'attestation.

La fiche et la liste affichent la pastille rouge **« Suspendue »**, la date et la raison.
**« Réactiver »** (une confirmation) efface la suspension ; la veille rattrape les annonces
ouvertes pour l'entreprise (`rematch_org`). Aucun e-mail n'est envoyé ni à la suspension ni à
la réactivation : Faycal prévient le client lui-même.

### 2.3 Supprimer

**« Supprimer »** ouvre une fenêtre qui annonce le mode :

- **Jamais utilisée** (aucun de ses utilisateurs n'a de `last_login_at`) : « Personne ne s'est
  jamais connecté à cet espace : il sera effacé tout de suite, définitivement. »
- **Utilisée** : « L'accès sera suspendu tout de suite et toutes les données seront effacées le
  {date dans 30 jours}. Vous pourrez annuler d'ici là. Ses utilisateurs sont prévenus par
  e-mail. »

Pour confirmer : recopier le nom de l'entreprise **et** saisir le code de l'application.

- Immédiat : l'entreprise est effacée par la même fonction que l'effacement programmé (fichiers
  du stockage d'abord, puis la base ; trace dans `purge_logs`) ; aucun e-mail ; retour à la
  liste avec « {nom} a été supprimée. ».
- Programmé : l'entreprise est suspendue (raison « Suppression programmée par Pilao » si elle ne
  l'était pas déjà), une demande `deletion` est créée (échéance 30 jours,
  `deletion_grace_days`), ses utilisateurs confirmés reçoivent :

  > Objet : Suppression des données de {entreprise} programmée le {date}
  >
  > Bonjour,
  >
  > Pilao a programmé la suppression de toutes les données de {entreprise} : elle aura lieu le
  > {date}. Comptes, profil, dossiers, mémoires, attestations et fichiers seront effacés
  > définitivement. Pour toute question, contactez Pilao{ : SUPPORT_EMAIL}.

  La purge horaire existante l'efface à l'échéance.

Pendant le délai, la fiche affiche « Suppression le {date} » et **« Annuler la suppression »**.
L'annulation vaut aussi pour une suppression demandée par le client lui-même. Après annulation,
l'entreprise **reste suspendue** si elle l'était (« Réactiver » pour lui rendre l'accès) : rien ne
se rouvre par surprise. Les utilisateurs reçoivent « Suppression des données de {entreprise}
annulée ».

Si le client avait lui-même programmé la suppression, le bouton « Supprimer » est remplacé par
« Annuler la suppression » (une demande à la fois).

### 2.4 Utilisateurs d'une entreprise

Carte « Utilisateurs » de la fiche : nom, e-mail, rôle, état (« Actif », « E-mail non
confirmé », « Invitation envoyée le … », « Invitation expirée »), dernière connexion. Bouton
**« Ajouter un utilisateur »** (nom, e-mail, rôle) : invitation au nom de Pilao, objet
« L'équipe Pilao vous invite sur Pilao ({entreprise}) ».

Actions de chaque ligne (seules celles qui ont un sens sont proposées) :

| Action | Proposée quand | Effet |
|---|---|---|
| Renvoyer l'invitation | pas de mot de passe | nouveau lien de 7 jours |
| Renvoyer l'e-mail de confirmation | mot de passe, e-mail non confirmé | nouveau lien de confirmation |
| Envoyer un lien « nouveau mot de passe » | mot de passe | e-mail du §2.5 |
| Passer administrateur / membre | toujours | refusé s'il s'agit du dernier administrateur |
| Déconnecter partout | sessions ouvertes | toutes ses sessions révoquées |
| Retirer | toujours | code de l'application demandé ; refusé pour le dernier administrateur |

Les envois sont plafonnés comme côté client : 5 par heure et par utilisateur
(`email_verify_max_per_hour`). Sur une entreprise suspendue, rien n'est envoyé : « Ajouter un
utilisateur » et les trois envois sont refusés ; « Retirer », « Passer administrateur / membre »
et « Déconnecter partout » restent possibles.

### 2.5 Mot de passe oublié (espace client)

- Page de connexion : lien **« Mot de passe oublié ? »** → `/mot-de-passe-oublie` : e-mail,
  « Recevoir un lien ». Réponse toujours identique : « Si un compte existe pour cette adresse,
  un e-mail vient de partir. Le lien est valable 1 heure. »
- E-mail (seulement pour un compte qui a un mot de passe, d'une entreprise non suspendue) :

  > Objet : Choisir un nouveau mot de passe Pilao
  >
  > Bonjour, pour choisir un nouveau mot de passe, ouvrez ce lien (valable 1 heure) : {lien}.
  > Si vous n'avez rien demandé, ignorez ce message : votre mot de passe ne change pas.

  Un compte invité qui n'a jamais créé son accès reçoit à la place une **nouvelle invitation**.
- `/nouveau-mot-de-passe?token=…` : le jeton est lu une fois puis retiré de l'adresse (comme la
  page d'invitation) ; nouveau mot de passe (12 caractères au moins, saisi deux fois) ;
  « Enregistrer ». Effet : mot de passe changé, **toutes les sessions** de l'utilisateur
  révoquées, adresse confirmée si elle ne l'était pas, nouvelle session ouverte, arrivée sur le
  tableau de bord.
- Lien inconnu, expiré ou déjà utilisé : « Ce lien n'est plus valable. Demandez-en un nouveau. »
  avec le lien vers `/mot-de-passe-oublie`.

### 2.6 Journal

Sixième entrée du menu, **« Journal »** (`/admin/journal`) : date (heure de Paris), qui (e-mail du
super admin), action en français, entreprise (lien vers sa fiche si elle existe encore, sinon
« Entreprise supprimée »), détail (utilisateur visé, raison de suspension, mode de suppression,
adresse IP). Filtres : type d'action (connexions / comptes / tout), entreprise. 100 lignes,
puis « Plus anciennes ». La fiche d'une entreprise a un lien « Voir le journal de cette
entreprise ».

### 2.7 La pastille « Lecture seule »

Elle reste sur les pages qui ne font que lire (vue d'ensemble, coûts de l'IA, technique, avis,
journal) et disparaît de la liste des entreprises et de la fiche, qui ont désormais des actions.

## 3. Données (migration 0023)

**`organizations`** — colonnes ajoutées :

| Colonne | Type | Rôle |
|---|---|---|
| `suspended_at` | timestamptz null | accès bloqué depuis |
| `suspension_reason` | text null | raison saisie par Pilao |

**`data_requests`** — colonne ajoutée : `platform_admin_id` uuid null (→ `platform_admins`,
`set null`) : la suppression a été programmée par Pilao (`requested_by` reste vide).

**`auth_tokens`** — nouveau `kind` : `password_reset` (1 heure). La purge existante efface les
jetons expirés ou utilisés.

**`audit_logs`** (historique de l'entreprise) — une action faite par Pilao a `user_id` vide et
`meta = {"by": "pilao"}`.

**`platform_audit_logs`** — actions ajoutées : `organization_created`, `organization_suspended`,
`organization_reactivated`, `organization_deleted` (meta `mode` : `immediate` / `scheduled`),
`deletion_cancelled`, `user_invited`, `invitation_resent`, `verification_resent`,
`password_reset_sent`, `role_changed`, `user_logged_out`, `user_removed`, `step_up_failed`.
`meta` porte l'utilisateur visé (id et e-mail), la raison, le rôle ; jamais de contenu.

Réglages (`core/config.py`) : `support_email` (vide par défaut, variable `SUPPORT_EMAIL`),
`password_reset_ttl_minutes` (60).

## 4. Construction

### 4.1 Qui agit

Les fonctions de `services/members.py` et `services/org_data.py` prennent un **auteur** au lieu
d'un `User` : `Actor = User | PlatformActor`, où `PlatformActor` porte le super admin. Pour un
`PlatformActor` : l'historique de l'entreprise reçoit `user_id` vide et `meta.by = "pilao"`, les
e-mails parlent de « L'équipe Pilao », et la règle « vous ne pouvez pas vous retirer vous-même »
ne s'applique pas. Les règles communes (dernier administrateur, nombre maximal d'utilisateurs,
plafond d'envois, adresse unique dans tout Pilao) restent à un seul endroit.

### 4.2 Où il agit

Nouvelle dépendance `AdminOrgDb` (`core/admin_deps.py`) pour les routes qui écrivent : super admin
connecté, entreprise chargée (404 sinon), puis `scope_session(db, org_id)` — la même barrière que
l'espace client : la session ne voit et n'écrit que les lignes de cette entreprise. Les routes de
supervision gardent `AdminReadDb` (lecture seule côté PostgreSQL). Le journal de la plateforme est
écrit par une session séparée sans portée, dans la même requête.

Logique dans `app/services/admin/accounts.py` ; routes dans `app/routers/admin/accounts.py`.

### 4.3 La suspension

Une fonction `access_blocked(org) -> bool` (`suspended_at` non vide), vérifiée par :

- `services/auth.login` (après le mot de passe juste) et `core/deps.get_auth_context` →
  403 `account_suspended` ;
- l'invitation (`members.lookup`, `members.accept`), la confirmation d'e-mail, la demande et
  l'usage du lien « nouveau mot de passe » ;
- `tenders.match_tenders` (pas de correspondance), `alerts.send_digests`,
  `alerts.send_expiry_alerts` (entreprises suspendues sautées).

### 4.4 Le code demandé à nouveau

Les routes « supprimer une entreprise » et « retirer un utilisateur » prennent un `code` : un code
à 6 chiffres de l'application (même vérification que la connexion, un pas déjà utilisé est
refusé) ou un code de secours (consommé). Code faux → 400 « Code incorrect. », action
`step_up_failed` au journal ; au 5ᵉ échec en 15 minutes la session d'administration est révoquée
(401, retour à la connexion).

### 4.5 « Jamais utilisée »

`never_used(org)` : aucun utilisateur de l'entreprise n'a de `last_login_at`. Décidé au moment de
la confirmation, sous verrou de la ligne `organizations` (une connexion simultanée ne peut pas
glisser entre la décision et l'effacement).

## 5. API

Les routes `/{id}…` sont sous `/admin/organizations` ; toutes exigent la session d'administration.

| Méthode et route | Corps | Rôle |
|---|---|---|
| `GET /admin/companies/lookup?siret=` | | annuaire (même réponse que `/companies/lookup`) |
| `POST /admin/organizations` | `{siret, name, contact_name, contact_email}` | crée l'entreprise et invite le responsable ; `{id}` |
| `POST /{id}/suspend` | `{reason}` | suspend, révoque les sessions |
| `POST /{id}/reactivate` | | réactive, relance la veille |
| `GET /{id}/deletion` | | `{mode: immediate|scheduled, due_at, pending}` : ce que ferait « Supprimer » |
| `POST /{id}/deletion` | `{confirmation, code}` | `{mode, due_at}` |
| `DELETE /{id}/deletion` | | annule la suppression programmée |
| `POST /{id}/users` | `{email, full_name, role}` | invite |
| `POST /{id}/users/{uid}/invitation` | | renvoie l'invitation |
| `POST /{id}/users/{uid}/verification` | | renvoie l'e-mail de confirmation |
| `POST /{id}/users/{uid}/password-reset` | | envoie le lien « nouveau mot de passe » |
| `PATCH /{id}/users/{uid}` | `{role}` | change le rôle |
| `POST /{id}/users/{uid}/logout` | | révoque ses sessions |
| `POST /{id}/users/{uid}/remove` | `{code}` | retire (POST : le code voyage dans le corps) |
| `GET /admin/audit` | `?kind=&org_id=&before=` | 100 lignes du journal |

La fiche (`GET /admin/organizations/{id}`) et la liste ajoutent : `suspended_at`,
`suspension_reason`, `deletion_due_at`, `deletion_by` (`pilao` / `client`), et par utilisateur
`status` et `has_sessions`.

Espace client (`routers/auth.py`, limiteur par adresse IP comme `/auth/resend-verification`) :

| Méthode et route | Corps | Rôle |
|---|---|---|
| `POST /auth/password/forgot` | `{email}` | 202, toujours le même message |
| `POST /auth/password/reset/lookup` | `{token}` | `{email}` ou 410 |
| `POST /auth/password/reset` | `{token, password}` | change le mot de passe, ouvre la session |

## 6. Écrans

- Admin : `entreprises/nouvelle/page.tsx`, `journal/page.tsx` ; la fiche
  (`entreprises/[id]/page.tsx`) gagne les boutons d'en-tête, la carte « Utilisateurs » avec
  actions, et les fenêtres de confirmation (`components/admin/dialogs.tsx` : raison, nom
  recopié, code). Menu : sixième entrée « Journal ».
- Client : `(auth)/mot-de-passe-oublie/page.tsx`, `(auth)/nouveau-mot-de-passe/page.tsx`, lien
  sur `(auth)/connexion` ; la connexion affiche le message de suspension quand l'API répond
  `account_suspended` ; `useApi` renvoie une page ouverte à `/connexion?suspendu=1`.
- Composants communs réutilisés (ADR-038) ; boutons d'action dangereuse en rouge ; toutes les
  fenêtres utilisables au clavier et sur téléphone.

## 7. Erreurs

| Cas | Réponse |
|---|---|
| SIRET déjà inscrit | 409 « Ce SIRET a déjà un compte : {nom}. » |
| E-mail déjà utilisé dans Pilao | 409 « Cette adresse e-mail a déjà un compte Pilao. » |
| Raison de suspension vide | 422 sous le champ |
| Nom recopié différent | 422 « Recopiez exactement le nom de l'entreprise pour confirmer. » |
| Code faux | 400 « Code incorrect. » ; 5ᵉ échec → 401 |
| Dernier administrateur | 409 « L'entreprise doit garder au moins un administrateur. » |
| Suppression déjà programmée | 409 « La suppression est déjà programmée. » |
| Ajout ou envoi (invitation, confirmation, lien) pour une entreprise suspendue | 409 « Entreprise suspendue : réactivez-la d'abord. » |
| Trop d'envois | 429 « Envoi déjà fait : réessayez plus tard. » |
| Connexion ou page d'une entreprise suspendue | 403 `account_suspended`, message du §2.2 |
| Lien « nouveau mot de passe » invalide | 410 « Ce lien n'est plus valable. Demandez-en un nouveau. » |
| Entreprise ou utilisateur inconnu (ou d'une autre entreprise) | 404 |

## 8. Tests

- **Comptes** (`tests/api/test_admin_accounts.py`) : création (annuaire disponible ou non,
  SIRET pris, e-mail pris), invitation reçue et acceptée de bout en bout ; suspension (sessions
  révoquées, connexion refusée après mot de passe juste seulement, page ouverte refusée,
  invitation, confirmation et lien refusés, aucun e-mail), réactivation (accès rendu, veille
  relancée) ; suppression immédiate (jamais utilisée, `purge_logs`, fichiers effacés) et
  programmée (suspension, e-mails, échéance), annulation (par Pilao, d'une demande du client,
  suspension conservée) ; code faux, code rejoué, code de secours, 5 échecs → session fermée ;
  chaque action d'utilisateur, ses refus et son entrée aux deux journaux.
- **Cloisonnement** : une action sur l'entreprise A avec l'id d'un utilisateur de B → 404, B
  intacte ; une session d'entreprise → 401 sur chaque nouvelle route ; aucune réponse ne contient
  un texte témoin placé dans un mémoire ou un document (le test du lot 1 couvre les nouvelles
  routes).
- **Mot de passe oublié** (`tests/api/test_password_reset.py`) : même réponse pour une adresse
  inconnue, un compte invité (nouvelle invitation), une entreprise suspendue (rien ne part) ;
  lien valable une fois, expiré, sessions révoquées, adresse confirmée ; plafond d'envois.
- **Veille et alertes** : une entreprise suspendue ne reçoit ni correspondance, ni score, ni
  alerte, ni rappel.
- **Journal** : filtres, pagination, entreprise supprimée.
- **Navigateur** (`journey.cjs`) : créer une entreprise, ouvrir le lien reçu, entrer ; suspendre
  (le client voit le message), réactiver ; mot de passe oublié de bout en bout ; ajouter et
  retirer un utilisateur (avec le code) ; lire le journal ; supprimer une entreprise jamais
  utilisée.

## 9. Documentation

- `docs/04` : US-6.4 (créer), US-6.5 (suspendre / réactiver), US-6.6 (supprimer), US-6.7
  (utilisateurs), US-6.8 (journal) ; US-1.6 (mot de passe oublié).
- `docs/06` (colonnes), `docs/09` (suspension, code redemandé, lien de mot de passe, journal),
  `docs/10` (lot 2 fait), `docs/14` (`SUPPORT_EMAIL`), `docs/12` : ADR-042 (actions de
  l'administration par les règles de l'espace client, au nom de Pilao, dans une session à la
  portée de l'entreprise ; code redemandé pour l'irréversible ; suppression immédiate réservée
  aux espaces jamais utilisés).
- `apps/web/e2e/README.md`.

## Hors périmètre du lot 2

Se connecter en tant qu'un utilisateur, choisir son mot de passe, lire son contenu ; modifier
l'identité d'une entreprise depuis l'administration ; gérer les super admins depuis un écran ;
e-mails automatiques de suspension ; modules (lot 3), formules et crédits (lot 4), réglages
(lot 5) ; export CSV du journal.

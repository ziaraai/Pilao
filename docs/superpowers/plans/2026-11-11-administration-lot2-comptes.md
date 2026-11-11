# Administration, lot 2 : gestion des comptes — plan de réalisation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** depuis `/admin`, créer une entreprise, la suspendre et la réactiver, la supprimer (tout de suite si jamais utilisée, sinon dans 30 jours), dépanner ses utilisateurs et lire le journal ; « Mot de passe oublié ? » pour tous les clients.

**Architecture:** une suspension (`organizations.suspended_at`) vérifiée à chaque entrée de l'espace client et dans les tâches de veille ; les fonctions existantes de `members` et `org_data` prennent un **auteur** (`User` ou `PlatformActor`) au lieu d'un `User`, et les routes de l'administration les appellent dans une session à la portée de l'entreprise visée (`AdminOrg`) ; le code de l'application d'authentification est redemandé pour l'irréversible. Côté web : deux pages client (mot de passe), une page de création, la fiche avec ses actions, le journal.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, pytest ; Next.js + Tailwind, vitest, Playwright (`journey.cjs`).

**Spec:** `docs/superpowers/specs/2026-11-11-administration-lot2-comptes-design.md`

## Global Constraints

- Le super admin ne choisit **jamais** un mot de passe, ne se connecte **jamais** en tant qu'un utilisateur, ne reçoit **jamais** le contenu d'un client (règle du lot 1 ; le test témoin de `test_admin_isolation.py` couvre les nouvelles routes).
- Toute écriture dans les données d'une entreprise passe par une session `scope_session(db, org_id)` de **cette** entreprise.
- Une action de Pilao dans `audit_logs` : `user_id = None`, `meta = {"by": "pilao"}`. Au journal de la plateforme (`audit.record`) : l'action, `org_id`, `ip`, et en `meta` l'utilisateur visé (`user_id`, `email`), la raison, le rôle, le mode — jamais de contenu.
- Message de suspension, exact : « L'accès de votre entreprise à Pilao est suspendu. Contactez Pilao : {support_email}. » ; sans adresse : « L'accès de votre entreprise à Pilao est suspendu. Contactez Pilao. » ; code `account_suspended`, statut 403.
- Lien « nouveau mot de passe » : **60** minutes, usage unique, `auth_tokens.kind = "password_reset"`. Mot de passe : **12** caractères au moins.
- Plafond d'envois : `email_verify_max_per_hour` (5) par utilisateur, côté client comme côté admin.
- Suppression : délai `deletion_grace_days` (30) ; « jamais utilisée » = aucun utilisateur de l'entreprise n'a de `last_login_at`.
- Code redemandé : 5 échecs (`admin_login_max_failures`) en `login_window_minutes` (15) → session d'administration révoquée, 401.
- Réglages nouveaux : `support_email: str = ""` (`SUPPORT_EMAIL`), `password_reset_ttl_minutes: int = 60`.
- Migration `0023` (révise `0022`). Code et API en anglais, interface et e-mails en français (textes du spec, §2).
- Avant chaque commit côté API : `uv run ruff check . && uv run black --check . && uv run mypy` ; côté web : `pnpm lint && pnpm format:check && pnpm typecheck && pnpm test`.

## Review Focus

1. **Session ouverte au moment de la suspension** : l'utilisateur clique dans une page déjà chargée → 403 `account_suspended`, et la coquille le renvoie à `/connexion?suspendu=1` qui affiche le message (pas une page blanche ni « Erreur inattendue ») → tests en tâche 1 (API) et tâche 6 (front).
2. **E-mail tapé autrement** dans « Mot de passe oublié » (`  Jean@Exemple.FR `) → même compte trouvé → test en tâche 3.
3. **Course connexion / suppression immédiate** : le premier login d'un utilisateur arrive pendant que l'admin confirme « Supprimer » → la décision et l'effacement se font sous verrou de la ligne `organizations` ; une connexion déjà enregistrée bascule en mode programmé → test en tâche 4 (`last_login_at` posé entre l'aperçu et la confirmation : le mode renvoyé est `scheduled`).
4. **Annuler la suppression d'un client qui l'avait demandée lui-même et n'était pas suspendu** : l'entreprise reste accessible (rien n'est suspendu par l'annulation) → test en tâche 4.
5. **Code de secours en majuscules ou sans tiret** au moment de « Retirer » → accepté comme à la connexion → test en tâche 4.

---

### Task 1: Suspension — colonnes, réglages et contrôles

**Files:**
- Create: `apps/api/alembic/versions/0023_account_management.py`, `apps/api/app/services/suspension.py`
- Modify: `app/db/models/organization.py`, `app/db/models/data_request.py`, `app/core/config.py`, `.env.example`, `app/core/deps.py` (`get_auth_context`), `app/services/auth.py` (`login`, `verify_email`, `resend_verification`), `app/services/members.py` (`_valid_link`), `app/services/tenders.py` (`match_tenders`), `app/services/alerts.py` (`send_digests`, `send_expiry_alerts`)
- Test: `apps/api/tests/api/test_suspension.py`

**Interfaces:**
- Produces: `Organization.suspended_at: datetime | None`, `Organization.suspension_reason: str | None` ; `DataRequest.platform_admin_id: uuid.UUID | None` (FK `platform_admins.id`, `SET NULL`).
- Produces, `app/services/suspension.py` :
  - `is_suspended(org: Organization) -> bool`
  - `suspended_message() -> str` (texte exact des Global Constraints)
  - `suspended_error() -> ApiError` (403, `account_suspended`, `suspended_message()`)
  - `contact_sentence() -> str` : « Pour toute question, contactez Pilao : {support_email}. » ou « Pour toute question, contactez Pilao. » (e-mails du §2.3)

- [ ] **Step 1: Write the failing tests** (`test_suspension.py`, une entreprise inscrite par `signed_in_client`, puis `suspended_at` posé en base) :
  - `test_login_refused_after_right_password_only` : mot de passe juste → 403 `account_suspended`, message exact ; mot de passe faux → 401 « E-mail ou mot de passe incorrect. » (le compte suspendu ne se révèle pas).
  - `test_open_session_refused` : `GET /auth/me` avec la session d'avant → 403 `account_suspended`.
  - `test_message_names_support_email` : `support_email="aide@pilao.test"` → « … Contactez Pilao : aide@pilao.test. ».
  - `test_invitation_link_refused` : invitation créée avant la suspension → `/auth/invitations/lookup` et `/accept` → 403 `account_suspended`.
  - `test_verify_email_refused_and_resend_silent` : lien de confirmation → 403 ; `/auth/resend-verification` → 200 même message, `outbox` vide.
  - `test_watch_skips_suspended` : `match_tenders` ne crée aucune correspondance pour l'entreprise suspendue (l'autre en reçoit) ; `send_digests` et `send_expiry_alerts` ne lui envoient rien.
- [ ] **Step 2: Run** `uv run pytest tests/api/test_suspension.py -q` — Expected: FAIL (colonnes absentes).
- [ ] **Step 3: Migration `0023`** : `organizations.suspended_at timestamptz null`, `organizations.suspension_reason text null`, `data_requests.platform_admin_id uuid null` (FK `platform_admins.id` `ondelete="SET NULL"`) ; `downgrade` les retire. Modèles et réglages (`support_email`, `password_reset_ttl_minutes`) ; `.env.example` : `SUPPORT_EMAIL=` commenté.
- [ ] **Step 4: `services/suspension.py`, puis les contrôles** : `login` après `ok` (enregistrer la tentative, `commit`, lever `suspended_error()` avant le contrôle « e-mail non confirmé ») ; `get_auth_context` après le chargement de l'entreprise ; `members._valid_link` et `auth.verify_email` après avoir trouvé l'utilisateur ; `resend_verification` ne fait rien ; `match_tenders` et `send_digests` filtrent `Organization.suspended_at.is_(None)` (jointure sur `CompanyProfile.org_id`) ; `send_expiry_alerts` saute les documents d'une entreprise suspendue.
- [ ] **Step 5: Run** `uv run alembic upgrade head && uv run pytest tests/api/test_suspension.py tests/api/test_auth.py tests/api/test_members.py tests/api/test_alerts.py tests/api/test_tenders.py -q` — Expected: PASS.
- [ ] **Step 6: Commit** — `git commit -m "Accounts: suspension columns and checks at every way in"`

### Task 2: Un auteur « Pilao » pour les règles existantes

**Files:**
- Create: `apps/api/app/services/actors.py`
- Modify: `app/services/members.py`, `app/services/org_data.py`, `app/routers/members.py`, `app/routers/organization.py`
- Test: `apps/api/tests/api/test_actors.py` (+ `test_members.py`, `test_org_data.py` inchangés et verts)

**Interfaces:**
- Produces, `app/services/actors.py` :
  - `@dataclass(frozen=True) class PlatformActor: admin_id: uuid.UUID; email: str`
  - `type Actor = User | PlatformActor`
  - `PILAO_NAME = "L'équipe Pilao"`
  - `user_id_of(actor: Actor) -> uuid.UUID | None` ; `meta_of(actor: Actor) -> dict[str, str]` (`{"by": "pilao"}` ou `{}`) ; `name_of(actor: Actor) -> str` (nom, à défaut e-mail ; `PILAO_NAME`)
- Produces, `services/members.py` (le paramètre `admin: User` devient `actor: Actor`) :
  - `invite(db, actor, org, data, mailer, *, first_access: bool = False) -> User`
  - `resend(db, actor, org, user_id, mailer) -> None` ; `change_role(db, actor, user_id, role) -> User` ; `remove(db, actor, user_id) -> None` (le refus « votre propre accès » seulement pour un `User`)
  - `logout_everywhere(db: Session, actor: Actor, user_id: uuid.UUID) -> int` (sessions révoquées ; audit `logout_everywhere`)
- Produces, `services/org_data.py` :
  - `request_deletion(db, actor, org, confirmation, mailer) -> DataRequest` (Pilao : `requested_by=None`, `platform_admin_id=actor.admin_id`, e-mail du §2.3 avec `contact_sentence()`)
  - `cancel_deletion(db, actor, org, mailer) -> None` (Pilao : « Pilao a annulé la suppression des données de {org}. Rien n'a été effacé. »)
  - `erase_organization(db: Session, org_id: uuid.UUID, storage: ObjectStorage, *, requested_at: datetime | None) -> bool` : le cœur actuel de `_purge` (fichiers d'abord, `PurgeLog`, suppression en cascade, `commit`) sans e-mail ; `_purge` l'appelle puis envoie le dernier message.

- [ ] **Step 1: Write the failing tests** (`test_actors.py`) :
  - `test_pilao_invites` : `invite(db, PlatformActor(...), org, InviteIn(...), mailer, first_access=True)` → objet « Pilao a ouvert l'espace de {org} », corps contenant « L'équipe Pilao a ouvert l'espace de » et le lien ; sans `first_access` → « L'équipe Pilao vous invite sur Pilao ({org}) » ; `audit_logs` : `user_id is None`, `meta == {"by": "pilao"}`.
  - `test_pilao_keeps_last_admin_rule` : `change_role` et `remove` du seul administrateur par Pilao → 409 `last_admin` (le retrait de soi-même ne s'applique pas).
  - `test_pilao_schedules_deletion` : `request_deletion` par Pilao → `requested_by is None`, `platform_admin_id` posé, e-mail « Pilao a programmé la suppression … » ; `cancel_deletion` par Pilao → e-mail « … annulée ».
  - `test_logout_everywhere` : deux sessions de l'utilisateur → 2, toutes révoquées.
  - `test_erase_organization_without_mail` : fichiers effacés du stockage, `purge_logs` écrit, entreprise absente, `outbox` vide.
- [ ] **Step 2: Run** `uv run pytest tests/api/test_actors.py -q` — Expected: FAIL (`app.services.actors` introuvable).
- [ ] **Step 3: Implement** `actors.py`, puis les signatures ci-dessus ; les routes client passent `user` comme auteur (aucun comportement client ne change). `remove` refuse en plus le retrait du dernier administrateur (409 `last_admin` « L'entreprise doit garder au moins un administrateur. ») : sans effet côté client (l'administrateur qui retire en est un), indispensable pour Pilao. Nouvelle `org_data.check_confirmation(org: Organization, confirmation: str) -> None` (la comparaison actuelle, 422 `confirmation_mismatch`), appelée par `request_deletion`.
- [ ] **Step 4: Run** `uv run pytest tests/api/test_actors.py tests/api/test_members.py tests/api/test_org_data.py -q` — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "Accounts: an author that can be Pilao for member and deletion rules"`

### Task 3: Mot de passe oublié (API client)

**Files:**
- Create: `apps/api/app/services/password_reset.py`
- Modify: `app/routers/auth.py`, `app/schemas/auth.py`
- Test: `apps/api/tests/api/test_password_reset.py`

**Interfaces:**
- Consumes: `suspension.is_suspended`, `suspension.suspended_error` (tâche 1).
- Produces, `services/members.py` : `reinvite(db: Session, user: User, org: Organization, mailer: Mailer) -> bool` — nouveau lien d'invitation de 7 jours pour un compte sans mot de passe, plafonné comme `resend` (au-delà : `False`, rien ne part) ; objet « Créez votre accès à Pilao ({org}) », corps : « Vous avez demandé un nouveau mot de passe, mais votre accès n'est pas encore créé. Choisissez votre mot de passe ici (lien valable 7 jours) : {lien} ».
- Produces, `services/password_reset.py` :
  - `KIND = "password_reset"`
  - `request_reset(db: Session, email: str, mailer: Mailer) -> None` : adresse `strip().lower()` ; compte inconnu ou entreprise suspendue → rien ; sans mot de passe → `members.reinvite` ; sinon jeton + e-mail du spec §2.5 ; plafond `email_verify_max_per_hour` (au-delà : rien, même réponse).
  - `send_reset_link(db: Session, user: User, org: Organization, mailer: Mailer) -> None` : jeton + e-mail ; plafond → 429 « Envoi déjà fait : réessayez plus tard. » (servira à l'admin, tâche 5).
  - `lookup(db: Session, token: str) -> str` (l'e-mail) ; 410 `reset_invalid` « Ce lien n'est plus valable. Demandez-en un nouveau. » ; entreprise suspendue → `suspended_error()`.
  - `reset(db: Session, token: str, password: str, ip: str | None, user_agent: str | None) -> tuple[str, User]` : verrou du jeton, `used_at`, nouveau hachage, `email_verified_at` posé s'il est vide, toutes les sessions révoquées, audit `password_reset`, puis `auth.open_session`.
- Produces, routes : `POST /auth/password/forgot {email}` → 202 `MessageOut` « Si un compte existe pour cette adresse, un e-mail vient de partir. Le lien est valable 1 heure. » ; `POST /auth/password/reset/lookup {token}` → `{email}` ; `POST /auth/password/reset {token, password}` → `MeOut` + cookie de session. Limiteur par adresse IP (`SlidingWindowLimiter(max_calls=10, window_seconds=60)`) sur les trois.

- [ ] **Step 1: Write the failing tests** :
  - `test_same_answer_for_everyone` : adresse inconnue, compte actif, entreprise suspendue → même statut et même message ; seul le compte actif reçoit un e-mail.
  - `test_address_typed_differently` : `"  Jean@Exemple.FR "` trouve `jean@exemple.fr`.
  - `test_invited_account_gets_an_invitation` : compte sans mot de passe → e-mail d'invitation, aucun jeton `password_reset`.
  - `test_reset_end_to_end` : lien → nouveau mot de passe (12 caractères) → connecté ; ancienne session révoquée ; ancien mot de passe refusé ; adresse non confirmée devenue confirmée.
  - `test_link_single_use_and_expiry` : réutilisé → 410 ; après 61 minutes → 410 ; mot de passe de 11 caractères → 422.
  - `test_cap_per_hour` : 6ᵉ demande dans l'heure → même réponse, pas d'e-mail.
- [ ] **Step 2: Run** `uv run pytest tests/api/test_password_reset.py -q` — Expected: FAIL (404 sur les routes).
- [ ] **Step 3: Implement** le service, les schémas (`ForgotPasswordIn`, `ResetLookupIn`, `ResetPasswordIn` avec `password: str = Field(min_length=12, max_length=256)`), les routes.
- [ ] **Step 4: Run** `uv run pytest tests/api/test_password_reset.py tests/api/test_auth.py tests/api/test_retention.py -q` — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "Auth: forgotten password, one-hour single-use link"`

### Task 4: Admin — créer, suspendre, réactiver, supprimer

**Files:**
- Create: `apps/api/app/services/admin/accounts.py`, `apps/api/app/routers/admin/accounts.py`
- Modify: `app/core/admin_deps.py`, `app/services/admin/auth.py`, `app/routers/admin/__init__.py`, `app/schemas/admin.py`
- Test: `apps/api/tests/api/test_admin_accounts.py`

**Interfaces:**
- Consumes: tâches 1 et 2 ; `auth._prefill_from_registry`, `get_company_directory`, `get_storage`, `get_job_queue`, `get_mailer`, `tenders.rematch_org`.
- Produces, `core/admin_deps.py` :
  - `@dataclass(frozen=True) class AdminOrgContext: admin: PlatformAdmin; session: PlatformAdminSession; org: Organization; db: Session`
  - `get_admin_org(org_id: uuid.UUID, ctx: CurrentAdmin, db: AdminDb) -> AdminOrgContext` : 404 « Entreprise introuvable. », puis `scope_session(db, org_id)` ; `AdminOrg = Annotated[AdminOrgContext, Depends(get_admin_org)]`
  - `actor_of(ctx: AdminContext | AdminOrgContext) -> PlatformActor`
- Produces, `services/admin/auth.py` : `confirm_code(db: Session, admin: PlatformAdmin, session: PlatformAdminSession, code: str, ip: str | None) -> None` — `_consume_code` ; échec : audit `step_up_failed`, `commit`, puis 401 `not_authenticated` (session révoquée) si c'est le 5ᵉ `step_up_failed` de ce super admin en 15 minutes, sinon 400 `invalid_code` « Code incorrect. ».
- Produces, `services/admin/accounts.py` :
  - `create_organization(db, admin: PlatformAdmin, data: AdminCreateOrgIn, directory: CompanyDirectory | None, mailer, ip) -> uuid.UUID` : 409 `siret_taken` « Ce SIRET a déjà un compte : {nom}. », 409 `email_taken` ; entreprise pré-remplie par l'annuaire, responsable `org_admin` invité avec `first_access=True` ; audit `organization_created`.
  - `suspend(ctx: AdminOrgContext, reason: str, ip) -> None` (sessions de l'entreprise révoquées ; audit `organization_suspended`, `meta.reason`) ; `reactivate(ctx, queue, ip) -> None` (`rematch_org` ; audit `organization_reactivated`)
  - `deletion_preview(ctx) -> DeletionPreviewOut` ; `delete(ctx, confirmation: str, code: str, storage, mailer, ip) -> DeletionOut` ; `cancel_deletion(ctx, mailer, ip) -> None`
- Produces, schémas : `AdminCreateOrgIn{siret, name, contact_name, contact_email}` (SIRET validé par `siret_ok`), `SuspendIn{reason: str = Field(min_length=1, max_length=500)}`, `DeletionPreviewOut{mode: Literal["immediate","scheduled"], due_at: datetime | None, pending: bool, by: Literal["pilao","client"] | None}`, `DeleteIn{confirmation, code}`, `DeletionOut{mode, due_at}`.
- Produces, routes (`/admin/…`) : `GET /companies/lookup`, `POST /organizations` (201 `{id}`), `POST /organizations/{org_id}/suspend`, `POST …/reactivate`, `GET …/deletion`, `POST …/deletion`, `DELETE …/deletion` (204).

- [ ] **Step 1: Write the failing tests** (`activated_admin` de `admin_helpers.py`) :
  - `test_create_organization_and_accept` : création (annuaire factice) → e-mail « Pilao a ouvert l'espace de … » ; le lien accepté par `/auth/invitations/accept` ouvre l'espace ; journal `organization_created`.
  - `test_create_refusals` : SIRET déjà inscrit → 409 « Ce SIRET a déjà un compte : {nom}. » ; e-mail pris → 409 ; SIRET invalide → 422 ; session d'entreprise → 401.
  - `test_suspend_and_reactivate` : sessions révoquées, connexion → 403 ; raison vide → 422 ; réactivation → connexion 200, `rematch_org` appelé (file factice) ; deux entrées au journal.
  - `test_delete_never_used_is_immediate` : aucun `last_login_at` → aperçu `immediate` ; nom recopié + code → entreprise absente, `purge_logs`, aucun e-mail ; journal `organization_deleted` `mode=immediate`.
  - `test_delete_used_is_scheduled_and_cancellable` : un utilisateur connecté une fois → `scheduled`, `due_at` à +30 jours, entreprise suspendue (raison « Suppression programmée par Pilao »), e-mails envoyés ; annulation → demande `cancelled`, entreprise **toujours suspendue**.
  - `test_cancel_client_request_keeps_access` (Review Focus 4) : demande faite par le client, non suspendu → l'admin annule → connexion toujours possible.
  - `test_race_first_login_turns_scheduled` (Review Focus 3) : aperçu `immediate`, puis `last_login_at` posé, puis confirmation → réponse `scheduled`.
  - `test_wrong_code_and_lockout` : nom faux → 422 ; code faux → 400 « Code incorrect. » ; code rejoué → 400 ; code de secours en majuscules sans tiret → accepté (Review Focus 5) ; 5 codes faux → 401 et la session ne sert plus.
  - `test_other_org_untouched` : actions sur A ; B garde ses sessions et ses données.
- [ ] **Step 2: Run** `uv run pytest tests/api/test_admin_accounts.py -q` — Expected: FAIL (404).
- [ ] **Step 3: Implement** dépendance, `confirm_code`, service, schémas, routes. `delete`, dans cet ordre : `org_data.check_confirmation` (une faute de frappe ne consomme pas de code), 409 `deletion_pending` si une suppression est déjà programmée, `confirm_code`, `SELECT … FOR UPDATE` sur l'entreprise, `never_used` relu sous verrou ; immédiat → `erase_organization` ; sinon suspension (si pas déjà, raison « Suppression programmée par Pilao ») puis `org_data.request_deletion(…, PlatformActor)`.
- [ ] **Step 4: Run** `uv run pytest tests/api/test_admin_accounts.py tests/api/test_admin_isolation.py tests/api/test_admin_auth.py -q` — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "Admin: create, suspend, reactivate and delete a company"`

### Task 5: Admin — utilisateurs, fiche enrichie, journal

**Files:**
- Modify: `app/services/admin/accounts.py`, `app/routers/admin/accounts.py`, `app/services/admin/supervision.py`, `app/schemas/admin.py`, `tests/api/test_admin_isolation.py` (nouvelles routes dans la liste des routes refusées et du texte témoin)
- Test: `apps/api/tests/api/test_admin_users.py`, `apps/api/tests/api/test_admin_journal.py`

**Interfaces:**
- Consumes: tâches 2, 3, 4 (`AdminOrg`, `actor_of`, `confirm_code`, `members.*`, `password_reset.send_reset_link`, `auth._verification_email`).
- Produces, service : `invite_user(ctx, data: InviteIn, mailer, ip)`, `resend_invitation(ctx, user_id, mailer, ip)`, `resend_verification(ctx, user_id, mailer, ip)` (409 `already_verified` « Adresse déjà confirmée. » ; plafond → 429), `send_password_reset(ctx, user_id, mailer, ip)` (409 `no_password` « Pas encore d'accès : renvoyez l'invitation. »), `change_role(ctx, user_id, role, ip)`, `logout_user(ctx, user_id, ip) -> int`, `remove_user(ctx, user_id, code, ip)` ; envois refusés pour une entreprise suspendue : 409 `organization_suspended` « Entreprise suspendue : réactivez-la d'abord. ». Audits : `user_invited`, `invitation_resent`, `verification_resent`, `password_reset_sent`, `role_changed`, `user_logged_out`, `user_removed`.
- Produces, routes : `POST /admin/organizations/{org_id}/users` (201), `POST …/users/{user_id}/invitation`, `…/verification`, `…/password-reset`, `…/logout` (204 chacune), `PATCH …/users/{user_id} {role}`, `POST …/users/{user_id}/remove {code}` (204) ; `GET /admin/audit?kind=all|logins|accounts&org_id=&before=` → `AuditPageOut{rows: list[AuditRowOut], next_before: datetime | None}` (100 lignes, plus récentes d'abord ; `AuditRowOut{at, admin_email, action, org_id, org_name: str | None, ip, meta}` ; `org_name` vide si l'entreprise n'existe plus).
- Produces, supervision : `OrganizationRowOut` gagne `siret`, `suspended: bool`, `deletion_due_at: datetime | None`, `invitation_pending: bool` (aucun utilisateur avec mot de passe) ; `OrganizationDetailOut` gagne `account: AccountStateOut{suspended_at, suspension_reason, deletion_due_at, deletion_by}` ; `OrgUserOut` gagne `id`, `status: Literal["active","unverified","invited","invitation_expired"]`, `invited_at`, `has_sessions: bool`.
- Kinds du journal : `logins` = `login`, `login_failed`, `logout`, `recovery_code_used`, `setup_completed`, `access_reset`, `disabled` ; `accounts` = toutes les actions du lot 2 + `organization_viewed`.

- [ ] **Step 1: Write the failing tests** :
  - `test_admin_users.py` : chaque action réussit et laisse une entrée aux deux journaux (`audit_logs` avec `meta.by == "pilao"` quand l'entreprise en a une) ; dernier administrateur → 409 pour le rôle et le retrait ; retrait sans code / code faux → 400 ; envoi sur entreprise suspendue → 409 mais rôle, déconnexion et retrait passent ; utilisateur de l'entreprise B appelé via A → 404 ; 6ᵉ envoi dans l'heure → 429 ; `has_sessions` et `status` de la fiche justes.
  - `test_admin_journal.py` : filtres `logins` / `accounts` / entreprise ; pagination `before` (101 lignes → 100 puis 1) ; entreprise supprimée → `org_name is None`.
  - `test_admin_isolation.py` : les nouvelles routes refusent une session d'entreprise (401) ; le texte témoin n'apparaît dans aucune réponse.
- [ ] **Step 2: Run** `uv run pytest tests/api/test_admin_users.py tests/api/test_admin_journal.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement** service, routes, champs de supervision.
- [ ] **Step 4: Run** `uv run pytest -q` (suite complète) puis `uv run ruff check . && uv run black --check . && uv run mypy` — Expected: tout vert.
- [ ] **Step 5: Commit** — `git commit -m "Admin: help a company's users, account state on the company page, journal"`

### Task 6: Front client — mot de passe oublié et message de suspension

**Files:**
- Create: `apps/web/app/(auth)/mot-de-passe-oublie/page.tsx`, `apps/web/app/(auth)/nouveau-mot-de-passe/page.tsx`
- Modify: `apps/web/app/(auth)/connexion/page.tsx`, `apps/web/lib/api.ts`, `apps/web/lib/types.ts`
- Test: `apps/web/lib/auth-messages.test.ts` (+ `lib/auth-messages.ts`)

**Interfaces:**
- Consumes: routes de la tâche 3 ; erreur `account_suspended` (tâche 1).
- Produces, `lib/auth-messages.ts` : `signInNotice(params: URLSearchParams): string | null` — `suspendu=1` → « L'accès de votre entreprise à Pilao est suspendu. » (la page affiche ensuite le message exact renvoyé par l'API à la tentative suivante), `mot-de-passe=change` → « Mot de passe enregistré. ».

- [ ] **Step 1: Write the failing test** (`auth-messages.test.ts`) : les deux paramètres, et `null` sans paramètre.
- [ ] **Step 2: Run** `pnpm test` — Expected: FAIL.
- [ ] **Step 3: Implement** :
  - connexion : lien « Mot de passe oublié ? » sous le champ mot de passe ; sur `account_suspended`, encadré rouge avec le message de l'API ; bandeau `signInNotice`.
  - `/mot-de-passe-oublie` : e-mail, « Recevoir un lien », puis le message de l'API à la place du formulaire.
  - `/nouveau-mot-de-passe` : lit `token` puis le retire de l'adresse (`history.replaceState`, comme `/invitation`) ; `lookup` → e-mail affiché ; deux champs, 12 caractères, saisies identiques vérifiées avant l'envoi ; succès → `/tableau-de-bord` ; 410 → message et lien vers `/mot-de-passe-oublie`.
  - `lib/api.ts` : une réponse d'erreur au code `account_suspended` renvoie le navigateur à `/connexion?suspendu=1` (`window.location.assign`), sauf depuis les pages `(auth)` elles-mêmes — un seul endroit pour toutes les pages ouvertes, chargement de la coquille compris.
- [ ] **Step 4: Run** `pnpm lint && pnpm format:check && pnpm typecheck && pnpm test` — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "Web: forgotten password pages and the suspended account message"`

### Task 7: Front admin — création, fiche avec actions, journal

**Files:**
- Create: `apps/web/app/(admin)/admin/(espace)/entreprises/nouvelle/page.tsx`, `apps/web/app/(admin)/admin/(espace)/journal/page.tsx`, `apps/web/components/admin/dialogs.tsx`, `apps/web/components/admin/org-users.tsx`
- Modify: `apps/web/app/(admin)/admin/(espace)/entreprises/page.tsx`, `apps/web/app/(admin)/admin/(espace)/entreprises/[id]/page.tsx`, `apps/web/lib/admin.ts`, `apps/web/lib/types.ts`, `apps/web/components/admin/ui.tsx`
- Test: `apps/web/lib/admin.test.ts`

**Interfaces:**
- Consumes: routes et formes des tâches 4 et 5.
- Produces, `lib/admin.ts` :
  - `ADMIN_NAV` gagne `{ href: "/admin/journal", label: "Journal", icon: "todo" }` (6ᵉ).
  - `AUDIT_LABELS: Record<string, string>` (une ligne par action du lot 1 et du lot 2 : « Connexion », « Connexion refusée », « Entreprise créée », « Entreprise suspendue », « Entreprise réactivée », « Entreprise supprimée », « Suppression annulée », « Utilisateur invité », « Invitation renvoyée », « E-mail de confirmation renvoyé », « Lien de mot de passe envoyé », « Rôle changé », « Utilisateur déconnecté », « Utilisateur retiré », « Code refusé », « Fiche consultée », …) et `auditLabel(action: string): string` (repli : le code brut).
  - `userActions(u: AdminOrgUser, suspended: boolean): UserAction[]` où `UserAction = "invitation" | "verification" | "password-reset" | "role" | "logout" | "remove"` — la règle du tableau du spec §2.4.
- Produces, `components/admin/dialogs.tsx` : `ConfirmDialog({title, children, confirmLabel, danger, needsCode, needsName, onConfirm})` — fenêtre accessible (focus piégé, Échap ferme), champ « Nom de l'entreprise » et champ « Code de l'application » à la demande.

- [ ] **Step 1: Write the failing tests** (`admin.test.ts`) : `auditLabel` connu / inconnu ; `userActions` pour un actif, un non confirmé, un invité, une entreprise suspendue (seulement `role`, `logout`, `remove`).
- [ ] **Step 2: Run** `pnpm test` — Expected: FAIL.
- [ ] **Step 3: Implement** :
  - liste : bouton « Créer une entreprise », pastilles « Suspendue » (rouge), « Suppression le … » (ambre), « Invitation en attente » (bleu) ; la pastille « Lecture seule » disparaît de la liste et de la fiche, et reste sur les autres pages.
  - nouvelle : SIRET + « Rechercher » (`/admin/companies/lookup`, repli saisie à la main), nom, responsable ; sur `siret_taken`, lien vers la fiche trouvée par `siret` dans `GET /admin/organizations` ; succès → fiche.
  - fiche : encadré d'état (suspendue depuis / raison ; suppression le … et par qui) ; boutons « Suspendre » / « Réactiver », « Supprimer » (aperçu `GET …/deletion` dans la fenêtre) / « Annuler la suppression » ; carte « Utilisateurs » (`org-users.tsx`) avec « Ajouter un utilisateur » et les actions de `userActions` ; lien « Voir le journal de cette entreprise » → `/admin/journal?entreprise={id}`.
  - journal : filtres (Tout / Connexions / Comptes, entreprise), tableau, « Plus anciennes ».
  - toutes les pages restent sans débordement à 390 px de large.
- [ ] **Step 4: Run** `pnpm lint && pnpm format:check && pnpm typecheck && pnpm test && pnpm build` — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "Web: admin company creation, actions on the company page, journal"`

### Task 8: Parcours navigateur, documentation, mise en ligne

**Files:**
- Modify: `apps/web/e2e/journey.cjs`, `apps/web/e2e/README.md`, `docs/04-specifications-fonctionnelles.md`, `docs/06-modele-de-donnees.md`, `docs/09-securite-rgpd.md`, `docs/10-roadmap-taches.md`, `docs/12-decisions.md`, `docs/14-deploiement.md`, `CLAUDE.md` (§6 phase en cours), `docs/superpowers/specs/2026-11-11-administration-lot2-comptes-design.md` (statut « validé et livré »)

- [ ] **Step 1: Journey** — après la section admin existante : créer une entreprise (SIRET de test, annuaire injoignable → saisie manuelle), lire le lien dans `api.log` (le mailer de dev l'y écrit), accepter, arriver sur le tableau de bord ; dans l'admin, suspendre → le navigateur du client est renvoyé à `/connexion?suspendu=1`, sa connexion affiche le message ; réactiver → connexion ; « Mot de passe oublié ? » de bout en bout ; ajouter un utilisateur puis le retirer avec un code calculé ; lire le journal (filtre Comptes) ; supprimer l'entreprise jamais utilisée (une seconde, créée et jamais ouverte). Capture `admin-comptes.png`.
- [ ] **Step 2: Run** le parcours complet (`apps/web/e2e/README.md`) — Expected: toutes les étapes ✓, erreurs de console identiques aux attendues (refus volontaires).
- [ ] **Step 3: Docs** — `docs/04` : US-6.4 à US-6.8 et US-1.6 avec critères d'acceptation ; `docs/06` : colonnes `0023` ; `docs/09` : suspension, code redemandé, lien de mot de passe, journal ; `docs/10` : lot 2 coché ; `docs/12` : ADR-042 (spec §9) ; `docs/14` : `SUPPORT_EMAIL` ; README du parcours.
- [ ] **Step 4: Revue finale** de toute la branche (agent de revue sur le modèle le plus capable), corrections, suite complète API + web verte.
- [ ] **Step 5: Commit et push** — `git push -u origin claude/nouveau-projet-5gm1zc` ; vérifier CI puis Deploy verts sur GitHub Actions.

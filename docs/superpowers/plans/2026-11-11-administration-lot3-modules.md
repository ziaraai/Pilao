# Administration, lot 3 : le socle des modules — plan de réalisation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** deux modules (« Veille des annonces », « Réponse aux appels d'offres ») déclarés dans un registre, actifs par défaut pour toutes les entreprises, que le super admin active ou désactive par entreprise ; le menu, le tableau de bord, les routes et le travail de fond suivent les modules actifs.

**Architecture:** `app/modules.py` déclare les modules ; `organizations.modules` (tableau de clés) dit lesquels sont actifs ; une dépendance `require_module(key)` garde le routeur de chaque module ; `/auth/me` renvoie les modules actifs et le front en tire le menu, le tableau de bord et une carte « module non activé » ; l'administration bascule un module dans la session limitée à l'entreprise (lot 2).

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, pytest ; Next.js + Tailwind, vitest, Playwright (`journey.cjs`).

**Spec:** `docs/superpowers/specs/2026-11-11-administration-lot3-modules-design.md`

## Global Constraints

- Clés et noms exacts : `veille` « Veille des annonces » ; `reponse` « Réponse aux appels d'offres ». Défaut : `("veille", "reponse")` pour toute entreprise, existante ou nouvelle.
- Désactiver ne supprime **aucune** donnée ; réactiver rend tout.
- Refus d'un module inactif : 403, code `module_disabled`, message « Ce module n'est pas activé pour votre entreprise. Contactez Pilao : {support_email}. » ou, sans adresse, « Ce module n'est pas activé pour votre entreprise. Contactez Pilao. »
- Ordre des refus : 401 non connecté → 403 `account_suspended` → 403 `module_disabled`.
- Routeurs de `veille` : `tenders`. Routeurs de `reponse` : `bids`, `memoir`, `documents`, `vault`, `knowledge`, et les routes `/profile/suggestions*`. Le reste est commun.
- Journal : `module_enabled`, `module_disabled`, meta `{"module": key, "name": name}`.
- Migration `0024` (révise `0023`). Code en anglais, interface en français.
- Avant chaque commit, côté API : `uv run ruff check . && uv run black --check . && uv run mypy`. Côté web : `pnpm lint && pnpm format:check && pnpm typecheck && pnpm test`.

## Review Focus

1. **Module désactivé pendant qu'une page est ouverte** : la requête suivante reçoit `module_disabled` et la page affiche la carte « Ce module n'est pas activé… », sans erreur brute ni page blanche → test dans le parcours de la tâche 6 (le client reste sur `/dossiers` pendant la désactivation, puis clique sur « Dossiers » dans son menu encore affiché).
2. **Entreprise sans aucun module** : le menu ne garde que Tableau de bord et Profil. Le tableau de bord s'affiche vide mais sans erreur, avec l'étape « Compléter le profil » → tests en tâche 2 (API) et tâche 4 (`visibleNav([])`).
3. **Clé inconnue en base** (un module retiré du code plus tard) : ignorée partout, aucune erreur 500 → test en tâche 1 (`active_modules`).
4. **Annonce déjà suivie avec un dossier, puis Réponse désactivée** : l'annonce reste « suivie », le lien « Ouvrir le dossier » n'apparaît pas, rien n'est effacé → test en tâche 2 (la correspondance garde son `bid_id`) et tâche 4 (pas de lien sans `reponse`).
5. **Réactiver la Veille** : les annonces ouvertes de l'entreprise sont de nouveau recherchées (`rematch_org` mis en file) → test en tâche 3.

---

### Task 1: Registre, colonne, barrière et `/auth/me`

**Files:**
- Create: `apps/api/app/modules.py`, `apps/api/alembic/versions/0024_organization_modules.py`
- Modify: `app/db/models/organization.py`, `app/core/deps.py`, `app/schemas/auth.py`, `app/routers/auth.py` (`_me_from`), `app/routers/tenders.py`, `bids.py`, `memoir.py`, `documents.py`, `vault.py`, `knowledge.py`, `profile.py` (routes `/suggestions*`)
- Test: `apps/api/tests/domain/test_modules.py`, `apps/api/tests/api/test_modules.py`

**Interfaces:**
- Produces, `app/modules.py` :
  - `@dataclass(frozen=True) class Module: key: str; name: str; description: str; contents: tuple[str, ...]; nav: tuple[str, ...]`
  - `MODULES: tuple[Module, ...]` (veille puis reponse), `DEFAULT_MODULES: tuple[str, ...] = ("veille", "reponse")`, `BY_KEY: dict[str, Module]`
  - `active_modules(org: Organization) -> list[str]` (dans l'ordre de `MODULES`, clés inconnues ignorées) ; `has_module(org: Organization, key: str) -> bool`
  - `module_disabled_error() -> ApiError`
- Produces : `Organization.modules: Mapped[list[str]]` (`ARRAY(Text)`, `server_default="{veille,reponse}"`, `default=lambda: list(DEFAULT_MODULES)`) ; `core.deps.require_module(key: str) -> Callable[[AuthContext], None]` ; `MeOut.modules: list[str]`.

- [ ] **Step 1: Write the failing tests**
  - `tests/domain/test_modules.py` :
    - `test_registry` : clés uniques, `DEFAULT_MODULES == ("veille", "reponse")`, les noms exacts ;
    - `test_unknown_key_ignored` : `active_modules` d'une entreprise `modules=["reponse", "crm", "veille"]` → `["veille", "reponse"]` (Review Focus 3).
  - `tests/api/test_modules.py` :
    - `test_me_lists_modules` → `["veille", "reponse"]` pour une inscription.
    - `test_disabled_module_refused` (paramétré) :
      - lecture et écriture par routeur (`GET /tenders`, `POST /tenders/{id}/track`, `GET /bids`, `POST /bids`, `GET /vault`, `GET /knowledge`, `GET /profile/suggestions`, une route de `memoir` et une de `documents` sur un dossier existant) ;
      - module retiré en base → 403 `module_disabled` et le message exact ; module remis → réponse habituelle.
    - `test_neighbour_keeps_its_module` : B a encore le module, A ne l'a plus → B passe.
    - `test_order_of_refusals` : suspendue **et** sans module → `account_suspended`.
    - `test_common_routes_stay_open` : `/profile`, `/dashboard`, `/organization/members`, `/files` (dépôt d'un logo) → 200/201 sans aucun module.
- [ ] **Step 2: Run** `uv run pytest tests/domain/test_modules.py tests/api/test_modules.py -q` — Expected: FAIL (`app.modules` introuvable).
- [ ] **Step 3: Implement.**
  - Migration `0024` : colonne `modules text[] not null server_default '{veille,reponse}'`.
  - Le registre (`contents` repris du tableau du spec §2).
  - `require_module` : dépend de `get_auth_context` (donc de la suspension), puis lève `module_disabled_error()`.
  - Poser la dépendance avec `APIRouter(dependencies=[Depends(require_module(...))])` sur chaque routeur de module. Pour `/profile/suggestions*`, la poser sur chaque route.
  - `_me_from` renvoie `active_modules(org)`.
- [ ] **Step 4: Run** `uv run alembic upgrade head && uv run pytest tests/domain/test_modules.py tests/api/test_modules.py tests/api/test_auth.py -q` — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "Modules: registry, per-company list, one guard per module, modules in /auth/me"`

### Task 2: Ce qui s'adapte — tableau de bord, « Suivre », travail de fond

**Files:**
- Modify: `app/routers/dashboard.py`, `app/routers/tenders.py` + `app/schemas/tenders.py` (`TrackOut`), `app/services/tenders.py` (`track`, `match_tenders`, `_watching_profiles`, `score_org`, `notify`), `app/services/alerts.py` (`send_digests`, `send_expiry_alerts`)
- Test: `apps/api/tests/api/test_modules_effects.py`

**Interfaces:**
- Consumes: `has_module`, `active_modules` (tâche 1).
- Produces: `TrackOut{bid: BidOut | None}` (réponse de `POST /tenders/{id}/track`) ; `tenders.track(db, user, tender_id) -> Bid | None`.

- [ ] **Step 1: Write the failing tests** (`test_modules_effects.py`) :
  - `test_dashboard_without_veille` : `new_tenders == 0`, `best_tenders == []`, `tenders_connected is False` alors qu'une annonce existe.
  - `test_dashboard_without_reponse` : `bids == []`, `actions == []`, résultats et temps gagné à zéro, `getting_started` réduit à l'étape `profile`.
  - `test_dashboard_without_any_module` : 200, `getting_started == [profile]` (Review Focus 2).
  - `test_track_without_reponse` : 201, `{"bid": None}`, la correspondance est `tracked` ; aucun `Bid` créé.
  - `test_track_with_reponse_unchanged` : `bid` rempli.
  - `test_tracked_bid_kept_when_reponse_disabled` : le dossier existant et `bid_id` restent (Review Focus 4).
  - `test_background_skips_without_module` :
    - sans `veille` : pas de correspondance, pas d'appel de notation, pas d'e-mail du matin, pas d'avis rectificatif ;
    - sans `reponse` : pas de rappel d'attestation.
- [ ] **Step 2: Run** `uv run pytest tests/api/test_modules_effects.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement.**
  - Dashboard : `veille = has_module(ctx.org, "veille")`, `reponse = has_module(ctx.org, "reponse")`. Chaque champ d'un module inactif est vide. Sans `reponse` : `actions=[]` et `getting_started` filtré à la clé `profile`.
  - `track` : sans `reponse`, la correspondance passe à `tracked` et la fonction renvoie `None`.
  - Travail de fond :
    - `_watching_profiles`, la requête de `send_digests` et `notify` ajoutent `Organization.modules.any("veille")` ;
    - `score_org` renvoie 0 sans `veille` ;
    - `send_expiry_alerts` saute une entreprise sans `reponse`.
- [ ] **Step 4: Run** `uv run pytest tests/api/test_modules_effects.py tests/api/test_tenders.py tests/api/test_alerts.py tests/api/test_dashboard*.py tests/api/test_suspension.py -q` — Expected: PASS (adapter les tests existants de `track` à `TrackOut`).
- [ ] **Step 5: Commit** — `git commit -m "Modules: the dashboard, « Suivre » and the background work follow the active modules"`

### Task 3: Administration — activer, désactiver, catalogue

**Files:**
- Create: `apps/api/app/services/admin/modules.py`
- Modify: `app/routers/admin/accounts.py` (routes), `app/schemas/admin.py`, `app/services/admin/supervision.py` (liste et fiche : `modules`), `tests/api/test_admin_isolation.py`, `tests/api/test_admin_supervision.py` (jeu de champs épinglé)
- Test: `apps/api/tests/api/test_admin_modules.py`

**Interfaces:**
- Consumes: `AdminOrg` / `AdminOrgContext` (lot 2), `MODULES`, `BY_KEY` (tâche 1), `audit.record`.
- Produces:
  - `set_module(ctx: AdminOrgContext, key: str, enabled: bool, queue: JobQueue, ip: str | None) -> list[str]` — renvoie les modules actifs ; 404 `unknown_module` « Module inconnu. » ; journal ; `queue.enqueue_rematch_org` (protégé comme `reactivate`) quand `veille` passe à actif.
  - `catalog(db: Session) -> list[ModuleOut]`.
  - Schémas : `ModuleOut{key, name, description, contents: list[str], nav: list[str], organizations: int}` et `ModuleToggleIn{enabled: bool}`.
  - `OrganizationRowOut.modules: list[str]`, `OrganizationDetailOut.modules: list[str]`.
  - Routes : `GET /admin/modules` → `list[ModuleOut]`, `PUT /admin/organizations/{org_id}/modules/{key}` → `{modules: list[str]}`.

- [ ] **Step 1: Write the failing tests** (`test_admin_modules.py`) :
  - désactiver `reponse` → le client reçoit 403 sur `/bids`, et la ligne `module_disabled` est au journal avec `{"module": "reponse", "name": "Réponse aux appels d'offres"}` ; réactiver → 200 et `module_enabled` au journal ;
  - réactiver `veille` → `queue.pending_rematch == [org_id]` (Review Focus 5) ;
  - clé `crm` → 404 « Module inconnu. » ; une autre entreprise reste intacte ;
  - `GET /admin/modules` → deux modules, les noms exacts et les comptes (2 entreprises, une sans `reponse` → `reponse.organizations == 1`) ;
  - la liste et la fiche portent `modules` ;
  - une session d'entreprise → 401 sur les deux routes (ajoutées aussi à `test_admin_isolation.py`).
- [ ] **Step 2: Run** `uv run pytest tests/api/test_admin_modules.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement** le service, les schémas, les routes et les champs de supervision. Ajouter `modules` au jeu de champs épinglé de `test_admin_supervision.py`.
- [ ] **Step 4: Run** `uv run pytest -q` (suite complète), puis ruff, black et mypy — Expected: tout vert.
- [ ] **Step 5: Commit** — `git commit -m "Admin: turn a company's modules on or off, the modules catalogue"`

### Task 4: Front client — menu, carte « module non activé », tableau de bord, profil, annonces

**Files:**
- Create: `apps/web/lib/modules.ts`, `apps/web/lib/modules.test.ts`, `apps/web/components/module-gate.tsx`, `apps/web/app/(app)/annonces/layout.tsx`, `apps/web/app/(app)/dossiers/layout.tsx`, `apps/web/app/(app)/coffre-fort/layout.tsx`, `apps/web/app/(app)/documents/layout.tsx`
- Modify: `components/sidebar.tsx`, `lib/types.ts` (`Me.modules`), `lib/api.ts`, `app/(app)/tableau-de-bord/page.tsx`, `app/(app)/profil/page.tsx`, `components/profile/watch-settings.tsx`, `app/(app)/annonces/page.tsx`

**Interfaces:**
- Consumes: `me.modules` (tâche 1), `TrackOut` (tâche 2), `module_disabled` (tâche 1).
- Produces, `lib/modules.ts` :
  - `type ModuleKey = "veille" | "reponse"` ;
  - `NAV` : la liste actuelle, avec pour chaque entrée `module: ModuleKey | null` ;
  - `visibleNav(modules: string[]): typeof NAV` (dans l'ordre actuel) ;
  - `hasModule(modules: string[], key: ModuleKey): boolean`.
- Produces : `ModuleGate({ module, children })`.

- [ ] **Step 1: Write the failing test** (`lib/modules.test.ts`) : `visibleNav(["veille","reponse"])` → les 6 entrées actuelles ; `visibleNav(["veille"])` → Tableau de bord, Annonces, Profil ; `visibleNav(["reponse"])` → Tableau de bord, Dossiers, Coffre-fort, Base documentaire, Profil ; `visibleNav([])` → Tableau de bord, Profil (Review Focus 2) ; `visibleNav(["crm"])` → Tableau de bord, Profil.
- [ ] **Step 2: Run** `pnpm test` — Expected: FAIL.
- [ ] **Step 3: Implement.**
  - La barre de gauche utilise `visibleNav(me.modules)`.
  - `ModuleGate` affiche, si le module est absent, une `Card` « Ce module n'est pas activé pour votre entreprise. » avec « Contactez Pilao. » et un lien « Retour au tableau de bord ». Les 4 `layout.tsx` l'enveloppent.
  - `lib/api.ts` : le code `module_disabled` recharge la page (`window.location.reload()`, une seule fois par chargement), qui affiche alors la carte (Review Focus 1).
  - Tableau de bord : les blocs annonces sont masqués sans `veille` ; les blocs dossiers, résultats, temps gagné et attestations sans `reponse`.
  - Profil :
    - `WatchSettings` reçoit `watch: boolean` ; sans veille, seuls les métiers s'affichent, et l'enregistrement renvoie les autres réglages tels quels ;
    - la carte « Pré-remplir depuis vos documents » est masquée sans `reponse`.
  - Annonces :
    - « Suivre » lit `TrackOut` ; avec un `bid`, il ouvre le dossier ; sans `bid`, il recharge la liste ;
    - « Ouvrir le dossier » n'apparaît qu'avec `reponse`.
- [ ] **Step 4: Run** `pnpm lint && pnpm format:check && pnpm typecheck && pnpm test && pnpm build` — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "Web: menu, dashboard, profile and notices follow the company's modules"`

### Task 5: Front admin — carte « Modules », colonne, catalogue

**Files:**
- Create: `apps/web/components/admin/org-modules.tsx`, `apps/web/app/(admin)/admin/(espace)/modules/page.tsx`
- Modify: `lib/admin.ts` (`ADMIN_NAV` : « Modules » en 7ᵉ entrée ; `AUDIT_LABELS` : « Module activé », « Module désactivé »), `lib/admin.test.ts`, `lib/types.ts`, `app/(admin)/admin/(espace)/entreprises/page.tsx`, `app/(admin)/admin/(espace)/entreprises/[id]/page.tsx`

**Interfaces:**
- Consumes: routes et schémas de la tâche 3 ; `ConfirmDialog` et `useAdminAction` (lot 2).
- Produces: `OrgModules({ orgId, modules, onChanged })`.

- [ ] **Step 1: Write the failing test** (`lib/admin.test.ts`) : `ADMIN_NAV` a 7 entrées, la dernière `/admin/modules` ; `auditLabel("module_disabled") === "Module désactivé"`, `auditLabel("module_enabled") === "Module activé"`.
- [ ] **Step 2: Run** `pnpm test` — Expected: FAIL.
- [ ] **Step 3: Implement.**
  - Fiche entreprise : carte « Modules ». Une ligne par module du catalogue (`GET /admin/modules`) : nom, description, pastille « Activé » (verte) ou « Désactivé » (grise), bouton « Activer » ou « Désactiver ». La désactivation passe par `ConfirmDialog` avec le texte du spec §3.1.
  - Liste des entreprises : colonne « Modules », avec les pastilles « Veille » et « Réponse », ou « Aucun ».
  - Page `/admin/modules` : `AdminTitle` en lecture seule ; une carte par module avec ce qu'il contient, ses entrées de menu et « {n} entreprise(s) ».
- [ ] **Step 4: Run** `pnpm lint && pnpm format:check && pnpm typecheck && pnpm test && pnpm build` — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "Web: modules on the admin company page, the list and the catalogue"`

### Task 6: Parcours navigateur, documentation, mise en ligne

**Files:**
- Modify: `apps/web/e2e/journey.cjs`, `apps/web/e2e/README.md`, `docs/04-specifications-fonctionnelles.md`, `docs/05-architecture.md`, `docs/06-modele-de-donnees.md`, `docs/10-roadmap-taches.md`, `docs/12-decisions.md`, `CLAUDE.md` (§6), le spec (statut « validé et livré »)

- [ ] **Step 1: Journey** — dans la section admin, sur la fiche de l'entreprise du parcours :
  - le client a `/dossiers` ouvert ; « Désactiver » « Réponse aux appels d'offres » et confirmer ;
  - côté client, un clic sur « Dossiers » dans le menu encore affiché → la page affiche « Ce module n'est pas activé pour votre entreprise. » et, après rechargement, le menu n'a plus « Dossiers » (Review Focus 1) ;
  - « Activer » → « Dossiers » revient ;
  - le catalogue « Modules » montre les deux modules ;
  - capture `admin-modules.png`.
- [ ] **Step 2: Run** le parcours complet (base locale vidée des entreprises des parcours précédents) — Expected: toutes les étapes ✓, erreurs de console identiques aux attendues.
- [ ] **Step 3: Docs.**
  - `docs/04` : US-6.9 et US-6.10, le module 6 mis à jour.
  - `docs/05` : le registre et la barrière.
  - `docs/06` : la colonne.
  - `docs/10` : lot 3 coché.
  - `docs/12` : ADR-041 précisé (statut « réalisé »).
- [ ] **Step 4: Revue finale** de la branche (agent de revue sur le modèle le plus capable), corrections, puis suites complètes API et web au vert.
- [ ] **Step 5: Commit et push** — `git push -u origin claude/nouveau-projet-5gm1zc` ; vérifier que CI puis Deploy sont verts sur GitHub Actions.

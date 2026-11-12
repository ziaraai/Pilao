# Administration, lot 4 : formules et crédits — plan de réalisation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** chaque entreprise a une formule (des modules + des crédits) ; les 4 actions d'IA du module « Réponse » se paient en crédits (prix réglés dans l'admin), sont refusées sans crédits et remboursées si elles échouent ; l'exploitant crée les formules, les attribue et recharge les entreprises ; le client ne voit que des crédits.

**Architecture:** le registre des modules (`app/modules.py`) déclare les actions payantes ; `app/domain/credits.py` calcule le solde à partir d'un journal (`credit_entries`) sans rien écrire le 1er du mois ; `app/services/credits.py` est le seul endroit qui écrit ce journal (prise, remboursement, recharge, crédits offerts, attribution d'une formule) ; les formules (`plans`) et les prix (`credit_prices`) sont des tables de la plateforme ; le remboursement passe par `set_job_status` (tout travail qui finit en erreur rend sa prise).

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, pytest ; Next.js + Tailwind, vitest, Playwright (`journey.cjs`).

**Spec:** `docs/superpowers/specs/2026-11-12-administration-lot4-formules-credits-design.md`

## Global Constraints

- Actions payantes, clés, noms, prix de départ, tâche d'IA : `dce_analysis` « Analyse du DCE » 2 `dce_extraction` ; `memoir_generation` « Rédaction du mémoire » 5 `memoir_generation` ; `chapter_regeneration` « Régénérer un chapitre » 1 `memoir_regeneration` ; `profile_prefill` « Pré-remplir le profil depuis vos documents » 1 `profile_extraction`. Toutes du module `reponse`.
- Formules de départ : « Pilote » (modules `veille`, `reponse` ; 100 par mois ; 0 offert ; donnée aux entreprises existantes) et « Découverte » (mêmes modules ; 0 par mois ; 7 offerts ; par défaut).
- Mois = mois civil, heure de Paris (`Europe/Paris`). Ordre de prise : crédits du mois, puis supplémentaires. Bandeau : `low` si `reference > 0` et `total < 0.2 × reference`, `empty` si `total == 0`.
- Refus : 402, code `credits_exhausted`, message « Il faut {n} crédit(s), il vous en reste {m}. Contactez Pilao : {support}. » (sans adresse : « … Contactez Pilao. »), accord au singulier pour 1.
- **Aucun euro côté client** : ni `€`, ni `cost`, ni `price_note` dans une réponse hors `/admin`.
- Bornes : prix 0 à 1000 ; recharge 1 à 100 000, raison 1 à 200 caractères ; nom de formule 1 à 80, unique sans tenir compte de la casse ; phrase ≤ 200 ; ton prix ≤ 120 ; crédits d'une formule 0 à 100 000.
- Journal admin : `plan_created`, `plan_updated`, `plan_archived`, `plan_unarchived`, `plan_default_set`, `plan_changed`, `credits_added`, `credit_price_changed`.
- Migration `0025` (révise `0024`). Code en anglais, interface en français.
- Avant chaque commit, côté API : `uv run ruff check . && uv run black --check . && uv run mypy`. Côté web : `pnpm lint && pnpm format:check && pnpm typecheck && pnpm test`.

## Review Focus

1. **Double clic sur une action payante** : une seule prise ; le second appel est refusé par la règle « une seule à la fois » de l'action, avant toute prise → tests en tâche 3 (pour chacune des 4 actions, deux appels de suite = une ligne `charge`).
2. **Changement de formule vers plus petit en cours de mois** (100 par mois, 30 pris, passage à 20) : crédits du mois à 0, jamais négatifs → test en tâche 1.
3. **Échec d'une action prise le mois précédent** : la part du mois revient en crédits supplémentaires, rien n'est perdu → test en tâche 1 (calcul) et tâche 3 (bout en bout).
4. **Prix changé entre la prise et l'échec** : le remboursement rend ce qui a été pris, pas le nouveau prix → test en tâche 3.
5. **Crédits offerts jamais deux fois** (Découverte → Pilote → Découverte) → test en tâche 4.
6. **Aucun euro côté client** : `/auth/me`, `/credits`, `/dashboard` ne contiennent ni « € » ni `cost` → test en tâche 2.

---

### Task 1: Données, registre des actions, calcul du solde

**Files:**
- Create: `apps/api/alembic/versions/0025_plans_and_credits.py`, `apps/api/app/db/models/billing.py`, `apps/api/app/domain/credits.py`
- Modify: `app/db/models/organization.py` (`plan_id`, `welcome_credits_at`), `app/db/models/__init__.py`, `app/modules.py` (`PaidAction`, `Module.actions`)
- Test: `apps/api/tests/domain/test_credits.py`, `tests/domain/test_modules.py`

**Interfaces:**
- Produces, `app/modules.py` :
  - `@dataclass(frozen=True) class PaidAction: key: str; name: str; default_credits: int; ai_task: str`
  - `Module.actions: tuple[PaidAction, ...] = ()` ; `PAID_ACTIONS: tuple[PaidAction, ...]` (ordre du registre) ; `ACTION_BY_KEY: dict[str, PaidAction]`.
- Produces, `app/db/models/billing.py` :
  - `Plan` (table `plans`, plateforme : `IdMixin, TimestampMixin, Base`) : `name`, `description`, `modules: list[str]`, `monthly_credits`, `welcome_credits`, `price_note`, `is_default`, `archived_at`.
  - `CreditPrice` (table `credit_prices`) : `action` (pk), `credits`, `updated_at`.
  - `CreditEntry` (table `credit_entries`, `IdMixin, OrgScoped, Base`) : les colonnes du spec §4 ; `kind` ∈ `charge`, `refund`, `grant`, `welcome`.
  - Écouteur `before_insert` sur `Organization` : `plan_id` vide → la formule par défaut (toutes les créations d'entreprise, CLI et tests compris).
- Produces, `app/domain/credits.py` (pur, sans base) :
  - `paris_month(at: datetime) -> date` (1er jour du mois de Paris) ;
  - `@dataclass(frozen=True) class Ledger: monthly: int; extra: int; month: date | None`
  - `@dataclass(frozen=True) class Balance: monthly_allowance: int; monthly_left: int; extra: int; total: int; reference: int; renews_on: date`
  - `compute_balance(monthly_allowance: int, welcome_credits: int, entries: Iterable[Ledger], now: datetime) -> Balance`
  - `class InsufficientCredits(Exception): needed: int; left: int`
  - `split_charge(balance: Balance, cost: int) -> tuple[int, int]` → (pris sur le mois, pris sur les supplémentaires), lève `InsufficientCredits` ;
  - `refund_parts(monthly: int, extra: int, month: date, now: datetime) -> tuple[int, int, date | None]` (les valeurs de la prise sont négatives ; renvoie les valeurs positives à écrire).

- [ ] **Step 1: Write the failing tests** (`tests/domain/test_credits.py`) :
  - `test_month_first_then_extra` : allocation 10, une ligne `grant` +5 → `split_charge(…, 12) == (10, 2)` ; après la prise, `monthly_left == 0`, `extra == 3`, `total == 3` ;
  - `test_new_month_starts_again` : 10 pris en octobre, `now` en novembre → `monthly_left == 10` ;
  - `test_paris_month_boundary` : une prise à `2026-11-30T23:30Z` compte en décembre (`paris_month == date(2026, 12, 1)`) ; `renews_on` du 15 novembre = `date(2026, 12, 1)` ;
  - `test_smaller_allowance_never_negative` (Review Focus 2) : 30 pris, allocation 20 → `monthly_left == 0` ;
  - `test_refund_same_month` → mêmes parts, même mois ; `test_refund_after_month_end` (Review Focus 3) → `(0, monthly + extra, None)`, la part du mois passe en supplémentaires ;
  - `test_insufficient` : total 3, coût 5 → `InsufficientCredits(needed=5, left=3)` ; coût 0 → `(0, 0)` sans erreur ;
  - `test_reference` : allocation 0, offerts 7 → `reference == 7` ; allocation 100 → 100.
  - `tests/domain/test_modules.py` : `PAID_ACTIONS` contient les 4 clés du Global Constraints, toutes uniques, prix de départ exacts.
- [ ] **Step 2: Run** `uv run pytest tests/domain/test_credits.py tests/domain/test_modules.py -q` — Expected: FAIL (module absent).
- [ ] **Step 3: Implement** le registre, les modèles, le calcul ; la migration crée les 3 tables et les 2 colonnes, insère « Pilote » et « Découverte » (Global Constraints, phrases : « Formule des entreprises du pilote. » et « Pour découvrir Pilao : de quoi répondre à un appel d'offres. »), donne « Pilote » à toutes les entreprises puis rend `plan_id` obligatoire ; index unique partiel `plans (is_default) WHERE is_default`, index unique `lower(name)`.
- [ ] **Step 4: Run** `uv run alembic upgrade head && uv run pytest -q` (suite complète : l'écouteur doit couvrir toutes les créations d'entreprise) — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "Credits: plans, prices and ledger tables, paid actions in the registry, balance arithmetic"`

### Task 2: Service des crédits, inscription, `/auth/me`, `/credits`

**Files:**
- Create: `apps/api/app/services/credits.py`, `apps/api/app/schemas/credits.py`, `apps/api/app/routers/credits.py`
- Modify: `app/main.py` (routeur), `app/services/auth.py` (inscription : `give_welcome`), `app/services/admin/accounts.py` (création : `plan_id` + `give_welcome`), `app/schemas/admin.py` (`AdminCreateOrgIn.plan_id: uuid.UUID | None = None`), `app/schemas/auth.py`, `app/routers/auth.py` (`_me_from`)
- Test: `apps/api/tests/api/test_credits.py`

**Interfaces:**
- Consumes: tâche 1.
- Produces, `app/services/credits.py` :
  - `org_balance(db: Session, org: Organization) -> Balance` ; `price(db: Session, action: str) -> int` ; `prices(db: Session) -> dict[str, int]` ;
  - `charge(db: Session, org: Organization, action: str, *, user_id: uuid.UUID | None, bid_id: uuid.UUID | None = None, ref_id: uuid.UUID | None = None) -> CreditEntry | None` — verrouille la ligne de l'entreprise (`with_for_update`), ne commite pas, `None` si le prix est 0, lève `credits_exhausted_error(needed, left)` (`ApiError` 402) ;
  - `refund(db: Session, entry: CreditEntry, reason: str) -> CreditEntry | None` (idempotent par `refund_of`) ;
  - `grant(db: Session, org: Organization, amount: int, reason: str, admin: PlatformAdmin) -> CreditEntry` ;
  - `give_welcome(db: Session, org: Organization) -> CreditEntry | None` (les crédits offerts de sa formule, une seule fois : `welcome_credits_at`) ;
  - `assign_plan(db: Session, org: Organization, plan: Plan) -> None` (modules = ceux de la formule + clés inconnues gardées, puis `give_welcome`) ;
  - `default_plan(db: Session) -> Plan` ;
  - `history(db: Session, org: Organization, limit: int) -> list[HistoryRow]`.
- Produces, schémas : `MeOut.credits: MeCreditsOut{total: int, reference: int, prices: dict[str, int]}` ; `CreditsOut{plan: {name, description, modules}, monthly_allowance, monthly_left, extra, total, renews_on, prices: list[{action, name, credits}], history: list[HistoryOut]}` ; `HistoryOut{at, kind, action_name: str | None, bid_title: str | None, user_name: str | None, credits: int, reason: str | None}`.
- Route : `GET /credits` (commune à tous, sans garde de module).

- [ ] **Step 1: Write the failing tests** (`tests/api/test_credits.py`) :
  - `test_signup_gets_discovery_and_welcome` : une inscription → formule « Découverte », `/auth/me` → `credits == {"total": 7, "reference": 7, "prices": {…4 clés…}}` ; une ligne `welcome` +7 ;
  - `test_admin_created_company_gets_chosen_plan` : `POST /admin/organizations` avec `plan_id` de « Pilote » → `total == 100`, aucune ligne `welcome` ; sans `plan_id` → « Découverte » et 7 ;
  - `test_credits_page` : `GET /credits` → nom, phrase, modules, `monthly_left`, `extra`, `renews_on`, prix (noms exacts), historique ;
  - `test_no_euro_on_the_client_side` (Review Focus 6) : `/auth/me`, `/credits`, `/dashboard` → ni « € », ni `cost`, ni `price_note` dans le texte de la réponse ;
  - `test_isolation` : une entreprise voisine ne voit que son propre solde et son historique ;
  - `test_charge_refused_message` (appel direct de `charge`) : solde 3, prix 5 → 402 `credits_exhausted` « Il faut 5 crédits, il vous en reste 3. Contactez Pilao. » ; avec `SUPPORT_EMAIL` → « … Contactez Pilao : aide@pilao.test. » ; prix 1 → « Il faut 1 crédit, … ».
- [ ] **Step 2: Run** `uv run pytest tests/api/test_credits.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement** le service, les schémas, la route et les branchements d'inscription et de création.
- [ ] **Step 4: Run** `uv run pytest tests/api/test_credits.py tests/api/test_auth.py tests/api/test_admin_accounts.py -q` — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "Credits: the service, plans at sign-up and creation, the balance in /auth/me and /credits"`

### Task 3: Les 4 actions payantes et leurs remboursements

**Files:**
- Modify: `tests/conftest.py` (fixture automatique `credits_aplenty`), `app/services/dce_analysis.py` (`request_analysis`), `app/services/dce.py` (appel automatique), `app/services/memoir_drafting.py` (`start_generation`, `regenerate_section`, `_maybe_finish`, tâche d'IA de la régénération), `app/services/profile_prefill.py` (`request_read`), `app/services/jobs.py` (`set_job_status`), `app/domain/admin_watch.py` (`TASK_LABELS["memoir_regeneration"] = "Régénération d'un chapitre"`), `app/schemas/…` (statut d'analyse `waiting_credits`)
- Test: `apps/api/tests/api/test_credits_actions.py`

**Interfaces:**
- Consumes: `credits.charge`, `credits.refund` (tâche 2).
- Produces :
  - `credits.refund_failed(db: Session, job: Job, reason: str) -> None` — appelé par `set_job_status` quand un travail passe à `error` ; correspondance `{"analyze_dce": "dce_analysis", "draft_memoir_section": "chapter_regeneration", "profile_prefill": "profile_prefill"}` ; rend la dernière prise non remboursée de cette action pour `job.ref_id` **faite après `job.created_at`** (une lecture gratuite qui échoue ne rend pas une prise plus ancienne) ;
  - rédaction du mémoire : prise `ref_id = memoir.id` ; remboursée par `_maybe_finish` quand **tous** les chapitres finissent en erreur ;
  - analyse : `request_analysis(db, version, queue, *, user_id: uuid.UUID | None, automatic: bool)` ; automatique et sans crédits → analyse créée au statut `waiting_credits`, erreur « Analyse non lancée : crédits insuffisants. », pas de travail mis en file ; à la main et sans crédits → 402 ;
  - régénération : gratuite si `section.status == "error"` ; prise `ref_id = section.id` ; appels d'IA avec `task="memoir_regeneration"` ;
  - raisons des remboursements (historique) : « Remboursé : l'analyse n'a pas abouti. », « Remboursé : la rédaction n'a pas abouti. », « Remboursé : la régénération n'a pas abouti. », « Remboursé : la lecture n'a pas abouti. ».

- [ ] **Step 0: Fixture** — `tests/conftest.py` : fixture automatique `credits_aplenty` qui donne 100 000 crédits par mois à la formule par défaut, sauf dans les modules de test qui déclarent `REAL_CREDITS = True` (`test_credits.py`, `test_credits_actions.py`, `test_admin_plans.py`, `test_admin_credits.py`) : les tests existants des 4 actions ne s'occupent pas des crédits.
- [ ] **Step 1: Write the failing tests** (`tests/api/test_credits_actions.py`, `REAL_CREDITS = True`), avec la file factice et le faux modèle des tests existants :
  - pour chaque action : le solde baisse du prix, une ligne `charge` avec l'action, le dossier et l'utilisateur ; sans crédits → 402 et rien n'est lancé ; prix réglé à 0 → aucune ligne ;
  - double clic (Review Focus 1) : deux appels de suite → le second refusé par la règle existante (409), une seule ligne `charge` ;
  - échec du travail (le faux modèle lève, et la file indisponible) → une ligne `refund`, solde rétabli, un second passage par `set_job_status(…, "error")` ne rembourse pas deux fois ;
  - analyse automatique sans crédits → `waiting_credits` et le message, puis `POST /bids/{id}/analysis` après une recharge → lancée et payée ;
  - mémoire : un chapitre en erreur → pas de remboursement, sa régénération est gratuite ; tous en erreur → remboursement de la rédaction ;
  - prix changé entre la prise et l'échec (Review Focus 4) → le remboursement rend l'ancien prix ;
  - prise le 30 novembre, échec le 1er décembre (Review Focus 3, `now` décalé) → la part du mois revient en supplémentaires ;
  - plafond mensuel d'IA atteint pendant l'analyse → remboursée.
- [ ] **Step 2: Run** `uv run pytest tests/api/test_credits_actions.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement** les prises (après les vérifications existantes, avant le `commit` qui crée le travail), `refund_failed`, le remboursement de la rédaction, la gratuité d'un chapitre en erreur, le statut `waiting_credits`.
- [ ] **Step 4: Run** `uv run pytest -q` (suite complète, avec `credits_aplenty`) — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "Credits: the four paid actions take their credits and give them back when they fail"`

### Task 4: Administration — formules, prix, crédits d'une entreprise

**Files:**
- Create: `apps/api/app/services/admin/plans.py`, `apps/api/app/routers/admin/plans.py`
- Modify: `app/main.py`, `app/schemas/admin.py`, `app/routers/admin/accounts.py` (formule et crédits d'une entreprise), `app/services/admin/supervision.py` (liste, fiche, vue d'ensemble), `app/domain/admin_watch.py` (`WatchItem.kind` ajoute `"credits"`), `tests/api/test_admin_isolation.py`, `tests/api/test_admin_supervision.py` (champs épinglés)
- Test: `apps/api/tests/api/test_admin_plans.py`, `apps/api/tests/api/test_admin_credits.py`

**Interfaces:**
- Consumes: tâches 1 à 3 ; `AdminOrg`, `AdminReadDb`, `audit.record`.
- Produces, routes (spec §5.2) :
  - `GET /admin/plans` → `list[PlanOut{id, name, description, modules, monthly_credits, welcome_credits, price_note, is_default, archived, organizations}]` ;
  - `POST /admin/plans` (`PlanIn`) → `PlanOut` 201 ; `PUT /admin/plans/{id}` → `PlanUpdateOut{plan, organizations_affected}` ;
  - `POST /admin/plans/{id}/archive`, `POST /admin/plans/{id}/unarchive`, `PUT /admin/plans/{id}/default` → `PlanOut` ;
  - `GET /admin/credit-prices` → `list[CreditPriceOut{action, name, module, credits, default_credits, uses_30d, avg_cost_30d: Decimal | None}]` ; `PUT /admin/credit-prices/{action}` (`{credits}`) ;
  - `PUT /admin/organizations/{id}/plan` (`{plan_id}`) → `OrgCreditsOut` ; `POST /admin/organizations/{id}/credits` (`{amount, reason}`) → `OrgCreditsOut` ; `GET /admin/organizations/{id}/credits` → `OrgCreditsOut{plan, monthly_allowance, monthly_left, extra, total, renews_on, history (50)}` ;
  - `OrganizationRowOut` + `plan: {id, name}`, `credits_total: int` ; `OrganizationDetailOut` + `plan`, `credits_total`, `modules_off_plan: {added: list[str], removed: list[str]}` ;
  - vue d'ensemble : une ligne orange « {entreprise} n'a plus de crédits » par entreprise à 0 (non suspendue).
- Règles : modifier les modules d'une formule ajoute ou retire **seulement** les clés changées chez ses entreprises ; `avg_cost_30d` = somme des `ai_calls.cost_eur` de la tâche d'IA de l'action sur 30 jours ÷ nombre de prises non remboursées sur 30 jours (`None` si aucune).

- [ ] **Step 1: Write the failing tests** :
  - `test_admin_plans.py` : créer (nom en double, sans tenir compte de la casse → 409 « Une formule porte déjà ce nom. ») ; modifier les modules → `organizations_affected` exact et une exception gardée chez une entreprise ; une seule par défaut ; archiver la formule par défaut → 409 « Choisissez d'abord une autre formule par défaut. » ; mettre par défaut ou attribuer une formule archivée → 409 « Cette formule est archivée. » ; module inconnu → 422 ; prix : 0 à 1000, action inconnue → 404 « Action inconnue. », `uses_30d` et `avg_cost_30d` calculés sur des `ai_calls` posés en base ; journal pour chaque action ;
  - `test_admin_credits.py` : changer de formule (modules suivent, exceptions tombent, allocation immédiate, supplémentaires gardés) ; crédits offerts jamais deux fois, Découverte → Pilote → Découverte (Review Focus 5) ; recharge (bornes 1 à 100 000, raison obligatoire → 422 ; journal `credits_added` avec le nombre et la raison) ; historique ; `modules_off_plan` après une exception du lot 3 ; « À surveiller » liste une entreprise à 0 ; une autre entreprise intacte ;
  - `test_admin_isolation.py` : les nouvelles routes refusent une session d'entreprise (401) ; `test_admin_supervision.py` : `plan` et `credits_total` dans le jeu de champs épinglé.
- [ ] **Step 2: Run** `uv run pytest tests/api/test_admin_plans.py tests/api/test_admin_credits.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement** le service, les routes, les champs de supervision et la ligne « À surveiller ».
- [ ] **Step 4: Run** `uv run pytest -q`, puis ruff, black, mypy — Expected: tout vert.
- [ ] **Step 5: Commit** — `git commit -m "Admin: plans, action prices with their real cost, a company's plan and credits"`

### Task 5: Front client — solde, bandeau, prix sur les boutons, onglet « Formule et crédits »

**Files:**
- Create: `apps/web/lib/credits.ts`, `apps/web/lib/credits.test.ts`, `apps/web/components/profile/plan-credits.tsx`, `apps/web/components/paid-button.tsx`
- Modify: `lib/types.ts` (`Me.credits`, `Credits`), `components/app-shell.tsx` (bandeau, normalisation d'un `/auth/me` sans `credits`), `app/(app)/tableau-de-bord/page.tsx` (compteur), `app/(app)/profil/page.tsx` (onglet `formule`), `components/dossier/analysis.tsx`, `components/dossier/memoir.tsx`, `components/dossier/chapter.tsx`, `components/profile/prefill.tsx`

**Interfaces:**
- Consumes: `me.credits` et `GET /credits` (tâche 2), statut `waiting_credits` (tâche 3).
- Produces, `lib/credits.ts` :
  - `type CreditLevel = "ok" | "low" | "empty"` ; `creditLevel(total: number, reference: number): CreditLevel` ;
  - `withPrice(label: string, credits: number): string` → « Lancer l'analyse · 2 crédits », « Régénérer · 1 crédit », le libellé seul pour 0 ;
  - `missing(needed: number, left: number, support: string | null): string | null` → `null` si assez, sinon le message du Global Constraints ;
  - `bannerText(level, total, support): string | null`.
- Produces : `PaidButton({ action, label, free?, ...buttonProps })` (`components/paid-button.tsx`) qui lit `me.credits`, affiche le prix, se grise sous le prix avec la phrase de `missing`, et après un succès appelle `refresh()` du contexte.

- [ ] **Step 1: Write the failing test** (`lib/credits.test.ts`) : `creditLevel(8, 100) === "low"`, `creditLevel(20, 100) === "ok"`, `creditLevel(0, 100) === "empty"`, `creditLevel(1, 7) === "low"`, `creditLevel(5, 0) === "ok"` ; `withPrice("Lancer l'analyse", 2) === "Lancer l'analyse · 2 crédits"`, `withPrice("Régénérer", 1) === "Régénérer · 1 crédit"`, `withPrice("Régénérer", 0) === "Régénérer"` ; `missing(5, 3, null) === "Il faut 5 crédits, il vous en reste 3. Contactez Pilao."`, `missing(2, 3, null) === null`.
- [ ] **Step 2: Run** `pnpm test` — Expected: FAIL.
- [ ] **Step 3: Implement.**
  - Bandeau dans la coquille : orange « Il vous reste {n} crédit(s). » (niveau `low`), rouge « Vous n'avez plus de crédits : les actions payantes sont en pause. Contactez Pilao{ : …}. » (niveau `empty`), lien « Voir mes crédits » vers `/profil?onglet=formule`.
  - Compteur du tableau de bord « {n} crédits restants » (couleur selon le niveau) ; la grille compte une case de plus.
  - Onglet « Formule et crédits » (`onglet=formule`) : la formule, « Crédits du mois : {left} sur {allowance}, renouvelés le {date} » (ou « Crédits offerts et ajoutés : {extra} » sans allocation), « Crédits supplémentaires : {extra} », les prix, l'historique (date, action, dossier, auteur, crédits signés, raison), la phrase de contact.
  - Les 4 boutons passent par `PaidButton` (analyse : « Lancer l'analyse » / « Relancer l'analyse » ; mémoire : « Rédiger le mémoire » ; chapitre : « Régénérer », gratuit pour un chapitre en erreur ; profil : le libellé actuel du bouton de lecture) ; l'analyse `waiting_credits` montre son message et le bouton.
- [ ] **Step 4: Run** `pnpm lint && pnpm format:check && pnpm typecheck && pnpm test && pnpm build` — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "Web: credits balance, banner, prices on the paid buttons, the « Formule et crédits » tab"`

### Task 6: Front admin — formules, prix des actions, carte de l'entreprise

**Files:**
- Create: `apps/web/app/(admin)/admin/(espace)/formules/page.tsx`, `apps/web/components/admin/org-plan.tsx`, `apps/web/components/admin/plan-form.tsx`
- Modify: `lib/admin.ts` (`ADMIN_NAV` 8ᵉ entrée « Formules » `/admin/formules` ; `AUDIT_LABELS` des 8 actions), `lib/admin.test.ts`, `lib/types.ts`, `app/(admin)/admin/(espace)/entreprises/page.tsx` (colonnes « Formule », « Crédits »), `app/(admin)/admin/(espace)/entreprises/[id]/page.tsx` (carte), `app/(admin)/admin/(espace)/entreprises/nouvelle/page.tsx` (champ « Formule »), `components/admin/org-modules.tsx` (« Hors formule »), page de la vue d'ensemble si la ligne `credits` a besoin d'un libellé

**Interfaces:**
- Consumes: routes et schémas de la tâche 4 ; `ConfirmDialog`, `useAdminAction`, `useAdminApi`.
- Produces: `OrgPlan({ orgId, onChanged })`, `PlanForm({ plan?, onSaved })`.

- [ ] **Step 1: Write the failing test** (`lib/admin.test.ts`) : `ADMIN_NAV` a 8 entrées, la dernière `/admin/formules` « Formules » ; `auditLabel` : `plan_created` « Formule créée », `plan_updated` « Formule modifiée », `plan_archived` « Formule archivée », `plan_unarchived` « Formule désarchivée », `plan_default_set` « Formule par défaut changée », `plan_changed` « Formule de l'entreprise changée », `credits_added` « Crédits ajoutés », `credit_price_changed` « Prix d'une action changé » ; `auditDetail({amount: 20, reason: "Geste"})` contient « 20 crédits » et « Geste ».
- [ ] **Step 2: Run** `pnpm test` — Expected: FAIL.
- [ ] **Step 3: Implement.**
  - Page « Formules » : carte « Formules » (tableau du spec §3.1, boutons « Nouvelle formule », « Modifier », « Par défaut », « Archiver »/« Désarchiver ») ; le formulaire confirme une modification par « Ces changements s'appliquent aux {N} entreprises qui ont cette formule. » quand N > 0 ; carte « Prix des actions » (prix modifiable, utilisations et coût moyen sur 30 jours en euros).
  - Carte « Formule et crédits » de la fiche (spec §3.1), « Changer de formule » confirmé, « Ajouter des crédits » (nombre, raison).
  - « Hors formule (offert) » / « Hors formule (retiré) » sur la carte « Modules ».
- [ ] **Step 4: Run** `pnpm lint && pnpm format:check && pnpm typecheck && pnpm test && pnpm build` — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "Web: plans and action prices in the administration, a company's plan and credits"`

### Task 7: Parcours navigateur, documentation, mise en ligne

**Files:**
- Modify: `apps/web/e2e/journey.cjs`, `apps/web/e2e/fixtures.py` (« Pilote » formule par défaut de la base locale du parcours : l'entreprise inscrite a 100 crédits par mois pour les étapes existantes), `apps/web/e2e/README.md`, `docs/01-vision-produit.md`, `docs/04-specifications-fonctionnelles.md`, `docs/05-architecture.md`, `docs/06-modele-de-donnees.md`, `docs/10-roadmap-taches.md`, `docs/12-decisions.md` (ADR-043), `docs/13-questions-ouvertes.md` (Q3), `CLAUDE.md` (§6), le spec (statut « validé et livré »)

- [ ] **Step 1: Journey** — dans la section admin : créer la formule « Parcours » (deux modules, 3 crédits par mois), la donner à l'entreprise du parcours ; côté client, le compteur affiche 3, « Lancer l'analyse · 2 crédits » relance l'analyse, le compteur passe à 1, le bandeau orange s'affiche ; « Rédiger le mémoire · 5 crédits » est grisé avec « Il faut 5 crédits, il vous en reste 1. » ; l'admin ajoute 10 crédits (« Parcours ») ; la ligne apparaît dans l'onglet « Formule et crédits » ; remettre « Pilote » à la fin ; captures `admin-formules.png`, `credits.png`. Les étapes existantes qui lancent des actions payantes passent avec les crédits de « Pilote » (fixture).
- [ ] **Step 2: Run** le parcours complet (base locale vidée des entreprises et des annonces `E2E-%`) — Expected: toutes les étapes ✓, erreurs de console identiques aux attendues (une 402 de plus si le bouton grisé est forcé, sinon aucune).
- [ ] **Step 3: Docs** — US-6.11 à US-6.14 ; ADR-043 (prix par action, journal, euros jamais côté client, remboursement automatique) ; tables ; feuille de route ; Q3 (l'outil est prêt, les prix restent à décider) ; `docs/01` (la grille se règle dans l'admin).
- [ ] **Step 4: Revue finale** de la branche (agent de revue sur le modèle le plus capable), corrections, suites complètes API et web au vert, parcours relancé.
- [ ] **Step 5: Commit et push** — `git push -u origin claude/nouveau-projet-5gm1zc` ; vérifier que CI puis Deploy sont verts sur GitHub Actions.

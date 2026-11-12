# Administration, lot 5 : réglages — plan de réalisation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** depuis `/admin/reglages`, l'exploitant change le modèle d'IA de chaque tâche (choisi dans le catalogue OpenRouter, essayé avant d'être enregistré), la clé OpenRouter (vérifiée, chiffrée, jamais réaffichée), les imports TED/BOAMP (actif, « Importer maintenant ») et trois réglages généraux ; la valeur de l'admin passe avant celle du serveur, compte partout en moins d'une minute et va au journal.

**Architecture:** une table de la plateforme `platform_settings` (une ligne par réglage réglé ici) ; un registre `app/platform_settings.py` (nom, libellé, type, bornes, valeur du serveur lue dans `Settings`) ; `app/core/runtime.py` donne la valeur effective (ligne de la base sinon serveur) à partir d'un instantané relu au plus toutes les 30 s par processus ; tout le code qui lisait ces réglages dans `get_settings()` passe par `runtime` ; `app/ai/openrouter.py` est le seul client HTTP d'OpenRouter hors LiteLLM.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, httpx, pytest ; Next.js + Tailwind, vitest, Playwright (`journey.cjs`).

**Spec:** `docs/superpowers/specs/2026-11-12-administration-lot5-reglages-design.md`

## Global Constraints

- Réglages (nom → libellé, type) :
  - `model.dce_extraction` « Lecture du DCE », `model.memoir_generation` « Rédaction du mémoire », `model.memoir_regeneration` « Régénération d'un chapitre », `model.profile_extraction` « Pré-remplissage du profil », `model.tender_scoring` « Note des annonces », `model.compliance_reading` « Lecture des attestations » — modèle ; valeur du serveur : l'attribut de `TASK_MODELS[task]` (`llm_model_extraction`, `_generation`, `_scoring`, `_vision`) ;
  - `openrouter_api_key` « Clé OpenRouter » — secret ; serveur : `Settings.openrouter_api_key` (variable `OPENROUTER_API_KEY`, déjà dans `secrets.env`) ;
  - `import.ted_enabled` « Import TED », `import.boamp_enabled` « Import BOAMP » — booléen ; serveur : `ted_import_enabled`, `boamp_import_enabled` ;
  - `ai_monthly_budget_eur_per_org` « Budget d'IA par entreprise et par mois » — entier 1 à 10 000 ; `support_email` « Adresse de support », `feedback_email` « Adresse des avis des testeurs » — adresse e-mail ou vide (= aucune).
- Instantané relu au plus toutes les **30 s** ; catalogue gardé **1 h** ; délais HTTP **10 s** (5 s pour « À surveiller »).
- Modèle utilisable : `response_format` dans `supported_parameters`, ni `:free` en fin d'identifiant, ni `~` en tête, `pricing.prompt` et `pricing.completion` lisibles et ≥ 0 ; `compliance_reading` exige `image` dans `architecture.input_modalities`. Prix affiché = dollars par jeton × 1 000 000 × `USD_EUR_RATE`.
- Modèle enregistré = `LLM_CATALOGUE_PREFIX` + identifiant du catalogue (préfixe du serveur, `openrouter/` par défaut). Adresse d'OpenRouter : `OPENROUTER_API_URL`, `https://openrouter.ai/api/v1` par défaut.
- Essai d'un modèle : messages `[{"role": "system", "content": "Réponds uniquement par l'objet JSON {\"ok\": true}."}, {"role": "user", "content": "Essai"}]`, réponse lue par `parse_json_object`, réussi si `data.get("ok") is True` ; journalisé dans `ai_calls` (`org_id` vide, tâche `settings_check`, libellé « Essai d'un modèle »).
- Chiffrement : `crypto.encrypt(key, "openrouter_api_key")` ; seuls les 4 derniers caractères en clair (`secret_last4`). Aucune réponse, aucun journal, aucun log ne contient une clé.
- Journal admin : `setting_changed`, `setting_reset`, `api_key_replaced`, `api_key_reset`, `import_started` (détails : spec §3.5).
- Messages d'erreur : ceux du tableau §6 du spec, mot pour mot.
- Migration `0027` (révise `0026`). Code en anglais, interface en français.
- Avant chaque commit, côté API : `uv run ruff check . && uv run black --check . && uv run mypy`. Côté web : `pnpm lint && pnpm format:check && pnpm typecheck && pnpm test`.

## Review Focus

1. **Un réglage changé dans l'API n'est pas vu par le worker avant 30 s** : c'est voulu, mais la valeur ne doit jamais rester ancienne plus longtemps → test en tâche 1 (instantané relu après 30 s, horloge simulée).
2. **Clé illisible** (`APP_SECRET_KEY` changée) : les appels d'IA retombent sur la clé du serveur, jamais d'erreur 500 sur l'écran ni sur la vue d'ensemble → tests en tâches 1 et 5.
3. **Catalogue avec des entrées incomplètes** (prix `"-1"` du routeur `openrouter/auto`, pas de `architecture`, `supported_parameters` absent) : ignorées, jamais d'erreur → test en tâche 3.
4. **Passage d'import resté « running »** après un worker tué : « Importer maintenant » ne doit pas être bloqué pour toujours ; un passage `running` de plus de 1 h (2 × `TENDER_JOB_TIMEOUT_SECONDS`) compte comme mort → test en tâche 5.
5. **Retour à la valeur du serveur quand le serveur n'a rien** (modèle vide, pas de clé) : refusé, une tâche ne se retrouve jamais sans modèle → tests en tâche 4.

---

### Task 1: Table, registre, lecture des réglages effectifs

**Files:**
- Create: `apps/api/alembic/versions/0027_platform_settings.py`, `apps/api/app/db/models/platform_setting.py`, `apps/api/app/platform_settings.py`, `apps/api/app/core/runtime.py`
- Modify: `app/db/models/__init__.py`, `app/core/config.py` (`openrouter_api_key: str = ""`, `openrouter_api_url: str = "https://openrouter.ai/api/v1"`, `llm_catalogue_prefix: str = "openrouter/"`), `app/ai/llm.py` (`TASK_MODELS` importé du registre), `tests/conftest.py` (fixture autouse `runtime_reads_the_test_database`)
- Test: `apps/api/tests/core/test_runtime.py`

**Interfaces:**
- Produces, `app/db/models/platform_setting.py` : `PlatformSetting(Base)` (table `platform_settings`, plateforme, sans `org_id`) : `key: str` (pk), `value: Any | None` (JSONB), `secret: str | None`, `secret_last4: str | None`, `updated_at: datetime`, `updated_by: uuid.UUID | None` (FK `platform_admins.id`, `ondelete="SET NULL"`).
- Produces, `app/platform_settings.py` :
  - `TASK_MODELS: dict[str, str]` (tâche → attribut de `Settings`, les 6 tâches) ; `MODEL_LABELS: dict[str, str]` (tâche → libellé du Global Constraints ; distinct de `admin_watch.TASK_LABELS`, libellés des coûts) ;
  - `@dataclass(frozen=True) class SettingDef: name: str; label: str; kind: Literal["model", "secret", "bool", "int", "email"]; server: Callable[[Settings], Any]; task: str | None = None; minimum: int | None = None; maximum: int | None = None`
  - `SETTINGS: tuple[SettingDef, ...]` (ordre du Global Constraints), `BY_NAME: dict[str, SettingDef]`, `GENERAL = ("ai_monthly_budget_eur_per_org", "support_email", "feedback_email")`, `IMPORTS = {"ted": "import.ted_enabled", "boamp": "import.boamp_enabled"}`.
- Produces, `app/core/runtime.py` :
  - `REFRESH_SECONDS = 30` ; `@dataclass(frozen=True) class Snapshot: values: dict[str, Any]; key: str | None; key_last4: str | None; key_unreadable: bool; updated: dict[str, tuple[datetime, uuid.UUID | None]]`
  - `snapshot() -> Snapshot` (relu si plus vieux que 30 s, horloge `time.monotonic`) ; `invalidate() -> None` ; `set_loader(load: Callable[[], list[PlatformSetting]] | None) -> None` (tests ; `None` = lecture par `get_sessionmaker()`) ;
  - `effective(name: str) -> Any` (valeur de la ligne si elle existe — `""` compris pour une adresse — sinon `BY_NAME[name].server(get_settings())`, relu à chaque appel) ; `source(name: str) -> Literal["admin", "server"]` ;
  - `api_key() -> str | None` (clé réglée ici et lisible, sinon `Settings.openrouter_api_key` non vide, sinon `None`) ; `model_for_task(task: str) -> str` ;
  - une clé illisible : `key=None`, `key_unreadable=True`, et un `logger.warning` sans la clé.

- [ ] **Step 1: Write the failing tests** (`tests/core/test_runtime.py`) :
  - `test_admin_value_wins_then_server_value` : sans ligne, `effective("support_email") == get_settings().support_email` et `source(...) == "server"` ; une ligne `"aide@pilao.test"` → cette valeur, `"admin"` ; une ligne `""` → `""` (« aucune ») ;
  - `test_model_for_task_falls_back_to_its_group` : `monkeypatch` `llm_model_scoring = "srv/scoring"` → `model_for_task("tender_scoring") == "srv/scoring"` ; ligne `model.tender_scoring = "openrouter/x"` → `"openrouter/x"` ;
  - `test_snapshot_is_reread_after_30_seconds` (Review Focus 1) : horloge simulée ; une ligne ajoutée sans `invalidate()` n'est pas vue à +29 s, vue à +31 s ; vue tout de suite après `invalidate()` ;
  - `test_api_key_admin_then_server_then_none` : clé chiffrée en base → elle ; sans ligne, `openrouter_api_key = "sk-srv"` → `"sk-srv"` ; rien → `None` ;
  - `test_unreadable_key_falls_back_to_server` (Review Focus 2) : `secret = "pas-un-jeton"` → `snapshot().key_unreadable is True`, `api_key() == "sk-srv"` ;
  - `test_registry` : 12 réglages (6 modèles, la clé, 2 imports, 3 généraux), noms uniques, les 6 tâches de `TASK_MODELS` ont un `model.<tâche>`, `BY_NAME["ai_monthly_budget_eur_per_org"]` bornes 1 et 10 000.
- [ ] **Step 2: Run** `uv run pytest tests/core/test_runtime.py -q` — Expected: FAIL (modules absents).
- [ ] **Step 3: Implement** la migration (table, FK `ON DELETE SET NULL`), le modèle, le registre, `runtime` ; la fixture autouse de `conftest.py` fait `runtime.set_loader` lire par la connexion du test (`conn`) quand le test en a une, et `runtime.invalidate()` avant et après chaque test.
- [ ] **Step 4: Run** `uv run alembic upgrade head && uv run pytest -q` — Expected: PASS (suite complète : `TASK_MODELS` déplacé).
- [ ] **Step 5: Commit** — `git commit -m "Settings: platform_settings table, registry, effective values read every 30 seconds"`

### Task 2: Brancher les réglages effectifs

**Files:**
- Modify: `app/ai/llm.py` (`model_for`, `_call_provider` : `api_key`, `ensure_budget`), `app/ai/embeddings.py` (`LiteLLMEmbedder.embed` : `api_key`), `app/services/suspension.py`, `app/services/credits.py`, `app/modules.py`, `app/routers/auth.py` (adresse de support), `app/services/feedback.py` (adresse des avis), `app/services/tender_import.py` (`readers`, `ALL_READERS`)
- Test: `apps/api/tests/test_runtime_wiring.py`

**Interfaces:**
- Consumes: `runtime.effective`, `runtime.api_key`, `runtime.model_for_task` (tâche 1).
- Produces, `app/services/tender_import.py` : `ALL_READERS: dict[str, Callable[[], Reader]]` (`"ted"`, `"boamp"`, import paresseux) ; `readers()` = les sources dont `runtime.effective(IMPORTS[source])` est vrai.
- Produces : `litellm.completion` et `litellm.embedding` reçoivent `api_key=` quand `runtime.api_key()` n'est pas `None` (sinon rien, LiteLLM lit l'environnement comme aujourd'hui).

- [ ] **Step 1: Write the failing tests** (`tests/test_runtime_wiring.py`, une ligne `PlatformSetting` écrite par test puis `runtime.invalidate()`) :
  - `test_an_ai_call_uses_the_task_model_and_the_key` : `model.tender_scoring = "openrouter/cheap"`, clé chiffrée `"sk-or-admin-1234"` ; `litellm.completion` remplacé par une fonction qui garde ses arguments ; un appel `llm.complete(…, task="tender_scoring", …)` → `model == "openrouter/cheap"` et `api_key == "sk-or-admin-1234"` ;
  - `test_indexing_uses_the_key` : même chose pour `LiteLLMEmbedder("openrouter/e", 1024).embed(["a"])` et `litellm.embedding` ;
  - `test_the_budget_set_here_blocks` : `ai_monthly_budget_eur_per_org = 1`, un `AiCall` à 1,50 € ce mois → `LlmBudgetExceeded` ;
  - `test_the_support_address_set_here_is_shown` : ligne `support_email = "aide@pilao.test"` → `/auth/me` `support_email == "aide@pilao.test"`, et le message 402 des crédits finit par « Contactez Pilao : aide@pilao.test. » ;
  - `test_the_feedback_address_set_here_receives_it` : ligne `feedback_email` → l'avis part à cette adresse (`Outbox`) ;
  - `test_a_source_switched_off_here_is_not_imported` : serveur `ted_import_enabled = True`, ligne `import.ted_enabled = false` → `readers()` sans `"ted"` ; ligne `import.boamp_enabled = true` avec serveur `False` → `"boamp"` présent.
- [ ] **Step 2: Run** `uv run pytest tests/test_runtime_wiring.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement** chaque branchement par `runtime` (plus aucun `get_settings().support_email`, `.feedback_email`, `.ai_monthly_budget_eur_per_org`, `.ted_import_enabled`, `.boamp_import_enabled` hors `platform_settings.py` : vérifier par `grep`).
- [ ] **Step 4: Run** `uv run pytest -q` — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "Settings: AI calls, indexing, budget, e-mail addresses and imports read the effective values"`

### Task 3: Client OpenRouter et catalogue

**Files:**
- Create: `apps/api/app/ai/openrouter.py`, `apps/api/app/domain/ai_catalogue.py`
- Modify: `app/ai/llm.py` (`probe`, `_journal` accepte `org_id: uuid.UUID | None`), `app/domain/admin_watch.py` (`TASK_LABELS["settings_check"] = "Essai d'un modèle"`)
- Test: `apps/api/tests/integrations/test_openrouter.py`, `apps/api/tests/domain/test_ai_catalogue.py`, `tests/test_llm_probe.py`

**Interfaces:**
- Produces, `app/ai/openrouter.py` :
  - `@dataclass(frozen=True) class CatalogueModel: id: str; name: str; prompt_usd: float; completion_usd: float; context_length: int; json_output: bool; reads_images: bool` (prix en dollars par jeton) ;
  - `@dataclass(frozen=True) class Credit: total_usd: float; used_usd: float` ;
  - `class OpenRouterUnavailable(Exception)`, `class KeyRefused(Exception)` ;
  - `class OpenRouter: __init__(self, base_url: str, http: httpx.Client | None = None, timeout: float = 10)` ; `models() -> list[CatalogueModel]` (une entrée illisible est sautée) ; `check_key(key: str) -> None` (`GET /key`, 401/403 → `KeyRefused`) ; `credit(key: str) -> Credit` (`GET /credits`) ; erreurs réseau et 5xx → `OpenRouterUnavailable` ;
  - `get_openrouter() -> OpenRouter` (dépendance FastAPI, adresse `Settings.openrouter_api_url`).
- Produces, `app/domain/ai_catalogue.py` : `usable(m: CatalogueModel, needs_images: bool) -> bool` ; `eur_per_million(usd_per_token: float, rate: float) -> float` (arrondi à 4 décimales) ; `NEEDS_IMAGES = {"compliance_reading"}`.
- Produces, `app/ai/llm.py` : `probe(db: Session, model: str) -> None` — l'essai du Global Constraints, par `_call_provider` (route et clé effectives) ; journal `ai_calls` (`org_id=None`, `task="settings_check"`) réussi ou non ; échec → `LlmError` avec la raison (≤ 200 caractères), sans plafond de budget (aucune entreprise).

- [ ] **Step 1: Write the failing tests** :
  - `test_openrouter.py` (réponses par `httpx.MockTransport`, tirées de la réponse réelle du 2026-11-12) : `models()` lit `id`, `name`, prix, `context_length`, `json_output`, `reads_images` ; une entrée sans `pricing` ou avec `"-1"` est gardée par le client mais `usable` la refuse (Review Focus 3) ; une entrée sans `architecture` ni `supported_parameters` ne lève rien ; `check_key` : 200 → rien, 401 → `KeyRefused`, `httpx.ConnectError` → `OpenRouterUnavailable` ; `credit` lit `data.total_credits` et `data.total_usage` ; l'en-tête `Authorization: Bearer <clé>` est envoyé, et jamais la clé dans un message d'exception ;
  - `test_ai_catalogue.py` : `usable` refuse `x:free`, `~a/b`, sans `response_format`, prix négatif ; `compliance_reading` refuse un modèle sans image ; `eur_per_million(0.0000001, 0.86) == 0.086` ;
  - `test_llm_probe.py` : `_call_provider` remplacé : réponse `{"ok": true}` → rien levé, une ligne `AiCall(org_id=None, task="settings_check", success=True)` ; réponse `{"ok": false}` ou texte → `LlmError`, ligne `success=False`.
- [ ] **Step 2: Run** `uv run pytest tests/integrations/test_openrouter.py tests/domain/test_ai_catalogue.py tests/test_llm_probe.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement** (httpx, `Authorization: Bearer`, `docs/07` sera mis à jour en tâche 7).
- [ ] **Step 4: Run** les mêmes tests puis `uv run pytest -q` — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "Settings: OpenRouter client (catalogue, key, credit), usable models, a model's trial call"`

### Task 4: API admin — état, catalogue, modèles, clé

**Files:**
- Create: `apps/api/app/services/admin/settings.py`, `apps/api/app/routers/admin/settings.py`
- Modify: `app/routers/admin/__init__.py`, `app/schemas/admin.py`, `tests/conftest.py` (`FakeOpenRouter`, surcharge de `get_openrouter` dans `make_client`), `tests/api/test_admin_isolation.py` (nouvelles routes)
- Test: `apps/api/tests/api/test_admin_settings.py`

**Interfaces:**
- Consumes: tâches 1 à 3.
- Produces, schémas (`app/schemas/admin.py`) :
  - `ModelSettingOut{task, label, model: str, model_name: str | None, source: Literal["admin","server"], server_model: str, price_in_eur: float | None, price_out_eur: float | None, in_catalogue: bool | None, cost_30d_eur: float, calls_30d: int, updated_at: datetime | None}` (prix et `in_catalogue` à `None` si le catalogue n'est pas connu) ;
  - `ApiKeyOut{source: Literal["admin","server","none"], last4: str | None, updated_at: datetime | None, unreadable: bool, server_key: bool, credit: CreditOut | None}`, `CreditOut{total_usd, used_usd}` ;
  - `ImportSettingOut{source, label, enabled: bool, origin: Literal["admin","server"], last: ImportPassOut | None}`, `ImportPassOut{started_at, status, created, updated, error}` ;
  - `GeneralSettingOut{name, label, kind, value, server_value, source}` ;
  - `SettingsOut{models: list[ModelSettingOut], embedding_model: str, api_key: ApiKeyOut, imports: list[ImportSettingOut], general: list[GeneralSettingOut]}` ;
  - `CatalogueModelOut{id, name, price_in_eur, price_out_eur, context_length}` ; `ModelChoiceIn{model_id: str}` ; `ApiKeyIn{key: str}` (bords enlevés, 1 à 200 caractères).
- Produces, `app/services/admin/settings.py` : `state(db, client: OpenRouter) -> SettingsOut` ; `catalogue(client, task) -> list[CatalogueModelOut]` (cache module 1 h, `clear_catalogue_cache()`) ; `set_model(db, admin, client, task, model_id, ip) -> ModelSettingOut` ; `reset(db, admin, name, ip) -> None` ; `set_api_key(db, admin, client, key, ip) -> ApiKeyOut` ; `reset_api_key(db, admin, ip) -> None`. Chaque écriture : `audit.record`, `commit`, `runtime.invalidate()`.
- Routes (`/admin/settings…`) : `GET ""`, `GET /catalogue?task=`, `PUT /models/{task}`, `DELETE /models/{task}`, `PUT /api-key`, `DELETE /api-key`.

- [ ] **Step 1: Write the failing tests** (`tests/api/test_admin_settings.py`, `FakeOpenRouter` : catalogue de 4 modèles dont un `:free` et un sans image, clés `sk-or-v1-good…` acceptées, crédit 5 / 1,32) :
  - `test_state_lists_six_tasks_with_their_server_values` : 6 lignes dans l'ordre du registre, `source == "server"`, `embedding_model` présent, `api_key.source == "server"` ou `"none"` ;
  - `test_catalogue_for_a_task` : sans `:free`, sans alias, `compliance_reading` sans le modèle sans image, prix en euros ; un second appel dans l'heure ne relit pas OpenRouter (`FakeOpenRouter.model_reads == 1`), après `clear_catalogue_cache()` il relit ; catalogue injoignable (cache vide) → 503 « Catalogue OpenRouter indisponible, réessayez dans un moment. » ;
  - `test_a_model_is_tried_then_saved` : `PUT /models/tender_scoring {"model_id": "acme/small"}` → 200, `model == "openrouter/acme/small"`, `source == "admin"`, essai fait (une ligne `settings_check`), journal `setting_changed` `{setting, label, from, to}` ;
  - `test_a_failed_trial_saves_nothing` : essai raté → 422 « Le modèle n'a pas répondu correctement : … », aucune ligne `platform_settings`, rien au journal ;
  - `test_a_model_unfit_for_the_task` : `:free` ou absent → 422 « Ce modèle ne convient pas à cette tâche. » ; tâche inconnue → 404 « Tâche inconnue. » ;
  - `test_back_to_the_server_value` : `DELETE` → `source == "server"`, journal `setting_reset` ; serveur sans modèle pour la tâche → 409 « Le serveur n'a pas de valeur pour ce réglage. » (Review Focus 5) ;
  - `test_the_key_is_checked_stored_encrypted_never_returned` : `PUT /api-key` → `last4`, `source == "admin"` ; la colonne `secret` ne contient pas la clé en clair ; aucune réponse (`GET ""` compris) ni ligne du journal ne contient la clé ; journal `api_key_replaced {"last4"}` ; clé refusée → 422 « Clé refusée par OpenRouter. », rien changé ; OpenRouter injoignable → 503 avec le message du spec ;
  - `test_back_to_the_server_key` : `DELETE /api-key` → `source == "server"`, journal `api_key_reset` ; sans clé du serveur → 409 « Le serveur n'a pas de clé : remplacez la clé plutôt que de la retirer. » (Review Focus 5) ;
  - `test_unreadable_key_on_the_screen` (Review Focus 2) : `secret` illisible → `GET ""` 200, `api_key.unreadable is True` ;
  - `test_company_session_refused` : chaque route → 401.
- [ ] **Step 2: Run** `uv run pytest tests/api/test_admin_settings.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement** (coût sur 30 jours : somme et nombre des `ai_calls` de la tâche ; `in_catalogue` : modèle effectif sans le préfixe dans les identifiants du catalogue).
- [ ] **Step 4: Run** `uv run pytest -q` — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "Settings: administration API for the AI models (catalogue, trial) and the OpenRouter key"`

### Task 5: API admin — imports, réglages généraux, « À surveiller »

**Files:**
- Modify: `app/services/admin/settings.py`, `app/routers/admin/settings.py`, `app/schemas/admin.py`, `app/workers/queue.py` (`enqueue_import_source`), `app/workers/jobs.py` (`import_source_job`), `tests/conftest.py` (`FakeQueue.pending_imports`, `enqueue_import_source`), `app/domain/admin_watch.py` (kind `"settings"`), `app/services/admin/supervision.py`, `app/routers/admin/supervision.py` (client OpenRouter injecté)
- Test: `tests/api/test_admin_settings.py`, `tests/domain/test_admin_watch.py`

**Interfaces:**
- Produces : `set_import(db, admin, source, enabled, ip) -> ImportSettingOut` ; `start_import(db, admin, queue, source, ip) -> None` ; `set_general(db, admin, name, value, ip) -> GeneralSettingOut` (entier borné, adresse validée par `EmailStr`, `""` permis) ; `reset(…)` de la tâche 4 sert aussi aux imports et aux réglages généraux.
- Routes : `PUT /imports/{source} {enabled}`, `DELETE /imports/{source}`, `POST /imports/{source}/run` (202), `PUT /general/{name} {value}`, `DELETE /general/{name}`.
- `JobQueue.enqueue_import_source(source: str) -> None` (RQ : `app.workers.jobs.import_source_job`, `job_timeout=TENDER_JOB_TIMEOUT_SECONDS`) ; `import_source_job(source: str) -> None` = `run_import(db, source, ALL_READERS[source](), mailer, queue)`.
- `admin_watch.watch(..., settings_alerts: list[WatchItem] | None = None)` ; `supervision.overview(db, now, catalogue_ids: set[str] | None)` : rouge « La clé OpenRouter enregistrée est illisible », orange « {libellé} : modèle retiré du catalogue OpenRouter » (seulement si `catalogue_ids` n'est pas `None`) ; le routeur obtient `catalogue_ids` par le cache ou une lecture à 5 s, `None` sur toute erreur.

- [ ] **Step 1: Write the failing tests** :
  - `test_switch_an_import_off_and_on` : `PUT /imports/boamp {"enabled": false}` → `enabled is False`, `origin == "admin"`, journal `setting_changed` ; le passage planifié ne lit plus BOAMP (`readers()`) ; source inconnue → 404 « Source inconnue. » ;
  - `test_import_now` : → 202, `queue.pending_imports == ["ted"]`, journal `import_started {"source": "ted"}` ; source coupée → 409 « Activez d'abord l'import TED. » ; un `TenderImport` `running` de 10 min → 409 « Un passage est déjà en cours. » ; un `running` de 2 h → 202 (Review Focus 4) ; file en panne → 503 « File d'attente indisponible. » ;
  - `test_general_settings` : budget 1 et 10 000 acceptés, 0 et 10 001 → 422 ; adresse mal formée → 422 ; `""` accepté ; réglage inconnu → 404 « Réglage inconnu. » ; retour au serveur ; journal ;
  - `test_last_pass_of_each_source` : le dernier `TenderImport` de chaque source dans `imports[].last` ;
  - `test_watch_lines` (vue d'ensemble) : clé illisible → ligne rouge `kind == "settings"` ; modèle effectif absent du catalogue simulé → ligne orange avec le libellé de la tâche ; OpenRouter injoignable → aucune ligne de modèle, 200 ;
  - `tests/domain/test_admin_watch.py` : `TASK_LABELS["settings_check"] == "Essai d'un modèle"` ; une ligne rouge de `settings_alerts` (sans date) se range avec les rouges, après celles qui ont une date ; les lignes orange de `settings_alerts` viennent en dernier, après les lignes « crédits ».
- [ ] **Step 2: Run** `uv run pytest tests/api/test_admin_settings.py tests/domain/test_admin_watch.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q` — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "Settings: imports on, off and now, general settings, watch lines for the key and withdrawn models"`

### Task 6: Front admin « Réglages »

**Files:**
- Create: `apps/web/app/(admin)/admin/(espace)/reglages/page.tsx`, `apps/web/components/admin/model-picker.tsx`, `apps/web/components/admin/api-key-card.tsx`, `apps/web/lib/settings.ts`, `apps/web/lib/settings.test.ts`
- Modify: `apps/web/lib/types.ts` (types de la tâche 4 et 5), `apps/web/lib/admin.ts` (`ADMIN_NAV` 9e entrée « Réglages » `/admin/reglages` icône `settings` ; `AUDIT_LABELS` des 5 actions ; `auditDetail` : `last4` → « •••• a1b2 », `source`), `apps/web/components/icon.tsx` (icône `settings`), la vue d'ensemble (lignes `kind === "settings"` → lien `/admin/reglages`)

**Interfaces:**
- Produces, `lib/settings.ts` : `eur(n: number | null): string` (« 0,086 € », « — » pour `null`) ; `matches(m: {id: string; name: string}, query: string): boolean` (sans casse ni accents, sur le nom et l'identifiant) ; `originLabel(source: "admin" | "server" | "none"): string` (« réglé ici », « valeur du serveur », « aucune ») ; `dollars(n: number): string` (« 3,68 $ »).

- [ ] **Step 1: Write the failing tests** (`lib/settings.test.ts`) : `eur(0.086) === "0,086 €"`, `eur(null) === "—"` ; `matches({id: "anthropic/claude-haiku-5.5", name: "Anthropic: Claude Haiku 5.5"}, "HAÏKU")` vrai, `"mistral"` faux ; les trois libellés d'origine ; `dollars(3.68) === "3,68 $"`.
- [ ] **Step 2: Run** `pnpm test` — Expected: FAIL.
- [ ] **Step 3: Implement** la page (4 cartes du spec §3.1, textes mot pour mot), le sélecteur (recherche, liste, « Essayer et enregistrer », message d'échec), la carte de la clé (champ mot de passe, « Vérifier et enregistrer », jamais la clé affichée après l'envoi), les imports (interrupteur, dernier passage, « Importer maintenant » seulement si actif), les réglages généraux (« Enregistrer » désactivé quand le budget est vide ou hors bornes — `creditInput(raw, 10000)` de `lib/credits.ts` et minimum 1), « Revenir à la valeur du serveur » grisé selon le spec.
- [ ] **Step 4: Run** `pnpm lint && pnpm format:check && pnpm typecheck && pnpm test && pnpm build` — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "Web: the Réglages screen (models, key, imports, general settings)"`

### Task 7: Parcours navigateur, documentation, revue finale, mise en ligne

**Files:**
- Modify: `apps/web/e2e/fake_openai.py` (`GET /api/v1/models` : 3 modèles `fake-…` dont un `:free` ; `GET /api/v1/key` : 200 si la clé commence par `sk-or-v1-e2e`, sinon 401 ; `GET /api/v1/credits` ; l'essai `{"ok": true}` reconnu à son message système), `apps/web/e2e/journey.cjs` (section 18), `apps/web/e2e/README.md` (`OPENROUTER_API_URL=http://127.0.0.1:5577/api/v1`, `LLM_CATALOGUE_PREFIX=openai/`), `docs/04` (US-6.15 à US-6.18, module 6), `docs/05`, `docs/06`, `docs/07` (OpenRouter : catalogue, clé, crédit vérifiés le 2026-11-12), `docs/09`, `docs/10`, `docs/12` (ADR-044), `docs/14`, `CLAUDE.md` §6, le spec (statut « validé et livré »)

- [ ] **Step 1: Journey section 18** : l'admin ouvre « Réglages » ; « Note des annonces » → « Changer » → cherche « fake » → choisit le modèle → « Essayer et enregistrer » → « réglé ici » ; remplace la clé (`sk-or-v1-e2e-…`) → « •••• » et le crédit ; coupe puis réactive TED, « Importer maintenant » ; règle l'adresse de support `support-e2e@pilao.test` et la lit dans « Contactez Pilao » côté client ; lit les 5 lignes au journal ; capture `admin-reglages.png`.
- [ ] **Step 2: Run** le parcours complet (README) — Expected: toutes les étapes ✓, erreurs de console attendues seulement.
- [ ] **Step 3: Docs** (liste ci-dessus) ; `docs/14` : la clé GitHub devient la clé de secours, les valeurs d'`app.env` restent celles du serveur.
- [ ] **Step 4: Run** `uv run pytest -q` et les contrôles des deux côtés — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "Lot 5 settings: browser journey, documentation"` ; puis revue finale, corrections, et mise en ligne après l'accord de Faycal.

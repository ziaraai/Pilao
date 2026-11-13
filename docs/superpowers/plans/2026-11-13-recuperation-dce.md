# Récupération des DCE — plan de réalisation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** dans un dossier, « Récupérer le DCE » télécharge le ZIP d'une consultation PLACE/Atexo (au nom de l'entreprise ou anonymement) et le dépose comme un dépôt ; ailleurs, une récupération guidée (page, aide-mémoire, zone de dépôt) ; chaque matin, Pilao vérifie les DCE récupérés et récupère la nouvelle version quand ils changent (différences, e-mail, analyse sur clic).

**Architecture:** reconnaissance pure du lien (`app/domain/dce_sources.py`) ; un robot Playwright (Chromium sans écran) dans le worker (`app/integrations/atexo.py`), derrière un protocole `DceRobot` et un filtre d'adresses publiques ; un service (`app/services/dce_retrieval.py`) qui crée des tentatives `dce_fetches`, met en file `fetch_dce`, dépose le ZIP par `dce.create_version` (origine `retrieval`/`update`) et fait le passage quotidien ; un verrou Redis par site ; un réglage de plateforme `dce_robot.enabled` (lot 5).

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, RQ + rq cron, Playwright pour Python 1.63.0, pytest ; Next.js + Tailwind, vitest, Playwright (`journey.cjs`).

**Spec:** `docs/superpowers/specs/2026-11-13-recuperation-dce-design.md`

## Global Constraints

- Migration `0028` (révise `0027`). Code en anglais, interface et e-mails en français. `org_id` sur `dce_fetches` ; toute requête de l'API filtre par l'entreprise.
- Module « Réponse aux appels d'offres » (`reponse`, dépendance `REPONSE`) pour toutes les routes ; entreprises suspendues ou sans le module : ni récupération ni surveillance.
- Réglages du serveur : `DCE_ROBOT_ENABLED` (vrai), `DCE_ROBOT_ALLOW_PRIVATE_HOSTS` (faux ; vrai → `production_problems` : « DCE_ROBOT_ALLOW_PRIVATE_HOSTS doit rester faux en production (le robot ne doit jamais joindre le réseau interne). »), `DCE_ROBOT_BROWSER_PATH` (vide). Réglage de plateforme `dce_robot.enabled`, libellé « Robot de récupération des DCE », type `bool`.
- Robot : HTTPS vers une adresse publique (HTTP et adresses privées seulement avec `DCE_ROBOT_ALLOW_PRIVATE_HOSTS`) ; robots.txt lu avec le nom `Pilao`, gardé 24 h par site ; agent : celui de Chromium suivi de ` Pilao/1.0 (+https://app.pilao.pro/mentions-legales#robot)` ; 10 s au moins entre deux pages d'un même site ; verrou Redis `dce-robot:<site>` 600 s, occupé → tâche remise 60 s plus tard ; téléchargement attendu 300 s au plus ; marqueurs de captcha `captcha`, `recaptcha`, `hcaptcha`, `turnstile` ; limite de taille `MAX_DCE_UPLOAD_BYTES`.
- Tâche `fetch_dce` : durée maximale 600 s, 2 nouvelles tentatives à 60 s puis 300 s (`RobotUnavailable`). Passage quotidien : `cron="40 5 * * *"`, durée maximale 3600 s ; 3 échecs de suite → surveillance interrompue.
- Messages (mot pour mot, spec § 8) : `closed` « La plateforme refuse l'accès à cette consultation (close ou réservée). » ; `unreadable` « Pilao n'a pas su lire cette page. Ouvrez-la et déposez le ZIP. » ; `refused_identity` « La plateforme a refusé les informations de l'entreprise : {message} » ; `too_big` « Ce DCE fait {taille}, au-delà de la limite de {limite} : téléchargez-le vous-même et déposez les pièces utiles (RC, CCTP, CCAP…). » ; `captcha` « Cette plateforme demande une vérification humaine. » ; `robots` « Cette plateforme n'accepte pas les robots. » ; `unavailable` « La plateforme ne répond pas. Réessayez plus tard. » ; `busy` « Un dépôt est déjà en cours de traitement. ».
- Crédits : récupérer est gratuit ; une version `retrieval` lance l'analyse automatique comme un dépôt (crédits pris) ; une version `update` ne lance jamais d'analyse.
- Aide-mémoires : spec § 4.1, mot pour mot ; « (référence : …) » rempli avec la référence du dossier, la parenthèse omise sans référence.
- Avant chaque commit, côté API : `uv run ruff check . && uv run black --check . && uv run mypy`. Côté web : `pnpm lint && pnpm format:check && pnpm typecheck && pnpm test`.

## Review Focus

1. **Lien collé « sale »** (espaces autour, `&amp;` des avis, `http://` d'une plateforme qui est en HTTPS, majuscules dans `orgAcronyme`, ancre `#…`) : reconnu comme le lien propre ; jamais d'erreur 500 → tests en tâche 1.
2. **Deux clics rapides sur « Récupérer »** : une seule tentative ; l'index unique partiel de la base empêche la seconde même en course → tests en tâches 2 et 4.
3. **Dossier supprimé pendant la récupération** : la tâche s'arrête proprement, le fichier temporaire est effacé, aucun fichier orphelin → test en tâche 4.
4. **Page sans taille ou sans date lisible** pendant la surveillance : ce n'est pas un changement (pas de fausse alerte, pas de téléchargement) → tests en tâches 1 et 5.
5. **Le « ZIP » reçu n'en est pas un** (page HTML d'erreur servie en pièce jointe) : tentative en erreur `unreadable` avec le message de la plateforme refusé par le dépôt, pas d'exception → test en tâche 4.

---

### Task 1: Reconnaissance des liens (pur)

**Files:**
- Create: `apps/api/app/domain/dce_sources.py`
- Test: `apps/api/tests/domain/test_dce_sources.py`

**Interfaces:**
- Produces, `app/domain/dce_sources.py` :
  - `Platform = Literal["atexo", "aws", "achatpublic", "e_marchespublics", "marches_securises", "other"]`
  - `@dataclass(frozen=True) class DceSource: url: str; platform: Platform; site: str; host: str; scheme: str; consultation_id: str | None; org_acronym: str | None` (`host` = domaine avec son port éventuel, pour bâtir les adresses ; `site` = nom connu, sinon le domaine sans port) avec les propriétés `automatic -> bool` (Atexo avec les deux identifiants) et `home_only -> bool` (Atexo sans numéro ; autre plateforme dont le chemin est vide ou `/` sans requête).
  - `ATEXO_SITES: dict[str, str]` (domaine → nom affiché, spec § 7.1) ; `recognize(url: str | None) -> DceSource | None` ; `consultation_url(src) -> str` ; `download_url(src) -> str` (`<scheme>://<host>/index.php?page=Entreprise.EntrepriseDemandeTelechargementDce&id=<n>&orgAcronyme=<code>`).
  - `parse_size(label: str | None) -> int | None` (Ko, Mo, Go ; virgule ou point ; 1 Mo = 1 048 576) ; `format_size(n: int) -> str` (« 250 Mo », « 738 Mo », « 1,2 Go ») ; `parse_deadline(text: str | None) -> datetime | None` (« 30/11/2026 12:00 », heure de Paris → UTC).
  - `guide(platform: Platform, reference: str | None) -> tuple[str, ...]` (spec § 4.1).
  - `@dataclass(frozen=True) class PageFacts: size_label: str | None; deadline_at: datetime | None; closed: bool`
  - `@dataclass(frozen=True) class Change: size_changed: bool; deadline_changed: bool; new_deadline: datetime | None` ; `watch_change(previous: dict[str, Any] | None, facts: PageFacts) -> Change` (une valeur absente d'un côté n'est jamais un changement) ; `watch_state(facts: PageFacts, now: datetime, failures: int = 0, stopped: bool = False) -> dict[str, Any]` (forme de `bids.dce_watch`, dates ISO).

- [ ] **Step 1: Write the failing tests** :
  - `test_atexo_links_seen_in_notices` (paramétré) : `https://www.marches-publics.gouv.fr/entreprise/consultation/3091292?orgAcronyme=h8j` → atexo, site « PLACE », id `3091292`, code `h8j`, `automatic` ; `…/app.php/entreprise/consultation/3094882?orgAcronyme=f5j` ; `…/?page=Entreprise.EntrepriseDetailConsultation&id=3094882&orgAcronyme=f5j` ; `…/?page=Entreprise.EntrepriseAdvancedSearch&AllCons&id=3064274&orgAcronyme=f2h` ; Maximilien `948922`/`p1v` (site « Maximilien ») ; Mégalis `241683`/`f9x` ; Ternum `695276`/`e9m` ; `https://demat-ampa.fr/entreprise/consultation/611232?orgAcronyme=PP295` (code gardé tel quel) ; un domaine inconnu au bon chemin → atexo, site = domaine.
  - `test_atexo_home_is_not_automatic` : `https://www.marches-publics.gouv.fr/?page=Entreprise.AccueilEntreprise` et `https://marches.maximilien.fr` → atexo, `automatic` faux, `home_only` vrai.
  - `test_other_platforms` : AWS `https://www.marches-publics.info/mpiaws/index.cfm?fuseaction=dematEnt.login&amp;type=DCE&amp;IDM=1878216` (et `gm.aws-achat.info`) → aws, `&amp;` décodé ; `https://www.achatpublic.com/sdm/ent/gen/ent_detail.do?PCSLID=CSL_2026_EgiMsoXRrb` et `…/sdm/ent2/gen/ficheCsl.action?PCSLID=…` → achatpublic ; `https://brl.e-marchespublics.com/pack/annonce_marche_public_34156_1186318.html` → e_marchespublics ; `https://www.marches-securises.fr` → marches_securises, `home_only` ; `https://exemple.fr/dce` → other.
  - `test_dirty_links` (Review Focus 1) : `"  https://www.marches-publics.gouv.fr/entreprise/consultation/3091292?orgAcronyme=H8J#pub  "` → même id, code `H8J` gardé, `url` sans espaces ni ancre ; `None`, `""`, `"ftp://x"`, `"pas un lien"` → `None`.
  - `test_urls_built_for_the_robot` : `download_url` et `consultation_url` du lien PLACE.
  - `test_sizes` : `parse_size("10,56 Mo") == round(10.56 * 1048576)`, `"738 Mo"`, `"136,42 Ko"`, `"1,2 Go"`, `"11.5 Mo"`, `"Mo"` → `None`, `None` → `None` ; `format_size(250 * 1048576) == "250 Mo"`.
  - `test_deadline` : `parse_deadline("30/11/2026 12:00") == datetime(2026, 11, 30, 11, 0, tzinfo=UTC)` ; `"18/06/2027 12:00"` → 10:00 UTC ; texte illisible → `None`.
  - `test_guides` : AWS → les 3 lignes du spec ; `guide("other", "26/BAT2102/02")[0] == "1. Trouvez la consultation (référence : 26/BAT2102/02)."` ; sans référence → « 1. Trouvez la consultation. ».
  - `test_watch_change` (Review Focus 4) : taille différente → `size_changed` ; date différente → `deadline_changed` et `new_deadline` ; taille ou date `None` d'un côté → aucun changement ; `previous=None` → aucun changement.
- [ ] **Step 2: Run** `uv run pytest tests/domain/test_dce_sources.py -q` — Expected: FAIL (module absent).
- [ ] **Step 3: Implement** `app/domain/dce_sources.py` (`urllib.parse`, `html.unescape`, `zoneinfo.ZoneInfo("Europe/Paris")`).
- [ ] **Step 4: Run** `uv run pytest tests/domain/test_dce_sources.py -q` — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "DCE retrieval: recognise the buyer platform behind a notice's link"`

### Task 2: Données et réglages

**Files:**
- Create: `apps/api/alembic/versions/0028_dce_retrieval.py`, `apps/api/app/db/models/dce_fetch.py`
- Modify: `app/db/models/__init__.py`, `app/db/models/organization.py`, `app/db/models/bid.py` (`Bid`, `DceVersion`), `app/core/config.py`, `app/platform_settings.py`, `app/services/dce.py` (`create_version`)
- Test: `apps/api/tests/db/test_dce_fetches.py`, `apps/api/tests/test_server_config.py`, `apps/api/tests/api/test_bids.py`

**Interfaces:**
- Produces, `app/db/models/dce_fetch.py` : `DceFetch(IdMixin, OrgScoped, Base)` (table `dce_fetches`) : `bid_id` (FK `bids.id`, `ondelete="CASCADE"`), `kind: str`, `mode: str | None`, `status: str` (défaut `pending`), `outcome: str | None`, `message: str | None`, `site: str`, `size_label: str | None`, `dce_version_id: uuid.UUID | None` (FK `dce_versions.id`, `SET NULL`), `requested_by: uuid.UUID | None` (FK `users.id`, `SET NULL`), `created_at`, `finished_at: datetime | None` ; index `(bid_id, created_at desc)`, `(status, created_at)` ; index unique partiel `uq_dce_fetches_one_active_per_bid` sur `bid_id` où `status in ('pending','running') and kind in ('retrieval','update')`.
- Produces : `Organization.dce_retrieval_mode`, `buyer_contact_first_name`, `buyer_contact_last_name`, `buyer_contact_email` (texte, null) ; `Bid.dce_url: str | None`, `Bid.dce_watch: dict[str, Any] | None` (JSONB) ; `DceVersion.origin: str` (défaut serveur `'deposit'`), `DceVersion.source_url: str | None`.
- Produces, `Settings` : `dce_robot_enabled: bool = True`, `dce_robot_allow_private_hosts: bool = False`, `dce_robot_browser_path: str = ""` ; `production_problems` ajoute le message du Global Constraints.
- Produces, registre : `SettingDef("dce_robot.enabled", "Robot de récupération des DCE", "bool", _attr("dce_robot_enabled"))` ; `DCE_ROBOT = "dce_robot.enabled"`.
- Produces : `dce.create_version(..., *, origin: str = "deposit", source_url: str | None = None) -> DceVersion` (mêmes contrôles qu'un dépôt).

- [ ] **Step 1: Write the failing tests** :
  - `tests/db/test_dce_fetches.py::test_one_active_fetch_per_bid` (Review Focus 2) : deux `DceFetch` `pending` de type `retrieval` sur le même dossier → `IntegrityError` ; une `pending` + une `check` `running` → accepté ; une `done` + une `pending` → accepté.
  - `tests/db/test_dce_fetches.py::test_fetches_follow_their_bid` : supprimer le dossier supprime ses tentatives.
  - `tests/test_server_config.py::test_private_hosts_refused_in_production` : `Settings(environment="production", dce_robot_allow_private_hosts=True, …valeurs de production valides)` → le message dans `production_problems()` ; `environment="local"` → aucun.
  - `tests/api/test_bids.py::test_deposit_origin_is_deposit` : un dépôt existant → `DceVersion.origin == "deposit"`, `source_url is None`.
  - `tests/core/test_runtime.py::test_registry` : passe à 13 réglages, `BY_NAME["dce_robot.enabled"].kind == "bool"`.
- [ ] **Step 2: Run** `uv run pytest tests/db/test_dce_fetches.py tests/test_server_config.py tests/core/test_runtime.py tests/api/test_bids.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement** migration (colonnes, table, index), modèles, réglages, registre, paramètres de `create_version`.
- [ ] **Step 4: Run** `uv run alembic upgrade head && uv run pytest -q` — Expected: PASS (suite complète).
- [ ] **Step 5: Commit** — `git commit -m "DCE retrieval: fetch attempts table, company and dossier fields, robot settings"`

### Task 3: Le robot Atexo, la fausse plateforme, l'image

**Files:**
- Create: `apps/api/app/integrations/robot_net.py`, `apps/api/app/integrations/atexo.py`, `apps/api/tests/fixtures/fake_atexo/__init__.py`, `apps/api/tests/fixtures/fake_atexo/__main__.py`, `apps/api/tests/integrations/test_robot_net.py`, `apps/api/tests/integrations/test_atexo_robot.py`
- Modify: `apps/api/pyproject.toml` + `uv.lock` (`playwright==1.63.0`), `apps/api/Dockerfile`, `.github/workflows/ci.yml`, `apps/api/tests/test_image.py`

**Interfaces:**
- Consumes: `DceSource`, `PageFacts`, `consultation_url`, `download_url`, `parse_size`, `format_size`, `parse_deadline` (tâche 1) ; `Settings.dce_robot_*` (tâche 2).
- Produces, `app/integrations/robot_net.py` : `is_public_address(ip: str) -> bool` ; `url_allowed(url: str, allow_private: bool, resolve: bool = True) -> bool` (HTTPS et toutes les adresses du nom publiques ; avec `allow_private`, HTTP et adresses privées admis ; `resolve=True` : résolution par `socket.getaddrinfo` (le robot) ; `resolve=False` : contrôle sans réseau du schéma, de `localhost` et d'une adresse écrite en chiffres (le service, tâche 4)).
- Produces, `app/integrations/atexo.py` :
  - `USER_AGENT_SUFFIX`, `ROBOT_NAME = "Pilao"`, `PAGE_GAP_SECONDS = 10`, `DOWNLOAD_TIMEOUT_SECONDS = 300`, `CAPTCHA_MARKERS`.
  - `@dataclass(frozen=True) class Identity: first_name: str; last_name: str; email: str; company_name: str; siren: str; siret: str`
  - `@dataclass(frozen=True) class Fetched: path: Path; filename: str; size_label: str | None; deadline_at: datetime | None`
  - `class RobotError(Exception)` avec `outcome: str` et `message: str` (texte du Global Constraints) ; `class RobotUnavailable(Exception)`.
  - `class DceRobot(Protocol): def inspect(self, src: DceSource) -> PageFacts: ...; def fetch(self, src: DceSource, identity: Identity | None, dest: Path, max_bytes: int) -> Fetched: ...`
  - `class AtexoRobot` : `__init__(self, *, browser_path: str = "", allow_private: bool = False, page_gap: float = PAGE_GAP_SECONDS, robots_ttl: float = 86400)` ; `get_robot() -> DceRobot` (depuis `Settings`).
- Produces, fausse plateforme : `python -m tests.fixtures.fake_atexo --port 8765 [--deny-robots]` ; `serve(port: int, deny_robots: bool = False) -> ThreadingHTTPServer` ; scénarios par numéro de consultation : `1001` ZIP (RC et CCTP en PDF, taille annoncée « 0,01 Mo »), `1002` close, `1003` captcha, `1004` « 738 Mo », `1005` page sans formulaire, `1006` identification refusée (« Le SIRET saisi est invalide. ») ; mêmes noms de champs que le spec § 2 ; `GET /_received` renvoie les champs du dernier formulaire reçu ; date limite affichée « 30/11/2026 12:00 ».

- [ ] **Step 1: Write the failing tests** :
  - `test_robot_net.py` : `10.0.0.1`, `127.0.0.1`, `169.254.169.254`, `::1`, `192.168.1.1` non publics ; `https://localhost/` refusé sans `allow_private`, admis avec ; `http://www.marches-publics.gouv.fr/` refusé sans `allow_private` (résolution simulée par `monkeypatch` de `socket.getaddrinfo`, jamais de réseau).
  - `test_atexo_robot.py` (vrai navigateur ; tout le module sauté avec une raison claire si Chromium ne démarre pas ; `page_gap=0`, `allow_private=True`, fausse plateforme sur un port libre) :
    - `test_anonymous_fetch` : `1001` → `Fetched` dont le ZIP contient `RC.pdf` et `CCTP.pdf`, `size_label == "0,01 Mo"`, `deadline_at == datetime(2026, 11, 30, 11, 0, tzinfo=UTC)` ; `/_received` montre le choix anonyme, la case des CGU, et un agent (`user_agent`) qui se termine par `USER_AGENT_SUFFIX` ;
    - `test_identified_fetch_sends_the_company` : `/_received` contient prénom, nom, e-mail, raison sociale, SIREN, SIRET de l'`Identity` ;
    - `test_closed`, `test_captcha`, `test_too_big` (message avec « 738 Mo » et « 250 Mo »), `test_unreadable` (`1005`), `test_identity_refused` (message « La plateforme a refusé les informations de l'entreprise : Le SIRET saisi est invalide. ») → `RobotError` avec l'`outcome` attendu ;
    - `test_robots_txt_forbids` : serveur `deny_robots=True` → `RobotError("robots")` ;
    - `test_private_address_refused` : `allow_private=False` contre la fausse plateforme (127.0.0.1) → `RobotError` d'`outcome` `unreadable`, levée avant tout chargement (`/_received` reste vide) ;
    - `test_inspect` : `1001` → `PageFacts("0,01 Mo", datetime(...), False)` ; `1002` → `closed=True`.
  - `test_image.py::test_browser_in_the_image` : le Dockerfile contient `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers` et `playwright install --with-deps chromium` avant `USER pilao`.
- [ ] **Step 2: Run** `uv run pytest tests/integrations/test_robot_net.py tests/integrations/test_atexo_robot.py tests/test_image.py -q` — Expected: FAIL (modules absents). En local : `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers` (Chromium 1243 déjà installé, celui de Playwright 1.63.0 ; ne jamais lancer `playwright install` dans le bac à sable).
- [ ] **Step 3: Implement** `robot_net`, `atexo` (une requête du navigateur vers une adresse non admise est abandonnée par `page.route`), la fausse plateforme ; Dockerfile (navigateur installé en root dans `/opt/pw-browsers`, lisible par `pilao`) ; CI (job API : `uv run playwright install --with-deps chromium` avec `continue-on-error` et un avertissement comme pour Tesseract ; job des images : Chromium démarre dans l'image).
- [ ] **Step 4: Run** `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers uv run pytest tests/integrations -q` puis `uv run pytest -q` — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "DCE retrieval: the Atexo robot (headless browser), public addresses only, a fake platform for tests"`

### Task 4: Récupération à la demande (services, tâche)

**Files:**
- Create: `apps/api/app/services/dce_retrieval.py`, `apps/api/app/workers/host_gate.py`
- Modify: `app/workers/queue.py` (`FETCH_JOB_TIMEOUT_SECONDS = 600`, `enqueue_fetch_dce(fetch_id, delay_seconds: int = 0)`), `app/workers/jobs.py` (`fetch_dce_job`), `app/services/dce.py` (`run_process_dce(..., mailer: Mailer | None = None)` : version `update` → e-mail, pas d'analyse), `app/workers/jobs.py` (`process_dce_job` passe `get_mailer()`), `app/services/stale_works.py`, `tests/conftest.py` (`FakeQueue.pending_fetches`, `drain_fetches(robot)`, `FakeQueue.outbox`, `FakeRobot`, `FreeGate`)
- Test: `apps/api/tests/api/test_dce_retrieval_service.py`

**Interfaces:**
- Consumes: tâches 1 à 3.
- Produces, `app/workers/host_gate.py` : `class HostGate(Protocol): def acquire(self, host: str) -> bool; def release(self, host: str) -> None; def wait_gap(self, host: str) -> None` ; `RedisHostGate(redis, ttl=600, gap=10)` ; `get_host_gate() -> HostGate`.
- Produces, `app/services/dce_retrieval.py` :
  - `JOB_KIND = "fetch_dce"` ; `robot_enabled() -> bool` (`runtime.effective("dce_robot.enabled")`).
  - `source_for(db: Session, bid: Bid) -> DceSource | None` (`bid.dce_url`, sinon `tenders.documents_url` du dossier) ; `set_link(db, user, bid, url: str | None) -> Bid` (422 `bad_link` « Collez un lien qui commence par https:// » ; journal `update` du dossier).
  - `@dataclass(frozen=True) class Contact: first_name: str | None; last_name: str | None; email: str | None` ; `settings_for(org) -> tuple[str | None, Contact]` ; `save_settings(db, user, org, mode: str | None, contact: Contact) -> None` (journal).
  - `identity_for(org: Organization) -> Identity | None` (contact complet, sinon `None`).
  - `request_retrieval(db, org, user, bid, *, mode: str | None, remember: bool, contact: Contact | None, queue: JobQueue) -> DceFetch` (erreurs : spec § 7.5 ; un mode identifié sans contact complet → 422 `contact_incomplete` « Indiquez le prénom, le nom et l'e-mail du contact. »).
  - `latest_fetch(db, bid_id) -> DceFetch | None` ; `last_success(db, bid) -> DceFetch | None` (dernière `retrieval`/`update` `done`/`ok` sur le lien actuel).
  - `run_fetch(db, fetch_id, robot: DceRobot, storage, scanner, queue, gate: HostGate) -> None` (`RobotUnavailable` : relevée tant que `app.workers.queue.will_retry()` est vrai, comme au lot 4 ; à la dernière tentative, `unavailable`).
  - `notify_update(db, version: DceVersion, mailer: Mailer) -> None` (e-mail « Le DCE de « {titre} » a changé » au responsable du dossier, sinon au demandeur ; corps : `diff_summary` et `{APP_BASE_URL}/dossiers/{bid_id}`).
- Produces, `tests/conftest.py` : `FakeRobot(result: Fetched | Exception | None = None, facts: PageFacts | None = None)` (enregistre les appels : `calls: list[tuple[str, Identity | None]]`) ; `FreeGate` ; `FakeQueue.drain_fetches(robot: DceRobot)`.

- [ ] **Step 1: Write the failing tests** (`test_dce_retrieval_service.py`, dossier créé depuis une annonce dont `documents_url` est le lien PLACE) :
  - `test_choice_needed_the_first_time` : aucun mode → 409 `retrieval_choice_needed` ;
  - `test_remembered_mode_and_contact` : `mode="identified", remember=True`, contact complet → entreprise : mode et contact enregistrés ; tentative `pending` + `Job` `fetch_dce` ; la suivante sans mode utilise `identified` ;
  - `test_identified_without_contact` → 422 `contact_incomplete` ;
  - `test_fetch_deposits_like_a_deposit` : `drain_fetches(FakeRobot(ZIP))` → version `origin="retrieval"`, `source_url` = lien, `uploaded_by` = demandeur ; `drain_dce` → pièces typées, analyse lancée et 2 crédits pris ; `bid.dce_watch` rempli (taille, date limite, `failures=0`) ; tentative `done`/`ok` ;
  - `test_identity_sent_only_in_identified_mode` : appels du `FakeRobot` : `Identity` avec raison sociale, SIREN, SIRET de l'entreprise ; anonyme → `None` ;
  - `test_robot_errors_become_messages` (paramétré `closed`, `captcha`, `too_big`, `robots`, `refused_identity`) → tentative `error`, `outcome`, `message` ; aucune version ;
  - `test_unavailable_is_retried_then_reported` : `RobotUnavailable` → l'exception remonte (nouvelle tentative de la file) tant que ce n'est pas la dernière, puis `unavailable` avec son message ;
  - `test_second_click_refused` (Review Focus 2) : deux demandes → la seconde 409 `retrieval_running` ;
  - `test_deposit_in_progress` : un dépôt en cours → 409 `dce_processing` ;
  - `test_robot_disabled` : réglage `dce_robot.enabled` faux → 409 `robot_disabled` ; `test_home_link_is_not_automatic` → 422 `not_automatic` ; `test_private_link_refused` : lien collé `https://10.0.0.5/entreprise/consultation/1?orgAcronyme=a` → 422 `not_automatic` (« Ce lien ne peut pas être récupéré automatiquement. »), sans aucun accès au réseau ;
  - `test_bid_deleted_meanwhile` (Review Focus 3) : dossier supprimé avant `drain_fetches` → pas d'exception, pas de `File` créé, fichier temporaire effacé ;
  - `test_not_a_zip` (Review Focus 5) : le robot renvoie une page HTML nommée `DCE.zip` → tentative `error`, `outcome="unreadable"`, message du dépôt refusé, aucune version ;
  - `test_busy_site_is_postponed` : `gate.acquire` faux → tentative toujours `pending`, remise en file avec `delay_seconds=60` ;
  - `test_update_version_mails_and_waits_for_a_click` : version `update` traitée → aucun `DceAnalysis`, aucun crédit pris, un e-mail au responsable avec le résumé des différences ;
  - `test_stale_fetch_is_closed` : tentative `running` vieille de plus de 1200 s → `error`, message « La récupération a été interrompue. Réessayez. ».
  - `test_other_company_cannot_see_or_run` : l'entreprise B ne voit pas la tentative de A (lecture par `latest_fetch` sous la session de B).
- [ ] **Step 2: Run** `uv run pytest tests/api/test_dce_retrieval_service.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement** le service, la porte Redis, la tâche, la file, le crochet de `run_process_dce`, le balayage, les doublures de `conftest.py`.
- [ ] **Step 4: Run** `uv run pytest -q` — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "DCE retrieval: retrieve on request, deposit like a deposit, update versions wait for a click"`

### Task 5: Surveillance quotidienne

**Files:**
- Modify: `app/services/dce_retrieval.py` (`watch_dces`), `app/workers/jobs.py` (`watch_dces_job`), `app/workers/cron.py`
- Test: `apps/api/tests/api/test_dce_watch.py`

**Interfaces:**
- Consumes: tâche 4.
- Produces : `@dataclass(frozen=True) class WatchReport: checked: int; changed: int; failed: int` ; `watch_dces(db, robot: DceRobot, queue: JobQueue, mailer: Mailer, gate: HostGate, now: datetime) -> WatchReport` ; e-mail « La date limite de « {titre} » a changé » (corps : « {ancienne} → {nouvelle} », format « 30/11 12:00 », heure de Paris, et le lien du dossier).

- [ ] **Step 1: Write the failing tests** (`test_dce_watch.py`, un dossier récupéré par le robot) :
  - `test_unchanged` → tentative `check` `done`/`unchanged`, `checked_at` mis à jour, pas de mise en file ;
  - `test_size_changed_fetches_an_update` → une tentative `update` en file, dans le mode de la dernière récupération ; après `drain_fetches` et `drain_dce` : version `update` enregistrée au nom du demandeur de la récupération d'origine, e-mail « Le DCE … a changé », aucune analyse ;
  - `test_identified_update_without_contact_goes_anonymous` : le contact retiré entre-temps → mise à jour en anonyme ;
  - `test_deadline_changed` → `bid.deadline_at` mis à jour, e-mail de la date limite ;
  - `test_missing_facts_are_not_changes` (Review Focus 4) : page sans taille ni date → `unchanged`, rien en file ;
  - `test_three_failures_stop_the_watch` : 3 passages en erreur → `dce_watch.stopped`, le 4e ne vérifie plus ; une récupération réussie remet `failures=0` et `stopped=False` ;
  - `test_who_is_watched` : ignorés — dossier `submitted`, date limite passée, dossier seulement déposé à la main, entreprise suspendue, entreprise sans le module, robot coupé ;
  - `test_cron_schedule` : `watch_dces_job` enregistré avec `cron="40 5 * * *"` et `job_timeout=3600`.
- [ ] **Step 2: Run** `uv run pytest tests/api/test_dce_watch.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement** `watch_dces` (une tentative `check` par dossier, `gate.wait_gap` avant chaque page), la tâche, l'entrée du `cron`.
- [ ] **Step 4: Run** `uv run pytest -q` — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "DCE retrieval: daily watch of retrieved DCEs (new version, deadline, three failures stop it)"`

### Task 6: API client et admin

**Files:**
- Create: `apps/api/app/routers/dce_retrieval.py`, `apps/api/app/schemas/dce_retrieval.py`
- Modify: `app/main.py` (routeur), `app/schemas/bids.py` (`DceVersionOut.origin`, `source_url`), `app/routers/bids.py` (`_version_out`), `app/schemas/admin.py` (`SettingsOut.dce_robot`), `app/services/admin/settings.py` (`dce_robot_out`, `set_dce_robot`, `reset_dce_robot`), `app/routers/admin/settings.py`, `app/domain/admin_watch.py` (`JOB_LABELS["fetch_dce"] = "Récupération du DCE"`, `RobotIssues`), `app/services/admin/supervision.py` (comptes sur 24 h)
- Test: `apps/api/tests/api/test_dce_retrieval_api.py`, `apps/api/tests/api/test_admin_settings.py`, `apps/api/tests/api/test_admin_supervision.py`

**Interfaces:**
- Consumes: tâches 4 et 5.
- Produces, routes (spec § 7.5) : `GET|PUT /bids/{bid_id}/dce/source`, `POST /bids/{bid_id}/dce/retrieve`, `GET|PUT /profile/dce-retrieval`.
- Produces, schémas : `ContactIO {first_name, last_name, email}` (e-mail validé quand présent) ; `DceFetchOut {id, kind, mode, status, outcome, message, site, created_at, finished_at}` ; `DceWatchOut {checked_at, size_label, deadline_at, failures, stopped}` ; `DceSourceOut {url, platform, site, automatic, home_only, guide: list[str], robot_enabled, mode, contact: ContactIO, last_fetch: DceFetchOut | None, watch: DceWatchOut | None}` ; `SourceIn {url: str | None}` ; `RetrieveIn {mode: Literal["identified","anonymous"] | None, remember: bool = False, contact: ContactIO | None}` ; `RetrievalSettingsIO {mode: Literal["identified","anonymous"] | None, contact: ContactIO}`.
- Produces, admin : `DceRobotSettingOut {enabled: bool, source: Literal["admin","server"], server_value: bool, succeeded_24h: int, failed_24h: int}` ; `PUT /admin/settings/dce-robot {enabled}` (journal `setting_changed`) ; `DELETE /admin/settings/dce-robot` (journal `setting_reset`) ; « À surveiller » : « Robot des DCE : {n} page(s) non comprise(s) en 24 h » et « Robot des DCE : {n} plateforme(s) sans réponse en 24 h » (tentatives `unreadable` et `unavailable` finales, toutes entreprises).

- [ ] **Step 1: Write the failing tests** :
  - `test_dce_retrieval_api.py` : chaque route — réussite ; `source` d'un dossier sans annonce ni lien → `url=None`, `platform=None` ; `PUT source` avec un lien AWS → `automatic=False`, `guide` de 3 lignes ; `PUT source` avec « pas un lien » → 422 `bad_link` ; `retrieve` 202 puis `last_fetch` `pending` ; 409/422 du spec ; module « reponse » retiré → 403 sur chaque route ; un dossier d'une autre entreprise → 404 ; `GET /bids/{id}/dce` montre `origin` et `source_url` ; `PUT /profile/dce-retrieval` avec un e-mail invalide → 422.
  - `test_admin_settings.py::test_dce_robot_switch` : état initial `enabled` = valeur du serveur, `source="server"` ; `PUT` faux → `source="admin"`, journal ; un client voit `robot_enabled=False` ; `DELETE` → retour au serveur ; comptes 24 h (2 réussites, 1 échec).
  - `test_admin_supervision.py::test_robot_issues_in_watch` : 2 tentatives `unreadable` et 1 `unavailable` en 24 h (2 entreprises) → les deux lignes ; une `closed` n'apparaît pas.
- [ ] **Step 2: Run** `uv run pytest tests/api/test_dce_retrieval_api.py tests/api/test_admin_settings.py tests/api/test_admin_supervision.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement** routeurs, schémas, admin.
- [ ] **Step 4: Run** `uv run pytest -q` — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "DCE retrieval: client and admin API (source, retrieve, company settings, robot switch, watch list)"`

### Task 7: Front client

**Files:**
- Create: `apps/web/components/dossier/dce-source.tsx`, `apps/web/components/dossier/retrieval-dialog.tsx`, `apps/web/components/profile/dce-retrieval.tsx`, `apps/web/lib/dce-source.ts`, `apps/web/lib/dce-source.test.ts`
- Modify: `apps/web/components/dossier/dce.tsx`, `apps/web/lib/types.ts`, `apps/web/app/(app)/profil/page.tsx`

**Interfaces:**
- Consumes: routes et schémas de la tâche 6.
- Produces, `lib/dce-source.ts` : `sourceCase(s: DceSource | null): "robot" | "guided" | "link"` (`robot` : `automatic && robot_enabled` ; `link` : pas d'URL ou `home_only` ; sinon `guided`) ; `originLabel(v: DceVersion, site: string | null, uploader: string | null): string` (« Récupéré sur PLACE le 13/11 à 15:25 », « Mise à jour trouvée par Pilao le 16/11 », « Déposé par Sabrina le 12/11 ») ; `updateBanner(versions: DceVersion[], analysedVersionIds: string[]): DceVersion | null` (dernière version `update` prête et pas analysée) ; `watchLine(w: DceWatch | null, now: Date): string | null` (« Surveillé par Pilao — dernière vérification : aujourd'hui 06:45 » ; « Surveillance interrompue : la page de la consultation ne répond plus »).

- [ ] **Step 1: Write the failing tests** (`lib/dce-source.test.ts`) : les trois cas de `sourceCase` (robot coupé → `guided` ; Atexo accueil → `link`) ; les trois libellés d'`originLabel` ; `updateBanner` (version analysée → `null`) ; `watchLine` (aujourd'hui, hier « hier 06:45 », interrompue).
- [ ] **Step 2: Run** `pnpm test` — Expected: FAIL.
- [ ] **Step 3: Implement** la carte du spec § 4.1 (trois cas, copie mot pour mot), la fenêtre du § 4.2 (radios, rappel raison sociale et SIRET depuis `/auth/me`, contact prérempli par l'utilisateur, phrase des conditions d'utilisation avec le lien `consultation_url` de la source, « Retenir ce choix pour les prochains dossiers » cochée), l'état de la tentative (rafraîchi toutes les 3 s tant qu'elle est `pending`/`running`), le message d'erreur et le bouton « Récupérer anonymement pour ce dossier » pour `refused_identity`, « Réessayer » pour `unavailable`, la ligne de surveillance, le bandeau (« Le DCE a changé le 16/11 : … — [Voir les différences] [Analyser la nouvelle version] », bouton payant existant), l'origine dans la liste des versions ; la rubrique « Récupération des DCE » du profil (onglet de l'entreprise, module « reponse »).
- [ ] **Step 4: Run** `pnpm lint && pnpm format:check && pnpm typecheck && pnpm test && pnpm build` — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "Web: retrieve the DCE from the dossier (robot, guided, pasted link), watch line and update banner, company settings"`

### Task 8: Front admin et pages légales

**Files:**
- Create: `apps/web/components/admin/dce-robot-card.tsx`
- Modify: `apps/web/app/(admin)/admin/(espace)/reglages/page.tsx`, `apps/web/lib/settings.ts`, `apps/web/app/(legal)/confidentialite/page.tsx`, `apps/web/app/(legal)/mentions-legales/page.tsx`
- Test: `apps/web/lib/settings.test.ts`

**Interfaces:**
- Consumes: `DceRobotSettingOut` et routes admin de la tâche 6.

- [ ] **Step 1: Write the failing test** : `robotSummary(s: DceRobotSetting): string` dans `lib/settings.ts` → « Activé — 12 réussies, 1 en échec sur 24 h » / « Coupé — mode guidé pour tous les clients ».
- [ ] **Step 2: Run** `pnpm test` — Expected: FAIL.
- [ ] **Step 3: Implement** le bloc « Robot de récupération des DCE » (interrupteur avec `aria-label`, origine « réglé ici » / « valeur du serveur », « Revenir à la valeur du serveur ») ; « Confidentialité » : la phrase du spec § 7.6 ; « Mentions légales », section `id="robot"` : « Robot de Pilao. À la demande de ses clients, Pilao récupère les dossiers de consultation publiés sur les plateformes des acheteurs publics (PLACE et plateformes Atexo). Il se présente sous le nom « Pilao », respecte les règles robots.txt, ne contourne jamais une vérification anti-robot et ne charge pas plus d'une page toutes les 10 secondes sur un même site. Pour toute question, ou pour demander l'arrêt sur votre plateforme : » suivi de l'adresse de support affichée par ces pages.
- [ ] **Step 4: Run** `pnpm lint && pnpm format:check && pnpm typecheck && pnpm test && pnpm build` — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "Web: robot switch in the admin settings; privacy and legal notices for the robot"`

### Task 9: Parcours navigateur, documentation, revue finale, mise en ligne

**Files:**
- Modify: `apps/web/e2e/journey.cjs`, `apps/web/e2e/README.md`, `docs/12-decisions.md` (ADR-045 ; ADR-004 « remplacée par l'ADR-045 »), `CLAUDE.md` (règle 5, phase), `docs/04-specifications-fonctionnelles.md` (US-3.4, US-3.5, US-6.19, « Hors périmètre V1 »), `docs/05-architecture.md`, `docs/06-modele-de-donnees.md`, `docs/07-integrations-api.md`, `docs/09-securite-rgpd.md`, `docs/10-roadmap-taches.md`, `docs/13-questions-ouvertes.md`, `docs/14-deploiement.md`, le spec (statut)
- Delete: `infra/spike/`, `.github/workflows/dce-probe.yml`

- [ ] **Step 1: Parcours** : la pile du parcours lance la fausse plateforme (`python -m tests.fixtures.fake_atexo --port 8765`) et le worker avec `DCE_ROBOT_ALLOW_PRIVATE_HOSTS=true` et `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers` (README) ; étapes ajoutées : dossier créé à la main → « Collez le lien de la consultation » `http://127.0.0.1:8765/entreprise/consultation/1001?orgAcronyme=t1x` → « Récupérer le DCE » → fenêtre, « Au nom de … », contact → pièces RC et CCTP lues, origine « Récupéré sur 127.0.0.1 … » ; lien AWS collé → aide-mémoire et « Ouvrir la page du DCE » ; profil, rubrique « Récupération des DCE » ; admin, robot coupé → le dossier montre le mode guidé ; robot rétabli.
- [ ] **Step 2: Run** le parcours complet — Expected: toutes les étapes vertes.
- [ ] **Step 3: Documentation** (fichiers ci-dessus ; ADR-045 : décision, constats du test, règles du robot, crédits, mode identifié avec accord, surveillance ; `docs/13` : DCE récupéré par l'équipe Pilao, avis juridique sur le partage d'un DCE entre clients) ; suppression des fichiers du test.
- [ ] **Step 4: Run** côté API `uv run ruff check . && uv run black --check . && uv run mypy && uv run pytest -q` et côté web `pnpm lint && pnpm format:check && pnpm typecheck && pnpm test && pnpm build` — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "DCE retrieval: browser journey, documentation (ADR-045 replaces ADR-004), spike removed"`
- [ ] **Step 6: Revue finale** de toute la branche (relecteur neuf), une passe de corrections RED→GREEN, puis **attendre le « go »** de l'utilisateur avant de pousser ; après le push : CI verte, Deploy vert, puis essai réel depuis le serveur (récupération anonyme d'un DCE public de PLACE dans un dossier d'essai, supprimé ensuite) et compte rendu en français.
